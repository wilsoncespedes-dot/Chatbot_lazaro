# Requirements — fechas_y_formularios_panel (#61)

Servicio: `orchestrator` (paneles `/admin` y `/asesor`). Pedido del usuario:
fechas más fáciles de leer en todo el panel y formularios/acciones simétricos.

## R1
El sistema DEBE mostrar las fechas con hora como "17 nov 2026, 2:33 p. m."
(día, mes abreviado, año, reloj de 12 horas, sin segundos) en la zona del
negocio; las fechas sin hora DEBEN mostrarse como "31 may 2026".

## R2
Cada fecha mostrada DEBE ir en un `<time>` cuyo atributo `datetime` conserve
el valor ISO exacto y cuyo `title` indique la zona ("Hora local (UTC−5)").

## R3
La zona de visualización DEBE tomarse de `BUSINESS_HOURS_UTC_OFFSET_MINUTES`
al crear la aplicación.

## R4
Ninguna página del panel DEBE mostrar fechas ISO en el texto visible, y el
script del panel en vivo DEBE reescribir las horas con el mismo formato.

## R5
Los formularios de alta de Plantillas, Respuestas guardadas, Categorías,
Etiquetas, Clientes y Manuales DEBEN usar una cuadrícula con los campos
alineados arriba, las áreas de texto a todo el ancho y el botón debajo.

## R6
Las acciones de cada cliente (Renovar, Revocar, Cerrar sesión) DEBEN
mostrarse en una fila con botones del mismo ancho.
