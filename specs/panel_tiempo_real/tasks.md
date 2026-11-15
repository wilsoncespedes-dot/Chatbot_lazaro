# Tasks — panel_tiempo_real (#53)

Requisito previo humano: instalar `websockets>=13,<16` en `.venv` y añadirlo a `services/orchestrator/requirements.txt` (ver design.md). Los tests no lo necesitan.

## Configuración y dominio puro
- [x] T1 — `config.py` y `.env.example`: `PANEL_LIVE_ENABLED`, `PANEL_WS_ALLOWED_ORIGINS` (propiedad que devuelve tupla), `PANEL_EVENTS_POLL_SECONDS`, `PANEL_EVENTS_RETENTION_HOURS`, `PANEL_WS_MAX_CONNECTIONS_PER_PROFILE`. Cubre: R4, R5, R9, R19, R21, R35.
- [x] T2 — `panel_live.py`: `PanelEvent`, `origin_allowed`, `event_payload`, `dedupe_new_events`. Cubre: R3, R4, R5, R13, R20.
- [x] T3 — `admin.py`: `PANEL_CSP` y `panel_security_headers()`; `advisor_routes.py` los usa en `_html`/`_redirect`. Cubre: R29.

## Repositorio y publicación
- [x] T4 — `repository.py`: tabla `panel_events` + índice en `_SCHEMA`; métodos `publish_panel_event`, `panel_events_cursor`, `panel_events_since`, `delete_panel_events_before`, `latest_case_for_contact` en Protocol, `InMemoryRepository` y `PostgresRepository`. Cubre: R19, R20, R21.
- [x] T5 — `add_message` (ambos repos) inserta evento `message` en la misma transacción; `link_case` inserta `case_created`; el fallo del evento no aborta el mensaje. Cubre: R15, R16, R18.
- [x] T6 — `domain.py`: `publish_case_event` (traga y registra errores) y llamadas tras éxito en `assign_case`, `close_case`, `transfer_case`, `reassign_case`, `return_case`, `reply_to_case`; purga de eventos en `execute_suppression`. Cubre: R17, R18, R21, R22.
- [x] T7 — `domain.py`: `visible_case_ids` y `advisor_case_history` (extraer `_case_history` de `advisor_case_view` sin cambiar su comportamiento). Cubre: R11, R12, R24, R25.

## Rutas, JS y plantillas
- [x] T8 — `panel_live_routes.py`: `WS /asesor/ws` (orden de rechazos, `hello`, bucle de sondeo, revalidación de sesión con `get_session_for_roles` sin tocar presencia, límite por perfil, cierre `1003`/`4401`). Cubre: R1, R2, R3, R6, R7, R8, R9, R10, R11, R12, R13, R14, R19, R20, R35.
- [x] T9 — `panel_live_routes.py`: `GET /asesor/live/inbox`, `GET /asesor/live/cases/{case_id}`, `GET /asesor/static/panel_live.js`; registrar el router en `main.py`. Cubre: R23, R24, R25, R26, R27.
- [x] T10 — `advisor_panel.py`: extraer `render_inbox_table`/`render_history_fragment`; añadir `<div id="live-region" data-...>`, `<script src defer>` (solo con `panel_live_enabled`) y `<noscript><meta refresh>`; formularios con CSRF intactos. Cubre: R27, R28, R33, R34, R35.
- [x] T11 — `panel_live_js.py`: `PANEL_LIVE_JS` (conexión, `hello`→refetch, evento→refetch con `DOMParser`+`replaceChildren`, backoff exponencial 1–30 s, sondeo de respaldo, sin `eval`/`Function`/strings en timers/CDN). Cubre: R28, R30, R31, R32.

## Pruebas (cada test cita su R en el docstring; `fastapi.testclient`, fakes, sin red)
- [x] T12 — `test_panel_live_pure.py`: `test_origin_allowed_exact_match_and_host_fallback`, `test_event_payload_has_only_allowed_keys`, `test_dedupe_new_events_delivers_each_id_once`. Cubre: R4, R5, R13, R20.
- [x] T13 — `test_panel_live_ws.py`: `test_ws_rejects_without_session`, `test_ws_rejects_expired_session`, `test_ws_rejects_non_panel_role`, `test_ws_rejects_missing_origin`, `test_ws_rejects_foreign_origin`, `test_ws_accepts_configured_origin`, `test_ws_scope_all_rejected_for_asesor`, `test_ws_does_not_touch_presence`, `test_ws_connection_limit_per_profile`, `test_ws_closes_4401_after_logout`, `test_ws_client_message_closes_1003`, `test_ws_first_message_is_hello_with_cursor`, `test_ws_disabled_rejects_handshake`. Cubre: R1, R2, R3, R6, R7, R8, R9, R10, R14, R35.
- [x] T14 — `test_panel_live_security.py`: `test_ws_delivers_only_cases_in_advisor_list`, `test_ws_never_delivers_other_advisors_case`, `test_ws_fails_closed_when_handover_unavailable`, `test_ws_event_has_no_tokens_text_or_client_data`, `test_supervisor_scope_all_receives_global_events`. Cubre: R11, R12, R13.
- [x] T15 — `test_panel_live_publish.py` y `test_panel_live_repository.py`: `test_add_message_publishes_event_for_latest_case`, `test_link_case_publishes_case_created`, `test_panel_actions_publish_case_updated` (parametrizado por acción), `test_publish_failure_does_not_fail_message_or_action`, `test_event_from_second_repository_instance_reaches_ws` (dos `InMemoryRepository` compartiendo almacén simulan instancia/proceso distintos), `test_events_older_than_retention_deleted_on_publish`, `test_suppression_deletes_case_events`, `test_postgres_schema_declares_panel_events`. Cubre: R15, R16, R17, R18, R19, R21, R22.
- [x] T16 — `test_panel_live_fragments.py`: `test_live_inbox_requires_session`, `test_live_inbox_matches_inbox_table_and_filters`, `test_live_case_history_requires_authorization`, `test_live_case_history_does_not_audit_memory_viewed`, `test_live_fragment_contains_no_forms_outside_inbox_reassign`, `test_actions_remain_post_forms_with_csrf`, `test_reconnect_refetch_returns_current_state_without_duplicates` (dos llamadas consecutivas tras añadir un mensaje: sin filas repetidas). Cubre: R23, R24, R25, R26, R30, R31, R34.
- [x] T17 — `test_panel_live_js.py`: `test_js_served_same_origin_with_js_content_type`, `test_pages_reference_script_without_inline_or_handlers`, `test_js_has_no_eval_function_string_timers_or_external_hosts`, `test_js_contains_backoff_and_polling_fallback_markers`, `test_inbox_has_noscript_meta_refresh`, `test_pages_without_live_flag_omit_script_but_keep_refresh`. Cubre: R27, R28, R32, R33, R35.
- [x] T18 — `test_panel_live_security.py`: `test_panel_pages_csp_is_strict` (todas las páginas del panel de asesores: directivas de R29, sin `unsafe-inline`/`unsafe-eval`). Cubre: R29.

## Cierre
- [x] T19 — `docs/architecture.md`: actualizar «Panel de asesores multicanal (#41)» (JS propio mismo origen, websocket de avisos, tabla `panel_events`). Cubre: R1, R19.
- [x] T20 — Ejecutar `./init.sh` (verde), escribir `progress/impl_panel_tiempo_real.md` con el mapa R→test y marcar `[x]` cada task. Cubre: R1–R35 (acceptance 6).
