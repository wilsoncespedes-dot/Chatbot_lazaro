# Implementación #24 — despliegue_produccion

## Resumen

Blueprint de Render y verificaciones de producción. Todo es preparación: no se
crean recursos ni se despliega nada. El Blueprint omite `plan` (R7) y los
secretos quedan con `sync: false` o `generateValue` (R8, R9).

### Corrección de la revisión enfocada

`production_problems()` recibía `Settings.model_dump()` con nombres snake_case
pero buscaba claves UPPERCASE, por lo que rechazaba configuraciones válidas.
Ahora resuelve cada nombre por su clave de entorno (`SERVICE_TOKEN`) o por su
campo de Settings (`service_token`), y los problemas se informan siempre con el
nombre UPPERCASE. Añadidas regresiones en
`contracts/tests/test_production.py::test_production_problems_accepts_settings_field_names`
y `...::test_production_problems_reports_uppercase_names_for_snake_case_values`.

`--drop-pending` del script del webhook sigue siendo opt-in; no se habilita
automáticamente.

La verificación final con `./init.sh` la ejecuta Claude tras esta sesión.

## Trazabilidad

- R1 → `scripts/tests/test_render_blueprint.py::test_r1_exactly_the_two_public_web_services`
- R2 → `scripts/tests/test_render_blueprint.py::test_r2_private_services_are_only_rag_and_handover`
- R3 → `scripts/tests/test_render_blueprint.py::test_r3_worker_uses_handover_image_and_loop_command`
- R4 → `scripts/tests/test_render_blueprint.py::test_r4_postgres_16_only_private_network`
- R5 → `scripts/tests/test_render_blueprint.py::test_r5_keyvalue_service_is_private`
- R6 → `scripts/tests/test_render_blueprint.py::test_r6_every_resource_uses_the_same_region`
- R7 → `scripts/tests/test_render_blueprint.py::test_r7_no_plan_field_anywhere`
- R8 → `scripts/tests/test_render_blueprint.py::test_r8_secrets_have_no_literal_values`
- R9 → `scripts/tests/test_render_blueprint.py::test_r9_shared_env_group_provides_generated_service_token`
- R10 → `scripts/tests/test_render_blueprint.py::test_r10_database_and_redis_use_resource_references`
- R11 → `scripts/tests/test_render_blueprint.py::test_r11_internal_urls_use_hostport_references`
- R12 → `contracts/tests/test_production.py::test_normalize_service_url`, `services/orchestrator/tests/test_production_config.py::test_valid_production_settings_normalize_internal_urls`, `services/telegram_gateway/tests/test_production_config.py::test_valid_production_settings_normalize_orchestrator_url`, `services/handover/tests/test_production_config.py::test_valid_production_settings_normalize_gateway_url`, `services/handover/tests/test_vencer_casos.py::test_handover_url_host_port_is_normalized_to_http`
- R13 → `contracts/tests/test_production.py::test_parse_app_env_rejects_other_values`, `services/*/tests/test_production_config.py::test_invalid_app_env_is_rejected`
- R14 → `contracts/tests/test_production.py::test_production_problems_accepts_valid_values`, `...::test_production_problems_accepts_settings_field_names`, `...::test_production_problems_reports_empty_values`, `services/*/tests/test_production_config.py::test_missing_required_variable_is_rejected`, `services/rag/tests/test_production_config.py::test_valid_production_settings_are_accepted`
- R15 → `contracts/tests/test_production.py::test_production_problems_rejects_placeholders_case_insensitive`, `services/*/tests/test_production_config.py::test_placeholder_is_rejected_case_insensitive`
- R16 → `contracts/tests/test_production.py::test_production_problems_rejects_short_service_token`, `services/*/tests/test_production_config.py::test_short_service_token_is_rejected`, `services/handover/tests/test_vencer_casos.py::test_short_service_token_is_rejected_in_production`, `...::test_long_service_token_is_accepted_in_production`
- R17 → `contracts/tests/test_production.py::test_production_problems_rejects_development_database_credentials`, `services/orchestrator/tests/test_production_config.py::test_development_database_credentials_are_rejected`, `services/rag/tests/test_production_config.py::test_development_database_credentials_are_rejected`, `services/handover/tests/test_production_config.py::test_development_database_credentials_are_rejected`
- R18 → `contracts/tests/test_production.py::test_is_valid_webhook_secret`, `services/telegram_gateway/tests/test_production_config.py::test_invalid_webhook_secret_is_rejected`, `...::test_webhook_secret_with_invalid_characters_is_rejected`
- R19 → `services/orchestrator/tests/test_production_config.py::test_insecure_admin_cookie_is_rejected`
- R20 → `contracts/tests/test_production.py::test_production_problems_names_only_variables`, `...::test_production_config_error_message_names_variables_without_values`, `...::test_production_problems_reports_uppercase_names_for_snake_case_values`, `services/*/tests/test_production_config.py::test_error_message_does_not_include_values`
- R21 → `scripts/tests/test_ci_workflow.py::test_r21_ci_runs_pytest_on_push_and_pull_request`
- R22 → `scripts/tests/test_ci_workflow.py::test_r22_ci_builds_every_service_image_without_publishing`
- R23 → `scripts/tests/test_configurar_webhook.py::test_r23_set_webhook_uses_public_url_and_secret`
- R24 → `scripts/tests/test_configurar_webhook.py::test_r24_non_https_public_url_exits_nonzero_without_calls`
- R25 → `scripts/tests/test_configurar_webhook.py::test_r25_invalid_secret_exits_nonzero_without_calls`, `...::test_r25_missing_variable_exits_nonzero_without_calls`
- R26 → `scripts/tests/test_configurar_webhook.py::test_r26_prints_webhook_info`
- R27 → `scripts/tests/test_configurar_webhook.py::test_r27_success_never_prints_token_or_secret`, `...::test_r27_http_error_never_prints_token_or_secret`, `...::test_r27_network_error_never_prints_token_or_secret`
- R28 → `scripts/tests/test_render_blueprint.py::test_r28_deployment_procedure_documents_every_step`
- R29 → `services/orchestrator/tests/test_public_exposure.py::test_r29_internal_routes_require_valid_service_token`, `...::test_r29_health_stays_public`
- R30 → `services/rag/tests/test_security.py::test_all_non_health_routes_require_service_token`, `services/handover/tests/test_security.py::test_all_non_health_routes_require_service_token`
- R31 → `services/orchestrator/tests/test_public_exposure.py::test_r31_admin_requires_session_even_with_service_token`, `...::test_r31_admin_post_requires_valid_csrf`, `...::test_r31_admin_login_is_not_opened_by_service_token`, `...::test_r31_admin_route_blocks_before_internal_token_check`
- R32 → `scripts/tests/test_render_blueprint.py::test_r32_orchestrator_trusts_proxy_headers_and_shared_group_does_not`, `services/orchestrator/tests/test_public_exposure.py::test_r32_uses_first_forwarded_value_never_the_proxy_terminal`, `...::test_r32_first_forwarded_value_is_stripped`, `...::test_r32_falls_back_to_connection_ip`, `...::test_r32_same_proxy_terminal_from_different_clients_does_not_block`

## Tasks

T1–T16 completadas en la implementación inicial; la corrección de la revisión
afecta a T1 (utilidad pura) y a la regresión de las cuatro configuraciones
válidas de T2–T4.

Corregidos los 19 fallos de `./init.sh` en los tests parametrizados de variables
faltantes: los cuatro `services/*/tests/test_production_config.py` construían
`Settings` con la clave uppercase (`SERVICE_TOKEN`), que `extra="ignore"`
descartaba; ahora mapean el nombre a su campo snake_case con `name.lower()` y
conservan la aserción sobre el nombre UPPERCASE del mensaje de error (R14).
La verificación final con `./init.sh` la ejecuta Claude tras esta sesión.
