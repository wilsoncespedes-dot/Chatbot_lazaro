# Implementación — feature #42 administracion_y_avisos

Modo: nocturno. Writer: OpenCode/DeepSeek vía `scripts/run_opencode_writer.sh`.

## Observaciones no bloqueantes del spec review (atender al implementar)

Fuente: `progress/specreview_administracion_y_avisos.md`.

1. R47, R48, R53 y R69 tienen dos `DEBE`/`NO DEBE` cada uno, y R42 combina
   MIENTRAS con CUANDO: en la trazabilidad `R<n> -> test`, cubrir con un test
   cada una de las dos partes de esos requisitos.
2. R22 (sujeto «el siguiente mensaje»): verificarlo en T36.
3. S2: una fila de aviso en estado `sending` huérfana no se reintenta nunca;
   mostrarla como `sending` en `/admin/clientes` (R1).

Al terminar, añade a este archivo la tabla de trazabilidad `R<n> -> test`
(archivo::nombre_test) para todos los requisitos.

## Registro

Implementadas las 44 tasks salvo T44 (la ejecución de `./init.sh` la hace
Claude al cerrar la sesión del implementer). Se atendieron las tres
observaciones del spec review:

1. R47, R48, R53 y R69 tienen tests para cada una de sus dos partes; R42
   cubre el estado (horario activo) y el evento (traspaso fuera de horario).
2. R22 se verifica en T36 con el siguiente mensaje procesado.
3. S2: una fila `sending` huérfana aparece como `sending` en
   `/admin/clientes` y no se reintenta; hay un test que lo comprueba.

## Trazabilidad

- R1 → `tests/test_admin_clients.py::test_clients_table_shows_state_days_session_and_notice`
- R2 → `tests/test_admin_clients.py::test_days_and_state_are_calculated_from_dates_without_counter`
- R3 → `tests/test_admin_clients.py::test_create_with_explicit_dates`
- R4 → `tests/test_admin_clients.py::test_create_without_dates_uses_configured_validity_days`; `tests/test_admin_clients.py::test_create_with_explicit_dates`
- R5 → `tests/test_admin_clients.py::test_invalid_client_returns_422_without_echoing_password`
- R6 → `tests/test_admin_clients.py::test_duplicate_client_returns_409`
- R7 → `tests/test_admin_clients.py::test_renew_from_expired_and_valid`
- R8 → `tests/test_admin_clients.py::test_renew_revoked_returns_409_and_does_not_change`
- R9 → `tests/test_admin_clients.py::test_revoke_closes_active_session`
- R10 → `tests/test_admin_clients.py::test_close_session_does_not_change_dates`
- R11 → `tests/test_admin_clients.py::test_unknown_client_returns_404`
- R12 → `tests/test_admin_permissions.py::test_get_without_session_redirects`; `test_post_without_session_redirects_before_csrf`; `test_advisor_session_is_not_an_admin_session`; `test_expired_admin_session_redirects`
- R13 → `tests/test_admin_permissions.py::test_post_without_or_with_wrong_csrf_is_forbidden`
- R14 → `tests/test_admin_permissions.py::test_expiry_notices_without_service_token_returns_401`
- R15 → `tests/test_admin_texts_versions.py::test_changed_field_creates_one_version_and_unchanged_none`
- R16 → `tests/test_admin_texts_versions.py::test_changed_field_creates_one_version_and_unchanged_none`
- R17 → `tests/test_admin_texts_versions.py::test_changed_field_creates_one_version_and_unchanged_none`
- R18 → `tests/test_admin_texts_versions.py::test_changing_notice_with_same_version_is_422_and_rolls_back`
- R19 → `tests/test_admin_texts_versions.py::test_version_and_history_are_visible_ordered_limited_and_escaped`
- R20 → `tests/test_admin_texts_versions.py::test_version_and_history_are_visible_ordered_limited_and_escaped`
- R21 → `tests/test_admin_texts_versions.py::test_unknown_text_field_history_returns_404`
- R22 → `tests/test_admin_texts_versions.py::test_next_message_uses_new_text_without_restart`
- R23 → `tests/test_admin_texts_versions.py::test_closing_reply_replaces_case_closed_reply`
- R24 → `tests/test_admin_texts_versions.py::test_topics_list_is_added_to_active_welcome`
- R25 → `tests/test_admin_templates.py::test_create_valid_template_in_draft`
- R26 → `tests/test_admin_templates.py::test_create_valid_template_in_draft`; `test_invalid_template_returns_422`
- R27 → `tests/test_admin_templates.py::test_invalid_template_returns_422`
- R28 → `tests/test_admin_templates.py::test_duplicate_template_returns_409`
- R29 → `tests/test_admin_templates.py::test_allowed_transitions_register_approver_and_invalid_rejected`
- R30 → `tests/test_admin_templates.py::test_allowed_transitions_register_approver_and_invalid_rejected`
- R31 → `tests/test_admin_templates.py::test_edit_returns_to_draft_and_clears_approval`
- R32 → `tests/test_admin_templates.py::test_effective_templates_use_approved_only_and_env_when_empty`; `tests/test_administration_pure.py::test_effective_templates_registered_then_approved_only_and_expiry_no_fallback`
- R33 → `tests/test_administration_pure.py::test_effective_templates_registered_then_approved_only_and_expiry_no_fallback`
- R34 → `tests/test_admin_templates.py::test_effective_templates_use_approved_only_and_env_when_empty`
- R72 → `tests/test_admin_templates.py::test_unapproved_template_is_rejected_without_gateway`
- R35 → `tests/test_admin_templates.py::test_suppression_uses_approved_template_or_skips`
- R73 → `tests/test_admin_templates.py::test_suppression_uses_approved_template_or_skips`
- R36 → `tests/test_admin_settings.py::test_settings_page_shows_effective_default_origin_and_range`
- R37 → `tests/test_admin_settings.py::test_valid_settings_are_saved_in_app_settings`
- R74 → `tests/test_admin_settings.py::test_empty_value_deletes_key_and_restores_default`
- R38 → `tests/test_admin_settings.py::test_invalid_settings_save_nothing`; `tests/test_administration_pure.py::test_validate_form_rejects_invalid_values_without_partial_save`
- R39 → `tests/test_administration_pure.py::test_valid_override_wins_and_invalid_falls_back_with_warning`
- R40 → `tests/test_admin_settings.py::test_effective_change_applies_to_client_status_without_restart`; `tests/test_admin_clients.py::test_create_without_dates_uses_configured_validity_days`
- R41 → `tests/test_administration_pure.py::test_within_business_hours_boundaries_days_offset_and_midnight`
- R42 → `tests/test_business_hours.py::test_out_of_hours_sends_configured_reply_event_and_keeps_case`; `test_out_of_hours_without_text_falls_back_to_current_ack`
- R43 → `tests/test_business_hours.py::test_within_business_hours_or_disabled_keeps_current_ack`
- R44 → `tests/test_admin_clients.py::test_client_actions_are_audited_without_password`; `tests/test_admin_texts_versions.py::test_texts_update_is_audited_without_values`; `tests/test_admin_templates.py::test_template_actions_are_audited_with_name`; `tests/test_admin_settings.py::test_settings_update_is_audited_per_key`; `tests/test_admin_metrics.py::test_metrics_view_is_audited`
- R45 → `tests/test_expiry_notices.py::test_sends_text_with_days_and_local_date`
- R46 → `tests/test_expiry_notices.py::test_candidates_follow_effective_expiry_notice_days`
- R47 (no envía) → `tests/test_expiry_notices.py::test_disabled_sends_nothing_and_writes_nothing`
- R47 (responde enabled=false) → `tests/test_expiry_notices.py::test_disabled_reports_enabled_false`
- R48 (no envía/reclama) → `tests/test_expiry_notices.py::test_out_of_hours_skips_without_claiming`
- R48 (cuenta out_of_hours) → `tests/test_expiry_notices.py::test_out_of_hours_counts_candidates`
- R49 → `tests/test_expiry_notices.py::test_no_chat_is_skipped_without_writing`
- R50 → `tests/test_expiry_notices.py::test_sends_text_with_days_and_local_date`
- R51 → `tests/test_expiry_notices.py::test_whatsapp_closed_window_sends_only_template_with_variables`
- R52 → `tests/test_expiry_notices.py::test_no_text_and_no_template_are_skipped_without_writing`
- R53 (reclamo atómico) → `tests/test_expiry_notices.py::test_success_is_sent_only_once_and_sending_orphan_is_not_retried`
- R53 (estados que no envían) → `tests/test_expiry_notices.py::test_failure_marks_failed_and_retries_until_max`
- R54 → `tests/test_expiry_notices.py::test_two_concurrent_passes_send_at_most_one_notice`
- R55 → `tests/test_expiry_notices.py::test_success_is_sent_only_once_and_sending_orphan_is_not_retried`
- R56 → `tests/test_expiry_notices.py::test_renewal_creates_a_new_period_that_can_notify_again`
- R57 → `tests/test_expiry_notices.py::test_sends_text_with_days_and_local_date`
- R58 → `tests/test_expiry_notices.py::test_failure_marks_failed_and_retries_until_max`; `test_failure_then_success_retries_once`
- R59 → `tests/test_expiry_notices.py::test_does_not_write_messages_state_or_session_activity`
- R60 → `scripts/tests/test_avisar_vencimientos.py::test_single_call_sends_token_and_path`; `test_loop_continues_after_error`; `tests/test_render_blueprint.py::test_expiry_notice_worker_uses_handover_image_and_loop`
- R61 → `scripts/tests/test_avisar_vencimientos.py::test_missing_env_returns_nonzero_without_network`; `test_invalid_interval_exits_without_network`; `test_invalid_timeout_returns_nonzero_without_network`
- R62 → `tests/test_admin_metrics.py::test_invalid_days_returns_422_without_repository`
- R63 → `tests/test_admin_metrics.py::test_first_response_average_median_and_unanswered`
- R64 → `tests/test_admin_metrics.py::test_conversations_per_advisor_use_username_or_reference`
- R65 → `tests/test_admin_metrics.py::test_escalation_reasons_and_unanswered_totals`
- R66 → `tests/test_admin_metrics.py::test_escalation_reasons_and_unanswered_totals`; `test_unanswered_samples_are_truncated_escaped_and_limit_zero_hides_texts`
- R67 → `tests/test_admin_metrics.py::test_invalid_days_returns_422_without_repository`
- R68 → `tests/test_admin_metrics.py::test_unanswered_samples_are_truncated_escaped_and_limit_zero_hides_texts`
- R69 (defaults y variables) → `tests/test_config.py::test_admin_settings_defaults_and_env_example`
- R69 (rangos fallan al arrancar) → `tests/test_config.py::test_admin_settings_reject_invalid_values`
- R70 → `tests/test_admin.py::test_navigation_links_to_new_admin_sections`
- R71 → T44, la ejecución de `./init.sh` queda para Claude; los defaults se cubren en `tests/test_config.py::test_admin_settings_defaults_and_env_example`

## Verificación (Claude, implementer puente)

- OpenCode/DeepSeek (`opencode-go/deepseek-v4.1-flash`) terminó con `done` (exit 0), en un solo intento.
- `bash ./init.sh` (una ejecución): EXIT=0 — 2951 passed, 1 skipped, 2 warnings (deprecaciones ajenas) en 158 s. Modo: nocturno.
- R71 queda cubierto: `./init.sh` verde. T44 marcada `[x]`; las 44 tasks están completas.
- Trazabilidad `R<n> -> test` presente para R1-R74 (las partes dobles de R47, R48, R53, R69 y R42 tienen cada una su test).
- `feature_list.json`: #42 sigue en `in_progress` (no se marcó done). Pendiente: revisión del reviewer.
