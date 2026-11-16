# Requirements — #59 `chat_caso_asesor`

El detalle del caso del panel de asesores (`GET /asesor/cases/{case_id}`) pasa a
mostrar la conversación como un chat de burbujas con el compositor pegado
debajo. Solo cambia la presentación del **orquestador**: no cambian contratos
entre servicios, ni handover, ni la lógica de envío de `POST /asesor/reply`, ni
variables de entorno. Todos los requirements los cumple el orquestador.

Definiciones usadas abajo:

- **Fragmento**: HTML que devuelve `advisor_panel.render_history_fragment` y que
  sirve `GET /asesor/live/cases/{case_id}`.
- **Región en vivo**: el elemento `id="live-region"` de la página del caso, cuyo
  contenido reemplaza `panel_live.js`.
- **Bloque de chat**: el único `<section class="chat">` de la página del caso.
- **Compositor**: el formulario `class="chat-composer"` del bloque de chat.
- **Control de formulario**: cualquier `<form>`, `<input>`, `<textarea>`,
  `<select>` o `<button>`.

## Burbujas del historial (fragmento)

### R1
CUANDO el historial tiene al menos un mensaje, el fragmento DEBE ser un único
`<ol class="chat-messages">` con exactamente un `<li>` de clase `chat-msg` por
mensaje, en el mismo orden en que se recibe el historial.

### R2
El fragmento DEBE dar a cada burbuja la clase de lado y la etiqueta de autor
(`<span class="chat-author">`) de esta tabla según el `role` del mensaje:

| `role` | Clase adicional | Etiqueta |
|---|---|---|
| `user` | `chat-msg-client` | `Cliente` |
| `advisor` | `chat-msg-advisor` | `Asesor` |
| `bot` | `chat-msg-bot` | `Bot` |
| cualquier otro | `chat-msg-other` | el propio `role`, escapado |

### R3
El fragmento DEBE incluir en cada burbuja un `<time class="chat-time">` cuyo
atributo `datetime` es `at.isoformat()` y cuyo texto es la fecha y hora en UTC
con el formato `dd/mm HH:MM UTC` (p. ej. `02/01 03:04 UTC`).

### R4
SI el historial está vacío ENTONCES el fragmento DEBE ser exactamente
`<p class="chat-empty">Sin mensajes en el periodo visible.</p>`.

### R5
El fragmento DEBE escapar con `html.escape(..., quote=True)` el texto de cada
mensaje y el `role` desconocido, de modo que un mensaje
`<script>alert(1)</script>"><img src=x onerror=1>` no produzca ninguna etiqueta
ni atributo nuevos.

### R6
El fragmento NO DEBE contener `<table`, `<script`, `style=` ni ningún control
de formulario.

### R7
CUANDO se pide `GET /asesor/live/cases/{case_id}` para un caso autorizado, el
orquestador DEBE responder con el mismo HTML que la página del caso coloca
dentro de la región en vivo para ese mismo historial.

## Bloque de chat y compositor (página del caso)

### R8
La página del caso DEBE contener exactamente un bloque de chat con, en este
orden: la cabecera `class="chat-header"`, la región en vivo y el compositor.

### R9
La cabecera del bloque de chat DEBE mostrar el encabezado `<h3>Historial</h3>`
y un `class="chat-title"` con el `username` del cliente (escapado) seguido del
canal, o `Cliente sin autenticar` seguido del canal cuando el caso no tiene
cliente autenticado.

### R10
La región en vivo DEBE llevar `class="chat-log"`, `role="log"`,
`aria-label="Mensajes de la conversación"` y `tabindex="0"`, y conservar sin
cambios los atributos `data-live-src`, `data-ws`, `data-poll` y `data-case-id`.

### R11
El compositor DEBE ser el único formulario de la página del caso con
`method="post" action="/asesor/reply"`, y contener el campo CSRF, el campo
oculto `case_id`, el campo oculto `origen` con valor `caso` y un
`<button type="submit">Enviar</button>`.

### R12
MIENTRAS la ventana del caso no es `closed`, el compositor DEBE ofrecer el
campo `<textarea name="text" maxlength="4096" required>` dentro de un `<label>`
con el texto visible `Escribe un mensaje`, y ningún `<select name="template">`.

### R13
MIENTRAS la ventana del caso es `closed`, el compositor DEBE ofrecer el
`<select name="template">` con las plantillas aprobadas del caso, y ningún
`<textarea name="text"`.

### R14
DONDE existen respuestas guardadas activas y la ventana no es `closed`, el
bloque de chat DEBE incluir, después de la región en vivo y antes del
compositor, el formulario `method="get"` hacia `/asesor/cases/{case_id}` con el
`<select name="respuesta">`.

### R15
CUANDO la página del caso se pide con `?respuesta=<id>` de una respuesta
guardada activa, el compositor DEBE mostrar el cuerpo de esa respuesta,
escapado, como contenido del `<textarea name="text">`, sin enviar nada al
cliente.

### R16
SI `?respuesta=<id>` no corresponde a una respuesta guardada activa ENTONCES el
bloque de chat DEBE mostrar, fuera de la región en vivo, el aviso
`La respuesta guardada no existe o está desactivada.` con `role="alert"`.

### R17
La región en vivo NO DEBE contener ningún control de formulario: el compositor,
el selector de respuestas guardadas y el aviso quedan fuera de ella.

### R18
La página del caso NO DEBE contener el encabezado `<h3>Responder</h3>` ni la
tabla de historial con columnas `Rol`, `Mensaje` y `Fecha`.

## Envío desde el chat

### R19
CUANDO `POST /asesor/reply` termina con éxito y el formulario trae
`origen=caso`, el orquestador DEBE responder `303` hacia
`/asesor/cases/{case_id}` (con el `case_id` validado y codificado para URL).

### R20
CUANDO `POST /asesor/reply` termina con éxito y el formulario no trae `origen`
o trae cualquier otro valor, el orquestador DEBE responder `303` hacia
`/asesor?ok=reply`, igual que hoy.

### R21
SI `POST /asesor/reply` llega con `origen=caso` y sin un token CSRF válido
ENTONCES el orquestador DEBE responder `403` sin enviar nada al cliente.

### R22
SI `POST /asesor/reply` con `origen=caso` falla por validación o por un error
de dominio ENTONCES el orquestador DEBE responder con la misma página de error
fija y el mismo código de estado que sin `origen`.

## JavaScript propio (`/asesor/static/panel_live.js`)

### R23
CUANDO el script arranca en una página cuya región en vivo tiene la clase
`chat-log`, el script DEBE desplazar la región al último mensaje
(`scrollTop = scrollHeight`).

### R24
CUANDO el script reemplaza el contenido de una región `chat-log` y el número de
elementos `.chat-msg` es mayor que antes del reemplazo, el script DEBE
desplazar la región al último mensaje.

### R25
CUANDO el script arranca o reemplaza el contenido de la región, el script DEBE
sustituir, mediante `textContent`, el texto de cada `time[datetime]` de la
región por la fecha y hora locales del navegador con formato `dd/mm HH:MM`.

### R26
SI el atributo `datetime` de un `<time>` no es una fecha válida ENTONCES el
script DEBE dejar su texto sin cambios.

### R27
El script NO DEBE leer ni modificar elementos fuera de la región en vivo ni
usar `innerHTML`: su código no contiene `innerHTML`, `textarea`,
`chat-composer` ni `document.forms`.

### R28
La página del caso NO DEBE emitir scripts en línea, atributos `on*`, `style=`
ni recursos de otro origen: su único `<script` es el de
`/asesor/static/panel_live.js`.

### R29
MIENTRAS `panel_live_enabled` es falso, la página del caso DEBE mostrar el
bloque de chat completo (burbujas y compositor) sin ninguna etiqueta `<script`.

### R30
Toda etiqueta `<script` emitida por las páginas de los paneles de asesores y de
administración DEBE ir seguida inmediatamente de su `</script>` (el número de
`<script` es igual al de `</script>` y cada apertura cumple
`<script\b[^>]*></script>`).

## Estilos (`/admin/static/admin.css`)

### R31
La hoja de estilos DEBE definir `.chat-log` con `overflow-y: auto` y un
`max-height` relativo a la ventana (`vh`).

### R32
La hoja de estilos DEBE alinear `.chat-msg` (y por tanto `.chat-msg-client`) con
`align-self: flex-start` y `.chat-msg-advisor` y `.chat-msg-bot` con
`align-self: flex-end`.

### R33
La hoja de estilos DEBE dar a las burbujas de cliente, asesor y bot tres fondos
distintos entre sí, tomados solo de variables existentes de `:root` mediante
`var(...)` (sin colores literales en las reglas `.chat*`).

### R34
La hoja de estilos DEBE mantener un contraste de al menos 4.5:1 entre los
colores de texto usados en las burbujas (`--text` y `--muted`) y cada uno de
los tres fondos de burbuja.

### R35
La hoja de estilos DEBE incluir `.chat-log:focus-visible` en la regla de foco
visible existente (contorno con `var(--focus)`).

### R36
La hoja de estilos DEBE limitar `.chat-msg` con un `max-width` en porcentaje no
mayor que `85%` y declarar en `.chat-text` `white-space: pre-wrap` y
`overflow-wrap: anywhere`, de modo que las burbujas no desborden en móvil.

## Resto de la página del caso

### R37
La página del caso DEBE seguir ofreciendo las secciones `Cliente`,
`Notas internas`, `Etiquetas`, `Transferir`, `Resolver` y
`Devolver al asistente` con sus formularios, acciones y campo CSRF actuales, y
`Memoria y resúmenes` cuando hay cliente autenticado.

### R38
DONDE el perfil es supervisor, la página del caso DEBE seguir ofreciendo el
formulario `Reasignar (supervisor)` hacia `/asesor/casos/{case_id}/reasignar`.

### R39
La página del caso DEBE colocar el bloque de chat después de la línea de
resumen del caso y antes de las secciones `Cliente` y `Notas internas`.

## Cobertura del `acceptance`

| Criterio del `acceptance` (#59) | Requirements |
|---|---|
| 1. Burbujas, lados, asistente distinguible, hora | R1, R2, R3, R4, R32, R33 |
| 2. Compositor pegado debajo, POST con CSRF, sin JS | R8, R11, R12, R19, R20, R21, R22, R29 |
| 3. Plantilla con ventana cerrada; respuestas guardadas | R13, R14, R15, R16 |
| 4. En vivo, sin duplicar, sin borrar lo escrito, autoscroll | R7, R10, R17, R23, R24, R25, R26, R27 |
| 5. Sin XSS, JS propio, accesibilidad y diseño de #56 | R5, R6, R9, R27, R28, R31, R34, R35, R36 |
| 6. Resto de secciones y `<script>` cerrado | R18, R30, R37, R38, R39 |

## Test que verifica cada requirement

Todos en `services/orchestrator/tests/test_chat_caso_asesor.py` salvo donde se
indica otro archivo.

| R | Test |
|---|---|
| R1 | `test_fragment_renders_one_bubble_per_message_in_order` |
| R2 | `test_fragment_bubble_side_and_author_label_by_role` |
| R3 | `test_fragment_bubble_has_time_with_iso_and_utc_text` |
| R4 | `test_fragment_empty_history_message` |
| R5 | `test_fragment_escapes_message_text_and_unknown_role` |
| R6 | `test_fragment_has_no_table_script_style_or_form_controls` |
| R7 | `test_live_fragment_equals_live_region_content` |
| R8 | `test_case_page_has_single_chat_block_in_order` |
| R9 | `test_chat_header_shows_client_or_unauthenticated` |
| R10 | `test_live_region_is_accessible_log_and_keeps_data_attributes` |
| R11 | `test_composer_is_only_reply_form_with_csrf_case_and_origin` |
| R12 | `test_composer_offers_textarea_when_window_not_closed` |
| R13 | `test_composer_offers_template_select_when_window_closed` |
| R14 | `test_saved_reply_selector_sits_between_log_and_composer` |
| R15 | `test_selected_saved_reply_prefills_composer` |
| R16 | `test_invalid_saved_reply_shows_notice_outside_live_region` |
| R17 | `test_live_region_contains_no_form_controls` |
| R18 | `test_case_page_drops_reply_heading_and_history_table` |
| R19 | `test_reply_from_chat_redirects_back_to_case` |
| R20 | `test_reply_without_origin_keeps_home_redirect` |
| R21 | `test_reply_from_chat_without_csrf_is_forbidden` |
| R22 | `test_reply_from_chat_errors_use_fixed_error_page` |
| R23, R24 | `test_js_scrolls_chat_log_to_last_message` |
| R25, R26 | `test_js_localizes_times_with_text_content` |
| R27 | `test_js_does_not_touch_composer_or_inner_html` |
| R28 | `test_case_page_has_only_own_script_and_no_inline_code` |
| R29 | `test_case_page_without_live_flag_keeps_chat_without_script` |
| R30 | `test_panel_visual.py::test_every_script_tag_is_closed` |
| R31 | `test_css_chat_log_scrolls_with_viewport_height` |
| R32 | `test_css_aligns_client_left_and_staff_right` |
| R33 | `test_css_bubble_backgrounds_are_distinct_variables` |
| R34 | `test_css_bubble_colors_meet_wcag_contrast` |
| R35 | `test_css_chat_log_has_visible_focus` |
| R36 | `test_css_bubbles_wrap_and_have_relative_max_width` |
| R37 | `test_case_page_keeps_other_sections_and_forms` |
| R38 | `test_supervisor_case_page_keeps_reassign_form` |
| R39 | `test_chat_block_precedes_client_and_notes` |
