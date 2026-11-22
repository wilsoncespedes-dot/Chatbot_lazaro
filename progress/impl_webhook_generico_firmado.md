# Implementación — #62 `webhook_generico_firmado`

Resumen: se añadió el adaptador `webhook_generico`, la ruta pública
`POST /webhooks/{canal_id}` con HMAC-SHA256 y ventana anti-repetición, el
callback saliente firmado con bloqueo anti-SSRF, la configuración asociada y la
documentación del contrato. `./init.sh` lo ejecuta Claude al cerrar la sesión.

## Trazabilidad R → test

- R1 → `contracts/tests/test_webhook_generico_doc.py::test_generic_section_documents_contract`
- R2 → `contracts/tests/test_webhook_generico_doc.py::test_both_signed_examples_are_verifiable_with_the_documented_secret`
- R3 → `services/telegram_gateway/tests/test_webhook_firma.py::test_sign_payload_reproduces_both_documented_signatures`, `…::test_sign_payload_returns_lowercase_sha256_hex`
- R4 → `…/test_webhook_firma.py::test_valid_signature_within_window_is_accepted`, `…::test_missing_header_or_bad_format_is_rejected_without_raising`, `…::test_wrong_secret_or_body_is_rejected`, `…::test_timestamp_exactly_on_window_boundary_is_accepted`, `…::test_verify_signature_uses_constant_time_comparison`
- R5 → `…/test_webhook_firma.py::test_timestamp_outside_window_is_rejected_even_with_valid_signature`, `…::test_timestamp_exactly_on_window_boundary_is_accepted`
- R6 → `…/test_webhook_ruta.py::test_generic_webhook_is_public_but_other_routes_still_require_token`
- R7 → `…/test_webhook_ruta.py::test_missing_inactive_unregistered_or_secretless_channel_is_404`
- R8 → `…/test_webhook_ruta.py::test_missing_inactive_unregistered_or_secretless_channel_is_404`
- R9 → `…/test_webhook_ruta.py::test_missing_inactive_unregistered_or_secretless_channel_is_404`
- R10 → `…/test_webhook_ruta.py::test_missing_or_wrong_signature_is_401`
- R11 → `…/test_webhook_ruta.py::test_missing_or_wrong_signature_is_401`, `…/test_webhook_firma.py::test_wrong_secret_or_body_is_rejected`
- R12 → `…/test_webhook_ruta.py::test_bad_or_expired_timestamp_is_401`
- R13 → `…/test_webhook_ruta.py::test_new_message_is_delivered_once_and_duplicate_is_not_repeated`
- R14 → `…/test_webhook_ruta.py::test_error_precedence_is_404_then_413_then_401_then_422`
- R15 → `…/test_webhook_ruta.py::test_413_when_body_exceeds_configured_limit`, `…::test_error_precedence_is_404_then_413_then_401_then_422`
- R16 → `…/test_webhook_ruta.py::test_body_must_be_a_utf8_json_object`
- R17 → `…/test_webhook_ruta.py::test_adapter_specific_payload_is_translated_before_delivery`
- R18 → `…/test_webhook_ruta.py::test_adapter_returning_none_is_422`
- R19 → `…/test_webhook_canal.py::test_recibir_mensaje_accepts_only_normalized_inbound_messages`
- R20 → `…/test_webhook_ruta.py::test_adapter_specific_payload_is_translated_before_delivery`
- R21 → `…/test_webhook_ruta.py::test_channel_mismatch_and_outbound_direction_are_422`
- R22 → `…/test_webhook_ruta.py::test_channel_mismatch_and_outbound_direction_are_422`, `…::test_adapter_returning_outbound_message_is_422`
- R23 → `…/test_webhook_ruta.py::test_new_message_is_delivered_once_and_duplicate_is_not_repeated`
- R24 → `…/test_webhook_ruta.py::test_new_message_is_delivered_once_and_duplicate_is_not_repeated`
- R25 → `…/test_webhook_ruta.py::test_same_external_id_on_two_channels_is_accepted_on_each`
- R26 → `…/test_webhook_ruta.py::test_redis_failure_treats_message_as_new_and_logs_error`
- R27 → `…/test_webhook_ruta.py::test_orchestrator_failure_is_logged_once_and_still_accepted`, `…::test_orchestrator_rejection_is_logged_with_reason`
- R28 → `…/test_webhook_ruta.py::test_new_message_is_delivered_once_and_duplicate_is_not_repeated`, `…::test_orchestrator_failure_is_logged_once_and_still_accepted`
- R29 → `…/test_webhook_ruta.py::test_channel_store_failure_is_503`, `…::test_undecryptable_channel_secrets_is_503`
- R30 → `…/test_webhook_ruta.py::test_secret_signature_and_body_never_appear_in_logs_or_errors`, `…/test_webhook_canal.py::test_channel_secret_and_credentials_never_appear_in_logs`
- R31 → `…/test_webhook_canal.py::test_generic_channel_implements_canal_port`, `…::test_generic_adapter_type_is_creatable_and_listed`, `tests/test_registro_canales.py::test_default_registry_contains_environment_and_generic_adapters`
- R32 → `…/test_webhook_canal.py::test_generic_channel_capabilities_deliver_only_text`
- R33 → `…/test_webhook_canal.py::test_build_without_secret_raises_channel_not_configured`
- R34 → `…/test_webhook_canal.py::test_invalid_callback_url_is_rejected_without_persisting`, `…::test_channel_without_callback_url_is_valid`, `…::test_patch_with_invalid_callback_url_is_rejected_without_changes`
- R35 → `…/test_webhook_canal.py::test_callback_sends_signed_outbound_normalized_message`
- R36 → `…/test_webhook_canal.py::test_callback_sends_signed_outbound_normalized_message`
- R37 → `…/test_webhook_canal.py::test_callback_2xx_is_sent`
- R38 → `…/test_webhook_canal.py::test_callback_non_2xx_is_failed`, `…::test_send_with_failed_callback_returns_502`, `tests/test_webhook_ssrf.py::test_http_callback_client_does_not_follow_redirects`
- R39 → `…/test_webhook_canal.py::test_callback_network_error_is_failed_and_logs_only_type`, `…::test_send_with_failed_callback_returns_502`, `tests/test_webhook_ssrf.py::test_http_callback_client_wraps_network_errors`
- R40 → `…/test_webhook_canal.py::test_long_text_is_split_in_order_within_the_limit`, `…::test_long_text_stops_at_first_failed_callback`
- R41 → `tests/test_webhook_ssrf.py::test_validate_callback_url_rejects_invalid_syntax`, `…::test_public_host_resolves_and_is_accepted`
- R42 → `…/test_webhook_ssrf.py::test_blocked_address_classes_are_rejected`
- R43 → `…/test_webhook_ssrf.py::test_all_resolved_addresses_must_be_public`
- R44 → `…/test_webhook_ssrf.py::test_public_literal_is_accepted_without_calling_resolver`, `…::test_host_without_resolution_is_rejected`
- R45 → `…/test_webhook_ssrf.py::test_http_callback_client_connects_to_validated_ip_with_original_host`
- R46 → `…/test_webhook_ssrf.py::test_http_callback_client_rejects_blocked_url_before_requesting`, `…/test_webhook_canal.py::test_blocked_callback_makes_no_request_and_logs_without_url`, `…::test_send_with_blocked_callback_returns_502`
- R47 → `…/test_webhook_canal.py::test_channel_without_callback_url_cannot_reply`
- R48 → `tests/test_webhook_config.py::test_webhook_settings_default_values`, `…::test_development_allows_private_callbacks`, `tests/test_webhook_ssrf.py::test_development_mode_allows_http_and_private_addresses`
- R49 → `tests/test_webhook_config.py::test_production_rejects_private_callbacks`
- R50 → `tests/test_webhook_config.py::test_webhook_settings_default_values`, `…::test_signature_window_out_of_range_is_rejected`, `…::test_max_body_bytes_out_of_range_is_rejected`, `…::test_boundary_values_are_accepted`
- R51 → `tests/test_webhook_config.py::test_env_example_declares_webhook_settings_with_ssrf_warning`
- R52 → batería existente de `services/telegram_gateway/tests` y `contracts/tests`; sustituciones anotadas abajo

## Tests sustituidos (design.md §6)

- `services/telegram_gateway/tests/test_registro_canales.py`:
  `test_default_registry_contains_only_environment_managed_adapters` →
  `test_default_registry_contains_environment_and_generic_adapters` (espera
  `webhook_generico` y `creatable_types() == ("webhook_generico",)`).
- `services/telegram_gateway/tests/test_canales_rutas.py`: la afirmación
  `adapter_types == ["simulado"]` pasa a `["webhook_generico", "simulado"]`.
- `services/telegram_gateway/tests/test_canales_rutas.py`: la prueba de código
  fuente de #61 (R10) incluye ahora `webhook_service.py` (T9).
- `contracts/tests/test_canal_abierto_doc.py` no necesitó cambios: no exigía la
  frase retirada «hasta entonces no existen».

## Notas

- `./init.sh` queda a cargo de Claude al cerrar la sesión; no se ejecutó aquí
  (el implementer no usa shell).
