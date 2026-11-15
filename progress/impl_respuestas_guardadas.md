# Implementación — #51 respuestas_guardadas

Solo `services/orchestrator` más configuración (`.env.example`, `render.yaml`).
Se reutilizan sesión admin, CSRF, `panel_audit`, autorización por caso de
handover y el envío existente `POST /asesor/reply`. Sin dependencias nuevas.

## Resumen

- CRUD de respuestas guardadas en `/admin/respuestas` con auditoría sin texto.
- Validadores puros para vacío, longitud, caracteres de control y variables.
- Tabla `saved_replies` idempotente, fuera de supresión y purga.
- Selector GET `?respuesta=<id>` en la vista del caso, solo con respuestas
  activas y ventana de WhatsApp abierta; el texto se carga en el `textarea`
  para editarlo y nada se envía hasta el `POST /asesor/reply` de siempre.
- T12: la trazabilidad está documentada abajo; `./init.sh` lo ejecuta Claude al
  cerrar la sesión.

## Trazabilidad

- R1 → `tests/test_saved_replies.py::test_admin_can_create_update_and_toggle_saved_replies`
- R2 → `tests/test_saved_replies.py::test_admin_can_create_update_and_toggle_saved_replies`
- R3 → `tests/test_saved_replies.py::test_admin_can_create_update_and_toggle_saved_replies`
- R4 → `tests/test_saved_replies.py::test_admin_can_create_update_and_toggle_saved_replies`
- R5 → `tests/test_saved_replies.py::test_admin_can_create_update_and_toggle_saved_replies`
- R6 → `tests/test_saved_replies.py::test_non_admin_cannot_manage_saved_replies`
- R7 → `tests/test_saved_replies.py::test_saved_reply_routes_require_session` y `::test_saved_reply_routes_require_csrf`
- R8 → `tests/test_saved_replies_pure.py` (vacío, longitud y controles) y `tests/test_saved_replies.py::test_invalid_saved_replies_are_rejected`
- R9 → `tests/test_saved_replies_pure.py::test_variable_markers_are_rejected` y `tests/test_saved_replies.py::test_variables_are_rejected_with_specific_code`
- R10 → `tests/test_saved_replies.py::test_saved_replies_limit_is_enforced`
- R11 → `tests/test_saved_replies.py::test_missing_saved_reply_returns_404`
- R12 → `tests/test_saved_replies.py::test_admin_can_create_update_and_toggle_saved_replies`
- R13 → `tests/test_saved_replies_advisor.py::test_selector_lists_only_active_titles`
- R14 → `tests/test_saved_replies_advisor.py::test_loading_a_reply_prefills_textarea_without_sending`
- R15 → `tests/test_saved_replies_advisor.py::test_loading_a_reply_prefills_textarea_without_sending`
- R16 → `tests/test_saved_replies_advisor.py::test_advisor_can_edit_loaded_reply_before_sending`
- R17 → `tests/test_saved_replies_advisor.py::test_inactive_or_missing_reply_shows_empty_field_and_notice`
- R18 → `tests/test_saved_replies_advisor.py::test_closed_whatsapp_window_hides_selector_and_ignores_forced_reply`
- R19 → `tests/test_saved_replies_advisor.py::test_advisor_can_edit_loaded_reply_before_sending` y `::test_sending_from_closed_whatsapp_window_is_blocked`
- R20 → `tests/test_saved_replies_advisor.py::test_unauthorized_case_does_not_reveal_saved_reply`
- R21 → `tests/test_saved_replies.py::test_saved_reply_page_escapes_title_and_body` y `tests/test_saved_replies_advisor.py::test_saved_reply_text_is_escaped_and_not_interpolated`
- R22 → `tests/test_saved_replies_advisor.py::test_saved_reply_text_is_escaped_and_not_interpolated`
- R23 → `tests/test_config.py::test_saved_reply_settings_defaults_and_env_example` y `::test_saved_reply_settings_reject_out_of_range`
- R24 → `tests/test_repository_schema.py::test_schema_declares_saved_replies_outside_personal_data`

## Verificación

`bash ./init.sh`: exit 0, 3325 passed, 1 skipped y 2 avisos de deprecación.
T1–T12 completas; queda pendiente la revisión de código Claude.
