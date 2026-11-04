# Review — feature #43 proveedor_whatsapp_real

**Veredicto:** APPROVED

`./init.sh` ejecutado por el reviewer (2026-11-04): EXIT=0, 3031 passed, 1 skipped,
2 warnings. Una sola feature `in_progress` (#43).

## Trazabilidad requirements ↔ tests
(archivos en `services/telegram_gateway/tests/`; `cfg` = test_whatsapp_config.py,
`wh` = test_whatsapp_webhook.py, `cl` = test_whatsapp_cloud.py)
- R1: [x] cfg `test_disabled_whatsapp_has_no_adapter_and_send_returns_502`, `test_disabled_default_build_has_no_whatsapp_adapter`
- R2: [x] cfg `test_disabled_whatsapp_webhook_returns_404`
- R3: [x] cfg `test_enabled_whatsapp_requires_each_secret` (comprueba que no aparecen valores)
- R4: [x] cfg `test_enabled_valid_settings_build_the_real_adapter`
- R5: [x] cfg `test_secrets_are_not_in_repr`; cl `test_error_log_has_codes_but_not_secrets_or_body`
- R6: [x] cl `test_logs_never_include_destination_or_text`; wh `test_orchestrator_failure_returns_200_and_logs_without_text`
- R7: [x] cfg `test_env_example_declares_whatsapp_variables_with_empty_secrets`
- R8: [x] wh `test_get_subscription_returns_challenge_as_plain_text`
- R9: [x] wh `test_get_subscription_rejects_wrong_mode_token_or_missing_challenge`
- R10: [x] wh `test_webhook_does_not_require_service_token`
- R11: [x] wh `test_valid_signature_processes_and_returns_ok`
- R12: [x] wh `test_invalid_signature_returns_401_and_touches_nothing`
- R13: [x] wh `test_signature_is_over_raw_bytes_not_reserialized_json`
- R14: [x] wh `test_valid_signature_with_invalid_json_or_foreign_object_is_ignored`
- R15, R51: [x] wh `test_non_applicable_changes_are_ignored_and_applicable_one_still_processed`
- R16: [x] wh `test_text_message_is_normalized_with_injected_clock`
- R17: [x] wh `test_interactive_button_and_list_replies_are_normalized`
- R18: [x] wh `test_template_quick_reply_button_payload_is_split`
- R19: [x] wh `test_non_text_types_are_forwarded_as_unsupported`
- R20, R27: [x] wh `test_reaction_is_not_forwarded_but_renews_the_window`
- R21, R52: [x] wh `test_invalid_messages_are_discarded_without_dropping_later_valid_ones`
- R22: [x] wh `test_multiple_messages_keep_body_order`
- R23, R53: [x] wh `test_duplicate_wamid_is_forwarded_once_and_both_return_200`, `test_only_duplicates_still_returns_ok`
- R24: [x] wh `test_whatsapp_wamid_equal_to_telegram_id_is_not_confused`
- R25: [x] wh `test_dedup_failure_forwards_as_new`
- R26: [x] wh `test_orchestrator_failure_returns_200_and_logs_without_text`
- R28, R29: [x] cl `test_capabilities_for_opens_window_with_recent_inbound`, `test_capabilities_for_closes_at_24_hours_or_without_inbound`
- R30: [x] cl `test_capabilities_without_destination_is_closed`
- R31: [x] cl `test_send_response_uses_capabilities_for_when_available`; wh `test_send_text_outside_window_returns_422_without_http`
- R32, R62: [x] cl `test_text_inside_window_has_exact_url_headers_and_body`
- R33: [x] cl `test_text_outside_window_makes_no_request`
- R34: [x] cl `test_template_inside_and_outside_window_includes_variables_in_order`; wh `test_send_template_outside_window_succeeds`
- R35: [x] cl `test_template_without_variables_omits_components`
- R36, R37, R54: [x] cl `test_options_with_ids_merge_previous_text_as_interactive_body`
- R38: [x] cl `test_too_long_reply_id_fails_without_request`
- R39: [x] cl `test_options_without_ids_list_and_link_are_sent_as_text`
- R40, R56: [x] cl `test_multiple_blocks_are_sent_in_order_and_return_sent`
- R41, R57, R58: [x] cl `test_failure_stops_following_blocks_without_retry`
- R42: [x] cl `test_window_store_failure_is_treated_as_open_with_warning`, `test_window_store_failure_does_not_block_sending`
- R43: [x] cl `test_window_error_code_becomes_channel_window_closed`
- R44: [x] cl `test_template_error_codes_become_template_not_approved`; wh `test_send_template_error_from_meta_returns_422`
- R45: [x] cl `test_other_errors_become_channel_send_failed`, `test_network_errors_become_channel_send_failed`; wh `test_send_meta_500_returns_502_upstream_error`
- R46, R59: [x] cl `test_error_log_has_codes_but_not_secrets_or_body`
- R47: [x] wh `test_delivery_statuses_are_logged_without_forwarding_or_dedup`
- R48: [x] cl `test_delivery_status_vocabulary`
- R49: [x] `httpx.MockTransport` en `make_adapter` (cl:50, wh:78); ninguna prueba abre red
- R50: [x] `test_webhook.py`/`test_send.py`/`test_grouping.py` no modificados por #43 (mtime anterior al 2026-11-04) y verdes
- R60, R61: [x] cl `test_send_response_falls_back_to_capabilities_for_telegram_and_fake` + `test_multicanal.py` verde

## Tasks completas
- T1–T22: [x] (todas en `[x]` en `specs/proveedor_whatsapp_real/tasks.md`)

## Checkpoints
- C1: [x] arnés completo; `./init.sh` exit 0
- C2: [x] una sola feature `in_progress` (#43)
- C3: [x] solo cambia `telegram_gateway` (+ config/docs); sin imports entre servicios; sin dependencias nuevas (httpx y redis ya estaban en `requirements.txt`); secretos en `.env.example` vacíos, `render.yaml` con `sync: false`; sin `print`/`eval`
- C4: [x] tests con fakes (`FakeDedupStore`, `FakeWhatsAppWindowStore`, `MockTransport`)
- C5: [x] estado coherente (cierre de sesión a cargo del leader)
- C6: [x] spec completo, R1–R62 cubiertos, tasks en `[x]`

## Observaciones no bloqueantes
1. R55: `test_long_previous_text_uses_default_interactive_body` (test_whatsapp_cloud.py:241) solo ejercita el caso «> 1024»; T18 mencionaba también «no es texto» y «no existe». El código (`whatsapp_cloud.py:342-349`) los cubre por la misma rama; se sugiere ampliar el test en una iteración futura.
2. `main.py:354-361` registra `str(OrchestratorError)`; hoy esos mensajes no contienen texto de usuario (`adapters/orchestrator.py:38-54`), pero conviene mantener esa garantía si se cambian.
