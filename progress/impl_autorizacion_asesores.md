# Implementación — autorizacion_asesores (feature #14)

Estado: implementada en `services/handover` y `services/orchestrator`. No se tocó
`contracts/`, `feature_list.json`, `progress/current.md` ni el harness. La verificación
(`./init.sh`) queda a cargo de Claude al cerrar la sesión (T52, sin ejecutar aquí).

## Desviaciones respecto al estado supuesto por el spec

El `design.md` §1 y `tasks.md` suponen implementadas la #11 (`handover_requests`, `add_request`,
`complete_request`) y la #12 (`claim_timeout`, `release_timeout_claim`, `mark_timed_out`,
`update_last_messages`, `ALTER TABLE ... timeout_claimed_at`, `tests/test_timeout_races.py`).
En el repositorio actual esas dos features siguen `blocked` y su código no existe. Se implementó
la #14 sobre el estado real (#10 + #13 + #17), sin inventar las piezas de #11/#12:

- **T9:** `test_postgres_repository_connects_lazily_and_once` pasa de `2` a `3` `CREATE TABLE`
  (dos de la #7 + `handover_denials`), no de `3` a `4`. La sentencia nueva se añade al final de
  `_SCHEMA`. T71 comprueba igualmente `3`.
- **T7b:** no se pudo aplicar: `services/handover/tests/test_timeout_races.py` no existe porque la
  #12 no está implementada. `assign_case`/`close_case` ya reciben `settings`; cualquier llamada
  futura de la #12 deberá pasarlo.
- **T62/T77:** para inyectar el repositorio con gancho se añadió a `tests/conftest.py` la fixture
  `env_factory` (equivalente a `make_env(advisors, repo, gateway)` que el spec atribuía a la #12),
  sin cambiar la fixture `env` ni los tests existentes.
- T8 (`test_close_marks_closed_and_records_advisor`) no necesitó cambios: su caso `assigned` sin
  `advisor_id` es huérfano y cualquier asesor registrado lo cierra (R47/R54). El test se deja
  intacto; queda verificado por `./init.sh`.
- Todo lo demás (R1-R55) se implementó según spec. Sin variables de entorno nuevas.

## Diferencias exactas en tests existentes

- `services/handover/tests/test_cases.py::test_assign_already_assigned_keeps_first_advisor`
  (T7): la segunda llamada pasa de `"333"` a `"111"`; aserciones idénticas.
- `services/handover/tests/test_repository.py::test_postgres_repository_connects_lazily_and_once`
  (T9): `2` → `3` (ver desviación).
- `services/handover/tests/test_security.py` (T10): alta de la ruta `authorize` en `ROUTES`, tres
  cuerpos inválidos en `INVALID_BODIES` y `assert env.repo.denials == []` en el test de 401.
- `services/orchestrator/tests/test_case_reply.py::test_http_handover_client_assign_raises_on_error_status`
  (T36): `[404, 409, 500]` → `[403, 404, 409, 500]`.
- Tests **añadidos**: `services/handover/tests/test_authorization.py`,
  `services/handover/tests/test_assign_close_races.py`, tests nuevos en
  `services/handover/tests/test_repository.py`, `services/handover/tests/test_startup.py`,
  `services/orchestrator/tests/test_authorization.py` y T32/T51 en los `test_security.py`.
- Ninguna aserción existente se elimina ni se debilita (salvo el recuento exacto de T9, ya
  justificado) y ningún test existente se renombra.

## Trazabilidad R → test

### Handover

- R1 → `handover/tests/test_authorization.py::test_registered_advisor_matches_decimal_id_exactly`;
  `test_security.py::test_security_unregistered_or_forged_advisor_ids_cannot_act`.
- R2 → `test_authorization.py::test_authorize_unassigned_case_allows_any_registered_advisor`.
- R3 → `test_authorization.py::test_authorize_assigned_case_allows_assigned_advisor`.
- R4 → `test_authorize_unregistered_advisor_returns_403_before_checking_case`;
  `test_security_unregistered_or_forged_advisor_ids_cannot_act`.
- R5 → `test_authorize_unknown_case_returns_404`.
- R6 → `test_authorize_closed_case_returns_409`.
- R7 → `test_authorize_assigned_case_rejects_other_advisor`.
- R8 → `test_authorize_never_modifies_cases_nor_sends`.
- R9 → `test_security.py::test_handover_routes_without_token_return_401_and_change_nothing`.
- R10 → `test_security.py::test_handover_invalid_body_returns_422`.
- R11 → `test_assign_unregistered_advisor_returns_403_and_keeps_case`;
  `test_security_unregistered_or_forged_advisor_ids_cannot_act`.
- R12 → `test_assign_assigned_case_by_other_advisor_returns_403`;
  `test_orphan_case_cannot_be_replied_or_assigned_by_other_advisor`.
- R13 → `test_assign_assigned_case_by_same_advisor_keeps_it`;
  `test_cases.py::test_assign_already_assigned_keeps_first_advisor`.
- R14 → `test_close_unregistered_advisor_returns_403_and_keeps_case`;
  `test_security_unregistered_or_forged_advisor_ids_cannot_act`.
- R15 → `test_close_assigned_case_by_other_advisor_returns_403`.
- R16 → `test_close_assigned_case_by_assigned_advisor`.
- R17 → `test_close_unassigned_case_by_any_registered_advisor`;
  `test_cases.py::test_close_marks_closed_and_records_advisor`.
- R18 → `test_close_closed_case_by_registered_advisor_keeps_first_closure`.
- R19 → `test_denials_are_recorded_with_case_advisor_action_and_date`;
  `test_assign_close_races.py::{test_assign_loses_race_to_other_advisor_returns_403,test_close_loses_race_to_other_advisor_assignment_returns_403}`;
  `test_security_unregistered_or_forged_advisor_ids_cannot_act`.
- R20 → `test_no_denial_recorded_for_allowed_or_other_errors`;
  `test_close_closed_case_by_registered_advisor_keeps_first_closure`.
- R21 → `test_repository.py::test_postgres_repository_add_denial_uses_parameters_only`;
  `test_fake_repository_add_denial_stores_copy`; T9.
- R22 → `test_denial_record_failure_returns_500_and_keeps_case`.
- R37 → `test_assign_close_races.py::test_assign_and_close_write_only_their_fields`;
  `test_repository.py::test_postgres_conditional_writes_use_parameters_only`.
- R38 → `test_assign_loses_race_to_other_advisor_returns_403`;
  `orchestrator/tests/test_authorization.py::test_reply_assign_forbidden_after_send_records_assign_failed`.
- R39 → `test_assign_loses_race_to_close_returns_409`.
- R40 → `test_assign_race_with_same_advisor_keeps_first_assignment`.
- R41 → `test_close_assigned_case_by_assigned_advisor`;
  `test_close_race_with_own_assignment_closes_case`;
  `test_assign_close_races.py::test_assign_and_close_write_only_their_fields`;
  `test_repository.py::{test_fake_close_if_still_allowed_checks_state_and_assignee,test_postgres_close_if_still_allowed_uses_parameters_only}`.
- R42 → `test_close_loses_race_to_other_close_keeps_first_closure`;
  `test_close_orphan_race_with_other_close_keeps_first_closure`.
- R43 → `test_repository.py::{test_postgres_conditional_writes_use_parameters_only,test_fake_close_if_still_allowed_checks_state_and_assignee,test_postgres_close_if_still_allowed_uses_parameters_only}`;
  `test_assign_and_close_write_only_their_fields`.
- R44 → `test_repository.py::test_postgres_repository_serializes_statements_across_threads`.
- R45 → `test_repository.py::test_postgres_repository_connects_once_with_concurrent_first_use`.
- R46 → `test_authorize_close_orphan_case_allowed_for_any_registered_advisor`.
- R47 → `test_close_orphan_case_by_any_registered_advisor`;
  `test_cases.py::test_close_marks_closed_and_records_advisor`.
- R48 → `test_orphan_case_cannot_be_replied_or_assigned_by_other_advisor`.
- R49 → `test_repository.py::test_postgres_count_assigned_by_advisor_uses_parameters`;
  `test_startup.py::test_startup_logs_orphan_case_count`;
  `test_startup_without_orphans_logs_zero_and_no_warning`.
- R50 → `test_startup_logs_orphan_case_count`;
  `test_startup_without_orphans_logs_zero_and_no_warning`.
- R51 → `test_startup_orphan_count_failure_warns_and_starts`.
- R52 → `test_startup.py::test_create_app_does_not_count_orphans`.
- R54 → `test_close_orphan_case_by_any_registered_advisor`;
  `test_close_orphan_race_with_other_close_keeps_first_closure`;
  `test_fake_close_if_still_allowed_checks_state_and_assignee`;
  `test_postgres_close_if_still_allowed_uses_parameters_only`.
- R55 → `test_close_loses_race_to_other_advisor_assignment_returns_403`.

### Orquestador

- R23 → `test_authorization.py::test_reply_authorizes_before_lookup_send_and_store`;
  `test_reply_forbidden_for_unknown_case_returns_403_not_404`.
- R24 → `test_reply_allowed_follows_authorize_send_store_assign_order`.
- R25 → `test_reply_forbidden_returns_403_without_sending_or_storing`;
  `test_security.py::test_security_unregistered_advisor_reply_is_never_sent`.
- R26 → `test_reply_closed_case_returns_409_without_sending`.
- R27 → `test_reply_case_unknown_in_handover_returns_404_without_sending`.
- R28 → `test_reply_authorize_unavailable_returns_502_without_sending`;
  `test_security_unregistered_advisor_reply_is_never_sent`.
- R29 → `test_reply_forbidden_records_advisor_forbidden_event`;
  `test_security_unregistered_advisor_reply_is_never_sent`.
- R30 → `test_reply_forbidden_unlinked_case_logs_without_event`.
- R31 → `test_reply_denied_or_failed_logs_do_not_contain_text`.
- R32 → `test_http_handover_client_authorize_posts_to_authorize_route`.
- R33 → `test_http_handover_client_authorize_maps_denials`;
  `test_security_unregistered_advisor_reply_is_never_sent`.
- R34 → `test_http_handover_client_authorize_fails_closed`;
  `test_security_unregistered_advisor_reply_is_never_sent`.
- R35 → `test_reply_assign_forbidden_after_send_records_assign_failed`;
  `test_case_reply.py::test_http_handover_client_assign_raises_on_error_status` (ampliado con `403`).
- R53 → `test_reply_closed_case_does_not_record_advisor_forbidden`.

### Transversal

- R36 → cambios de T7, T9, T10 y T36 y ejecución de `./init.sh` (T52, a cargo de Claude).

## Decisiones y notas

- D7, D8, D9, D12 y D13 quedan implementadas según las decisiones del humano del 2026-10-31
  (`design.md` §8.2): solo los `403` generan denegación/evento, fallo al guardar la denegación →
  `500`, sin contacto vinculado solo log, recuento de huérfanos en `lifespan` y fallo del recuento
  → `WARNING` sin bloquear el arranque.
- Los riesgos (d) y (e) de la #12 (reutilización que se cierra a mitad; dos `POST /handover`
  simultáneos) siguen abiertos (`design.md` §8.4) y no se tocan aquí.
- La limitación de identidad por HTTP con `SERVICE_TOKEN` no es verificable con un test; queda
  documentada en `design.md` §7 y en S12 de `CONTRATOS.md` (#13).


## Verificación de Claude (puente)

| Ejecución | Sesión | Modelo verificado (export) | Resultado |
|---|---|---|---|
| 1 | `ses_e6a8c0989ffe6skSVYcqV5Xa3M` | `deepseek` / `deepseek-flash` | Cortada al quedarse el sistema sin memoria; solo hizo lecturas y no editó nada. |
| 2 | `ses_e6a8ab727ffes1iFGtW33EjFUR` | `deepseek` / `deepseek-flash` (114 `providerID: deepseek`, 113 `modelID: deepseek-flash`, ningún otro modelo) | `done`. Editó solo `services/handover`, `services/orchestrator`, `specs/autorizacion_asesores/tasks.md` y este informe. `contracts/` sin tocar. |

No hizo falta una tercera ejecución.

- `./init.sh`: exit 0, **887 passed**, entorno OK (2026-11-01).
- Tasks: 79/80 `[x]`. La única abierta es T7b, que no aplica porque la #12 no está implementada (anotado en `tasks.md`).
- Diff de los tests existentes revisado (T52): todos los cambios añaden cobertura o mantienen la compatibilidad. Son T7 (`"333"` → `"111"`), T9, T10, `make_env` con parámetros opcionales, la fixture nueva `env_factory` y el `403` añadido al parametrize de assign en `orchestrator/tests/test_case_reply.py`. Ninguna aserción eliminada ni relajada. T9 se aparta de §6 (2 → 3 en vez de 3 → 4) porque la #11 y la #12 no están implementadas; está documentado arriba.
- Pendiente para el reviewer: las desviaciones por la ausencia de la #11 y la #12 (T7b, T9, `env_factory`).
