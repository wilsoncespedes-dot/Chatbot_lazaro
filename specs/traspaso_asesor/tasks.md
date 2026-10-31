# Tasks — traspaso_asesor

Orden: contratos, handover, orchestrator, configuración. Cada test lleva en su docstring el `R<n>`.

## Precondición (no es tarea de esta feature)

La feature previa de contrato (`assign`) debe estar `done` antes de empezar. Verificar que
`lazaro_contracts` exporta `CaseAssignRequest` y `CaseAssignResponse`; si no, parar. No se edita `contracts/`.

## handover: base

- [x] T5 — Añadir `httpx` y `pg8000` a `services/handover/requirements.txt` (versiones del design). Cubre: R26.
- [x] T6 — Ampliar `handover/config.py` con `database_url`, `telegram_gateway_url`, `advisor_chat_ids` + propiedad `advisor_ids`, `handover_timeout_seconds` (≥ 1, 300), `handover_timeout_reply`, `http_timeout_seconds`. Cubre: R23.
- [x] T7 — Test `test_config.py`: ids con blancos y entradas no numéricas se descartan, valores por defecto, `HANDOVER_TIMEOUT_SECONDS=0` rechazado (`test_advisor_ids_discards_blank_and_non_numeric`, `test_timeout_defaults_to_300`). Cubre: R23.
- [x] T8 — Crear `handover/adapters/gateway.py` con `GatewayClient`, `HttpGatewayClient` y `FakeGatewayClient(fail_for=...)`; `ServiceUnavailable` en `domain.py`. Cubre: R3, R17.
- [x] T9 — Crear `handover/adapters/repository.py` con `CaseRepository`, `FakeCaseRepository` y `PostgresCaseRepository` (SQL con `%s`, tablas `handover_cases` y `handover_notifications`). Cubre: R26.
- [x] T10 — Test `test_repository.py` con conexión pg8000 falsa: toda sentencia usa `%s` y los valores viajan solo como parámetros (`test_postgres_repository_uses_parameters_only`). Cubre: R26.

## handover: dominio y rutas

- [x] T11 — En `handover/domain.py`: `CaseStatus`, `Case`, `Adapters`, `CaseNotFound`, `CaseClosed`, `build_advisor_notice`. Cubre: R4, R41.
- [x] T12 — Implementar `open_case` (crear/reutilizar, avisos, registro de notificaciones, `notified`/`no_advisors`, paso a `timed_out`). Cubre: R1, R2, R3, R5, R6, R7, R8, R9, R10.
- [x] T13 — Implementar `assign_case` y `close_case`. Cubre: R11, R12, R13, R14, R15, R16.
- [x] T14 — Implementar `check_timeouts` con el reloj inyectado. Cubre: R17, R18, R19, R20, R21, R22.
- [x] T15 — Reescribir `create_app(settings=None, adapters=None)` y registrar `POST /handover`, `/cases/{id}/assign`, `/cases/{id}/close`, `/cases/check-timeouts` con modelos de `lazaro_contracts`; `build_default_adapters`. Cubre: R1-R21, R24, R25.
- [x] T16 — Test `test_handover.py::test_handover_creates_case_and_notifies_three_advisors` (3 avisos entregados y registrados con caso, asesor, motivo y fecha; respuesta `notified`). Cubre: R1, R3, R5, R7.
- [x] T17 — Tests `test_notice_contains_case_reason_and_messages` (R4) y `test_notice_fits_4096_limit_with_long_messages` (R41). Cubre: R4, R41.
- [x] T18 — Test `test_handover_reuses_open_case_of_same_contact` y `test_handover_reuses_assigned_case`. Cubre: R2.
- [x] T19 — Test `test_handover_without_advisors_returns_no_advisors_and_does_not_send` (prueba de seguridad). Cubre: R8, R10.
- [x] T20 — Test `test_handover_one_failed_notice_still_notifies_others` y `test_handover_all_notices_fail_returns_no_advisors` (registra `delivered=false`). Cubre: R6, R7, R9, R10.
- [x] T21 — Test `test_cases.py`: `test_assign_marks_case_assigned`, `test_assign_already_assigned_keeps_first_advisor`, `test_assign_timed_out_case`, `test_assign_closed_case_returns_409`, `test_assign_and_close_unknown_case_return_404`. Cubre: R11, R12, R13, R14.
- [x] T22 — Test `test_close_marks_closed_and_records_advisor` y `test_close_is_idempotent_and_keeps_first_closure`. Cubre: R15, R16.
- [x] T23 — Test `test_timeouts.py` con reloj falso: `test_check_timeouts_notifies_client_and_marks_timed_out`, `test_check_timeouts_ignores_assigned_closed_and_recent_cases`, `test_check_timeouts_send_failure_keeps_case_open`, `test_check_timeouts_continues_after_failure`, `test_check_timeouts_returns_empty_list_when_none_expired`. Cubre: R17, R18, R19, R20, R21, R22.
- [x] T24 — Test `test_security.py`: `test_handover_routes_without_token_return_401_and_change_nothing` (parametrizado en las 4 rutas) y `test_handover_invalid_body_returns_422`. Cubre: R24, R25.

## orchestrator

- [x] T25 — Añadir `no_advisors_reply` a `orchestrator/config.py` y test `test_no_advisors_reply_has_default` en `tests/test_config.py`. Cubre: R27.
- [x] T26 — Ampliar `Repository` (+ Fake + Postgres, tabla `case_links`) con `link_case` y `get_case_contact`; ampliar `HandoverClient` (+ Fake) con `assign`. Cubre: R28, R31, R33.
- [x] T27 — Modificar `_handover` en `domain.py`: guardar vínculo y enviar `NO_ADVISORS_REPLY` con `no_advisors`. Cubre: R28, R29, R30.
- [x] T28 — Actualizar los tests de la feature 4 que asumen que `no_advisors` no envía nada al cliente (`tests/test_decisions.py`, `tests/test_messages.py`) y añadir `test_no_advisors_sends_fixed_reply_to_client` y `test_case_is_linked_to_contact_after_handover` en `tests/test_case_reply.py`. Cubre: R28, R29, R30.
- [x] T29 — Añadir `CaseNotFound`, `UpstreamError` y `reply_to_case` en `domain.py`. Cubre: R31-R36.
- [x] T30 — Registrar `POST /cases/{id}/reply` en `main.py` con `CaseReplyRequest`/`CaseReplyResponse`. Cubre: R31-R38.
- [x] T31 — Tests en `tests/test_case_reply.py`: `test_reply_sends_text_stores_advisor_message_and_event`, `test_reply_assigns_case_in_handover`, `test_reply_assign_failure_still_returns_sent`, `test_reply_unknown_case_returns_404_without_sending`, `test_reply_send_failure_returns_502_and_stores_nothing`, `test_reply_without_token_returns_401`, `test_reply_invalid_body_returns_422`. Cubre: R31, R32, R33, R34, R35, R36, R37, R38.

## Configuración y cierre

- [x] T32 — Añadir `NO_ADVISORS_REPLY` y `HANDOVER_TIMEOUT_REPLY` a `.env.example`; comprobar que `docker-compose.yml` pasa las variables del design a `handover` y `orchestrator` (editar solo si falta alguna). Cubre: R23, R27.
- [x] T33 — Ejecutar `./init.sh` (todo verde) y escribir `progress/impl_traspaso_asesor.md` con el mapa de trazabilidad R1-R38 y R41 → test. Cubre: R1-R38 y R41.
