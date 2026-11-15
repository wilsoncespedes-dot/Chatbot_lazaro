# Review — feature 53 (panel_tiempo_real)

**Veredicto:** APPROVED

`./init.sh`: exit 0, 3416 passed, 1 skipped (resultado aportado tras las correcciones; no se repite).

## Trazabilidad requirements ↔ tests
(Todos los tests citados existen en `services/orchestrator/tests/test_panel_live_*.py`, verificado por nombre.)
- R1: [x] `test_ws_accepts_configured_origin`
- R2: [x] `test_ws_rejects_without_session`, `_expired_session`, `_non_panel_role`
- R3: [x] `test_ws_rejects_missing_origin`, `_foreign_origin`
- R4: [x] `test_origin_allowed_exact_match_and_host_fallback`
- R5: [x] mismo test puro (fallback a `Host`)
- R6: [x] `test_ws_closes_4401_after_logout`
- R7: [x] `test_ws_scope_all_rejected_for_asesor`, `test_supervisor_scope_all_receives_global_events`
- R8: [x] `test_ws_does_not_touch_presence`
- R9: [x] `test_ws_connection_limit_per_profile`
- R10: [x] `test_ws_client_message_closes_1003`
- R11: [x] `test_ws_delivers_only_cases_in_advisor_list`, `test_ws_never_delivers_other_advisors_case`
- R12: [x] `test_ws_fails_closed_when_handover_unavailable`
- R13: [x] `test_event_payload_has_only_allowed_keys`, `test_ws_event_has_no_tokens_text_or_client_data`
- R14: [x] `test_ws_first_message_is_hello_with_cursor`
- R15: [x] `test_add_message_publishes_event_for_latest_case`
- R16: [x] `test_link_case_publishes_case_created`
- R17: [x] `test_panel_actions_publish_case_updated` (parametrizado: las 6 acciones)
- R18: [x] `test_publish_failure_does_not_fail_message_or_action`
- R19: [x] `test_event_from_second_repository_instance_reaches_ws`, `test_postgres_schema_declares_panel_events`
- R20: [x] `test_dedupe_new_events_delivers_each_id_once`
- R21: [x] `test_events_older_than_retention_deleted_on_publish`
- R22: [x] `test_suppression_deletes_case_events`
- R23: [x] `test_live_inbox_matches_inbox_table_and_filters`
- R24: [x] `test_live_case_history_requires_authorization`, `_does_not_audit_memory_viewed`
- R25: [x] `test_live_case_history_requires_authorization`, `_missing_case_is_not_found`
- R26: [x] `test_live_inbox_requires_session`
- R27: [x] `test_js_served_same_origin_with_js_content_type`, `test_pages_reference_script_without_inline_or_handlers`
- R28: [x] `test_js_has_no_eval_function_string_timers_or_external_hosts` (+ el de páginas)
- R29: [x] `test_panel_pages_csp_is_strict`
- R30: [x] `test_reconnect_refetch_returns_current_state_without_duplicates` (+ marcadores JS; la lógica es `replaceChildren`, sin anexar)
- R31: [x] mismo test + marcadores JS (`hello` → `refresh()`)
- R32: [x] `test_js_contains_backoff_and_polling_fallback_markers`
- R33: [x] `test_inbox_has_noscript_meta_refresh`
- R34: [x] `test_actions_remain_post_forms_with_csrf`, `test_live_fragment_contains_no_forms_outside_inbox_reassign`
- R35: [x] `test_ws_disabled_rejects_handshake`, `test_pages_without_live_flag_omit_script_but_keep_refresh`

## Tasks completas
- T1–T20: [x] (20 `[x]`, 0 `[ ]` en `specs/panel_tiempo_real/tasks.md`; T20 documentada en `progress/impl_panel_tiempo_real.md`).

## Revisión de código (puntos pedidos)
- Origin/sesión: `panel_live_routes.py` rechaza antes de `accept()` (flag, Origin, sesión/rol, scope, límite por perfil). Sin Origin → `False` en `origin_allowed`. Lista exacta si está configurada; si no, host/puerto contra `Host`.
- Autorización por caso y fallo cerrado: `visible_case_ids` (`list_cases`) por lote; ante excepción se registra `panel_events_visibility_failed` sin datos y no se envía nada. Payload limitado a `type/id/case_id`.
- Sesión revalidada en cada sondeo (4401). Mensajes del cliente → 1003. No se toca la presencia.
- Publicación transaccional: Postgres `add_message` y `link_case` insertan el evento y purgan la retención en la misma transacción que el mensaje o el enlace. Si falla la publicación, hace rollback y reinserta solo el mensaje o el enlace (R18). Las acciones usan `publish_case_event` con try/except y log.
- Retención/supresión: `DELETE ... created_at < %s` al publicar. `execute_suppression` y la purga de inactivos borran `panel_events` de los casos purgados. Todo el SQL es parametrizado.
- CSP/JS: `PANEL_CSP` cumple R29. El JS es propio, de mismo origen, sin `eval` ni cadenas en timers. El HTML reemplaza con `replaceChildren` y `DOMParser`, sin `innerHTML`. Los fragmentos `/asesor/live/*` no tienen formularios de acción nuevos.
- Fallback/no duplicación: reintento con backoff exponencial acotado, sondeo mientras no hay conexión y `<noscript>` meta refresh. Dedupe por conjunto de ids acotado y reemplazo de región.
- Cambios en tests existentes (CSP, rutas, requirements, expectativa SQL de `link_case`): conservan su intención y solo reflejan #53, sin debilitar la parametrización.
- Dependencia `websockets>=13,<16` (BSD-3) acotada en `requirements.txt`. Variables nuevas en `.env.example`.

## Checkpoints
- C1: [x]
- C2: [x]
- C3: [x]
- C4: [x]
- C5: [x] (el cierre de sesión, `history.md` y el estado de la feature corresponden al leader)
- C6: [x]

## Observaciones no bloqueantes
- En la vista de caso el websocket usa `scope=mine`, así que un supervisor que mire un caso ajeno no recibe avisos en vivo. Es coherente con R11, y el reconectar o recargar recupera el estado. Se puede mejorar en otra feature.

## Cambios requeridos
Ninguno.
