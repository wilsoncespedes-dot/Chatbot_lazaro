# Review — feature #41 panel_asesores_multicanal

**Veredicto:** APPROVED

`./init.sh` ejecutado por el reviewer: `2789 passed, 1 skipped` → OK.

## Trazabilidad requirements ↔ tests

Se comprobó que existe cada función de test citada en
`progress/impl_panel_asesores_multicanal.md` (búsqueda `def <nombre>` en
`services/` y `contracts/`; 0 ausentes).

- R1: [x] `test_panel_inbox.py::test_inbox_shows_both_channels_and_respects_role`, `::test_inbox_uses_advisor_id_from_session`
- R2–R6: [x] `test_panel_inbox.py::test_inbox_shows_both_channels_and_respects_role`; R4 también `test_panel_pure.py::test_case_wait_three_branches`; R5 también `::test_channel_window_boundaries_and_telegram`
- R7: [x] `test_inbox_filters_by_channel_and_assignment`
- R8: [x] `test_invalid_filter_is_422_without_calling_handover`
- R9, R10: [x] `test_inbox_orders_by_created_at_and_tolerates_unlinked_case`
- R11: [x] `test_non_advisor_session_redirects_without_listing`
- R12: [x] `test_meta_refresh_is_configurable`
- R13: [x] `test_repository_schema.py::test_get_case_contact_selects_all_six_columns`, `test_panel_case_view.py::test_memory_route_and_whatsapp_contact_remain_available`
- R14: [x] `test_reply_telegram_uses_gateway_send`, `test_reply_whatsapp_open_uses_channel_send`
- R15: [x] `test_reply_requires_exactly_one_of_text_or_template`
- R16: [x] `test_reply_whatsapp_closed_returns_409_without_sending`
- R17, R18: [x] `test_template_valid_is_sent_and_stored`
- R19, R20: [x] `test_template_rejected_without_calling_gateway`
- R21: [x] `test_gateway_422_maps_to_channel_window_closed`, `test_adapters.py::test_http_gateway_raises_channel_rejected_on_422`
- R22: [x] `test_responder_command_on_closed_whatsapp_sends_failed_reply`
- R23: [x] `test_authorize_happens_before_window_check`
- R24, R25: [x] `test_case_view_renders_selector_or_textarea`
- R26: [x] `contracts/tests/test_examples.py` (ejemplos `case_transfer_*.json`), `test_adapters.py::test_http_transfer_uses_route_token_and_payload`; ruta documentada en `contracts/CONTRATOS.md:598`
- R27: [x] `handover/tests/test_transfer.py::test_transfer_reassigns_case_and_updates_assigned_at`
- R28: [x] `test_unregistered_actor_is_denied_and_records_transfer`, `test_case_not_assigned_to_actor_is_denied`, `test_case_assigned_to_other_advisor_is_denied`
- R29: [x] `test_invalid_or_same_target_returns_422_without_changes`
- R30: [x] `test_missing_case_returns_404`, `test_closed_case_returns_409`
- R31: [x] `test_lost_race_to_target_returns_200`, `test_lost_race_to_other_advisor_returns_403`
- R32–R35: [x] `test_panel_actions.py::test_transfer_success_records_handover_and_event`, `::test_transfer_maps_handover_errors`, `::test_transfer_invalid_target_is_422_without_handover`, `::test_transfer_away_target_is_409_without_handover`
- R36: [x] `test_resolve_keeps_closed_reply_and_state`
- R37, R38: [x] `test_return_closes_sends_return_reply_and_records_event`
- R39: [x] `test_whatsapp_closed_skips_notice_but_closes_case`
- R40, R41: [x] `test_panel_case_view.py::test_authorization_happens_before_reading_case_data`
- R42, R43: [x] `test_history_respects_lookback_limit_labels_and_order`
- R44: [x] `test_foreign_session_windows_are_hidden_with_and_without_profile`
- R45, R46: [x] `test_memory_and_summaries_are_shown_and_client_data_is_masked`
- R47: [x] `test_case_without_profile_shows_no_client_and_no_memory`
- R48: [x] `test_all_texts_are_escaped`
- R49: [x] `test_transfer_targets_include_presence`
- R50: [x] `test_panel_audit.py::test_reads_record_one_audit_row_each`
- R51: [x] `test_actions_record_ok`
- R52: [x] `test_domain_errors_record_their_code`
- R53: [x] `test_audit_never_stores_client_text_username_external_id_or_note`
- R54: [x] `test_domain_errors_record_their_code`, `test_advisor_panel.py::test_forbidden_actions_record_advisor_forbidden_event`
- R55: [x] `test_repository_schema.py::test_schema_declares_panel_audit_and_presence`
- R56–R59: [x] `test_presence_is_stored_with_now`, `test_invalid_presence_is_422_without_changing_state`, `test_protected_request_touches_last_seen_keeping_status`, `test_logout_sets_presence_away`
- R60, R61: [x] `test_panel_suppression.py::test_admin_queue_shows_pending_with_priority`, `::test_asesor_queue_requires_executor_role`
- R62: [x] `test_queue_orders_pending_by_deadline_and_limits_executed`
- R63, R64: [x] `test_panel_pure.py::test_business_deadline_skips_weekend`, `::test_business_days_left_and_priority_three_branches`
- R65: [x] `test_admin_queue_shows_pending_with_priority`
- R66: [x] `test_execute_telegram_saves_note_and_sends_text`, `test_execute_without_csrf_is_forbidden`
- R67: [x] `test_long_note_is_422_without_executing`
- R68: [x] `test_execute_whatsapp_open_uses_text_and_closed_uses_template`
- R69: [x] `test_notice_failure_and_missing_contact_are_recorded`
- R70: [x] `test_execution_errors_do_not_notify`
- R71, R72: [x] `test_config.py::test_panel_settings_defaults_and_env_example`, `::test_panel_settings_reject_invalid_values`
- R73: [x] `test_memory_route_and_whatsapp_contact_remain_available` + suites existentes verdes (`test_advisor_commands.py`, `test_advisor_panel.py`, `test_case_reply.py`, `test_memory_panel.py`)
- R74: [x] `test_transfer.py::test_transfer_without_token_returns_401`, `::test_invalid_body_returns_422`; filas añadidas en `handover/tests/test_security.py:26,40-42`

## Tasks completas
- T1–T32: [x] (todas `[x]` en `specs/panel_asesores_multicanal/tasks.md`)

## Checkpoints
- C1: [x] archivos base y docs presentes; `./init.sh` exit 0.
- C2: [x] #41 es la única feature `in_progress`; las features `done` están verdes.
- C3: [x] Sin servicios nuevos. `panel.py` vive en el orchestrator, `transfer` en handover, y los modelos compartidos solo en `contracts/lazaro_contracts/cases.py`. Ruta documentada en `CONTRATOS.md`. Sin dependencias nuevas. Variables nuevas en `.env.example:143-155` y `render.yaml:121-143`. Sin `print`/`eval`/`exec`/TODO en los archivos nuevos. El SQL nuevo está parametrizado (el único f-string de `orchestrator/adapters/repository.py:3407` ya existía, con columna en lista blanca). `docs/architecture.md:45-47` actualizado.
- C4: [x] tests con fakes (gateway, handover, repo); hay tests de seguridad 401/422 de la ruta nueva.
- C5: [x] no hay archivos sospechosos; los archivos sin trackear pertenecen a esta feature y a las anteriores. Al cerrar, el leader debe añadir la entrada en `progress/history.md`.
- C6: [x] spec completo con 3 archivos, EARS aprobado en `progress/specreview_panel_asesores_multicanal.md` y cada R cubierto por tests.

## Observaciones no bloqueantes
1. `services/orchestrator/tests/panel_helpers.py` quedó como un módulo vacío (solo docstring) sin uso; conviene borrarlo al cerrar.
2. Aviso de deprecación de Pydantic en `test_conversation_states.py:648` (`model_fields` sobre la instancia). Es anterior a #41 y no afecta.
