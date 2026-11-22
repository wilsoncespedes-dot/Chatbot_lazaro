# Design — #67 `etiqueta_origen_canal`

## 1. Resumen

Un componente puro `channel_label.py` renderiza la etiqueta. Una función de
dominio resuelve `id -> ChannelLabel` con una sola consulta a `ChannelDirectory`
(#65) y las rutas pasan el mapa a los renderizadores del panel. El gateway,
los contratos y el esquema de base de datos no cambian.

## 2. Archivos

- Nuevo `services/orchestrator/orchestrator/channel_label.py` (puro, sin IO):
  - `NEUTRAL_COLOR = "#5B6470"`, `UNKNOWN_NAME = "Canal desconocido"`, `UNKNOWN_GLYPH = "❔"`.
  - `@dataclass(frozen=True) ChannelLabel(name: str, glyph: str, color: str, known: bool)`.
  - `label_from_policy(policy: ChannelPolicy) -> ChannelLabel`: glifo con `icon_glyph` (R5); color a `NEUTRAL_COLOR` si no es `#RRGGBB` o `contrast_ratio(color, "#FFFFFF") < 4.5` (R4); `known=policy.known`.
  - `unknown_label() -> ChannelLabel` (R6).
  - `render_channel_label(label: ChannelLabel) -> str` (R1-R3, R20): `<svg class="channel-label" role="img" aria-label="nombre">` con `<rect fill>` y `<text fill="#FFFFFF">`; todo con `html.escape`. Mueve aquí la lógica de `admin._channel_label`, que pasa a delegar (misma salida visual en `/admin/canales`).
- `channels.py`: `ChannelPolicy.known: bool = True`; `default_policy` pone `known=False`. Un id ausente del directorio ya devuelve `default_policy` (#65 R14), así se distingue sin cambiar firmas.
- `domain.py`:
  - `HistoryItem.channel: str = ""`; `_case_history` lo rellena con `contact.channel` (R12).
  - `channel_labels(adapters, ids: Iterable[str]) -> dict[str, ChannelLabel]`: una llamada a `adapters.channels.list_policies()`; ids ausentes -> `unknown_label()`; `ServiceUnavailable` -> todos `unknown_label()` y log `channel_directory_unavailable` (R7). Nunca lanza.
- `advisor_panel.py`: los renderizadores reciben `labels: Mapping[str, ChannelLabel] = {}` y usan el helper `_label(labels, channel_id)` (cae a `unknown_label()` si falta):
  - `render_inbox_table(..., labels)` columna Canal (R9).
  - `render_history_fragment(history, labels)` etiqueta en cada burbuja (R11).
  - `_chat_block` encabezado (R10), `_client_section` (R13), `_memory_section` y `render_advisor_memory` (R14), vía `render_advisor_case` y `render_advisor_cases`.
- `advisor_routes.py` y `panel_live_routes.py`: tras obtener filas, historial o vista, `labels = channel_labels(adapters, {ids usados})` y se pasa a los renderizadores, incluidos `live_inbox` (R18) y `live_case` (R19).
- CSS del panel: `.channel-label { vertical-align: middle; }` (sin `style` en línea).
- Filtro (R15-R17): ya implementado en #65 (`inbox_channel_options`, validación en `advisor_inbox`). No se cambia; se cubre con pruebas de regresión que incluyen un canal inactivo y la combinación con `asignacion` y `tag`.

## 3. Excepciones

Ninguna nueva. `ServiceUnavailable` del directorio se absorbe en `channel_labels`; el filtro mantiene `UpstreamError` y `PanelValidationError` de #65.

## 4. Nota sobre «varios canales»

Hoy `messages` pertenece a un `contact` (canal + id externo), así que todos los mensajes de un caso comparten canal. La etiqueta se calcula por mensaje (`HistoryItem.channel`) para que un historial unificado futuro por cliente funcione sin cambiar la vista.

## 5. Alternativas descartadas

1. Etiqueta con `style="background:..."`: la CSP bloquea estilos en línea; se usa SVG como en #66.
2. Consultar el directorio por cada fila o mensaje: N llamadas; se resuelve un mapa por petición.
3. Añadir columna `channel` a `messages`: migración innecesaria; el canal se deriva del contacto.

## 6. Supuestos (defaults seguros)

- S1 Color neutro `#5B6470` (contraste ≈ 5.9:1 con blanco) para colores ilegibles y canal desconocido.
- S2 Si el directorio cae, el panel sigue funcionando con etiquetas «Canal desconocido» en lugar de error.
- S3 El filtro no marca los canales inactivos; se listan por su nombre.
