# Tasks — #59 `chat_caso_asesor`

Reglas para todas las tasks: solo se tocan los cuatro archivos de aplicación de
`design.md`; no se edita ni se borra ningún test existente; los tests nuevos
llevan en su docstring el `R<n>` que cubren y usan las fixtures `env_factory` y
`panel` de `tests/conftest.py`. No se tocan los cambios sin commitear ajenos a
esta feature. Rutas relativas a `services/orchestrator/`.

## Fragmento en burbujas

- [x] T1 — En `orchestrator/advisor_panel.py`: añadir `ROLE_CLASSES` y `_chat_time(at)`, y reescribir `render_history_fragment` (misma firma) con la lista `<ol class="chat-messages">` y el caso vacío de `design.md`. Cubre: R1, R2, R3, R4, R5, R6.
- [x] T2 — Crear `tests/test_chat_caso_asesor.py` con los tests del fragmento llamando a `advisor_panel.render_history_fragment` con `HistoryItem`: `test_fragment_renders_one_bubble_per_message_in_order`, `test_fragment_bubble_side_and_author_label_by_role` (parametrizado: `user`, `advisor`, `bot`, `system`), `test_fragment_bubble_has_time_with_iso_and_utc_text` (`panel.NOW` → `datetime="2026-01-02T03:04:05+00:00"` y texto `02/01 03:04 UTC`; un `at` con desfase `-05:00` se muestra convertido a UTC), `test_fragment_empty_history_message` (igualdad exacta), `test_fragment_escapes_message_text_and_unknown_role` (el texto de R5 y un `role` `<b>x`: sin `<script`, `<img` ni `<b>` en la salida), `test_fragment_has_no_table_script_style_or_form_controls`. Cubre: R1, R2, R3, R4, R5, R6.

## Bloque de chat y compositor

- [x] T3 — En `orchestrator/advisor_panel.py`: añadir `_chat_block(view, csrf, poll_seconds)` según `design.md`, eliminar `_history_section` y el formulario `Responder` de `render_advisor_case`, y reordenar el cuerpo (resumen → chat → Cliente → Notas → Etiquetas → Memoria → Transferir → Resolver → Devolver → Reasignar). Cubre: R8, R9, R10, R11, R12, R13, R14, R15, R16, R17, R18, R37, R38, R39.
- [x] T4 — En `tests/test_chat_caso_asesor.py`: añadir un ayudante local que analice la página con `html.parser.HTMLParser` y devuelva (a) las etiquetas abiertas dentro de `#live-region` y (b) el HTML interno de `#live-region`. Tests de estructura sobre `GET /asesor/cases/case-1`: `test_case_page_has_single_chat_block_in_order` (un solo `<section class="chat"`; posiciones `chat-header` < `id="live-region"` < `class="chat-composer"`), `test_chat_header_shows_client_or_unauthenticated` (con y sin `profile_id`; un `username` con `<` sale escapado), `test_live_region_is_accessible_log_and_keeps_data_attributes`, `test_live_region_contains_no_form_controls` (con mensajes, respuestas guardadas y `?respuesta=` inválido), `test_case_page_drops_reply_heading_and_history_table` (sin `<h3>Responder</h3>`, sin `<th>Rol</th>`), `test_live_fragment_equals_live_region_content` (el cuerpo de `GET /asesor/live/cases/case-1` es igual al HTML interno de `#live-region` con tres mensajes). Cubre: R7, R8, R9, R10, R17, R18.
- [x] T5 — En el mismo archivo, tests del compositor (preparar ventana cerrada, plantillas y respuestas guardadas como en `tests/test_panel_reply.py::test_case_view_renders_selector_or_textarea` y `tests/test_saved_replies_advisor.py`): `test_composer_is_only_reply_form_with_csrf_case_and_origin` (`action="/asesor/reply"` aparece una vez; dentro del formulario: `name="csrf_token"`, `name="case_id" value="case-1"`, `name="origen" value="caso"`, `<button type="submit">Enviar</button>`), `test_composer_offers_textarea_when_window_not_closed` (texto `Escribe un mensaje` y la etiqueta exacta del `textarea`), `test_composer_offers_template_select_when_window_closed`, `test_saved_reply_selector_sits_between_log_and_composer`, `test_selected_saved_reply_prefills_composer` (cuerpo con `<` escapado; ninguna llamada de envío al cliente), `test_invalid_saved_reply_shows_notice_outside_live_region`. Cubre: R11, R12, R13, R14, R15, R16.
- [x] T6 — En el mismo archivo: `test_case_page_keeps_other_sections_and_forms` (encabezados `Cliente`, `Notas internas`, `Etiquetas`, `Memoria y resúmenes`, `Transferir`, `Resolver`, `Devolver al asistente`; acciones `/asesor/transfer`, `/asesor/close`, `/asesor/return`, `/asesor/cases/case-1/notes` con `method="post"` y CSRF), `test_supervisor_case_page_keeps_reassign_form` (`panel.login(env, role="supervisor")`; un asesor normal no lo ve), `test_chat_block_precedes_client_and_notes` (índice de `<section class="chat"` menor que el de `<h3>Cliente</h3>` y el de `<h3>Notas internas</h3>`, y mayor que el de `Volver a la bandeja`). Cubre: R37, R38, R39.

## Envío desde el chat

- [x] T7 — En `orchestrator/advisor_routes.py`, función `reply`: redirigir a `/asesor/cases/{quote(case_id, safe='')}` cuando `form.get("origen", "") == "caso"`; en otro caso, `/asesor?ok=reply`. Nada más cambia en la función. Cubre: R19, R20, R22.
- [x] T8 — En `tests/test_chat_caso_asesor.py`: `test_reply_from_chat_redirects_back_to_case` (texto libre y plantilla: `303`, `location == "/asesor/cases/case-1"`, y el envío se registró igual que hoy), `test_reply_without_origin_keeps_home_redirect` (sin `origen` y con `origen=otro` → `/asesor?ok=reply`), `test_reply_from_chat_without_csrf_is_forbidden` (`403` y cero envíos), `test_reply_from_chat_errors_use_fixed_error_page` (texto vacío → `422` con `data-code="validation_error"`; `case_id` inválido → `422`; error de dominio `forbidden` → `403`, mismos códigos que sin `origen`). Cubre: R19, R20, R21, R22.

## JavaScript

- [x] T9 — En `orchestrator/panel_live_js.py`: añadir `isChat`, `countMessages`, `scrollToEnd`, `pad` y `localizeTimes`, llamarlas en `replaceRegion` y en el arranque según `design.md`. Sin `innerHTML`; conservar los marcadores de #53. Cubre: R23, R24, R25, R26, R27.
- [x] T10 — En `tests/test_chat_caso_asesor.py`, sobre el texto de `GET /asesor/static/panel_live.js`: `test_js_scrolls_chat_log_to_last_message` (contiene `chat-log`, `.chat-msg`, `scrollTop` y `scrollHeight`), `test_js_localizes_times_with_text_content` (contiene `time[datetime]`, `textContent`, `isNaN`, `getHours`), `test_js_does_not_touch_composer_or_inner_html` (no contiene `innerHTML`, `textarea`, `chat-composer` ni `document.forms`). Añadir `test_case_page_has_only_own_script_and_no_inline_code` (página del caso con mensajes: un solo `<script`, el de `panel_live.js`; sin `style=`, sin atributos `on*`, sin `src`/`href` externos) y `test_case_page_without_live_flag_keeps_chat_without_script` (`env_factory(panel_live_enabled=False)`: hay `<section class="chat"`, burbuja y compositor, y cero `<script`). Cubre: R23, R24, R25, R26, R27, R28, R29.

## Estilos

- [x] T11 — En `orchestrator/admin.py`: añadir a `ADMIN_CSS` las reglas `.chat*` de la tabla de `design.md` y `.chat-log:focus-visible` a la regla de foco. Sin variables nuevas, colores literales, `url(` ni `@import`. Cubre: R31, R32, R33, R34, R35, R36.
- [x] T12 — En `tests/test_chat_caso_asesor.py`, sobre `admin.ADMIN_CSS` (ayudantes locales equivalentes a `_block`, `_root_vars` y `_contrast` de `tests/test_panel_visual.py`): `test_css_chat_log_scrolls_with_viewport_height`, `test_css_aligns_client_left_and_staff_right`, `test_css_bubble_backgrounds_are_distinct_variables` (los tres `background` son `var(--…)` distintos y ningún bloque `.chat*` contiene `#` ni `rgb`), `test_css_bubble_colors_meet_wcag_contrast` (`--text` y `--muted` contra los tres fondos resueltos, ≥ 4.5), `test_css_chat_log_has_visible_focus`, `test_css_bubbles_wrap_and_have_relative_max_width` (`max-width` en `%` ≤ 85; `pre-wrap`; `overflow-wrap: anywhere`). Cubre: R31, R32, R33, R34, R35, R36.

## Regresión de `<script>`

- [x] T13 — Al final de `tests/test_panel_visual.py`: añadir `test_every_script_tag_is_closed`, que recorre `_admin_pages(...) | _advisor_pages(...)` y además `advisor_panel.render_advisor_cases([], "csrf", live_enabled=True)`; en cada HTML `count("<script") == count("</script>")` y cada apertura cumple `<script\b[^>]*></script>`; la bandeja y el caso tienen al menos un `<script` (el test no pasa en vacío). Cubre: R30.

## Cierre

- [x] T14 — Ejecutar la suite de `services/orchestrator` y confirmar que los tests existentes listados en `design.md` («Tests existentes») siguen en verde sin haber sido editados; registrar el mapa de trazabilidad R1–R39 (tabla «Test que verifica cada requirement» de `requirements.md`) en `progress/impl_chat_caso_asesor.md`. Comprobación de cierre; no cubre ningún `R<n>`.
