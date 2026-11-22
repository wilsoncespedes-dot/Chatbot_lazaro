# Implementación — #63 `canal_simulado`

## Resumen

- Adaptador `SimuladoChannel` registrado como tipo `simulado` (sin red, escribe
  en un buzón propio).
- Buzón con repositorio PostgreSQL (`buzon_simulado`) y falso en memoria; retención
  y tope configurables (`SIMULATED_MAILBOX_RETENTION_SECONDS`,
  `SIMULATED_MAILBOX_MAX_ENTRIES`).
- `WebhookService` extrae `_deliver`/`inject` y usa hooks opcionales
  `registrar_entrada`/`registrar_rechazo`; el canal genérico conserva el
  comportamiento de #62.
- Rutas internas `GET /channels/{id}/mailbox` y `POST /channels/{id}/simulate`.
- Orquestador: `SimulatorClient` (HTTP y falso), página `/admin/simulador` y
  `/asesor/simulador` (admin y supervisor) con SIMULADO visible y escape HTML.
- Herramienta `scripts/simular_canal.py` con firma HMAC y secreto solo por
  entorno.
- `ATTENDED_CHANNELS` y `POST /messages` no cambian.

## Trazabilidad

- R1 → `contracts/tests/test_canal_simulado_contrato.py::test_simulator_models_are_exported`, `::test_simulator_models_forbid_extra_fields`, `::test_mailbox_entry_rejects_values_outside_limits`, `::test_simulated_request_rejects_invalid_external_ids`, `::test_simulated_request_rejects_invalid_text`, `::test_simulated_response_rejects_invalid_status_or_reason`, `::test_simulated_request_accepts_valid_external_ids`
- R2 → `contracts/tests/test_canal_simulado_contrato.py::test_contract_documents_routes_examples_errors_settings_and_rejection`, `::test_documented_json_examples_validate_against_the_models`
- R3 → `services/telegram_gateway/tests/test_canal_simulado.py::test_post_channels_accepts_simulado_and_lists_it`; `tests/test_registro_canales.py::test_default_registry_contains_environment_and_generic_adapters`
- R4 → `services/telegram_gateway/tests/test_canal_simulado.py::test_simulated_channel_implements_port_name_and_docstring`
- R5 → `services/telegram_gateway/tests/test_canal_simulado.py::test_capabilities_use_defaults_and_custom_values_per_channel`
- R6 → `services/telegram_gateway/tests/test_canal_simulado.py::test_validate_config_accepts_empty_and_rejects_extra_keys_or_bad_values`, `::test_invalid_simulated_config_is_rejected_without_persisting`
- R7 → `services/telegram_gateway/tests/test_canal_simulado.py::test_send_degrades_image_into_text_in_the_mailbox`
- R8 → `services/telegram_gateway/tests/test_canal_simulado.py::test_recibir_mensaje_and_identificar_usuario_accept_only_inbound`
- R9 → `services/telegram_gateway/tests/test_canal_simulado.py::test_send_writes_reply_chunks_in_order_without_network`
- R10 → `services/telegram_gateway/tests/test_canal_simulado.py::test_mailbox_failure_returns_failed_and_logs_only_exception_type`, `::test_send_with_failed_mailbox_returns_502`
- R11 → `services/telegram_gateway/tests/test_canal_simulado.py::test_build_without_mailbox_is_channel_not_configured`
- R12 → `services/telegram_gateway/tests/test_buzon_simulado.py::test_fake_mailbox_orders_filters_and_isolates_channels`, `::test_fake_and_postgres_mailbox_behave_the_same`
- R13 → `services/telegram_gateway/tests/test_buzon_simulado.py::test_fake_mailbox_retention_uses_the_controlled_clock`
- R14 → `services/telegram_gateway/tests/test_buzon_simulado.py::test_fake_mailbox_keeps_at_most_max_entries_per_channel`
- R15 → `services/telegram_gateway/tests/test_buzon_simulado.py::test_postgres_mailbox_creates_schema_reconnects_and_parameterizes_sql`
- R16 → `services/telegram_gateway/tests/test_buzon_simulado.py::test_default_composition_uses_postgres_and_tests_fall_back_to_fake`
- R17 → `services/telegram_gateway/tests/test_buzon_simulado.py::test_postgres_mailbox_creates_schema_reconnects_and_parameterizes_sql`
- R18 → `services/telegram_gateway/tests/test_buzon_simulado.py::test_settings_reject_mailbox_values_outside_their_range`
- R19 → `services/telegram_gateway/tests/test_canal_simulado_rutas.py::test_internal_routes_require_service_token`, `::test_missing_or_non_mailbox_channel_is_the_same_404`, `::test_inactive_simulated_channel_can_be_read_but_not_simulated`, `::test_mailbox_limit_and_after_are_validated`
- R20 → `services/telegram_gateway/tests/test_canal_simulado_rutas.py::test_simulate_returns_forwarded_true_when_orchestrator_accepts`, `::test_inactive_simulated_channel_can_be_read_but_not_simulated`, `::test_simulate_rejects_invalid_body_with_422`, `::test_internal_routes_require_service_token`
- R21 → `services/telegram_gateway/tests/test_canal_simulado_rutas.py::test_signed_webhook_records_client_and_rejection_when_orchestrator_fails`, `::test_channel_without_hooks_keeps_behavior_from_62`, `::test_core_files_do_not_compare_with_channel_names`
- R22 → `services/telegram_gateway/tests/test_canal_simulado_rutas.py::test_signed_webhook_records_client_and_rejection_when_orchestrator_fails`
- R23 → `services/telegram_gateway/tests/test_canal_simulado_rutas.py::test_signed_webhook_records_client_and_rejection_when_orchestrator_fails`, `::test_simulate_returns_forwarded_false_with_reason_when_orchestrator_fails`
- R24 → `services/telegram_gateway/tests/test_canal_simulado_rutas.py::test_simulate_returns_forwarded_true_when_orchestrator_accepts`
- R25 → `services/telegram_gateway/tests/test_canal_simulado_rutas.py::test_duplicate_signed_message_adds_no_mailbox_entries`
- R26 → `services/telegram_gateway/tests/test_canal_simulado_rutas.py::test_mailbox_hook_failure_does_not_change_delivery`
- R27 → `services/telegram_gateway/tests/test_canal_simulado_rutas.py::test_two_simulated_channels_work_end_to_end_without_new_code`
- R28 → `services/orchestrator/tests/test_simulator_page.py::test_admin_and_supervisor_can_open_the_simulated_page`, `::test_non_allowed_roles_are_rejected_without_calling_the_gateway`, `::test_anonymous_redirects_to_the_panel_login_without_calling_the_gateway`
- R29 → `services/orchestrator/tests/test_simulator_page.py::test_page_shows_simulado_title_heading_and_label_even_if_name_lacks_it`, `::test_page_without_simulated_channels_shows_notice_without_form`, `::test_non_simulated_channels_are_not_listed`
- R30 → `services/orchestrator/tests/test_simulator_page.py::test_valid_post_calls_simulate_and_redirects_with_channel_and_user`, `::test_supervisor_post_also_calls_simulate_and_redirects`
- R31 → `services/orchestrator/tests/test_simulator_page.py::test_post_with_invalid_csrf_is_forbidden_and_calls_nothing`, `::test_invalid_external_id_or_text_is_422_without_calling_the_gateway`, `::test_channel_outside_the_simulated_list_is_422_without_simulate`, `::test_non_allowed_roles_are_rejected_without_calling_the_gateway`
- R32 → `services/orchestrator/tests/test_simulator_page.py::test_conversation_shows_client_reply_and_rejection_in_order`, `::test_conversation_escapes_every_message`
- R33 → `services/orchestrator/tests/test_simulator_page.py::test_conversation_shows_client_reply_and_rejection_in_order`
- R34 → `services/orchestrator/tests/test_simulator_page.py::test_gateway_failure_shows_503_without_token_or_traceback`, `::test_gateway_failure_on_post_is_503`; `services/orchestrator/tests/test_simulator_client.py::test_non_2xx_is_simulator_unavailable`, `::test_network_error_and_invalid_json_are_simulator_unavailable`
- R35 → `services/orchestrator/tests/test_simulator_client.py::test_list_channels_sends_token_filters_and_uses_only_get_channels`, `::test_simulate_posts_only_the_simulate_route`, `::test_mailbox_uses_only_the_mailbox_route_with_destination_and_after`, `::test_fake_simulator_filters_calls_and_can_fail`; `services/orchestrator/tests/test_simulator_page.py::test_admin_and_supervisor_can_open_the_simulated_page`
- R36 → `scripts/tests/test_simular_canal.py::test_build_body_is_a_normalized_inbound_message`, `::test_signature_is_verified_by_the_gateway`, `::test_send_signs_exactly_the_bytes_it_sends`, `::test_main_exit_code_depends_on_http_status`
- R37 → `scripts/tests/test_simular_canal.py::test_main_reads_secret_from_environment_and_never_prints_it`, `::test_main_accepts_an_alternate_secret_variable`, `::test_missing_secret_exits_two_without_printing_a_value`, `::test_secret_is_not_accepted_as_a_command_line_argument`
- R38 → `scripts/tests/test_simular_canal.py::test_signature_matches_the_signed_example_of_the_contract`, `::test_send_signs_exactly_the_bytes_it_sends`, `::test_network_error_exits_two_without_traceback`, `::test_same_message_id_produces_the_same_body`, `::test_default_message_id_is_prefixed_sim`
- R39 → `services/telegram_gateway/tests/test_buzon_simulado.py::test_env_example_declares_mailbox_settings_with_test_only_note`
- R40 → `services/telegram_gateway/tests/test_canal_simulado.py::test_simulated_channel_implements_port_name_and_docstring`; `services/orchestrator/tests/test_simulator_page.py::test_page_shows_simulado_title_heading_and_label_even_if_name_lacks_it`; `scripts/tests/test_simular_canal.py::test_help_and_docstring_contain_simulado`
- R41 → baterías existentes de `services/telegram_gateway/tests`, `services/orchestrator/tests`, `contracts/tests` y `scripts/tests` (ver sustituciones en la sección siguiente)
- R42 → `services/orchestrator/tests/test_simulator_guard.py::test_attended_channels_is_still_the_temporary_guard`, `::test_simulated_channel_message_still_gets_422_from_the_orchestrator`

## Tests existentes sustituidos (design.md §7)

- `services/telegram_gateway/tests/test_canales_rutas.py`: el tipo de prueba
  `simulado` pasa a `tipo_prueba`; la lista esperada de `adapter_types` pasa a
  `["webhook_generico", "simulado", "tipo_prueba"]`.
- `services/telegram_gateway/tests/test_canales_secretos.py`: el tipo de prueba
  `simulado` pasa a `tipo_prueba` en la factory y en las peticiones.
- `services/telegram_gateway/tests/test_registro_canales.py`: el registry por
  defecto añade `simulado`; `creatable_types()` pasa a
  `("webhook_generico", "simulado")`.
- `services/orchestrator/tests/test_config.py`: la superficie de rutas añade
  `/admin/simulador` y `/asesor/simulador`.
- `test_canales_repositorio.py`, `test_webhook_canal.py` y los contratos usan
  `simulado` solo como dato y no requirieron cambios.

## Correcciones de la revisión

- **Intento 1 (`init.sh`):** la recolección de `services/orchestrator/tests`
  fallaba con `FastAPIError: Invalid args for response field`. En
  `services/orchestrator/orchestrator/simulator_routes.py`, `admin_send` y
  `advisor_send` anotaban el retorno como `HTMLResponse | RedirectResponse`.
  Se cambió la anotación a `Response` (importado de `fastapi.responses`) en
  ambas rutas; FastAPI lo trata como respuesta sin `response_model` y no se
  alteró ningún comportamiento ni el estado HTTP/redirección. El resto de
  rutas conserva su anotación.

## Verificación

Pendiente de que el leader ejecute `./init.sh` al cerrar esta sesión (el writer
no ejecuta shell). Los comandos por servicio indicados en `tasks.md` se
ejecutarán en esa pasada. Las tasks T1–T9 quedaron completadas; la corrección
de arriba es el único cambio posterior al primer intento de verificación.

### Resultado de init.sh (tras la corrección)

`./init.sh` en verde: 4103 passed, 1 skipped, 2 warnings (sin fallos). La
corrección de OpenCode anotó `admin_send` y `advisor_send` como `-> Response`
en `services/orchestrator/orchestrator/simulator_routes.py`. La trazabilidad
R1..R42 → test de la sección Trazabilidad sigue vigente.
