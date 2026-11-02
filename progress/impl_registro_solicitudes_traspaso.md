# Implementación — registro_solicitudes_traspaso (#11)

Estado: implementada y verificada (`./init.sh` verde, T24 completada); review APPROVED.

## Alcance tocado

- `services/handover/handover/domain.py`: `RequestResult`, `HandoverRequestRecord`,
  `_RequestTally`, `_start_request`, `_finish_request`; `open_case` envuelve la lógica
  de traspaso (movida sin cambios de comportamiento a `_process_handover`).
- `services/handover/handover/adapters/repository.py`: `add_request` y
  `complete_request` en el Protocol, en `FakeCaseRepository` (lista `requests`) y en
  `PostgresCaseRepository`; cuarta sentencia de `_SCHEMA` (`handover_requests`).
- `services/handover/tests/test_requests.py` (nuevo): T6–T21.
- `services/handover/tests/test_repository.py`: T22, T23 (conteo de `CREATE TABLE`
  de 3 a 4 y dos tests nuevos) y un test extra del fake.
- No se toca `contracts/`, el orquestador, `main.py`, `config.py`, `docker-compose.yml`
  ni `.env.example`.

## Mapa R<n> → test

| Req | Test |
|---|---|
| R1 | `test_requests.py::test_record_is_created_on_receipt_before_processing`, `test_record_stores_message_count`; `test_repository.py::test_fake_repository_request_ids_are_incremental_and_copies` |
| R2 | `test_requests.py::test_record_contains_no_message_text`; `test_repository.py::test_postgres_creates_requests_table_if_not_exists` |
| R3 | `test_requests.py::test_notified_request_completes_record_with_delivered_count` |
| R4 | `test_requests.py::test_no_advisors_request_is_recorded` |
| R5 | `test_requests.py::test_all_notices_failed_request_is_recorded` |
| R6 | `test_requests.py::test_reused_case_creates_new_record_with_new_reason`; `test_repository.py::test_fake_repository_request_ids_are_incremental_and_copies` |
| R7 | `test_requests.py::test_reused_case_keeps_original_case_reason` |
| R8 | `test_requests.py::test_internal_error_before_case_is_known_records_error`, `test_internal_error_after_notice_records_error_with_case_and_count` |
| R9 | `test_requests.py::test_internal_error_returns_500_internal_error` |
| R10 | `test_requests.py::test_record_creation_failure_does_not_change_response` |
| R11 | `test_requests.py::test_record_completion_failure_does_not_change_response` |
| R12 | `test_requests.py::test_error_completion_failure_propagates_original_error` |
| R13 | `test_requests.py::test_rejected_handover_creates_no_record` |
| R14 | `test_requests.py::test_handover_response_and_notifications_unchanged_with_record` |
| R15 | `test_requests.py::test_handover_response_and_notifications_unchanged_with_record` (los tests de `test_handover.py` no se modifican) |
| R16 | `test_repository.py::test_postgres_creates_requests_table_if_not_exists` |
| R17 | `test_repository.py::test_postgres_request_methods_use_parameters_only` |
| R18 | `test_requests.py::test_request_logs_are_error_level_and_contain_no_client_text` |
| R19 | `test_requests.py::test_record_stores_message_count`; `test_repository.py::test_postgres_creates_requests_table_if_not_exists` |
| R20 | `test_requests.py::test_request_logs_are_error_level_and_contain_no_client_text` |
| R21 | `test_requests.py::test_request_logs_are_error_level_and_contain_no_client_text` |

## Notas

- `received_at` usa el reloj inyectado (`adapters.clock()`), igual que los avisos.
- Complejidad de concurrencia: `add_request`/`complete_request` llaman a `_run` una
  sola vez; no se añade ningún lock ni se llama a `_run` anidado.
- Los logs nuevos son `ERROR`, sin `exc_info` y sin texto de mensajes; solo ids y
  nombre del tipo de excepción.

## Verificación (implementer Claude, nocturno 2026-11-01)

- `bash ./init.sh` ejecutado una vez tras la respuesta `done` de OpenCode: **verde**, `912 passed, 1 warning` (deprecación de httpx en starlette, ajena a la feature). Antes eran 887.
- No hubo ciclos de corrección.
- Trazabilidad R1-R21 → test: presente en la tabla de arriba.
- `feature_list.json`: la #11 sigue en `in_progress`; no se marca `done` (eso queda para el reviewer o el leader).
- Alcance: el código solo cambia en `services/handover/` (domain.py, adapters/repository.py, tests/test_requests.py nuevo, tests/test_repository.py).
