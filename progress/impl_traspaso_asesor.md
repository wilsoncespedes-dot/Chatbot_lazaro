# Implementación — #7 traspaso_asesor

Estado: implementada, pendiente de revisión (NO marcada `done`).
Spec: `specs/traspaso_asesor/` (T5..T33 todas `[x]`). Precondición verificada: `lazaro_contracts`
exporta `CaseAssignRequest`/`CaseAssignResponse` (feature #9 `done`). `contracts/` no se ha tocado.
R10 y R11 implementados tal cual (supuestos CONFIRMADOS por el humano).

## Resultado de `./init.sh`

Verde: **674 passed** (línea base 598 → +76 tests). Sin `skip`.

## Archivos tocados

### services/handover
- `requirements.txt` — `httpx>=0.27,<1`, `pg8000>=1.31,<2` (T5).
- `handover/config.py` — `database_url`, `telegram_gateway_url`, `advisor_chat_ids` + `advisor_ids`,
  `handover_timeout_seconds` (≥1, 300), `handover_timeout_reply`, `http_timeout_seconds` (T6).
- `handover/domain.py` — `CaseStatus`, `Case`, `Notification`, `Adapters`, `CaseNotFound`,
  `CaseClosed`, `ServiceUnavailable`, `build_advisor_notice`, `open_case`, `assign_case`,
  `close_case`, `check_timeouts` (T8, T11-T14).
- `handover/adapters/gateway.py` (nuevo) — `GatewayClient`, `HttpGatewayClient`,
  `FakeGatewayClient(fail_for=...)` (T8).
- `handover/adapters/repository.py` (nuevo) — `CaseRepository`, `FakeCaseRepository`,
  `PostgresCaseRepository` (tablas `handover_cases`, `handover_notifications`; SQL con `%s`;
  conexión perezosa) (T9).
- `handover/main.py` — `create_app(settings=None, adapters=None)`, `build_default_adapters`,
  rutas `POST /handover`, `/cases/check-timeouts`, `/cases/{case_id}/assign`,
  `/cases/{case_id}/close` (T15).
- Tests nuevos: `tests/conftest.py`, `tests/fakes.py`, `tests/test_config.py`,
  `tests/test_handover.py`, `tests/test_cases.py`, `tests/test_timeouts.py`,
  `tests/test_security.py`, `tests/test_repository.py`.
- Test modificado: `tests/test_handover_app.py` (ver «Tests existentes modificados»).

### services/orchestrator
- `orchestrator/config.py` — `no_advisors_reply` con valor por defecto (T25).
- `orchestrator/adapters/repository.py` — `link_case`, `get_case_contact` en Protocol, Fake
  (`case_links`) y Postgres (tabla `case_links`) (T26).
- `orchestrator/adapters/handover.py` — `assign(case_id, advisor_id)` en Protocol, Http
  (`POST /cases/{id}/assign`, id con `quote`, `ServiceUnavailable` ante error/4xx/5xx) y Fake
  (`assigned`, `fail_assign`) (T26).
- `orchestrator/domain.py` — `_handover` guarda el vínculo caso↔contacto y, con `no_advisors`,
  envía `NO_ADVISORS_REPLY`; `CaseNotFound`, `UpstreamError`, `reply_to_case` (T27, T29).
- `orchestrator/main.py` — `POST /cases/{case_id}/reply` (T30).
- Tests nuevos: `tests/test_case_reply.py`; `tests/test_config.py` + `test_no_advisors_reply_has_default`.
- `tests/fakes.py` sin cambios (ya reexporta `FakeHandoverClient`, que es donde están `assigned`
  y `fail_assign`).

### Raíz
- `.env.example` — `NO_ADVISORS_REPLY` (sección orchestrator) y `HANDOVER_TIMEOUT_REPLY` (nueva
  sección `# handover`). `HTTP_TIMEOUT_SECONDS`, `ADVISOR_CHAT_IDS`, `HANDOVER_TIMEOUT_SECONDS`,
  `DATABASE_URL`, `TELEGRAM_GATEWAY_URL` ya existían.
- `docker-compose.yml` — comprobado, **sin cambios**: `handover` y `orchestrator` usan
  `env_file: [.env]`, así que reciben todas las variables del design.
- `specs/traspaso_asesor/tasks.md` — T5..T33 marcadas.
- `progress/current.md` — anotada la feature en curso.

## Tests existentes modificados (antes → después)

Ninguno eliminado ni debilitado; cada cambio solo refleja lo que el spec aprobado añade.

1. `services/orchestrator/tests/test_decisions.py::test_ack_sent_when_notified_for_user_request`
   (feature 4, R21) — el que asumía que con `no_advisors` no se envía nada al cliente (T28).
   - Antes: tras el segundo traspaso con `no_advisors`, `assert env.gateway.sent == [(100, ACK)]`.
   - Después: `assert env.gateway.sent == [(100, ACK), (100, env.settings.no_advisors_reply)]`.
   - Justificación: R30 obliga a enviar `NO_ADVISORS_REPLY`. Lo que verifica R21 (con
     `no_advisors` no se manda el ACK) sigue comprobado: la lista exacta no contiene un segundo ACK.
   - `test_decisions.py::test_handover_failure_or_no_advisors_saves_event` y `test_messages.py`
     no han necesitado cambios (solo miran eventos o no usan `no_advisors`).

2. `services/orchestrator/tests/test_config.py::test_only_health_and_messages_routes_exposed`
   (feature 4, R35). **Ajuste fuera de la lista de T28**; lo exige T30.
   - Antes: `assert paths == {"/health", "/messages"}`.
   - Después: `assert paths == {"/health", "/messages", "/cases/{case_id}/reply"}`.
   - Justificación: T30 registra la ruta del contrato `POST /cases/{id}/reply`. La aserción sigue
     siendo de igualdad exacta: cualquier otra ruta no prevista la sigue haciendo fallar.

3. `services/handover/tests/test_handover_app.py::test_requirements_txt_matches_design`
   (feature 2, R5). **Ajuste fuera de la lista de T28**; lo exige T5.
   - Antes: `names == ["fastapi", "pydantic", "pydantic-settings", "uvicorn"]`.
   - Después: la misma lista exacta más `"httpx"` y `"pg8000"`.
   - Justificación: T5 añade las dos dependencias del design. Sigue siendo una lista exacta y
     sigue exigiendo cota doble. La feature 4 hizo lo mismo en el test del orquestador (commit 600b59c).

Para el reviewer: los ajustes 2 y 3 no son los de «no_advisors» que el design nombra, pero el
spec aprobado los hace inevitables (T5 y T30). Son mecánicos y no cambian ninguna otra aserción.

## Trazabilidad R<n> → test

Prefijos: `H` = `services/handover/tests/`, `O` = `services/orchestrator/tests/`.

- R1 → `H/test_handover.py::test_handover_creates_case_and_notifies_three_advisors`, `H/test_handover.py::test_handover_does_not_reuse_closed_or_timed_out_cases`
- R2 → `H/test_handover.py::test_handover_reuses_open_case_of_same_contact`, `H/test_handover.py::test_handover_reuses_assigned_case`
- R3 → `H/test_handover.py::test_handover_creates_case_and_notifies_three_advisors`, `H/test_repository.py::test_http_gateway_client_posts_send_with_token`
- R4 → `H/test_handover.py::test_notice_contains_case_reason_and_messages`
- R41 → `H/test_handover.py::test_notice_fits_4096_limit_with_long_messages`, `H/test_handover.py::test_notice_cuts_each_message_to_300_characters`
- R5 → `H/test_handover.py::test_handover_creates_case_and_notifies_three_advisors`
- R6 → `H/test_handover.py::test_handover_one_failed_notice_still_notifies_others`, `H/test_handover.py::test_handover_all_notices_fail_returns_no_advisors`, `H/test_repository.py::test_http_gateway_client_raises_service_unavailable_on_error`
- R7 → `H/test_handover.py::test_handover_creates_case_and_notifies_three_advisors`, `H/test_handover.py::test_handover_one_failed_notice_still_notifies_others`
- R8 → `H/test_handover.py::test_handover_without_advisors_returns_no_advisors_and_does_not_send`
- R9 → `H/test_handover.py::test_handover_all_notices_fail_returns_no_advisors`
- R10 → `H/test_handover.py::test_handover_without_advisors_returns_no_advisors_and_does_not_send`, `H/test_handover.py::test_handover_all_notices_fail_returns_no_advisors`, `H/test_handover.py::test_no_advisors_case_is_not_notified_again_by_check_timeouts`, `H/test_handover.py::test_no_advisors_keeps_reused_assigned_case_assigned`
- R11 → `H/test_cases.py::test_assign_marks_case_assigned`, `H/test_cases.py::test_assign_timed_out_case`
- R12 → `H/test_cases.py::test_assign_already_assigned_keeps_first_advisor`
- R13 → `H/test_cases.py::test_assign_closed_case_returns_409`
- R14 → `H/test_cases.py::test_assign_and_close_unknown_case_return_404`
- R15 → `H/test_cases.py::test_close_marks_closed_and_records_advisor`
- R16 → `H/test_cases.py::test_close_is_idempotent_and_keeps_first_closure`
- R17 → `H/test_timeouts.py::test_check_timeouts_notifies_client_and_marks_timed_out`
- R18 → `H/test_timeouts.py::test_check_timeouts_ignores_assigned_closed_and_recent_cases`
- R19 → `H/test_timeouts.py::test_check_timeouts_send_failure_keeps_case_open`
- R20 → `H/test_timeouts.py::test_check_timeouts_continues_after_failure`
- R21 → `H/test_timeouts.py::test_check_timeouts_returns_empty_list_when_none_expired`, `H/test_timeouts.py::test_check_timeouts_notifies_client_and_marks_timed_out`
- R22 → `H/test_timeouts.py::test_check_timeouts_uses_injected_clock`, `H/test_timeouts.py::test_package_never_reads_wall_clock_outside_main`
- R23 → `H/test_config.py::test_advisor_ids_discards_blank_and_non_numeric`, `H/test_config.py::test_timeout_defaults_to_300`, `H/test_config.py::test_timeout_below_one_is_rejected`, `H/test_config.py::test_settings_read_from_env`, `H/test_config.py::test_advisor_ids_empty_by_default`
- R24 → `H/test_security.py::test_handover_routes_without_token_return_401_and_change_nothing` (4 rutas × sin token / token erróneo)
- R25 → `H/test_security.py::test_handover_invalid_body_returns_422` (las 4 rutas)
- R26 → `H/test_repository.py::test_postgres_repository_uses_parameters_only`, `H/test_repository.py::test_postgres_repository_connects_lazily_and_once`, `H/test_repository.py::test_postgres_repository_reads_cases_from_rows`, `H/test_repository.py::test_import_main_does_not_connect`
- R27 → `O/test_config.py::test_no_advisors_reply_has_default`
- R28 → `O/test_case_reply.py::test_case_is_linked_to_contact_after_handover`, `O/test_case_reply.py::test_case_link_uses_effective_case_id`, `O/test_case_reply.py::test_postgres_case_links_use_parameters_only`
- R29 → `O/test_case_reply.py::test_no_advisors_sends_fixed_reply_to_client`
- R30 → `O/test_case_reply.py::test_no_advisors_sends_fixed_reply_to_client`, `O/test_case_reply.py::test_no_advisors_after_no_relevant_chunks_also_informs_client`
- R31 → `O/test_case_reply.py::test_reply_sends_text_stores_advisor_message_and_event`
- R32 → `O/test_case_reply.py::test_reply_sends_text_stores_advisor_message_and_event`
- R33 → `O/test_case_reply.py::test_reply_assigns_case_in_handover`, `O/test_case_reply.py::test_http_handover_client_assign_posts_to_assign_route`
- R34 → `O/test_case_reply.py::test_reply_assign_failure_still_returns_sent`, `O/test_case_reply.py::test_http_handover_client_assign_raises_on_error_status`
- R35 → `O/test_case_reply.py::test_reply_unknown_case_returns_404_without_sending`
- R36 → `O/test_case_reply.py::test_reply_send_failure_returns_502_and_stores_nothing`
- R37 → `O/test_case_reply.py::test_reply_without_token_returns_401`
- R38 → `O/test_case_reply.py::test_reply_invalid_body_returns_422`
- R39, R40 → retirados del spec (sin test en esta feature).

## Decisiones menores de implementación (dentro del design)

- Etiqueta del motivo en el aviso: el propio código de `reason` (`Motivo: user_request`); el
  design no define otras etiquetas y no se han inventado.
- Al reutilizar un caso, el aviso y la notificación usan el `reason` de la petición en curso; el
  `reason` guardado en el caso no cambia (R2 solo pide actualizar `last_messages`).
- `close_case` guarda el asesor en `closed_by` (campo del design); `advisor_id` del caso (el
  asignado) se conserva.
- Los logs de handover y del orquestador llevan `case_id`/`advisor_id`/códigos, nunca texto
  de clientes ni de asesores (comprobado para el vencimiento en
  `test_check_timeouts_send_failure_keeps_case_open`).
- Si handover no responde (`ServiceUnavailable`), el orquestador no crea vínculo ni envía nada,
  como hasta ahora (supuesto del design; `test_handover_unavailable_creates_no_link`).

## Bloqueos

Ninguno.
