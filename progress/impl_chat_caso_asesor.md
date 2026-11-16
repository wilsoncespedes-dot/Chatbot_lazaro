# Implementación — #59 `chat_caso_asesor`

## Notas para el writer (antes de empezar)

- El árbol tiene cambios sin commitear ajenos a #59 (retiro del segundo factor:
  `two_factor*` borrados; cambios en `admin.py`, `advisor_routes.py`,
  `config.py`, `main.py`, tests). Constrúyelo encima: no los reviertas ni los
  "arregles".
- En `advisor_panel.py` ya se añadió a mano el `</script>` que faltaba en las
  dos etiquetas de `panel_live.js`. Consérvalo.
- `advisor_routes.py` todavía no importa `quote`: añade
  `from urllib.parse import quote`.
- En `_chat_time`, una fecha `at` sin zona horaria se trata como UTC también
  en el atributo `datetime` (R3), para que `localizeTimes` no la lea como hora
  local.
- Marca cada task `[x]` en `specs/chat_caso_asesor/tasks.md` al terminarla.

## Resumen de la implementación

- `advisor_panel.py`: historial como `<ol class="chat-messages">` con burbujas,
  autor, hora UTC y escapado; `_chat_block` con cabecera, `#live-region`
  (`chat-log` accesible) y compositor `chat-composer`; selector de respuestas
  guardadas y aviso en `.chat-tools`; orden del cuerpo con el chat tras el
  resumen y antes de Cliente/Notas. Sin `<h3>Responder</h3>` ni tabla de
  historial.
- `advisor_routes.py`: `POST /asesor/reply` con `origen=caso` redirige al caso;
  sin `origen` mantiene `/asesor?ok=reply`.
- `panel_live_js.py`: autoscroll de `chat-log`, recuento de `.chat-msg` y hora
  local con `textContent`; sin `innerHTML` ni acceso al compositor.
- `admin.py`: reglas `.chat*` en `ADMIN_CSS` con variables existentes y
  `.chat-log:focus-visible` en la regla de foco.
- Tests nuevos en `tests/test_chat_caso_asesor.py`; `test_every_script_tag_is_closed`
  al final de `tests/test_panel_visual.py`. Ningún test existente editado ni
  borrado.

## Trazabilidad

- R1 → `services/orchestrator/tests/test_chat_caso_asesor.py::test_fragment_renders_one_bubble_per_message_in_order`
- R2 → `services/orchestrator/tests/test_chat_caso_asesor.py::test_fragment_bubble_side_and_author_label_by_role`
- R3 → `services/orchestrator/tests/test_chat_caso_asesor.py::test_fragment_bubble_has_time_with_iso_and_utc_text`
- R4 → `services/orchestrator/tests/test_chat_caso_asesor.py::test_fragment_empty_history_message`
- R5 → `services/orchestrator/tests/test_chat_caso_asesor.py::test_fragment_escapes_message_text_and_unknown_role`
- R6 → `services/orchestrator/tests/test_chat_caso_asesor.py::test_fragment_has_no_table_script_style_or_form_controls`
- R7 → `services/orchestrator/tests/test_chat_caso_asesor.py::test_live_fragment_equals_live_region_content`
- R8 → `services/orchestrator/tests/test_chat_caso_asesor.py::test_case_page_has_single_chat_block_in_order`
- R9 → `services/orchestrator/tests/test_chat_caso_asesor.py::test_chat_header_shows_client_or_unauthenticated`
- R10 → `services/orchestrator/tests/test_chat_caso_asesor.py::test_live_region_is_accessible_log_and_keeps_data_attributes`
- R11 → `services/orchestrator/tests/test_chat_caso_asesor.py::test_composer_is_only_reply_form_with_csrf_case_and_origin`
- R12 → `services/orchestrator/tests/test_chat_caso_asesor.py::test_composer_offers_textarea_when_window_not_closed`
- R13 → `services/orchestrator/tests/test_chat_caso_asesor.py::test_composer_offers_template_select_when_window_closed`
- R14 → `services/orchestrator/tests/test_chat_caso_asesor.py::test_saved_reply_selector_sits_between_log_and_composer`
- R15 → `services/orchestrator/tests/test_chat_caso_asesor.py::test_selected_saved_reply_prefills_composer`
- R16 → `services/orchestrator/tests/test_chat_caso_asesor.py::test_invalid_saved_reply_shows_notice_outside_live_region`
- R17 → `services/orchestrator/tests/test_chat_caso_asesor.py::test_live_region_contains_no_form_controls`
- R18 → `services/orchestrator/tests/test_chat_caso_asesor.py::test_case_page_drops_reply_heading_and_history_table`
- R19 → `services/orchestrator/tests/test_chat_caso_asesor.py::test_reply_from_chat_redirects_back_to_case`
- R20 → `services/orchestrator/tests/test_chat_caso_asesor.py::test_reply_without_origin_keeps_home_redirect`
- R21 → `services/orchestrator/tests/test_chat_caso_asesor.py::test_reply_from_chat_without_csrf_is_forbidden`
- R22 → `services/orchestrator/tests/test_chat_caso_asesor.py::test_reply_from_chat_errors_use_fixed_error_page`
- R23, R24 → `services/orchestrator/tests/test_chat_caso_asesor.py::test_js_scrolls_chat_log_to_last_message`
- R25, R26 → `services/orchestrator/tests/test_chat_caso_asesor.py::test_js_localizes_times_with_text_content`
- R27 → `services/orchestrator/tests/test_chat_caso_asesor.py::test_js_does_not_touch_composer_or_inner_html`
- R28 → `services/orchestrator/tests/test_chat_caso_asesor.py::test_case_page_has_only_own_script_and_no_inline_code`
- R29 → `services/orchestrator/tests/test_chat_caso_asesor.py::test_case_page_without_live_flag_keeps_chat_without_script`
- R30 → `services/orchestrator/tests/test_panel_visual.py::test_every_script_tag_is_closed`
- R31 → `services/orchestrator/tests/test_chat_caso_asesor.py::test_css_chat_log_scrolls_with_viewport_height`
- R32 → `services/orchestrator/tests/test_chat_caso_asesor.py::test_css_aligns_client_left_and_staff_right`
- R33 → `services/orchestrator/tests/test_chat_caso_asesor.py::test_css_bubble_backgrounds_are_distinct_variables`
- R34 → `services/orchestrator/tests/test_chat_caso_asesor.py::test_css_bubble_colors_meet_wcag_contrast`
- R35 → `services/orchestrator/tests/test_chat_caso_asesor.py::test_css_chat_log_has_visible_focus`
- R36 → `services/orchestrator/tests/test_chat_caso_asesor.py::test_css_bubbles_wrap_and_have_relative_max_width`
- R37 → `services/orchestrator/tests/test_chat_caso_asesor.py::test_case_page_keeps_other_sections_and_forms`
- R38 → `services/orchestrator/tests/test_chat_caso_asesor.py::test_supervisor_case_page_keeps_reassign_form`
- R39 → `services/orchestrator/tests/test_chat_caso_asesor.py::test_chat_block_precedes_client_and_notes`

## Verificación

La ejecución de `./init.sh` la hace Claude al cerrar la sesión (el writer no
tiene shell). No se ha editado ningún test existente de los listados en
`design.md` («Tests existentes»).

### Resultado (implementer Claude, 2026-11-16)

- Tasks T1–T14 marcadas `[x]` en `specs/chat_caso_asesor/tasks.md` (un solo
  intento del writer; sin ciclos de corrección).
- Archivos tocados por #59: `orchestrator/advisor_panel.py`,
  `orchestrator/advisor_routes.py`, `orchestrator/panel_live_js.py`,
  `orchestrator/admin.py`, `tests/test_chat_caso_asesor.py` (nuevo),
  `tests/test_panel_visual.py` (solo se añadió `test_every_script_tag_is_closed`).
  Se conservan los `</script>` del hotfix (`advisor_panel.py` l. 397 y 699) y los
  cambios ajenos del retiro del segundo factor.
- `pytest services/orchestrator` (.venv): verde, exit 0.
- `./init.sh`: `3613 passed, 1 skipped, 2 warnings` — «Todos los tests pasan»,
  exit 0.
- `feature_list.json`: #59 sigue `in_progress` (pendiente de revisión de código).
- Desvíos del design: ninguno conocido.

