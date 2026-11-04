# #40 memoria_por_cliente — Requirements

Servicio afectado: **orchestrator**. Ningún otro servicio cambia su código y no
se modifica ningún contrato de `contracts/` (ver design, alternativas
descartadas). Se apoya en #27 (purga de retención), #36 (contactos por canal),
#38 (sesiones de cliente, `active_client_id`, `end_client_session`) y #39
(harness, `suppression_requests`, `_tool_escalate`).

Vocabulario:

- **cliente_id**: `profile_id` de una sesión de cliente (`client_sessions`, #38).
- **Conversación**: una sesión de cliente (`client_sessions.id`). Pertenece a un
  único `profile_id` y a un único `contact_id` (un chat de un canal).
- **Ventana de la conversación**: mensajes de `messages` con
  `contact_id = session.contact_id`, `session.started_at <= at`,
  `at <= (session.ended_at o ahora)` y
  `at < session.last_activity_at + session_idle_minutes` (política de identidad
  vigente, #38). Función pura `session_window`.
- **Resumen de conversación**: fila de `conversation_summaries` (una por
  conversación) con el texto `summary` generado por el LLM.
- **Memoria permanente**: fila de `client_memory` (una por `profile_id`) con una
  lista ordenada de elementos de texto (`items`).
- **Resumidor**: llamada `llm.complete(MEMORY_SUMMARY_PROMPT, user)` que devuelve
  el JSON `{"resumen": <texto>, "memoria": [<texto>, ...]}`.
- **Filtro de sensibles**: función pura `is_sensitive(text, keywords,
  min_digits)`; es verdadera si `normalize_text(text)` contiene alguna frase de
  `MEMORY_SENSITIVE_KEYWORDS`, una secuencia de al menos
  `MEMORY_SENSITIVE_MIN_DIGITS` dígitos (admitiendo separadores espacio, punto o
  guion entre ellos) o una dirección de correo.
- **Ejecutor de supresión**: perfil del personal cuyo `role` pertenece a
  `SUPPRESSION_EXECUTOR_ROLES`.

Trazabilidad con el acceptance de `feature_list.json` (#40):

| Acceptance | Requirements |
|---|---|
| A1 al cerrar o resumir se conserva resumen y memoria del cliente autenticado, sin mezclar chats ni clientes | R1–R14 |
| A2 la memoria nunca contiene contraseñas ni datos sensibles y se entrega a la IA solo para el cliente autenticado | R15–R26 |
| A3 el asesor consulta la memoria dentro de sus permisos de caso | R27–R34, R55, R56 |
| A4 la supresión ejecutada por persona elimina memoria e historiales de la solicitud; la retención no elimina memoria | R35–R47, R53 |
| A5 pruebas de continuidad entre sesiones/canales, aislamiento y borrado; `./init.sh` verde | R48–R52, R54 |

## Generación de resumen y memoria

## R1
DONDE `MEMORY_ENABLED=true`, CUANDO `end_client_session` cierra una sesión con
un motivo distinto de `suppression` (es decir, `repository.end_client_session`
devuelve `True`), el orchestrator DEBE invocar al resumidor con los mensajes de
la ventana de esa conversación.

## R2
DONDE `MEMORY_ENABLED=true`, CUANDO `escalar_a_asesor` (#39) termina con
handover disponible para un contacto con sesión activa, el orchestrator DEBE
invocar al resumidor con los mensajes de la ventana de la conversación activa
y guardar solo el resumen (sin actualizar la memoria permanente).

## R3
CUANDO el resumidor devuelve una respuesta válida tras un cierre de sesión
(R1), el orchestrator DEBE guardar en `conversation_summaries` la fila de esa
`session_id` con `profile_id` y `contact_id` de la sesión, `channel` del
contacto, `summary`, `trigger = "session_end"` y la fecha.

## R4
CUANDO el resumidor devuelve una respuesta válida tras un escalamiento (R2), el
orchestrator DEBE guardar o reemplazar la fila de `conversation_summaries` de
esa `session_id` con `trigger = "escalation"`.

## R5
CUANDO se guarda un resumen de una `session_id` que ya tiene fila, el
orchestrator DEBE reemplazar su `summary` y `trigger` sin crear una segunda
fila para esa sesión.

## R6
CUANDO el resumidor devuelve una respuesta válida tras un cierre de sesión
(R1), el orchestrator DEBE reemplazar los `items` de `client_memory` del
`profile_id` de la sesión por la lista depurada de R16–R18.

## R7
DONDE `MEMORY_ENABLED=false` (valor por defecto), el orchestrator NO DEBE
llamar al resumidor ni escribir en `conversation_summaries` ni en
`client_memory`.

## R8
SI la ventana de la conversación no contiene mensajes ENTONCES el orchestrator
NO DEBE llamar al resumidor.

## R9
El mensaje de usuario que se envía al resumidor DEBE contener únicamente la
memoria actual del `profile_id` de la sesión y los mensajes de la ventana de
esa sesión (como máximo los últimos `MEMORY_INPUT_MAX_MESSAGES`), delimitados
como datos (`<memoria_actual>`, `<historial>`) y neutralizados contra el
cierre de esas etiquetas.

## R10
CUANDO dos clientes A y B tienen conversaciones en el mismo chat o en chats
distintos, el mensaje del resumidor para la sesión de A NO DEBE contener
mensajes de las ventanas de sesiones de B ni elementos de la memoria de B.

## R11
SI el resumidor lanza `ServiceUnavailable` o su respuesta no supera
`parse_summary_answer` (JSON inválido, claves distintas de `resumen` y
`memoria`, tipos incorrectos) ENTONCES el orchestrator NO DEBE modificar
`conversation_summaries` ni `client_memory`.

## R12
SI el resumidor falla o su respuesta es inválida (R11) ENTONCES el orchestrator
DEBE registrar el evento `memory_failed` con el motivo (`llm_unavailable` o
`invalid_summary`) y completar el cierre de sesión o el escalamiento como sin
esta feature.

## R13
CUANDO el resumidor se ejecuta, el orchestrator NO DEBE enviar ningún mensaje
al contacto por el gateway ni añadir mensajes a `messages`.

## R14
CUANDO una sesión del cliente P se cerró con memoria guardada y P inicia una
sesión nueva en otro chat (mismo canal u otro canal), el orchestrator DEBE
usar la misma fila de `client_memory` de P en la conversación nueva.

## Contenido de la memoria (sensibles)

## R15
El orchestrator NO DEBE incluir en el mensaje del resumidor los mensajes de la
ventana para los que `is_sensitive` es verdadero.

## R16
CUANDO se depura la memoria devuelta por el resumidor, el orchestrator DEBE
descartar cada elemento para el que `is_sensitive` es verdadero.

## R17
CUANDO se depura la memoria devuelta por el resumidor, el orchestrator DEBE
recortar espacios, descartar elementos vacíos y duplicados (por
`normalize_text`), truncar cada elemento a `MEMORY_ITEM_MAX_CHARS` y conservar
como máximo los primeros `MEMORY_MAX_ITEMS`.

## R18
CUANDO se depura el resumen devuelto por el resumidor, el orchestrator DEBE
eliminar cada oración (separada por `.`, `!`, `?` o salto de línea) para la que
`is_sensitive` es verdadero y truncar el resultado a
`MEMORY_SUMMARY_MAX_CHARS`.

## R19
El orchestrator NO DEBE guardar en `client_memory` ni en
`conversation_summaries` ningún texto para el que `is_sensitive` es verdadero.

## R20
El prompt de sistema del resumidor (`MEMORY_SUMMARY_PROMPT`) DEBE prohibir
guardar contraseñas, credenciales, números de documento, tarjetas o cuentas,
datos sensibles de la Ley 1581 (salud, vida sexual, biometría, origen étnico,
religión, política, sindicatos) y datos de otras personas.

## Entrega a la IA

## R21
DONDE `MEMORY_ENABLED=true`, CUANDO se ejecuta `buscar_base_conocimiento` para
un contacto con sesión activa, el orchestrator DEBE incluir en el mensaje de
usuario del LLM un bloque `<memoria>` con los elementos de `client_memory` del
`cliente_id` obtenido de `active_client_id(contact.id)`.

## R22
DONDE `MEMORY_ENABLED=true` y `MEMORY_CONTEXT_MESSAGES > 0`, CUANDO se ejecuta
`buscar_base_conocimiento` para un contacto con sesión activa, el orchestrator
DEBE incluir en el mensaje de usuario del LLM un bloque `<historial>` con los
últimos `MEMORY_CONTEXT_MESSAGES` mensajes de la ventana de la sesión activa
anteriores al mensaje actual.

## R23
SI el contacto no tiene sesión activa ENTONCES el orchestrator NO DEBE incluir
`<memoria>` ni `<historial>` en el prompt del LLM.

## R24
CUANDO el cliente A con sesión activa consulta, el prompt del LLM NO DEBE
contener elementos de memoria de otro cliente B, aunque el texto de A nombre a
B o su `profile_id`.

## R25
El orchestrator NO DEBE incluir memoria, resúmenes ni historial en el prompt del
router (#39 R17) ni en el prompt SQL de `consultar_mis_datos`.

## R26
DONDE `MEMORY_ENABLED=false`, el orchestrator DEBE construir el prompt de
`buscar_base_conocimiento` byte a byte igual que antes de esta feature
(`build_llm_prompt(question, chunks)` sin contexto).

## Consulta del asesor

## R27
CUANDO un asesor autenticado del panel pide `GET /asesor/cases/{case_id}/memoria`,
el orchestrator DEBE llamar a `handover.authorize(case_id, advisor_id, "reply")`
antes de leer `client_memory` o `conversation_summaries`.

## R28
SI handover deniega la autorización con `forbidden` ENTONCES el orchestrator
DEBE responder `403` con la página de error `forbidden` y registrar el evento
`advisor_forbidden` como en #13, sin mostrar memoria ni resúmenes.

## R29
SI handover responde `case_closed` ENTONCES el orchestrator DEBE responder
`409` con la página de error `case_closed` sin mostrar memoria ni resúmenes.

## R55
SI handover responde `not_found` o el caso no tiene contacto vinculado
ENTONCES el orchestrator DEBE responder `404` con la página de error
`not_found` sin mostrar memoria ni resúmenes.

## R56
SI handover no está disponible (`ServiceUnavailable`) ENTONCES el orchestrator
DEBE responder `502` con la página de error `upstream_error` sin mostrar
memoria ni resúmenes.

## R30
CUANDO la autorización de R27 es aceptada, el orchestrator DEBE mostrar los
elementos de `client_memory` y los últimos `MEMORY_PANEL_SUMMARIES` resúmenes
de `conversation_summaries` del `profile_id` guardado en el vínculo del caso.

## R31
CUANDO `_handover` vincula un caso nuevo (`link_case`), el orchestrator DEBE
guardar junto al vínculo el `profile_id` de la sesión activa del contacto en ese
momento, o nulo si no hay sesión.

## R32
SI el vínculo del caso no tiene `profile_id` ENTONCES la página de R30 DEBE
indicar "sin cliente autenticado" y NO DEBE mostrar memoria ni resúmenes.

## R33
CUANDO se muestra la página de R30, el orchestrator DEBE registrar el evento
`memory_viewed` con `case:<case_id> advisor:<advisor_id>` en el contacto del
caso.

## R34
La página de R30 DEBE escapar en HTML todo texto de memoria y resúmenes.

## Supresión y retención

## R35
El orchestrator DEBE ofrecer la función de dominio
`execute_suppression(request_id, actor_profile_id, settings, adapters)` como
única vía que borra memoria, resúmenes e historiales de una solicitud.

## R36
SI el perfil `actor_profile_id` no existe o su `role` no pertenece a
`SUPPRESSION_EXECUTOR_ROLES` ENTONCES `execute_suppression` DEBE lanzar
`SuppressionForbidden` (`403 forbidden`) sin borrar nada.

## R37
SI `request_id` no existe en `suppression_requests` ENTONCES
`execute_suppression` DEBE lanzar `SuppressionNotFound` (`404 not_found`) sin
borrar nada.

## R38
SI la solicitud no está en `status = "pending"` ENTONCES `execute_suppression`
DEBE lanzar `SuppressionNotPending` (`409 suppression_not_pending`) sin borrar
nada.

## R39
CUANDO se ejecuta una supresión válida y el `profile_id` de la solicitud tiene
una sesión activa, el orchestrator DEBE cerrarla con
`end_client_session(session, "suppression", notify=False)` antes de borrar.

## R40
CUANDO se ejecuta una supresión válida, el orchestrator DEBE borrar la fila de
`client_memory` del `profile_id` de la solicitud.

## R41
CUANDO se ejecuta una supresión válida, el orchestrator DEBE borrar todas las
filas de `conversation_summaries` del `profile_id` de la solicitud.

## R42
CUANDO se ejecuta una supresión válida, el orchestrator DEBE borrar de
`messages` los mensajes de las ventanas de todas las sesiones (`client_sessions`)
del `profile_id` de la solicitud.

## R43
CUANDO se ejecuta una supresión, el orchestrator NO DEBE borrar memoria,
resúmenes ni mensajes de otro `profile_id`, ni mensajes del mismo contacto
fuera de las ventanas de las sesiones del `profile_id` de la solicitud.

## R44
CUANDO termina una supresión válida, el orchestrator DEBE marcar la solicitud
con `status = "executed"`, `executed_at`, `executed_by = actor_profile_id` y
los recuentos borrados, en la misma transacción que los borrados de R40–R42.

## R45
CUANDO termina una supresión válida, el orchestrator DEBE registrar en
`identity_audit` la acción `suppression_executed` con el `profile_id` de la
solicitud y el motivo `request:<id> by:<actor_profile_id>`.

## R46
CUANDO se ejecuta cualquiera de las seis herramientas de #39 (incluida
`crear_solicitud_supresion`), el orchestrator NO DEBE borrar filas de
`client_memory` ni de `conversation_summaries`.

## R47
CUANDO se ejecuta la purga de retención (`POST /privacy/purge`, #27), el
orchestrator NO DEBE borrar ni modificar filas de `client_memory`.

## R53
CUANDO se ejecuta la purga de retención (#27), el orchestrator DEBE borrar las
filas de `conversation_summaries` con `updated_at < cutoff` e informar el número
en `deleted["conversation_summaries"]`.

## Pruebas y configuración

## R48
El orchestrator DEBE incluir una prueba de continuidad que cierre una sesión
del cliente P en un chat de Telegram, inicie otra de P en un chat de WhatsApp y
verifique que el prompt RAG de la segunda contiene un elemento de memoria de la
primera.

## R49
El orchestrator DEBE incluir pruebas de aislamiento que verifiquen R10 y R24
con dos clientes en el mismo chat y en chats distintos.

## R50
El orchestrator DEBE incluir una prueba de borrado que, tras
`execute_suppression`, verifique que el prompt RAG de una sesión nueva del
mismo cliente ya no contiene el elemento de memoria anterior.

## R51
CUANDO se ejecuta `./init.sh` con la feature implementada, todas las suites
existentes y nuevas DEBEN pasar (las de #6, #24, #27, #35–#39 sin cambios de
comportamiento con `MEMORY_ENABLED=false`).

## R52
El orchestrator DEBE leer de variables de entorno todas las variables nuevas de
la tabla de `design.md`, declaradas en `.env.example` con sus valores por
defecto.

## R54
SI una variable numérica nueva está fuera de su rango o
`SUPPRESSION_EXECUTOR_ROLES` está vacía o contiene un rol distinto de `admin` y
`asesor` ENTONCES `Settings` DEBE lanzar un error de validación al arrancar.
