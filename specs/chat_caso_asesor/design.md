# Design — #59 `chat_caso_asesor`

Cambio de presentación en el orquestador. Sin contratos, rutas, modelos,
variables de entorno, dependencias ni archivos estáticos nuevos. No se reutiliza
código externo (no hay licencias que confirmar).

## Archivos a modificar

Todos bajo `services/orchestrator/orchestrator/`.

| Archivo | Cambio |
|---|---|
| `advisor_panel.py` | Fragmento en burbujas, bloque de chat y compositor en `render_advisor_case` |
| `admin.py` | Reglas `.chat*` dentro de `ADMIN_CSS` |
| `panel_live_js.py` | Autoscroll y hora local en `PANEL_LIVE_JS` |
| `advisor_routes.py` | Redirección de `POST /asesor/reply` cuando `origen=caso` |

No se tocan `panel_live_routes.py` (sigue llamando a
`render_history_fragment(history)` con la misma firma), `domain.py`,
`config.py`, `.env.example`, `render.yaml` ni nada de `contracts/`.

Tests: archivo nuevo `services/orchestrator/tests/test_chat_caso_asesor.py` y
un test añadido al final de `tests/test_panel_visual.py` (R30).

## `advisor_panel.py`

### Firmas

```python
ROLE_CLASSES = {"user": "chat-msg-client", "advisor": "chat-msg-advisor", "bot": "chat-msg-bot"}

def _chat_time(at: datetime) -> str: ...          # "dd/mm HH:MM UTC"
def render_history_fragment(history) -> str: ...  # firma sin cambios
def _chat_block(view, csrf: str, poll_seconds: int) -> str: ...
```

`render_advisor_case` conserva su firma. `_history_section` desaparece (lo
sustituye `_chat_block`). `ROLE_LABELS` no cambia.

### Fragmento (R1-R6)

```html
<ol class="chat-messages">
<li class="chat-msg chat-msg-client"><span class="chat-author">Cliente</span><p class="chat-text">TEXTO</p><time class="chat-time" datetime="2026-01-02T03:04:05+00:00">02/01 03:04 UTC</time></li>
...
</ol>
```

- Clase adicional: `ROLE_CLASSES.get(role, "chat-msg-other")`. Etiqueta:
  `ROLE_LABELS.get(role, role)`. Texto, etiqueta y `datetime` pasan por `_esc`.
- `_chat_time`: si `at` no tiene zona se asume UTC; en otro caso
  `at.astimezone(timezone.utc)`; formato `%d/%m %H:%M` más ` UTC`.
- Historial vacío: `<p class="chat-empty">Sin mensajes en el periodo visible.</p>`.
- Ya no se usa `admin._table_wrap` aquí.

### Bloque de chat (R8-R18)

```html
<section class="chat" aria-label="Conversación del caso">
<div class="chat-header"><h3>Historial</h3><p class="chat-title">NOMBRE · CANAL</p></div>
<div id="live-region" class="chat-log" role="log" aria-label="Mensajes de la conversación" tabindex="0"
     data-live-src="/asesor/live/cases/CASE" data-ws="/asesor/ws?scope=mine" data-poll="N" data-case-id="CASE">FRAGMENTO</div>
<div class="chat-tools">AVISO SELECTOR_DE_RESPUESTAS</div>   <!-- solo si hay aviso o selector -->
<form method="post" action="/asesor/reply" class="chat-composer">
  CSRF <input type="hidden" name="case_id" value="CASE"><input type="hidden" name="origen" value="caso">
  CAMPO <button type="submit">Enviar</button>
</form>
</section>
```

- `NOMBRE`: `view.client.username` o `Cliente sin autenticar`; `CANAL`:
  `view.client.channel`.
- El contenido de `#live-region` es exactamente `render_history_fragment(view.history)`,
  sin espacios ni nodos extra (R7).
- `CAMPO` con ventana no cerrada:
  `<label class="chat-field">Escribe un mensaje <textarea name="text" maxlength="4096" required>CUERPO</textarea></label>`.
  La etiqueta de apertura del `textarea` se conserva carácter a carácter: la
  fijan tests existentes de #41 y #52.
- `CAMPO` con ventana `closed`:
  `<label class="chat-field">Plantilla <select name="template">…</select></label>`.
- Aviso y selector de respuestas guardadas: el mismo HTML de hoy, movido a
  `.chat-tools`.
- Se eliminan `<h3>Responder</h3>` y el formulario `class="card"` del final.
- Orden del cuerpo: línea de resumen → bloque de chat → Cliente → Notas
  internas → Etiquetas → Memoria → Transferir → Resolver → Devolver →
  Reasignar (R39). El resto de secciones no cambia de HTML.

## `advisor_routes.py` (R19-R22)

En `reply`, tras la auditoría `ok`:

```python
if form.get("origen", "") == "caso":
    return _redirect(f"/asesor/cases/{quote(case_id, safe='')}")
return _redirect("/asesor?ok=reply")
```

`case_id` ya pasó `_valid_case_id`; el destino es una ruta fija del mismo
origen (no hay redirección abierta). Validación, CSRF, auditoría, errores y
llamadas a `reply_to_case` / `advisor_send_template` no cambian. El formulario
de la página de inicio no envía `origen` y sigue yendo a `/asesor?ok=reply`.

## `panel_live_js.py` (R23-R27)

Funciones nuevas dentro del mismo IIFE; todo opera sobre `region`:

```js
var isChat = region.classList.contains("chat-log");
function countMessages() { return region.querySelectorAll(".chat-msg").length; }
function scrollToEnd() { if (isChat) { region.scrollTop = region.scrollHeight; } }
function pad(n) { return n < 10 ? "0" + n : "" + n; }
function localizeTimes() { /* cada time[datetime]: new Date(attr); si isNaN -> nada;
  si no, textContent = dd/mm HH:MM con getDate/getMonth/getHours/getMinutes */ }
```

- `replaceRegion`: guarda `countMessages()` antes, reemplaza, llama a
  `localizeTimes()` y, si el conteo creció, a `scrollToEnd()`. Así un sondeo
  sin mensajes nuevos no mueve al asesor que está leyendo mensajes anteriores.
- Arranque: `localizeTimes(); scrollToEnd();` antes de `connect()`.
- `#live-region` es a la vez el contenedor con scroll, por lo que
  `replaceChildren` conserva su posición.
- No hay intérprete de JS en los tests: R23-R27 se verifican por marcadores en
  el texto servido (`scrollTop`, `scrollHeight`, `chat-log`, `.chat-msg`,
  `time[datetime]`, `textContent`, `isNaN`, `getHours`; ausencia de
  `innerHTML`, `textarea`, `chat-composer`, `document.forms`), igual que #53.
- Se conservan los marcadores de #53 (`DOMParser`, `replaceChildren`,
  `BACKOFF_*`, `setInterval`).

## `admin.py` — `ADMIN_CSS` (R31-R36)

Reglas nuevas, solo con variables existentes de `:root` (no se añaden
variables ni colores literales):

| Selector | Declaraciones verificadas |
|---|---|
| `.chat` | superficie, borde, radio, sombra, `display: flex; flex-direction: column` |
| `.chat-header`, `.chat-tools`, `.chat-composer` | relleno, borde separador, `margin: 0` |
| `.chat-log` | `background: var(--bg)`, `max-height: 60vh`, `min-height: 12rem`, `overflow-y: auto` |
| `.chat-messages` | lista sin viñetas, columna flex con separación |
| `.chat-msg` | `max-width: 85%`, `align-self: flex-start`, `background: var(--surface)`, `color: var(--text)`, borde y radio |
| `.chat-msg-advisor` | `align-self: flex-end`, `background: var(--ok-bg)` |
| `.chat-msg-bot` | `align-self: flex-end`, `background: var(--info-bg)` |
| `.chat-author`, `.chat-time` | `color: var(--muted)`, tamaño menor; hora alineada a la derecha |
| `.chat-text` | `margin: 0`, `white-space: pre-wrap`, `overflow-wrap: anywhere` |
| `.chat-field` | `flex: 1 1 16rem`; `.chat-field textarea, .chat-field select { width: 100% }` |
| regla de foco | añadir `.chat-log:focus-visible` a la lista de selectores |

- `.chat-msg-other` no tiene regla propia: hereda `.chat-msg` (lado del
  cliente, fondo neutro) y se distingue por su etiqueta.
- El compositor hereda el comportamiento global de `form` (#56): columna en
  móvil, fila en escritorio. No se declaran anchos en `px`.
- Contraste (R34): `--text` y `--muted` sobre `--surface`, `--ok-bg` e
  `--info-bg` superan 4.5:1 con los valores actuales; el test lo calcula.

## Excepciones

Ninguna nueva. Se reutilizan `DomainError`, `ValidationError` y
`_error_page` / `_domain_error` tal como están.

## Dependencias nuevas

Ninguna.

## Decisiones por defecto (no bloquean)

1. **Lados y colores**: cliente a la izquierda (fondo `--surface`); asesor y
   asistente a la derecha, asesor con `--ok-bg` y asistente con `--info-bg`.
   Además del color, cada burbuja lleva la etiqueta de autor (no depende solo
   del color).
2. **Etiqueta del asistente**: se mantiene `Bot` (`ROLE_LABELS` sin cambios)
   porque un test de #41 la fija; cambiarla a `Asistente` es un cambio de una
   línea que queda fuera de esta feature.
3. **Hora**: no hay zona horaria configurada en el proyecto. El servidor emite
   `dd/mm HH:MM UTC` (explícito, funciona sin JS) y el script la convierte a la
   hora local del navegador del asesor. No se añade variable de entorno.
4. **Después de enviar desde el chat** se vuelve al mismo caso (R19); la nueva
   burbuja es la confirmación. Desde la página de inicio no cambia nada.
5. **Etiqueta visible en vez de `placeholder`**: `Escribe un mensaje` va como
   `<label>` visible; un `placeholder` no sirve de etiqueta accesible y
   obligaría a cambiar la etiqueta `textarea` que fijan tests existentes.
6. **Autoscroll sin JS o con `panel_live_enabled` apagado**: no hay; el chat
   abre arriba dentro de su caja con scroll. Es la mejora progresiva acordada.
7. **Encabezado `Historial`** se conserva dentro de la cabecera del chat (lo
   usa un test de #49 para comprobar el orden frente a las notas).
8. **Sin separadores por día**: cada burbuja lleva fecha corta y hora.

## Alternativas descartadas

- **Anexar por JS solo los mensajes nuevos** (cursor o `since`): exige ruta o
  parámetros nuevos y lógica de deduplicación en el cliente. El reemplazo
  completo de #53 ya es idempotente y basta con sacar el compositor de la
  región reemplazada.
- **Segundo archivo JS (`chat.js`) para que el autoscroll funcione con el
  panel en vivo apagado**: rompería los tests de #53 que exigen un único
  `<script` y ninguno con el interruptor apagado.
- **Variable `PANEL_TIMEZONE`**: añade configuración, `render.yaml`,
  `.env.example` y posible dependencia `tzdata` en Windows para algo que el
  navegador resuelve solo.
- **Enviar con `fetch` sin recargar**: duplica la lógica de errores y CSRF en
  el cliente y deja de funcionar igual sin JS; el POST con redirección al caso
  da el mismo resultado visible.

## Tests existentes

No se edita ni se borra ningún test existente. Se revisaron los que fijan el
HTML afectado y siguen siendo válidos con este diseño:
`test_panel_case_view.py` (etiquetas `Cliente`/`Bot`/`Asesor` y orden),
`test_notes.py` (`Historial` antes de `Notas internas`),
`test_panel_reply.py` y `test_saved_replies_advisor.py` (etiqueta exacta del
`textarea`, `<select name="template">`, `name="respuesta"`),
`test_panel_live_fragments.py` (fragmento sin `<form`, sin duplicados),
`test_panel_live_js.py` (un solo `<script`), `test_panel_visual.py`
(`id="live-region"`, atributos `data-*`, tablas envueltas, sin `style=`) y
`test_advisor_panel.py` (`/asesor?ok=reply` sin `origen`). Si alguno fallara,
el implementer lo anota en `progress/impl_chat_caso_asesor.md` en lugar de
modificarlo.
