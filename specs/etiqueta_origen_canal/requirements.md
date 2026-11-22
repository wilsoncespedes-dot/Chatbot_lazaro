# Requirements — #67 `etiqueta_origen_canal`

Servicio: `orchestrator` (panel de asesores). El gateway y los contratos no cambian.
La etiqueta = ícono + nombre + color del canal, tomados de `canales` vía
`ChannelDirectory` (#65). Es un único componente (`channel_label.py`) que reutilizará #75.

## Componente

## R1
El sistema DEBE ofrecer un único componente `render_channel_label` que genere la etiqueta como `<svg>` con el emoji del ícono y el nombre del canal como texto visible, sobre el color del canal.

## R2
El sistema DEBE escapar HTML en el nombre, el ícono y el color de la etiqueta antes de insertarlos en el marcado.

## R3
El sistema NO DEBE depender solo del color: la etiqueta DEBE incluir el nombre del canal como texto y como `aria-label`.

## R4
SI el color del canal no es `#RRGGBB` o su contraste contra `#FFFFFF` es menor que 4.5 ENTONCES el sistema DEBE pintar la etiqueta con el color neutro `#5B6470` conservando el nombre.

## R5
SI el ícono del canal no está en `CHANNEL_ICONS` ENTONCES el sistema DEBE usar el glifo del ícono por defecto.

## R6
SI el id de canal no existe en el directorio ENTONCES el sistema DEBE mostrar la etiqueta neutra «Canal desconocido» sin lanzar error.

## R7
SI el directorio de canales no está disponible al pintar etiquetas ENTONCES el sistema DEBE mostrar la etiqueta neutra «Canal desconocido» y NO DEBE responder error.

## R8
MIENTRAS un canal está desactivado, el sistema DEBE seguir mostrando su etiqueta (nombre, ícono y color) en la bandeja, el chat y el historial.

## Ubicaciones

## R9
El sistema DEBE mostrar la etiqueta del canal en la columna «Canal» de cada conversación de la tabla de la bandeja (vistas `/asesor/cases` y `/asesor/todos`).

## R10
El sistema DEBE mostrar la etiqueta del canal en el encabezado del chat abierto del caso.

## R11
El sistema DEBE mostrar la etiqueta del canal en cada mensaje del historial del chat, tomada del canal de ese mensaje (`HistoryItem.channel`).

## R12
El sistema DEBE rellenar `HistoryItem.channel` con el canal del contacto al que pertenece cada mensaje.

## R13
El sistema DEBE mostrar la etiqueta del canal en la ficha del cliente del caso (con y sin cliente autenticado).

## R14
El sistema DEBE mostrar la etiqueta del canal en la columna «Canal» de la tabla de resúmenes del historial del cliente, tanto en la vista del caso como en `/asesor/cases/{id}/memoria`.

## Filtro

## R15
El sistema DEBE ofrecer en el filtro de canal de la bandeja una opción por cada canal registrado en el directorio, incluidos los desactivados, sin lista fija.

## R16
CUANDO se filtra por `canal` junto con `asignacion` y `tag`, el sistema DEBE devolver solo los casos que cumplan los tres filtros.

## R17
SI el valor de `canal` no corresponde a un canal del directorio ENTONCES el sistema DEBE responder `422` con el mensaje de filtro inválido existente.

## En vivo

## R18
CUANDO `GET /asesor/live/inbox` actualiza la tabla, el sistema DEBE devolver las filas con la misma etiqueta que la carga inicial.

## R19
CUANDO `GET /asesor/live/cases/{id}` actualiza el historial, el sistema DEBE devolver los mensajes con la misma etiqueta por mensaje que la carga inicial.

## Seguridad

## R20
El sistema DEBE servir la etiqueta sin estilos ni scripts en línea, de modo que cumpla `PANEL_CSP`.

## Cobertura de pruebas

## R21
El sistema DEBE tener pruebas por cada ubicación (R9-R14), el filtro (R15-R17), la vista en vivo (R18, R19), canal inactivo (R8), canal desconocido (R6, R7) y escape de nombre e ícono (R2).
