# Implementación — vencimiento_automatico (#12)

Estado: implementada (modo nocturno; escritor OpenCode/DeepSeek). La verificación
(`./init.sh`) queda a cargo de Claude al cerrar la sesión (T42). No se tocó
`contracts/`, `feature_list.json`, `progress/current.md` ni el harness.

## Alcance tocado

- `services/handover/handover/adapters/repository.py`: métodos nuevos
  `claim_timeout`, `release_timeout_claim`, `mark_timed_out` y
  `update_last_messages` en `CaseRepository`, `FakeCaseRepository` (con
  `timeout_claims`) y `PostgresCaseRepository`; `ALTER TABLE handover_cases ADD
  COLUMN IF NOT EXISTS timeout_claimed_at TIMESTAMPTZ NULL` al final de `_SCHEMA`.
  `update_case` se mantiene.
- `services/handover/handover/domain.py`: `check_timeouts` reclama antes de
  enviar, libera si falla el envío y marca `timed_out` de forma condicional;
  `_process_handover` usa `update_last_messages` al reutilizar y `mark_timed_out`
  en la rama `no_advisors`.
- `scripts/vencer_casos.py` (nuevo): llamada única o bucle, validaciones y logs
  sin token.
- `services/handover/Dockerfile`: `COPY scripts/vencer_casos.py
  ./vencer_casos.py` (CMD sin cambios).
- `docker-compose.yml`: servicio `timeouts_worker` sin puertos.
- `.env.example`: `CHECK_TIMEOUTS_INTERVAL_SECONDS=60` y
  `CHECK_TIMEOUTS_HTTP_TIMEOUT_SECONDS=120`.
- Tests nuevos: `services/handover/tests/test_timeout_races.py`,
  `services/handover/tests/test_vencer_casos.py` y
  `services/handover/tests/test_worker_compose.py`; tests nuevos T5-T7 en
  `services/handover/tests/test_repository.py`.

## Ajustes exactos en tests existentes (S1)

- **S1 (A)** en `test_repository.py::test_postgres_repository_uses_parameters_only`
  (test de la #7): filtro `not sql.startswith(("CREATE", "ALTER"))`; se añadieron
  las llamadas `claim_timeout`, `release_timeout_claim`, `mark_timed_out` y
  `update_last_messages`; el recuento de sentencias pasó de 6 a 10. El resto de
  aserciones queda igual.
- **S1 (B)** en el helper `_statements` de la #14 (`test_repository.py`): el
  filtro pasa a `not sql.startswith(("CREATE", "ALTER"))`. Los tests de la #11 y
  la #14 que lo usan pasan sin cambiar sus aserciones.
- `test_postgres_repository_connects_lazily_and_once` sigue contando 4
  `CREATE TABLE`; no se tocó.

## Trazabilidad R → test

| Req | Test |
|---|---|
| R1 | `test_vencer_casos.py::test_single_call_posts_check_timeouts_with_token` |
| R2 | `test_vencer_casos.py::test_single_call_exits_zero_on_200` |
| R3 | `test_vencer_casos.py::test_single_call_exits_nonzero_on_401_and_500` |
| R4 | `test_vencer_casos.py::test_single_call_exits_nonzero_on_network_error` |
| R5 | `test_vencer_casos.py::test_missing_env_exits_nonzero_without_request` |
| R6 | `test_vencer_casos.py::test_loop_repeats_and_sleeps_interval` |
| R7 | `test_vencer_casos.py::test_loop_interval_defaults_to_env_then_60` |
| R8 | `test_vencer_casos.py::test_invalid_interval_exits_nonzero_without_request`, `test_invalid_interval_from_env_exits_nonzero_without_request`, `test_explicit_interval_ignores_invalid_env` |
| R9 | `test_vencer_casos.py::test_loop_logs_failure_code` |
| R10 | `test_vencer_casos.py::test_loop_continues_after_failures` |
| R11 | `test_vencer_casos.py::test_token_never_in_logs_or_output` |
| R12 | `test_vencer_casos.py::test_request_uses_http_timeout_from_env` |
| R13 | `test_worker_compose.py::test_compose_has_timeouts_worker_running_script_in_loop` |
| R14 | `test_worker_compose.py::test_timeouts_worker_publishes_no_ports` |
| R15 | `test_worker_compose.py::test_handover_dockerfile_copies_worker_script` |
| R16 | `test_worker_compose.py::test_env_example_declares_worker_variables` |
| R17 | `test_timeout_races.py::test_check_timeouts_claims_case_before_sending`; `test_two_simultaneous_check_timeouts_send_once`; `test_repository.py::test_postgres_conditional_updates_filter_status_in_where` |
| R18 | `test_timeout_races.py::test_two_simultaneous_check_timeouts_send_once`, `test_stale_claim_is_reclaimed` |
| R19 | `test_timeout_races.py::test_check_timeouts_skips_case_assigned_or_closed_before_claim` |
| R20 | `test_timeout_races.py::test_assignment_during_timeout_send_is_kept`; `test_repository.py::test_postgres_conditional_updates_filter_status_in_where` |
| R21 | `test_timeout_races.py::test_assignment_during_timeout_send_is_kept`, `test_close_during_timeout_send_is_kept` |
| R22 | `test_timeout_races.py::test_case_changed_during_send_not_listed` (y aserciones de T15/T16) |
| R23 | `test_timeout_races.py::test_send_failure_releases_claim_and_retries_immediately` |
| R24 | `test_timeout_races.py::test_stale_claim_is_reclaimed` |
| R25 | `test_timeout_races.py::test_reuse_concurrent_with_assignment_keeps_assignment`; `test_repository.py::test_postgres_update_last_messages_writes_only_last_messages` |
| R26 | `test_timeout_races.py::test_no_advisors_reuse_concurrent_with_assignment_keeps_assignment` |
| R27 | `test_repository.py::test_postgres_conditional_updates_filter_status_in_where`, `test_postgres_repository_uses_parameters_only` |
| R28 | `test_repository.py::test_postgres_schema_adds_claim_column_if_not_exists` |
| R29 | `test_vencer_casos.py::test_invalid_http_timeout_exits_nonzero_without_request` |
| R30 | `test_vencer_casos.py::test_single_call_ignores_invalid_interval_env` |

## Notas

- **T7b de `specs/autorizacion_asesores/tasks.md`**: cumplida al crear
  `test_timeout_races.py`: todas las llamadas a `domain.assign_case` /
  `domain.close_case` usan la firma `(case_id, advisor_id, env.settings,
  env.adapters)` y el asesor `"222"` (de `ADVISORS`).
- Las carreras se reproducen de forma determinista con `HookGateway` y
  `HookRepository`, inyectados con `make_env`/`env_factory` de `conftest.py` sin
  modificarlo.
- La reclamación de vencimiento es `timeout_claimed_at` (columna interna, fuera
  de `Case` y `_CASE_COLUMNS`); `check_timeouts` mantiene el caso `open` durante
  el envío y libera la reclamación si el gateway falla.
- El script no usa `lazaro_contracts`, no imprime con `print` y nunca registra
  `SERVICE_TOKEN`, encabezados ni cuerpos completos.
- T42: `python -m pytest` completo y `./init.sh` los ejecuta Claude al cerrar la
  sesión; el mapa de trazabilidad y el detalle de S1 quedan documentados aquí.

## Verificación (implementer Claude)

- `bash ./init.sh` (una vez, tras la respuesta `done` de OpenCode): EXIT=0,
  `965 passed, 1 warning` (warning de deprecación de starlette/httpx, ajeno).
- Comprobado: T1-T42 marcadas `[x]`; `test_timeout_races.py` usa
  `assign_case`/`close_case` con `env.settings, env.adapters` y asesor `"222"`;
  T21 usa `repo.assign_if_unassigned` directamente; filtros S1 (A) y (B) con
  `("CREATE", "ALTER")`; `vencer_casos.py` sin `print` ni `lazaro_contracts`;
  `timeouts_worker` sin `ports`.
- Trazabilidad R1-R30 → test presente arriba. Feature no marcada `done`.
