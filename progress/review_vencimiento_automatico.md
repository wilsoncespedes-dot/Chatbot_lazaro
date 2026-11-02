# Review — feature 12 `vencimiento_automatico`

**Veredicto:** APPROVED

`./init.sh` (una vez, modo nocturno): EXIT 0, `965 passed, 1 warning` (deprecación starlette/httpx, ajena).

## Trazabilidad requirements ↔ tests
- R1: [x] `test_vencer_casos.py::test_single_call_posts_check_timeouts_with_token` (URL con y sin `/` final, POST, `{}`, encabezado)
- R2: [x] `test_single_call_exits_zero_on_200`
- R3: [x] `test_single_call_exits_nonzero_on_401_and_500` (401/500/503)
- R4: [x] `test_single_call_exits_nonzero_on_network_error` (ConnectError, ReadTimeout)
- R5: [x] `test_missing_env_exits_nonzero_without_request` (falta/vacía, 0 peticiones)
- R6: [x] `test_loop_repeats_and_sleeps_interval`
- R7: [x] `test_loop_interval_defaults_to_env_then_60`
- R8: [x] `test_invalid_interval_exits_nonzero_without_request`, `test_invalid_interval_from_env_exits_nonzero_without_request`, `test_explicit_interval_ignores_invalid_env`
- R9: [x] `test_loop_logs_failure_code`
- R10: [x] `test_loop_continues_after_failures`
- R11: [x] `test_token_never_in_logs_or_output` (incluye token en el mensaje de la excepción de red, caplog DEBUG + capsys)
- R12: [x] `test_request_uses_http_timeout_from_env` (7 y 120 vía `request.extensions["timeout"]`)
- R13: [x] `test_worker_compose.py::test_compose_has_timeouts_worker_running_script_in_loop`
- R14: [x] `test_timeouts_worker_publishes_no_ports`
- R15: [x] `test_handover_dockerfile_copies_worker_script` (y CMD de uvicorn intacto)
- R16: [x] `test_env_example_declares_worker_variables`
- R17: [x] `test_timeout_races.py::test_check_timeouts_claims_case_before_sending`; `test_repository.py::test_postgres_conditional_updates_filter_status_in_where`
- R18: [x] `test_two_simultaneous_check_timeouts_send_once`, `test_stale_claim_is_reclaimed` (299 s no reenvía)
- R19: [x] `test_check_timeouts_skips_case_assigned_or_closed_before_claim` (param. assigned/closed)
- R20: [x] `test_assignment_during_timeout_send_is_kept`; `test_postgres_conditional_updates_filter_status_in_where`
- R21: [x] `test_assignment_during_timeout_send_is_kept`, `test_close_during_timeout_send_is_kept`
- R22: [x] `test_case_changed_during_send_not_listed` (param.) + aserciones de T15/T16
- R23: [x] `test_send_failure_releases_claim_and_retries_immediately`
- R24: [x] `test_stale_claim_is_reclaimed` (300 s reclama y marca)
- R25: [x] `test_reuse_concurrent_with_assignment_keeps_assignment`; `test_postgres_update_last_messages_writes_only_last_messages`
- R26: [x] `test_no_advisors_reuse_concurrent_with_assignment_keeps_assignment`
- R27: [x] `test_postgres_conditional_updates_filter_status_in_where`, `test_postgres_repository_uses_parameters_only`
- R28: [x] `test_postgres_schema_adds_claim_column_if_not_exists`
- R29: [x] `test_invalid_http_timeout_exits_nonzero_without_request` (0/-1/abc × llamada única/bucle, log nombra la variable)
- R30: [x] `test_single_call_ignores_invalid_interval_env`

## Tasks completas
- T1-T42 (incl. T30b, T34b): [x] en `specs/vencimiento_automatico/tasks.md`.

## Verificaciones específicas
- Cambios en tests existentes: solo S1 (A) en `test_repository.py:84-86` (filtro `("CREATE", "ALTER")`, 6 → 10, cuatro llamadas nuevas) y S1 (B) en `_statements` (`test_repository.py:265`). `test_postgres_repository_connects_lazily_and_once` sigue en 4 `CREATE TABLE` (l.189). Los cambios en `conftest.py` (`make_env(repo, gateway)`, `env_factory`) y `test_cases.py:45` provienen de la #14 y están declarados en `progress/impl_autorizacion_asesores.md`; `conftest.py` no se tocó en esta feature (T10).
- T7b de la #14: cumplida; todas las llamadas de `test_timeout_races.py` usan `(case_id, "222", env.settings, env.adapters)`; T21 usa `repo.assign_if_unassigned` directamente (l.256).
- Token: `scripts/vencer_casos.py` solo registra `type(exc).__name__`, `status` y el campo `error` del cuerpo (l.37, 54, 109, 119, 134); nunca encabezados ni token; sin `print`; sin `lazaro_contracts`.
- SQL: `claim_timeout`, `release_timeout_claim`, `mark_timed_out`, `update_last_messages` (`repository.py:336-367`) son un único `UPDATE` con `%s`, `'open'` como parámetro y condición de estado en el `WHERE`; `RETURNING case_id` en los que devuelven `bool`. `ALTER TABLE ... ADD COLUMN IF NOT EXISTS timeout_claimed_at` al final de `_SCHEMA` (l.214-215); `_CASE_COLUMNS` y `Case` sin cambios.
- Semántica de vigencia coherente entre fake (`claimed_at > stale_before` bloquea, l.93) y Postgres (`timeout_claimed_at <= %s` reclama, l.340), con `stale_before = now - HANDOVER_TIMEOUT_SECONDS` (`domain.py:386`).
- `docker-compose.yml`: `timeouts_worker` con build del Dockerfile de handover, `env_file: [.env]`, `command` con `--intervalo`, `depends_on: [handover]`, `restart: unless-stopped`, sin `ports`.
- `.env.example`: sección `# timeouts_worker` con `CHECK_TIMEOUTS_INTERVAL_SECONDS=60` y `CHECK_TIMEOUTS_HTTP_TIMEOUT_SECONDS=120`.
- Despliegue: no hay cambios en ficheros de Render ni `.github/`; `httpx` ya estaba en `services/handover/requirements.txt` (sin dependencias nuevas).

## Checkpoints
- C1: [x]
- C2: [x] (una sola feature `in_progress`: la #12)
- C3: [x]
- C4: [x]
- C5: [x] (aplica al cierre de sesión del leader)
- C6: [x]

## Observaciones no bloqueantes
1. `_parse_positive` (`scripts/vencer_casos.py:60-64`) acepta `nan`/`inf` (`float("nan") <= 0` es `False`); el spec no lo exige. Si se quiere endurecer, usar `math.isfinite` en una feature futura.
2. `check_timeouts` solo libera la reclamación ante `ServiceUnavailable` (`domain.py:395`); otra excepción del gateway deja la reclamación hasta que caduque (R24 la recupera). Coherente con el design.

## Cambios requeridos
Ninguno.
