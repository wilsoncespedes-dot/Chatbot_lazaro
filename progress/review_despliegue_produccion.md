# Review — feature #24 despliegue_produccion

**Veredicto:** APPROVED

`./init.sh` en verde con 1561 tests (ejecución reciente del leader; no se repitió).
La corrección de `production_problems` (`contracts/lazaro_contracts/production.py:60-66`,
`_value_for` admite UPPERCASE y snake_case y siempre informa en UPPERCASE) y los
cuatro `test_missing_required_variable_is_rejected` (con `name.lower()`) están incluidos.

## Trazabilidad requirements ↔ tests
Todos los tests citados en `progress/impl_despliegue_produccion.md` existen (comprobado con grep).
- R1–R11: [x] `scripts/tests/test_render_blueprint.py::test_r1_…` … `test_r11_…`
- R12: [x] `contracts/tests/test_production.py::test_normalize_service_url`, `services/{orchestrator,telegram_gateway,handover}/tests/test_production_config.py::test_valid_production_settings_normalize_*`, `services/handover/tests/test_vencer_casos.py::test_handover_url_host_port_is_normalized_to_http`
- R13: [x] `test_parse_app_env_rejects_other_values`, `services/*/tests/test_production_config.py::test_invalid_app_env_is_rejected`
- R14: [x] `services/*/tests/test_production_config.py::test_missing_required_variable_is_rejected`, `test_production_problems_accepts_settings_field_names`
- R15: [x] `services/*/…::test_placeholder_is_rejected_case_insensitive`
- R16: [x] `services/*/…::test_short_service_token_is_rejected`, `test_vencer_casos.py::test_short_service_token_is_rejected_in_production`
- R17: [x] `test_development_database_credentials_are_rejected` (orchestrator, rag, handover)
- R18: [x] `services/telegram_gateway/tests/test_production_config.py::test_invalid_webhook_secret_is_rejected`
- R19: [x] `services/orchestrator/tests/test_production_config.py::test_insecure_admin_cookie_is_rejected`
- R20: [x] `services/*/…::test_error_message_does_not_include_values`, `test_production_problems_reports_uppercase_names_for_snake_case_values`
- R21, R22: [x] `scripts/tests/test_ci_workflow.py::test_r21_…`, `test_r22_…`
- R23–R27: [x] `scripts/tests/test_configurar_webhook.py::test_r23_…` … `test_r27_network_error_never_prints_token_or_secret`
- R28: [x] `scripts/tests/test_render_blueprint.py::test_r28_deployment_procedure_documents_every_step`
- R29: [x] `services/orchestrator/tests/test_public_exposure.py::test_r29_internal_routes_require_valid_service_token`
- R30: [x] `services/{rag,handover}/tests/test_security.py::test_all_non_health_routes_require_service_token`
- R31: [x] `test_public_exposure.py::test_r31_admin_requires_session_even_with_service_token`, `test_r31_admin_post_requires_valid_csrf`
- R32: [x] `test_render_blueprint.py::test_r32_…`, `test_public_exposure.py::test_r32_*` (primer valor, strip, fallback, 6.º cliente no bloqueado); `admin_routes.py:44-49` coincide con `design.md`

## Tasks completas
- T1–T16: [x]

## Checkpoints
- C1: [x] archivos y docs base presentes; `./init.sh` exit 0.
- C2: [x] una sola feature `in_progress` (#24); `progress/current.md` describe la sesión.
- C3: [x] sin servicios nuevos (solo `render.yaml` y scripts previstos en design); lo compartido va en `lazaro_contracts/production.py`; ningún contrato HTTP cambia; `PyYAML>=6,<7` (MIT) solo en `requirements-dev.txt` y listado en design; `render.yaml` sin `value` en secretos; `.env` no trackeado; `APP_ENV`/`PUBLIC_BASE_URL` en `.env.example`. Los `print()` de `scripts/configurar_webhook.py` son salida de CLI, no debug.
- C4: [x] tests con `httpx.MockTransport`/fakes; ninguno llama a Telegram ni a Render.
- C5: [x] sin archivos temporales sospechosos (los no trackeados son specs/progress/tests de features previas). Estado e historial los actualiza el leader al cerrar.
- C6: [x] specs completos, EARS, design con dependencias y «Supuestos a confirmar»; tasks en `[x]`; cada R<n> con test.

## Observaciones no bloqueantes
1. `production_problems` convierte valores no-`str` con `str()`, así que un `None` pasaría como `"None"`; hoy todos los campos validados son `str` con default `""`, por lo que no aplica.
2. `scripts/vencer_casos.py` solo valida la longitud de `SERVICE_TOKEN` en producción (R16) y no comprueba placeholders; es lo que pide el spec (R15 aplica a los servicios).
