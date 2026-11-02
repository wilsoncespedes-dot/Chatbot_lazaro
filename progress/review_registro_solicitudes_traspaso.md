# Review — feature 11 (`registro_solicitudes_traspaso`)

**Veredicto:** APPROVED

`./init.sh` ejecutado por el reviewer (2026-11-01, modo nocturno): verde, `912 passed, 1 warning`
(deprecación httpx/starlette, ajena a la feature).

## Trazabilidad requirements ↔ tests
- R1: [x] `test_requests.py::test_record_is_created_on_receipt_before_processing` (espía en `find_active_case`: registro `received`, `case_id=None`, `received_at=START`, `advisors_configured=3`)
- R2: [x] `test_requests.py::test_record_contains_no_message_text`; `test_repository.py::test_postgres_creates_requests_table_if_not_exists`
- R3: [x] `test_notified_request_completes_record_with_delivered_count`
- R4: [x] `test_no_advisors_request_is_recorded`
- R5: [x] `test_all_notices_failed_request_is_recorded`
- R6: [x] `test_reused_case_creates_new_record_with_new_reason`
- R7: [x] `test_reused_case_keeps_original_case_reason`
- R8: [x] `test_internal_error_before_case_is_known_records_error`, `test_internal_error_after_notice_records_error_with_case_and_count`
- R9: [x] `test_internal_error_returns_500_internal_error`
- R10: [x] `test_record_creation_failure_does_not_change_response`
- R11: [x] `test_record_completion_failure_does_not_change_response`
- R12: [x] `test_error_completion_failure_propagates_original_error`
- R13: [x] `test_rejected_handover_creates_no_record` (401 y 422)
- R14: [x] `test_handover_response_and_notifications_unchanged_with_record` + `test_handover.py` sin modificar (no aparece en `git status`)
- R15: [x] ídem
- R16: [x] `test_repository.py::test_postgres_creates_requests_table_if_not_exists` + conteo 4 en l.97 y l.315
- R17: [x] `test_repository.py::test_postgres_request_methods_use_parameters_only`
- R18: [x] `test_request_logs_are_error_level_and_contain_no_client_text`
- R19: [x] `test_record_stores_message_count` (0/1/2)
- R20: [x] `test_request_logs_are_error_level_and_contain_no_client_text` (casos `add_request`, `complete_request`)
- R21: [x] ídem (caso `find_active_case`, comprueba `request_id=1 case_id=None`)

## Tasks completas
- T1-T24: [x] (todas marcadas en `specs/registro_solicitudes_traspaso/tasks.md`)

## Revisión de código
- `handover/domain.py` l.91-110: `RequestResult`, `HandoverRequestRecord` (sin campo de texto de mensajes, solo `messages_count` — Ley 1581 respetada), `_RequestTally`.
- `handover/domain.py` l.185-238: `_start_request` / `_finish_request` / `open_case` según el flujo del design; logs `logger.error` sin `exc_info`, solo ids y `type(exc).__name__`; `raise` desnudo preserva la excepción original (R9, R12).
- `handover/domain.py` l.241-288: `_process_handover` mantiene el cuerpo previo; solo añade `tally.case_id` (l.260) y `tally.delivered += 1` antes de `add_notification` (l.273-274).
- `handover/adapters/repository.py` l.169-173: cuarta sentencia de `_SCHEMA` con las 10 columnas; l.373-404: `INSERT ... RETURNING id` y `UPDATE ... WHERE id = %s` con una sola llamada a `_run` cada uno, todo con `%s`, sin lock adicional ni `_run` anidado. Métodos existentes intactos.
- Alcance: los cambios de la feature están solo en `services/handover/` (domain.py, adapters/repository.py, tests/test_requests.py nuevo, tests/test_repository.py). Los demás cambios sin commitear del árbol (orchestrator, contracts) corresponden a features ya `done` (#10, #13, #14, #17) y no referencian `handover_requests`/`add_request`.
- Sin dependencias nuevas, sin variables nuevas, sin `print()`, sin SQL concatenado.

## Checkpoints
- C1: [x] archivos base y docs presentes; `./init.sh` exit 0.
- C2: [x] solo la #11 en `in_progress`.
- C3: [x] capas respetadas, sin imports entre servicios, sin dependencias nuevas, SQL parametrizado.
- C4: [x] tests con fakes (`FakeCaseRepository`, `_FakeConn`), 912 verdes.
- C5: [x] aplicable a cierre del leader (history/estado los actualiza el leader).
- C6: [x] spec completo, tasks en `[x]`, cada R<n> con test.

## Observaciones no bloqueantes
1. `progress/impl_registro_solicitudes_traspaso.md` l.3-4 dice "T24 sin marcar", pero la sección «Verificación» y `tasks.md` ya la reflejan completada; el leader puede corregir esa línea al cerrar.
2. Los supuestos S1-S4, S6 y Retención del design siguen marcados «REVISAR (pendiente del humano)»; la implementación sigue las recomendaciones del spec. Conviene reportarlos en el informe nocturno (en especial abrir una feature de retención antes de producción).
