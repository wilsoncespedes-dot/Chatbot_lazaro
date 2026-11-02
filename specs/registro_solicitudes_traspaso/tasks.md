# Tasks — registro_solicitudes_traspaso

Orden: modelo, repositorio, dominio, tests. Solo `services/handover/`. Cada test lleva en su
docstring los `R<n>` que cubre. No se modifica ningún método existente del repositorio (ver
design.md, «Coordinación con la #12 y con la #14»).

Antes de empezar, leer «Estado actual del código» en design.md: el código ya incluye la #10
(validación de `ADVISOR_CHAT_IDS`, `configure_logging`), la #14 (`add_denial`,
`assign_if_unassigned`, `close_if_still_allowed`, `count_assigned_by_advisor`,
`handover_denials`, `threading.Lock` en `_run`) y la #17. Las líneas citadas son orientativas.

## Modelo y repositorio

- [x] T1 — En `handover/domain.py`, junto a `Case`/`Notification`/`Denial` (l.62-88): añadir `RequestResult`, `HandoverRequestRecord` (campos del design, sin ningún campo de texto de mensajes, con `messages_count: int`) y `_RequestTally` (`dataclass` y `Literal` ya están importados). Cubre: R1, R2, R19.
- [x] T2 — En `handover/adapters/repository.py`: ampliar el import de `..domain` (l.12) con `HandoverRequestRecord` y `RequestResult`; añadir `add_request` y `complete_request` al final del Protocol `CaseRepository` (tras `count_assigned_by_advisor`) e implementarlos en `FakeCaseRepository` (lista `requests` creada en `__init__` junto a `denials`, ids 1, 2, 3..., guarda copias). No tocar los métodos existentes. Cubre: R1, R3, R6, R8.
- [x] T3 — En el mismo archivo: añadir la sentencia `CREATE TABLE IF NOT EXISTS handover_requests` como **cuarta** y última entrada de `_SCHEMA` (tras `handover_denials`) e implementar en `PostgresCaseRepository` `add_request` (`INSERT ... RETURNING id`, una sola llamada a `self._run(..., fetch=True)`, devuelve `int(rows[0][0])`) y `complete_request` (`UPDATE ... WHERE id = %s`, una sola llamada a `self._run`), siempre con `%s`. No tomar `self._lock` directamente ni llamar a `_run` anidado (el `Lock` no es reentrante); no tocar `_connection`, `_run` ni el lock. Cubre: R16, R17.

## Dominio

- [x] T4 — Mover el cuerpo actual de `open_case` (`domain.py` l.164-205) a `_process_handover(req, settings, adapters, tally)` sin cambiar su comportamiento (mismos logs `advisor_notice_failed` y `no_advisors`); fijar `tally.case_id` justo después de `update_case`/`create_case` y sumar `tally.delivered` tras cada `send` con éxito, antes de `add_notification`. `authorize_case`, `assign_case`, `close_case` y `log_orphan_cases` no se tocan. Cubre: R7, R14, R15.
- [x] T5 — Reescribir `open_case` con `_start_request` / `_finish_request` según el flujo del design (registro `received` al recibir con `messages_count = len(req.last_messages)`, completado con `notified`/`no_advisors`, `error` + relanzar en excepción, fallos del registro solo al log). Los tres logs del design (`handover_request_not_recorded`, `handover_request_update_failed`, `handover_request_failed`) con `logger.error` (nivel `ERROR`), sin `exc_info` y sin texto de mensajes. Cubre: R1, R3, R4, R5, R6, R8, R9, R10, R11, R12, R18, R19, R20, R21.

## Tests — `services/handover/tests/test_requests.py` (nuevo)

- [x] T6 — `test_record_is_created_on_receipt_before_processing`: espía en `find_active_case`; al llamarlo ya existe un registro `received` con `requested_case_id`, `contact_id`, `reason`, `received_at == START` (reloj falso), `advisors_configured == 3`, `notices_delivered == 0`, `case_id is None`. Cubre: R1.
- [x] T7 — `test_record_contains_no_message_text`: dos mensajes con texto marcador; el marcador no aparece en `record.model_dump_json()` y `HandoverRequestRecord.model_fields` es exactamente el conjunto del design (sin campo de texto de mensajes). Cubre: R2.
- [x] T7b — `test_record_stores_message_count`: parametrizado con 0, 1 y 2 mensajes; el registro (ya en `received`, vía el espía de T6, y tras completarse) tiene `messages_count` igual al número de elementos de `last_messages`. Cubre: R19.
- [x] T8 — `test_notified_request_completes_record_with_delivered_count`: `fail_for = {222}`; registro `notified`, `case_id == "case-1"`, `advisors_configured == 3`, `notices_delivered == 2`. Cubre: R3.
- [x] T9 — `test_no_advisors_request_is_recorded` (fixture `env_no_advisors`): registro `no_advisors`, `case_id == "case-1"`, `advisors_configured == 0`, `notices_delivered == 0`. Cubre: R4.
- [x] T10 — `test_all_notices_failed_request_is_recorded`: `fail_for = set(ADVISORS)`; registro `no_advisors`, `advisors_configured == 3`, `notices_delivered == 0`. Cubre: R5.
- [x] T11 — `test_reused_case_creates_new_record_with_new_reason`: `/handover` (`case-1`, `no_relevant_chunks`), avanzar el reloj, `/handover` (`case-2`, `user_request`, mismo contacto); dos registros con ids distintos, el segundo con `requested_case_id == "case-2"`, `case_id == "case-1"`, `reason == "user_request"` y su propio `received_at`. Cubre: R6.
- [x] T12 — `test_reused_case_keeps_original_case_reason`: mismo escenario; `env.repo.cases["case-1"].reason == "no_relevant_chunks"`. Cubre: R7.
- [x] T13 — `test_internal_error_before_case_is_known_records_error`: `find_active_case` lanza; registro `error`, `case_id is None`, `notices_delivered == 0`. Cubre: R8.
- [x] T14 — `test_internal_error_after_notice_records_error_with_case_and_count`: `add_notification` lanza; registro `error`, `case_id == "case-1"`, `notices_delivered == 1`. Cubre: R8.
- [x] T15 — `test_internal_error_returns_500_internal_error`: cliente con `raise_server_exceptions=False`; `find_active_case` lanza; `500` y `error == "internal_error"`. Cubre: R9.
- [x] T16 — `test_record_creation_failure_does_not_change_response`: `add_request` lanza; respuesta `{"status": "notified", "case_id": "case-1"}`, 3 avisos enviados, `env.repo.requests == []`. Cubre: R10.
- [x] T17 — `test_record_completion_failure_does_not_change_response`: `complete_request` lanza; respuesta `notified` idéntica y el registro sigue `received`. Cubre: R11.
- [x] T18 — `test_error_completion_failure_propagates_original_error`: `find_active_case` lanza `RuntimeError("fallo-simulado")` y `complete_request` lanza `OSError`; `open_case(...)` directo levanta `RuntimeError` con ese mensaje. Cubre: R12.
- [x] T19 — `test_rejected_handover_creates_no_record` (parametrizado: sin token → `401`, cuerpo inválido → `422`); `env.repo.requests == []`. Cubre: R13.
- [x] T20 — `test_handover_response_and_notifications_unchanged_with_record`: con 3 asesores, la respuesta, `env.gateway.sent` (destinatarios, texto de `build_advisor_notice`, orden) y `env.repo.notifications` coinciden exactamente con lo esperado en la #7. Además, los tests existentes de `test_handover.py` deben pasar **sin modificarse**. Cubre: R14, R15.
- [x] T21 — `test_request_logs_are_error_level_and_contain_no_client_text`: parametrizado con los escenarios de T13 (código esperado `handover_request_failed`), T16 (`handover_request_not_recorded`) y T17 (`handover_request_update_failed`), `caplog.set_level(logging.DEBUG)` y un mensaje con `"TEXTO-CLIENTE-SECRETO"`. Comprueba: (a) el marcador no aparece en `caplog.text`; (b) existe un `LogRecord` cuyo `getMessage()` empieza por el código esperado; (c) ese `LogRecord` tiene `levelno == logging.ERROR`; (d) en T13 el mensaje incluye `request_id=1` y `case_id=None`. Cubre: R18, R20, R21.

## Tests — `services/handover/tests/test_repository.py`

- [x] T22 — Actualizar de 3 a 4 sentencias `CREATE TABLE` las aserciones de `test_postgres_repository_connects_lazily_and_once` (l.97) y `test_postgres_repository_connects_once_with_concurrent_first_use` (l.315) (único cambio en tests existentes; no se debilita nada) y añadir `test_postgres_creates_requests_table_if_not_exists`: hay una sentencia `CREATE TABLE IF NOT EXISTS handover_requests` con las 10 columnas del design (incluida `messages_count INTEGER`) y ninguna columna de texto de mensajes. Cubre: R16, R2, R19.
- [x] T23 — `test_postgres_request_methods_use_parameters_only`: con `_FakeConn(rows=[(7,)])` y el helper existente `_statements(conn)`, `add_request` devuelve `7`; hay exactamente una sentencia no-`CREATE` por método; `add_request` y `complete_request` usan solo `%s` (`sql.count("%s") == len(params)`), ningún valor (`case-1`, `contact-1`, `user_request`) aparece en el SQL y no hay literales entre comillas. Cubre: R17.

## Cierre

- [x] T24 — Ejecutar `./init.sh` (todo verde, incluidos todos los tests previos: 887 tras la #14 según `progress/history.md`; lo que cuenta es que ninguno falle, no el número) y escribir `progress/impl_registro_solicitudes_traspaso.md` con el mapa R1-R21 → test. Cubre: R1-R21.
