# Requirements — panel_tiempo_real (#53)

> Servicio: **orchestrator** (única parte tocada). No cambia contratos entre servicios
> (el websocket es del panel, no una ruta interna) ni toca `handover`, `gateway` ni `rag`.
> Dependencias: #41 (panel de asesores) y #49 (cola/presencia).

## Websocket — autenticación y origen

## R1
El sistema DEBE exponer en el orchestrator un websocket `GET /asesor/ws` (esquema `ws`/`wss`) por el que el servidor envía eventos de panel a la bandeja y a la vista de conversación.

## R2
SI una conexión a `/asesor/ws` llega sin la cookie `advisor_session`, con una sesión inexistente o expirada, o con un perfil cuyo rol no es `asesor` ni `supervisor` ENTONCES el sistema DEBE rechazar el handshake antes de aceptarlo y no enviar ningún evento.

## R3
SI una conexión a `/asesor/ws` llega sin cabecera `Origin` o con un `Origin` que no está permitido ENTONCES el sistema DEBE rechazar el handshake antes de aceptarlo, incluso con sesión válida.

## R4
DONDE `PANEL_WS_ALLOWED_ORIGINS` contenga uno o más orígenes, el sistema DEBE permitir únicamente los orígenes que coincidan de forma exacta (esquema, host y puerto) con esa lista.

## R5
DONDE `PANEL_WS_ALLOWED_ORIGINS` esté vacío, el sistema DEBE permitir únicamente el `Origin` cuyo host y puerto coincidan con la cabecera `Host` de la petición.

## R6
MIENTRAS una conexión de `/asesor/ws` está abierta, el sistema DEBE revalidar la sesión en cada ciclo de sondeo y cerrar la conexión con código `4401` cuando la sesión ya no sea válida (logout, expiración o perfil sin rol de panel).

## R7
SI una conexión solicita `scope=all` y el rol de la sesión no es `supervisor` ENTONCES el sistema DEBE rechazar el handshake antes de aceptarlo.

## R8
El sistema NO DEBE renovar la presencia del asesor (`touch_advisor_presence`) por abrir, mantener o cerrar una conexión de `/asesor/ws`.

## R9
SI una conexión excede `PANEL_WS_MAX_CONNECTIONS_PER_PROFILE` conexiones abiertas simultáneas del mismo perfil en la instancia ENTONCES el sistema DEBE rechazar el handshake antes de aceptarlo.

## R10
SI el cliente envía cualquier mensaje por `/asesor/ws` ENTONCES el sistema DEBE cerrar la conexión con código `1003` sin ejecutar ninguna acción.

## Websocket — autorización por caso y contenido

## R11
El sistema DEBE entregar a una conexión únicamente eventos cuyo `case_id` esté en el resultado de `handover.list_cases(advisor_id, scope)` del perfil de la sesión (`scope=mine` por defecto, `all` solo para supervisor).

## R12
SI `handover` no está disponible al autorizar un lote de eventos ENTONCES el sistema NO DEBE entregar ningún evento de ese lote y DEBE registrar un error sin datos del cliente.

## R13
El sistema DEBE limitar cada evento enviado a las claves `type`, `id` y `case_id` (más `type="hello"` con `cursor`), sin tokens, `csrf_token`, texto de mensajes, nombres, identificadores externos de canal ni datos de otros clientes.

## R14
CUANDO se abre una conexión autorizada, el sistema DEBE enviar como primer mensaje `{"type": "hello", "cursor": <id del último evento existente>}` antes de cualquier evento.

## Publicación de eventos y multi-instancia

## R15
CUANDO el orchestrator guarda un mensaje de rol `user`, `bot` o `advisor` en `add_message`, el sistema DEBE insertar un evento `message` para el caso vinculado más reciente del contacto en la misma transacción que el mensaje.

## R16
CUANDO el orchestrator enlaza un caso nuevo a un contacto (`link_case`), el sistema DEBE publicar un evento `case_created` para ese caso.

## R17
CUANDO una acción de panel o de escalamiento sobre un caso (`assign`, `transfer`, `reassign`, `close`, `return`, `reply`) termina con éxito, el sistema DEBE publicar un evento `case_updated` para ese caso.

## R18
SI la publicación de un evento falla ENTONCES el sistema NO DEBE hacer fallar la acción ni el procesamiento del mensaje que la originó y DEBE registrar el error con `logging`.

## R19
El sistema DEBE almacenar los eventos en una tabla compartida de Postgres (`panel_events`) y cada conexión DEBE sondearla cada `PANEL_EVENTS_POLL_SECONDS`, de modo que un evento publicado por cualquier instancia o proceso llegue a conexiones de cualquier otra instancia.

## R20
El sistema DEBE entregar cada `id` de evento como máximo una vez por conexión, aunque el sondeo relea eventos dentro de la ventana de solape.

## R21
CUANDO se publica un evento, el sistema DEBE borrar los eventos más antiguos que `PANEL_EVENTS_RETENTION_HOURS`.

## R22
CUANDO se ejecuta una supresión de datos de un cliente (`execute_suppression`), el sistema DEBE borrar los eventos de `panel_events` de los casos purgados.

## Fragmentos en vivo (recuperación de estado)

## R23
El sistema DEBE exponer `GET /asesor/live/inbox` (misma sesión, mismos filtros `canal`, `asignacion`, `tag` y `scope`, mismas reglas de `advisor_inbox`/`advisor_all_cases`) que devuelve solo el HTML de la tabla de casos.

## R24
El sistema DEBE exponer `GET /asesor/live/cases/{case_id}` que devuelve solo el HTML del historial del caso, autorizado con la misma regla que la vista de caso (`handover.authorize(..., "reply")`) y sin registrar el evento `memory_viewed` ni la auditoría `case_viewed`.

## R25
SI el caso de `/asesor/live/cases/{case_id}` no está autorizado para el asesor ENTONCES el sistema DEBE responder `403` (o `404` si no existe) sin devolver contenido del caso.

## R26
SI una petición a `/asesor/live/*` llega sin sesión válida ENTONCES el sistema DEBE redirigir a `/asesor/login` como el resto del panel.

## JavaScript, CSP y degradación

## R27
El sistema DEBE servir el JavaScript propio del panel desde el mismo origen en `GET /asesor/static/panel_live.js` con `Content-Type: text/javascript`, y las páginas de bandeja y de caso DEBEN referenciarlo con `<script src="/asesor/static/panel_live.js" defer>`.

## R28
El sistema NO DEBE incluir en el JavaScript ni en el HTML del panel de asesores `eval`, `new Function`, `setTimeout`/`setInterval` con cadenas, scripts inline, manejadores `on*=` ni referencias a hosts externos o CDN.

## R29
El sistema DEBE responder todas las páginas del panel de asesores con una `Content-Security-Policy` que incluya `default-src 'self'`, `script-src 'self'`, `connect-src 'self'`, `form-action 'self'`, `frame-ancestors 'none'`, `base-uri 'none'` y `object-src 'none'`, y no contenga `unsafe-inline` ni `unsafe-eval`.

## R30
CUANDO el JavaScript recibe un evento (`message`, `case_created` o `case_updated`) relevante para la página abierta, el sistema DEBE refrescar la región en vivo pidiendo el fragmento correspondiente y reemplazando su contenido (nunca anexando), de modo que no haya mensajes duplicados.

## R31
CUANDO el websocket se conecta o reconecta y llega `hello`, el JavaScript DEBE pedir el fragmento actual y reemplazar la región en vivo, de modo que el estado se recupere sin perder mensajes.

## R32
SI el websocket falla, se cierra o es rechazado ENTONCES el JavaScript DEBE reintentar con espera exponencial acotada y, mientras no esté conectado, DEBE sondear el fragmento cada `ADVISOR_INBOX_REFRESH_SECONDS` segundos.

## R33
MIENTRAS el navegador no ejecuta JavaScript, el sistema DEBE seguir sirviendo la bandeja con la recarga periódica actual (`<meta http-equiv="refresh">` dentro de `<noscript>` con `ADVISOR_INBOX_REFRESH_SECONDS`) y la misma tabla renderizada en servidor.

## R34
El sistema DEBE mantener responder, transferir, cerrar, devolver y reasignar como formularios `POST` con `csrf_token`, sin ninguna acción disponible por el websocket ni por `/asesor/live/*`.

## R35
DONDE `PANEL_LIVE_ENABLED` sea `false`, el sistema DEBE rechazar el handshake de `/asesor/ws` y omitir el `<script>` de las páginas, conservando la recarga periódica de R33.

## Trazabilidad con el acceptance

| Acceptance | R |
|---|---|
| 1 Bandeja/caso en vivo con websocket autenticado con la sesión | R1, R2, R14–R17, R19, R23, R24, R30 |
| 2 Rechazo sin sesión / Origin ajeno; autorización por caso | R2–R7, R9–R12, R25 |
| 3 JS propio mismo origen, CSP estricta, eventos sin secretos | R13, R27–R29 |
| 4 Degradación sin JS/ws; acciones con CSRF | R32–R35 |
| 5 Multi-instancia / otro proceso; recuperación al reconectar | R15, R19–R22, R31 |
| 6 Pruebas, `./init.sh` verde, reviewer | tasks T12–T16 (cada R tiene test; ver `tasks.md`) |
