# Informe de implementación — #66 `panel_administracion_canales`

Claude escribió el código directamente (OpenCode Go sin cuota, por decisión del dueño). No hubo revisión de código del reviewer.

## Qué se hizo

- **Contratos:**
  - `CHANNEL_ICONS`, una lista cerrada de emoji, con `DEFAULT_CHANNEL_ICON="chat"`.
  - `credential_hint(value)`: devuelve `…` más los últimos 4 caracteres si el valor tiene 8 o más.
  - `ChannelInfo.credential_hints`.
  - Todo documentado en `CONTRATOS.md`.
- **Gateway:**
  - Columna `pistas_credenciales` (JSONB, migración idempotente), calculada al crear y al reemplazar credenciales.
  - Nunca guarda ni devuelve el valor completo.
  - El adaptador `simulado` acepta `consent_mode`.
- **Orquestador:**
  - `HttpChannelAdminClient` y `FakeChannelAdminClient`. Un 4xx (salvo 401) es `ChannelAdminError`; un 5xx, un 401, un fallo de red o un cuerpo inválido es `ChannelAdminUnavailable`, que da 502.
  - `ChannelDirectory.invalidate()`, llamado tras cada cambio.
  - `GATEWAY_PUBLIC_BASE_URL`.
  - Validación pura en `admin_channels.py`:
    - ícono de la lista;
    - color `#RRGGBB` con contraste WCAG ≥ 4.5 frente a blanco;
    - credenciales `nombre=valor`;
    - callback `https`;
    - id.
  - Vista `render_channels`: etiqueta SVG con `fill`, sin estilos inline.
  - Script `/admin/static/canales.js` del mismo origen, sin cambiar la CSP.
  - Rutas `/admin/canales…`: solo admin, con CSRF auditado.
  - Auditoría `channel_create`, `channel_update`, `channel_active`, `channel_secret_reveal` y `channel_secret_regenerate`, sin secretos ni credenciales.

## Trazabilidad R → test

| R | Test |
|---|------|
| R1, R2, R6 | `contracts/tests/test_panel_canales_contrato.py` |
| R3, R4, R5, R27 | `services/telegram_gateway/tests/test_canales_pistas.py` |
| R7 | `test_without_admin_session_redirects_without_gateway`, `test_advisor_session_cannot_open_channels` |
| R8 | `test_bad_csrf_is_403_without_gateway` |
| R9 | `test_nav_shows_channels` |
| R10, R21, R31 | `test_listing_shows_fields_and_hints_without_secret` |
| R11 | `test_create_offers_only_gateway_adapter_types` |
| R12 | `test_create_sends_request_and_shows_secret_once`, `test_edit_can_clear_callback_url` |
| R13 | `test_edit_sends_patch_and_keeps_credentials_when_empty`, `test_edit_with_credentials_sends_them_and_shows_hints` |
| R14 | `test_managed_channel_offers_no_credentials_secret_or_webhook` |
| R15–R17 | `test_invalid_create_is_422_without_gateway`, `test_invalid_edit_is_422_without_gateway`, `test_contrast_rule` |
| R18 | `test_gateway_rejection_passes_status`, `test_duplicate_id_is_409` |
| R19 | `test_gateway_unavailable_is_502`, `test_listing_unavailable_is_502`, `test_http_client_*` |
| R20 | `test_webhook_url_with_public_base`, `test_webhook_url_without_base_shows_notice`, `test_webhook_url_helper` |
| R22, R25 | `test_reveal_secret_shows_it_and_audits_without_value` |
| R23 | `test_regenerate_requires_confirmation`, `test_regenerate_shows_new_secret_and_audits` |
| R24 | `test_credentials_never_in_audit_or_logs` y las dos anteriores |
| R26 | `test_toggle_active_calls_gateway_and_audits`, `test_toggle_rejects_invalid_state` |
| R28 | `test_inbox_keeps_cases_of_inactive_channel` |
| R29 | `invalidations` en los tests de alta, edición y activación; `test_invalidate_failure_does_not_break_panel` |
| R30 | `test_copy_script_served_same_origin`, `test_webhook_url_with_public_base` |
| R32 | Auditorías en los tests de alta, edición y activación |

Los tests del orquestador están en `services/orchestrator/tests/test_admin_canales.py`: 65 tests. También se actualizó `test_config.py` con las rutas nuevas.

## Resultado

- Las suites de contratos, gateway y orquestador pasan.
- El resultado de `./init.sh` queda en `progress/history.md`.
