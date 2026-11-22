# Requirements — #75 `dashboard_canales_svg`

Servicio: `orchestrator` (panel). Gateway, handover y contratos no cambian. Rutas nuevas
de solo lectura: `GET /admin/dashboard` (rol admin) y `GET /asesor/dashboard` (rol
supervisor). Reutiliza `admin_metrics`/`first_response_summary` (#42), la etiqueta de
canal (#67, `channel_label.py`) y `ChannelPolicy.simulated` (#62/#65).

Parámetros de query (ambas rutas): `dias` (entero 1-90, default 7; mismo rango que
`/admin/metricas`) y `simulados` (`incluir` por defecto, o `excluir`).

## Acceso y rango

## R1
El sistema DEBE ofrecer `GET /admin/dashboard` a sesiones con rol admin y `GET /asesor/dashboard` a sesiones con rol supervisor, y ambas DEBEN mostrar el mismo dashboard.

## R2
SI la petición al dashboard no trae sesión válida ENTONCES el sistema DEBE responder como el resto del panel (redirección a login) y NO DEBE calcular métricas.

## R3
SI la sesión del dashboard tiene un rol sin permiso (asesor en `/asesor/dashboard`, supervisor en `/admin/dashboard`) ENTONCES el sistema DEBE responder 403 sin datos del dashboard.

## R4
SI `dias` no es un entero entre 1 y 90 ENTONCES el sistema DEBE responder 422 `validation_error` como `/admin/metricas`.

## R5
SI `simulados` no es `incluir` ni `excluir` ENTONCES el sistema DEBE responder 422 `validation_error`.

## R6
CUANDO se muestra el dashboard, el sistema DEBE mostrar el intervalo `desde — hasta` calculado y un formulario GET sin JavaScript con los campos `dias` y `simulados` (valores actuales preseleccionados).

## R7
CUANDO se muestra el dashboard, el sistema DEBE registrar la auditoría `dashboard_viewed` con el rango como `target`, igual que `metrics_viewed`.

## R8
El sistema DEBE enlazar el dashboard desde la navegación del admin y desde la sección «Supervisión» del inicio del supervisor.

## Mensajes por canal

## R9
El sistema DEBE contar los mensajes (roles `user`, `bot` y `advisor`) del intervalo agrupados por canal del contacto y DEBE mostrar un gráfico de barras con una barra por canal.

## R10
El sistema DEBE rotular cada canal del dashboard con la etiqueta de #67 (`render_channel_label`/`channel_labels`) y NO DEBE definir otro componente de etiqueta.

## R11
SI un canal del conteo no existe en el directorio ENTONCES el sistema DEBE agruparlo con la etiqueta «Canal desconocido» sin error.

## R12
SI el directorio de canales no está disponible ENTONCES el sistema DEBE mostrar el dashboard con todas las etiquetas «Canal desconocido», sin marcar canales como simulados, y NO DEBE responder error.

## R13
SI hay más de `DASHBOARD_MAX_CHANNELS` (constante, 12) canales con mensajes ENTONCES el sistema DEBE mostrar en el gráfico los de mayor conteo y agrupar el resto en una barra «Otros», y la tabla de datos DEBE listar todos.

## Conversaciones por estado

## R14
El sistema DEBE mostrar un gráfico de barras con las conversaciones (casos) creadas en el intervalo agrupadas por estado `open`, `assigned`, `timed_out` y `closed`, con el estado en español legible, incluyendo estados con 0.

## R15
SI el servicio de handover no está disponible ENTONCES el sistema DEBE mostrar el gráfico de estados como no disponible con un aviso, y los demás gráficos DEBEN mostrarse sin error.

## Tiempos de respuesta

## R16
El sistema DEBE mostrar el tiempo de primera respuesta (minutos entre la creación del caso y el primer mensaje de asesor) con casos, respondidos, sin respuesta, mediana y p90, calculado con `case_first_responses` y `first_response_summary` existentes.

## R17
El sistema DEBE extender `FirstResponseSummary` con `p90_minutes` (percentil 90 por rango más cercano, `None` sin datos) sin cambiar `avg_minutes`, `median_minutes` ni lo que muestran `/admin/metricas` y `/asesor/metricas`.

## R18
El sistema DEBE calcular el tiempo de respuesta de asesor como los minutos entre cada mensaje de cliente sin responder y el siguiente mensaje de asesor del mismo contacto, y DEBE mostrar cantidad, mediana y p90.

## R19
SI un mensaje de cliente no tiene mensaje de asesor posterior, o el de asesor precede al de cliente, ENTONCES el sistema NO DEBE incluirlo en el cálculo de R18.

## R20
SI no hay datos para un tiempo de respuesta ENTONCES el sistema DEBE mostrar «—» en mediana y p90, sin error ni división por cero.

## R21
El sistema DEBE mostrar los tiempos de R16 y R18 como un gráfico de barras agrupado (mediana y p90 por medida) en minutos.

## Canales simulados

## R22
El sistema DEBE distinguir los canales simulados con el sufijo «SIMULADO» (`simulated_label`) en etiqueta, barra y tabla.

## R23
CUANDO `simulados=excluir`, el sistema DEBE excluir de los tres gráficos, de las tablas y de los tiempos los mensajes y casos de canales simulados.

## R24
MIENTRAS `simulados=incluir`, el sistema DEBE contar los canales simulados en todos los gráficos, marcados según R22.

## Reutilización

## R25
El sistema DEBE reutilizar `median_minutes`, `first_response_summary` y `case_first_responses` de las métricas existentes, y NO DEBE reimplementar la mediana ni la primera respuesta.

## R26
El sistema NO DEBE modificar lo que muestran `/admin/metricas` y `/asesor/metricas` (solo se añade `p90_minutes` al modelo).

## SVG, accesibilidad y CSP

## R27
El sistema DEBE generar cada gráfico como `<svg>` en el servidor mediante funciones puras sin IO, sin JavaScript, sin imágenes externas y sin atributos `style` ni elementos `<style>`/`<script>` dentro del SVG.

## R28
El sistema NO DEBE cambiar `PANEL_CSP` ni añadir scripts ni dependencias de terceros para el dashboard.

## R29
El sistema DEBE dar a cada gráfico un título visible (`<h3>`), `role="img"`, `<title>` y `<desc>` internos y `aria-labelledby`, con texto alternativo que resuma los datos.

## R30
El sistema DEBE acompañar cada gráfico de una tabla HTML de datos con `<caption>` y encabezados `<th scope>`, con los mismos valores que las barras.

## R31
El sistema DEBE escapar HTML en nombres de canal, de estado y cualquier valor de usuario, en SVG, título, descripción y tabla.

## R32
SI todos los valores de un gráfico son 0 o no hay datos ENTONCES el sistema DEBE mostrar un SVG válido con el texto «Sin datos» y una tabla con una fila «Sin datos», sin división por cero.

## R33
El sistema DEBE escalar las barras proporcionalmente al máximo del gráfico y DEBE usar el color de la etiqueta de #67 para canales y colores fijos con contraste ≥ 4.5 para estados y tiempos.

## R34
El sistema DEBE devolver las cabeceras de seguridad del panel (`panel_security_headers`) en el dashboard.
