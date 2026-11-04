# Implementación — proveedor_whatsapp_real (#43)

Proveedor: **Meta WhatsApp Cloud API**. Solo `telegram_gateway` (y configuración,
docs y Blueprint). `.env.example` deja vacíos los secretos.

## Mapa R → test

| Requirement | Test(s) |
|---|---|
| R1 | `test_whatsapp_config.py::test_disabled_whatsapp_has_no_adapter_and_send_returns_502`, `test_disabled_default_build_has_no_whatsapp_adapter` |
| R2 | `test_whatsapp_config.py::test_disabled_whatsapp_webhook_returns_404` |
| R3 | `test_whatsapp_config.py::test_enabled_whatsapp_requires_each_secret` |
| R4 | `test_whatsapp_config.py::test_enabled_valid_settings_build_the_real_adapter` |
| R5 | `test_whatsapp_config.py::test_secrets_are_not_in_repr`, `test_whatsapp_cloud.py::test_error_log_has_codes_but_not_secrets_or_body` |
| R6 | `test_whatsapp_cloud.py::test_logs_never_include_destination_or_text`, `test_whatsapp_webhook.py::test_orchestrator_failure_returns_200_and_logs_without_text` |
| R7 | `test_whatsapp_config.py::test_env_example_declares_whatsapp_variables_with_empty_secrets` |
| R8 | `test_whatsapp_webhook.py::test_get_subscription_returns_challenge_as_plain_text` |
| R9 | `test_whatsapp_webhook.py::test_get_subscription_rejects_wrong_mode_token_or_missing_challenge` |
| R10 | `test_whatsapp_webhook.py::test_webhook_does_not_require_service_token` |
| R11 | `test_whatsapp_webhook.py::test_valid_signature_processes_and_returns_ok` |
| R12 | `test_whatsapp_webhook.py::test_invalid_signature_returns_401_and_touches_nothing` |
| R13 | `test_whatsapp_webhook.py::test_signature_is_over_raw_bytes_not_reserialized_json` |
| R14 | `test_whatsapp_webhook.py::test_valid_signature_with_invalid_json_or_foreign_object_is_ignored` |
| R15, R51 | `test_whatsapp_webhook.py::test_non_applicable_changes_are_ignored_and_applicable_one_still_processed` |
| R16 | `test_whatsapp_webhook.py::test_text_message_is_normalized_with_injected_clock` |
| R17 | `test_whatsapp_webhook.py::test_interactive_button_and_list_replies_are_normalized` |
| R18 | `test_whatsapp_webhook.py::test_template_quick_reply_button_payload_is_split` |
| R19 | `test_whatsapp_webhook.py::test_non_text_types_are_forwarded_as_unsupported` |
| R20, R27 | `test_whatsapp_webhook.py::test_reaction_is_not_forwarded_but_renews_the_window` |
| R21, R52 | `test_whatsapp_webhook.py::test_invalid_messages_are_discarded_without_dropping_later_valid_ones` |
| R22 | `test_whatsapp_webhook.py::test_multiple_messages_keep_body_order` |
| R23, R53 | `test_whatsapp_webhook.py::test_duplicate_wamid_is_forwarded_once_and_both_return_200`, `test_only_duplicates_still_returns_ok` |
| R24 | `test_whatsapp_webhook.py::test_whatsapp_wamid_equal_to_telegram_id_is_not_confused` |
| R25 | `test_whatsapp_webhook.py::test_dedup_failure_forwards_as_new` |
| R26 | `test_whatsapp_webhook.py::test_orchestrator_failure_returns_200_and_logs_without_text` |
| R27 | `test_whatsapp_webhook.py::test_reaction_is_not_forwarded_but_renews_the_window` |
| R28, R29 | `test_whatsapp_cloud.py::test_capabilities_for_opens_window_with_recent_inbound`, `test_capabilities_for_closes_at_24_hours_or_without_inbound` |
| R30 | `test_whatsapp_cloud.py::test_capabilities_without_destination_is_closed` |
| R31 | `test_whatsapp_cloud.py::test_send_response_uses_capabilities_for_when_available`, `test_whatsapp_webhook.py::test_send_text_outside_window_returns_422_without_http` |
| R32, R62 | `test_whatsapp_cloud.py::test_text_inside_window_has_exact_url_headers_and_body` |
| R33 | `test_whatsapp_cloud.py::test_text_outside_window_makes_no_request` |
| R34 | `test_whatsapp_cloud.py::test_template_inside_and_outside_window_includes_variables_in_order` |
| R35 | `test_whatsapp_cloud.py::test_template_without_variables_omits_components` |
| R36, R37, R54 | `test_whatsapp_cloud.py::test_options_with_ids_merge_previous_text_as_interactive_body` |
| R55 | `test_whatsapp_cloud.py::test_long_previous_text_uses_default_interactive_body` |
| R38 | `test_whatsapp_cloud.py::test_too_long_reply_id_fails_without_request` |
| R39 | `test_whatsapp_cloud.py::test_options_without_ids_list_and_link_are_sent_as_text` |
| R40, R56 | `test_whatsapp_cloud.py::test_multiple_blocks_are_sent_in_order_and_return_sent` |
| R41, R57, R58 | `test_whatsapp_cloud.py::test_failure_stops_following_blocks_without_retry` |
| R42 | `test_whatsapp_cloud.py::test_window_store_failure_is_treated_as_open_with_warning`, `test_window_store_failure_does_not_block_sending` |
| R43 | `test_whatsapp_cloud.py::test_window_error_code_becomes_channel_window_closed` |
| R44 | `test_whatsapp_cloud.py::test_template_error_codes_become_template_not_approved`, `test_whatsapp_webhook.py::test_send_template_error_from_meta_returns_422` |
| R45 | `test_whatsapp_cloud.py::test_other_errors_become_channel_send_failed`, `test_network_errors_become_channel_send_failed`, `test_whatsapp_webhook.py::test_send_meta_500_returns_502_upstream_error` |
| R46, R59 | `test_whatsapp_cloud.py::test_error_log_has_codes_but_not_secrets_or_body` |
| R47 | `test_whatsapp_webhook.py::test_delivery_statuses_are_logged_without_forwarding_or_dedup` |
| R48 | `test_whatsapp_cloud.py::test_delivery_status_vocabulary` |
| R49 | Toda la suite de `test_whatsapp_cloud.py` usa `httpx.MockTransport` |
| R50 | Tests existentes de Telegram sin cambios (`test_webhook.py`, `test_send.py`, `test_multicanal.py`, `test_grouping.py`) |
| R60 | `test_whatsapp_cloud.py::test_send_response_falls_back_to_capabilities_for_telegram_and_fake` y tests de `FakeWhatsAppAdapter` |
| R61 | `test_whatsapp_cloud.py::test_send_response_falls_back_to_capabilities_for_telegram_and_fake` |

## Resumen

- `whatsapp_cloud.py`: firma HMAC sobre bytes crudos, verificación GET,
  normalización del webhook, separación id/prueba, cuerpos de envío y traducción
  de errores/estados.
- `adapters/whatsapp_cloud.py`: adaptador real con `httpx.Client` inyectado,
  ventana de 24 h por wa_id, envío secuencial sin reintentos y errores del
  gateway.
- `adapters/whatsapp_window.py`: almacén Redis y falso.
- `config.py`, `domain.py`, `main.py`: variables `WHATSAPP_*`, `WebhookForbidden`,
  `capabilities_for`, rutas `GET/POST /whatsapp/webhook` fuera de
  `X-Service-Token`.
- `.env.example`, `docker-compose.yml`, `render.yaml`, tests del Blueprint y docs
  actualizados. No se tocó `contracts/`, `orchestrator`, `handover`, `rag` ni
  `eval`.

`./init.sh` queda pendiente de ejecución por Claude al cerrar la sesión.

## Verificación (implementer Claude, 2026-11-04)

- La ejecución de OpenCode se detuvo por el límite de tiempo de la sesión en background
  (600 s) mientras releía `main.py`, después de marcar T1–T22 `[x]` y escribir este informe.
  No hubo error del escritor.
- `bash ./init.sh`: EXIT=0 — 3031 passed, 1 skipped, 2 warnings (255 s). Entorno listo.
- Trazabilidad: R1–R62 aparecen todos en este informe (comprobado de forma mecánica).
- `feature_list.json` sigue en `in_progress`; no se marcó `done`.
