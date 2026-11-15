# Implementación — panel_tiempo_real (#53)

## Resumen

Websocket de solo lectura `GET /asesor/ws`, fragmentos HTML autorizados
(`/asesor/live/inbox`, `/asesor/live/cases/{id}`), JavaScript propio de mismo
origen y tabla Postgres `panel_events` sondeada por cada conexión. Se añaden
los avisos `message`, `case_created` y `case_updated`, la retención por horas y
la limpieza al ejecutar una supresión. No se tocan `handover`, gateway, rag ni
`contracts/`.

Se actualizó `test_advisor_panel.py::test_advisor_html_has_csp_and_no_external_resources`
para la CSP estricta y el único script propio de mismo origen que exigen
#53 R27–R29; su intención (sin recursos externos) se conserva. También se
añadieron las tres rutas HTTP nuevas al conjunto exacto de
`test_config.py::test_only_health_and_messages_routes_exposed` (el websocket no es `APIRoute`).

## Trazabilidad

- R1 → `tests/test_panel_live_ws.py::test_ws_accepts_configured_origin`
- R2 → `tests/test_panel_live_ws.py::test_ws_rejects_without_session`, `::test_ws_rejects_expired_session`, `::test_ws_rejects_non_panel_role`
- R3 → `tests/test_panel_live_ws.py::test_ws_rejects_missing_origin`, `::test_ws_rejects_foreign_origin`
- R4 → `tests/test_panel_live_pure.py::test_origin_allowed_exact_match_and_host_fallback`, `tests/test_panel_live_ws.py::test_ws_accepts_configured_origin`
- R5 → `tests/test_panel_live_pure.py::test_origin_allowed_exact_match_and_host_fallback`
- R6 → `tests/test_panel_live_ws.py::test_ws_closes_4401_after_logout`
- R7 → `tests/test_panel_live_ws.py::test_ws_scope_all_rejected_for_asesor`, `tests/test_panel_live_security.py::test_supervisor_scope_all_receives_global_events`
- R8 → `tests/test_panel_live_ws.py::test_ws_does_not_touch_presence`
- R9 → `tests/test_panel_live_ws.py::test_ws_connection_limit_per_profile`
- R10 → `tests/test_panel_live_ws.py::test_ws_client_message_closes_1003`
- R11 → `tests/test_panel_live_security.py::test_ws_delivers_only_cases_in_advisor_list`, `::test_ws_never_delivers_other_advisors_case`
- R12 → `tests/test_panel_live_security.py::test_ws_fails_closed_when_handover_unavailable`
- R13 → `tests/test_panel_live_pure.py::test_event_payload_has_only_allowed_keys`, `tests/test_panel_live_security.py::test_ws_event_has_no_tokens_text_or_client_data`
- R14 → `tests/test_panel_live_ws.py::test_ws_first_message_is_hello_with_cursor`
- R15 → `tests/test_panel_live_publish.py::test_add_message_publishes_event_for_latest_case`
- R16 → `tests/test_panel_live_publish.py::test_link_case_publishes_case_created`
- R17 → `tests/test_panel_live_publish.py::test_panel_actions_publish_case_updated`
- R18 → `tests/test_panel_live_publish.py::test_publish_failure_does_not_fail_message_or_action`
- R19 → `tests/test_panel_live_publish.py::test_event_from_second_repository_instance_reaches_ws`, `tests/test_panel_live_repository.py::test_postgres_schema_declares_panel_events`
- R20 → `tests/test_panel_live_pure.py::test_dedupe_new_events_delivers_each_id_once`
- R21 → `tests/test_panel_live_publish.py::test_events_older_than_retention_deleted_on_publish`
- R22 → `tests/test_panel_live_publish.py::test_suppression_deletes_case_events`
- R23 → `tests/test_panel_live_fragments.py::test_live_inbox_matches_inbox_table_and_filters`
- R24 → `tests/test_panel_live_fragments.py::test_live_case_history_requires_authorization`, `::test_live_case_history_does_not_audit_memory_viewed`
- R25 → `tests/test_panel_live_fragments.py::test_live_case_history_requires_authorization`, `::test_live_case_history_missing_case_is_not_found`
- R26 → `tests/test_panel_live_fragments.py::test_live_inbox_requires_session`
- R27 → `tests/test_panel_live_js.py::test_js_served_same_origin_with_js_content_type`, `::test_pages_reference_script_without_inline_or_handlers`
- R28 → `tests/test_panel_live_js.py::test_pages_reference_script_without_inline_or_handlers`, `::test_js_has_no_eval_function_string_timers_or_external_hosts`
- R29 → `tests/test_panel_live_security.py::test_panel_pages_csp_is_strict`
- R30 → `tests/test_panel_live_fragments.py::test_reconnect_refetch_returns_current_state_without_duplicates`, `tests/test_panel_live_js.py::test_js_contains_backoff_and_polling_fallback_markers`
- R31 → `tests/test_panel_live_fragments.py::test_reconnect_refetch_returns_current_state_without_duplicates`, `tests/test_panel_live_js.py::test_js_contains_backoff_and_polling_fallback_markers`
- R32 → `tests/test_panel_live_js.py::test_js_contains_backoff_and_polling_fallback_markers`
- R33 → `tests/test_panel_live_js.py::test_inbox_has_noscript_meta_refresh`
- R34 → `tests/test_panel_live_fragments.py::test_actions_remain_post_forms_with_csrf`, `::test_live_fragment_contains_no_forms_outside_inbox_reassign`
- R35 → `tests/test_panel_live_ws.py::test_ws_disabled_rejects_handshake`, `tests/test_panel_live_js.py::test_pages_without_live_flag_omit_script_but_keep_refresh`

## Notas

- `websockets>=13,<16` se añadió a `services/orchestrator/requirements.txt` y se instaló en `.venv` con autorización explícita del dueño.

## `init.sh` intento 1 — fallo

- La suite superó el límite de 30 minutos al 52%; la ejecución diagnóstica `pytest -x -q` aisló el primer fallo: `services/orchestrator/tests/test_case_reply.py::test_postgres_case_links_use_parameters_only` esperaba dos sentencias SQL y ahora `link_case` inserta también `case_created` y limpia la retención de `panel_events` (R16, R21). Actualizar la expectativa para comprobar las sentencias nuevas y sus parámetros, sin debilitar la comprobación de parametrización. T20 queda pendiente.
- Tras corregir esa expectativa, el grupo de pruebas dirigido se bloqueó en `test_panel_live_security.py::test_ws_event_has_no_tokens_text_or_client_data`: el caso de prueba no añade `case-1` a `FakeHandoverClient.case_list`, así que el filtro de autorización correctamente descarta el evento y `receive_json()` espera indefinidamente. Configurar el caso como visible en handover en el test; no relajar el filtro del websocket.

## Corrección del fallo del intento 1

- `test_case_reply.py::test_postgres_case_links_use_parameters_only` actualizado: espera las
  cuatro sentencias reales (`INSERT INTO case_links`, `INSERT INTO panel_events` con
  `case_created`, `DELETE FROM panel_events` con `FIXED_NOW - 24h` y la consulta
  `get_case_contact`) y verifica que cada una conserva SQL parametrizado (`sql.count("%s") ==
  len(params)`, secreto fuera del SQL). Se añade `timedelta` al import. No se elimina ni se
  debilita ninguna aserción previa de parametrización.
- T20 sigue pendiente: `./init.sh` lo ejecuta Claude tras esta sesión. No se han detectado otros
  tests existentes con conteos de sentencias afectados por `add_message`/`link_case`
  (`test_adapters`, `test_privacy_purge`, `test_memory_suppression`, `test_multicanal_dedup`,
  `test_auto_handover`, `test_client_forward`): todos siguen siendo compatibles con las
  sentencias adicionales porque no fijan el número total o solo comprueban parametrización.

## Corrección del segundo fallo del intento 1

- `test_panel_live_security.py::test_ws_event_has_no_tokens_text_or_client_data`: el test no
  configuraba el caso `case-1` en `FakeHandoverClient.case_list`, por lo que
  `visible_case_ids` lo descartaba correctamente y `receive_json()` esperaba sin límite hasta
  agotar el tiempo de `init.sh`. Se añade `env.handover.case_list = [panel.case_item("case-1")]`
  tras `panel.link_case`; no se relaja el filtro de autorización del websocket.
- T20 sigue pendiente: queda la ejecución de `./init.sh` y la revisión de código final de Claude.

## `init.sh` intento 2 — fallo

- Resultado: 1 failed, 3415 passed, 1 skipped. `services/orchestrator/tests/test_orchestrator_app.py::test_requirements_txt_matches_design` valida una lista cerrada de dependencias anterior a #53 y no incluye `websockets`, ahora declarada por el design aprobado. Actualizar la expectativa de dependencias del test de superficie; no retirar el paquete requerido por el websocket.

## Corrección del fallo del intento 2

- `test_orchestrator_app.py::test_requirements_txt_matches_design` incluye ahora `websockets` en la
  lista exacta de dependencias esperadas. Se conserva la comprobación de cota doble
  (`>=` y `<`) para todas las líneas, que `websockets>=13,<16` cumple, y no se retira ninguna
  dependencia ni aserción previa. El paquete lo exige el design aprobado de #53 para atender
  handshakes websocket en ejecución real.
- T20 sigue pendiente: queda la ejecución de `./init.sh` y la revisión de código final de Claude.

## Verificación final

`bash ./init.sh`: exit 0, 3416 passed, 1 skipped y 2 avisos de deprecación.
T1–T20 completas; queda pendiente la revisión de código Claude.
