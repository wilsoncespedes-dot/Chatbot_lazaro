# Review — feature #51 respuestas_guardadas

**Veredicto:** APPROVED

## Trazabilidad requirements ↔ tests
Todos los tests citados en `progress/impl_respuestas_guardadas.md` existen (verificados por nombre en `services/orchestrator/tests/`).
- R1–R5, R12: [x] `test_admin_can_create_update_and_toggle_saved_replies`
- R6: [x] `test_non_admin_cannot_manage_saved_replies`
- R7: [x] `test_saved_reply_routes_require_session`, `test_saved_reply_routes_require_csrf`
- R8: [x] `test_saved_replies_pure.py`, `test_invalid_saved_replies_are_rejected`
- R9: [x] `test_variable_markers_are_rejected`, `test_variables_are_rejected_with_specific_code`
- R10: [x] `test_saved_replies_limit_is_enforced`
- R11: [x] `test_missing_saved_reply_returns_404`
- R13: [x] `test_selector_lists_only_active_titles`
- R14, R15: [x] `test_loading_a_reply_prefills_textarea_without_sending`
- R16: [x] `test_advisor_can_edit_loaded_reply_before_sending`
- R17: [x] `test_inactive_or_missing_reply_shows_empty_field_and_notice`
- R18: [x] `test_closed_whatsapp_window_hides_selector_and_ignores_forced_reply`
- R19: [x] `test_advisor_can_edit_loaded_reply_before_sending`, `test_sending_from_closed_whatsapp_window_is_blocked`
- R20: [x] `test_unauthorized_case_does_not_reveal_saved_reply`
- R21: [x] `test_saved_reply_page_escapes_title_and_body`, `test_saved_reply_text_is_escaped_and_not_interpolated`
- R22: [x] `test_saved_reply_text_is_escaped_and_not_interpolated`
- R23: [x] `test_saved_reply_settings_defaults_and_env_example`, `test_saved_reply_settings_reject_out_of_range`
- R24: [x] `test_schema_declares_saved_replies_outside_personal_data`

## Tasks completas
- T1–T12: [x] todas marcadas en `specs/respuestas_guardadas/tasks.md`.

## Checkpoints
- C1: [x] `./init.sh` exit 0 (3325 passed, 1 skipped).
- C2: [x]
- C3: [x] Variables nuevas en `.env.example` (l.160-162) y `render.yaml` (l.188-192); sin dependencias nuevas; sin `print`/TODO en el código nuevo (los 4 hallazgos están en `bootstrap_admin.py`, preexistente).
- C4: [x]
- C5: [x] Pendiente de cierre normal por el leader (historia/estado `done`).
- C6: [x]

## Cambios requeridos
Ninguno.
