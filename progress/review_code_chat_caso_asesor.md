# Review — feature #59 `chat_caso_asesor` (código)

**Veredicto:** APPROVED

Alcance: solo el diff de #59 en `services/orchestrator/orchestrator/{advisor_panel.py,advisor_routes.py,panel_live_js.py,admin.py}`,
`services/orchestrator/tests/test_chat_caso_asesor.py` (nuevo) y `test_every_script_tag_is_closed`
al final de `tests/test_panel_visual.py`. Los cambios del retiro del segundo factor no se evalúan.

Verificación: `./init.sh` reportado verde (3613 passed, 1 skipped). Re-ejecutado aquí:
`pytest tests/test_chat_caso_asesor.py tests/test_panel_visual.py` → todo verde.

## Trazabilidad requirements ↔ tests
Todos en `services/orchestrator/tests/test_chat_caso_asesor.py` salvo R30.
- R1: [x] `test_fragment_renders_one_bubble_per_message_in_order`
- R2: [x] `test_fragment_bubble_side_and_author_label_by_role` (user/advisor/bot/system)
- R3: [x] `test_fragment_bubble_has_time_with_iso_and_utc_text` (incluye desfase -05:00)
- R4: [x] `test_fragment_empty_history_message` (igualdad exacta)
- R5: [x] `test_fragment_escapes_message_text_and_unknown_role`
- R6: [x] `test_fragment_has_no_table_script_style_or_form_controls`
- R7: [x] `test_live_fragment_equals_live_region_content` (igualdad con HTML interno parseado)
- R8: [x] `test_case_page_has_single_chat_block_in_order`
- R9: [x] `test_chat_header_shows_client_or_unauthenticated`
- R10: [x] `test_live_region_is_accessible_log_and_keeps_data_attributes`
- R11: [x] `test_composer_is_only_reply_form_with_csrf_case_and_origin`
- R12: [x] `test_composer_offers_textarea_when_window_not_closed`
- R13: [x] `test_composer_offers_template_select_when_window_closed`
- R14: [x] `test_saved_reply_selector_sits_between_log_and_composer`
- R15: [x] `test_selected_saved_reply_prefills_composer` (escapado y sin envíos)
- R16: [x] `test_invalid_saved_reply_shows_notice_outside_live_region`
- R17: [x] `test_live_region_contains_no_form_controls`
- R18: [x] `test_case_page_drops_reply_heading_and_history_table`
- R19: [x] `test_reply_from_chat_redirects_back_to_case` (texto y plantilla)
- R20: [x] `test_reply_without_origin_keeps_home_redirect` (sin origen y `origen=otro`)
- R21: [x] `test_reply_from_chat_without_csrf_is_forbidden` (403, cero envíos)
- R22: [x] `test_reply_from_chat_errors_use_fixed_error_page` (422/422/403)
- R23, R24: [x] `test_js_scrolls_chat_log_to_last_message`
- R25, R26: [x] `test_js_localizes_times_with_text_content`
- R27: [x] `test_js_does_not_touch_composer_or_inner_html`
- R28: [x] `test_case_page_has_only_own_script_and_no_inline_code`
- R29: [x] `test_case_page_without_live_flag_keeps_chat_without_script`
- R30: [x] `tests/test_panel_visual.py::test_every_script_tag_is_closed`
- R31: [x] `test_css_chat_log_scrolls_with_viewport_height`
- R32: [x] `test_css_aligns_client_left_and_staff_right`
- R33: [x] `test_css_bubble_backgrounds_are_distinct_variables`
- R34: [x] `test_css_bubble_colors_meet_wcag_contrast`
- R35: [x] `test_css_chat_log_has_visible_focus`
- R36: [x] `test_css_bubbles_wrap_and_have_relative_max_width`
- R37: [x] `test_case_page_keeps_other_sections_and_forms`
- R38: [x] `test_supervisor_case_page_keeps_reassign_form`
- R39: [x] `test_chat_block_precedes_client_and_notes`

## Tasks completas
- T1–T14: [x] (todas marcadas en `specs/chat_caso_asesor/tasks.md`)

## Puntos de seguridad verificados
- XSS: `render_history_fragment` (`advisor_panel.py` ~l.412-427) escapa texto, etiqueta de rol y
  `datetime` con `_esc` (`html.escape(quote=True)`); la clase CSS sale solo de `ROLE_CLASSES` o del
  literal `chat-msg-other`, nunca del rol. Cabecera (`_esc(title)`), `data-case-id`, `case_id` oculto
  y cuerpo de respuesta guardada también escapados.
- Redirección `origen=caso` (`advisor_routes.py` l.558-559): solo tras CSRF (`_require_csrf`, l.510),
  `_valid_case_id` (l.518) y `_audit(... "ok")` (l.550); destino fijo `/asesor/cases/` +
  `quote(case_id, safe='')`. Comparación exacta `== "caso"`; ningún valor del formulario se usa como URL.
  No es redirección abierta. Errores/auditoría de error sin cambios.
- Compositor fuera de `#live-region` (`_chat_block`: `live_region` se cierra antes de `tools` y
  `composer`). `panel_live_js.py` solo opera sobre `region` (`querySelectorAll` en la región,
  `textContent`, `scrollTop`); sin `innerHTML`, `textarea`, `chat-composer` ni `document.forms`.
- Sin JS inline, sin `on*`, sin `style=`, sin CDN; las dos `<script` (l.397 y l.699) cerradas con
  `</script>`. CSS `.chat*` solo con `var(...)`.

## Checkpoints (aplicables a #59)
- C1: [x] (init.sh verde reportado; archivos base presentes)
- C2: [x] una sola feature `in_progress`
- C3: [x] sin dependencias nuevas, sin imports entre servicios, sin print/eval, contratos sin cambios
- C4: [x] tests con adaptadores falsos; suite verde
- C5: n/a hasta el cierre por el leader (history/estado)
- C6: [x] specs completos, tasks en `[x]`, cada R con test

## Observaciones no bloqueantes
1. `test_css_bubble_colors_meet_wcag_contrast` (l.658-664) fija a mano `--surface`, `--ok-bg`,
   `--info-bg` en vez de resolverlos desde los bloques `.chat-msg*`; si se cambia un fondo en el
   CSS, R34 podría dejar de verificarse. Conviene derivarlos con `_background(...)` en el futuro.
2. Los tests R23–R27 son de presencia/ausencia de marcadores en el JS (tal como fijó T10), sin
   ejecución en navegador.
