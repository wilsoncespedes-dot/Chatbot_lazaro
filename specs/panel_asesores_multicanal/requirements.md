# #41 panel_asesores_multicanal — Requirements

Servicios afectados: **orchestrator** (panel de asesores, panel administrativo,
dominio y repositorio), **handover** (nueva ruta de transferencia) y
**contracts** (modelos aditivos de transferencia). `telegram_gateway`, `rag` y
`eval` no cambian. Se apoya en #29/#33 (panel de asesores, sesiones de
personal, CSRF y `GET /cases`), #36 (contactos por canal, `send_channel`, bloques
`TemplateBlock`), #37 (estados `with_advisor` / `active` y eventos
`ADVISOR_RESOLVED` / `ADVISOR_RETURNED`), #38 (sesiones y credenciales de
cliente), #39 (`suppression_requests`) y #40 (`advisor_client_memory`,
`execute_suppression`, resúmenes).

Vocabulario:

- **Asesor del panel**: perfil con `role = "asesor"` autenticado en `/asesor`
  con sesión de rol `asesor`. Su `advisor_id` ante handover es
  `str(profile.telegram_user_id)` (compatibilidad vigente, ver design S1).
- **Ejecutor de supresión**: perfil cuyo `role` pertenece a
  `SUPPRESSION_EXECUTOR_ROLES` (#40).
- **Contacto del caso**: `Contact` vinculado al caso en `case_links` (#40).
- **Ventana WhatsApp abierta**: para un contacto de canal `whatsapp`, existe un
  mensaje `role = "user"` con `now - at < WHATSAPP_WINDOW_HOURS` horas. Sin
  mensajes de cliente la ventana está cerrada. Un contacto `telegram` siempre
  admite texto libre. Función pura `channel_window(channel, last_user_at, now,
  hours)`.
- **Espera** de un caso: si no hay mensaje `advisor` posterior a la creación del
  vínculo del caso, `now - case_links.created_at`; si el último mensaje `user`
  es posterior al último mensaje `advisor`, `now - último user`; en otro caso,
  sin espera (`None`). Función pura `case_wait`.
- **Presencia efectiva**: `available` si el último estado guardado del asesor es
  `available` y `now - last_seen_at <= ADVISOR_PRESENCE_TTL_MINUTES`; en otro
  caso `away`.
- **Fecha límite de supresión**: `created_at` más
  `SUPPRESSION_DEADLINE_BUSINESS_DAYS` días hábiles (lunes a viernes, UTC,
  conservando la hora). Función pura `business_deadline`.
- **Auditoría del panel**: fila de la tabla `panel_audit` (actor, rol, acción,
  `case_id`, `request_id`, destino, resultado, fecha).

Trazabilidad con el acceptance de `feature_list.json` (#41):

| Acceptance | Requirements |
|---|---|
| A1 conversaciones escaladas de ambos canales en bandeja con canal, estado, espera y asignación, respetando roles y autorización por caso | R1–R13 |
| A2 responder, transferir, resolver y devolver; cada envío usa el adaptador del canal y respeta ventana/plantilla WhatsApp | R14–R39 |
| A3 historial, resumen, datos permitidos del cliente y memoria; auditoría sin exponer otros clientes | R40–R55 |
| A4 cola de supresión con prioridad y fecha límite; una persona autorizada ejecuta y registra el resultado | R56–R70 |
| A5 pruebas de ambos canales, permisos, auditoría, respuesta y supresión; `./init.sh` verde | R71–R74 (y los tests de todos los R) |

## Bandeja (orchestrator)

## R1
CUANDO un asesor del panel pide `GET /asesor/cases`, el orchestrator DEBE
mostrar únicamente los casos devueltos por `handover.list_cases(advisor_id)`
para su propio `advisor_id`.

## R2
CUANDO el orchestrator muestra la bandeja, el sistema DEBE pintar por cada caso
una fila con: identificador del caso, canal del contacto del caso
(`telegram` / `whatsapp`), estado del caso de handover, estado de conversación
del contacto (#37), asignación, espera, estado de ventana y nombre del cliente.

## R3
El sistema DEBE mostrar la asignación como `Mío` cuando el estado del caso es
`assigned` y como `Sin asignar` cuando es `open` o `timed_out`.

## R4
El sistema DEBE calcular la espera de cada fila con la función pura
`case_wait(link_created_at, last_user_at, last_advisor_at, now)` según el
vocabulario y mostrarla en minutos enteros, o `—` cuando es `None`.

## R5
El sistema DEBE mostrar el estado de ventana de cada fila como `Abierta`,
`Cerrada` o `No aplica` (Telegram) usando `channel_window`.

## R6
El sistema DEBE mostrar como nombre del cliente el `username` del perfil
vinculado al caso (`case_links.profile_id`) o `Sin autenticar` si el caso no
tiene perfil.

## R7
DONDE la petición incluye `canal=telegram|whatsapp` o
`asignacion=mias|sin_asignar`, el sistema DEBE mostrar solo las filas que
cumplen todos los filtros indicados.

## R8
SI un filtro de la bandeja trae un valor fuera de los permitidos ENTONCES el
sistema DEBE responder `422` con la página de error `validation_error` sin
consultar handover.

## R9
El sistema DEBE ordenar las filas de la bandeja por fecha de creación del caso
ascendente (la más antigua primero).

## R10
SI un caso listado no tiene contacto vinculado en `case_links` ENTONCES el
sistema DEBE pintar la fila con canal `desconocido`, sin estado de
conversación, espera ni datos de cliente, y sin fallar la página.

## R11
SI una sesión válida de un rol distinto de `asesor` (p. ej. `admin`) o sin
sesión pide cualquier ruta `/asesor/...` protegida ENTONCES el sistema DEBE
redirigir a `/asesor/login` sin consultar handover.

## R12
DONDE `ADVISOR_INBOX_REFRESH_SECONDS` es mayor que 0, la página de bandeja DEBE
incluir `<meta http-equiv="refresh" content="<valor>">`; con 0 NO DEBE incluirla.

## R13
El repositorio Postgres DEBE devolver en `get_case_contact` el `Contact`
completo (`id`, `channel`, `external_user_id`, `external_chat_id`,
`telegram_user_id`, `chat_id`), de modo que un caso WhatsApp conserve su canal
y destino.

## Respuesta y ventana (orchestrator)

## R14
CUANDO un asesor del panel envía `POST /asesor/reply` con `case_id` y `text`
válidos y autorizados, el sistema DEBE entregar el texto con el adaptador del
canal del contacto: `gateway.send(chat_id, text)` para Telegram con `chat_id`
y `gateway.send_channel("whatsapp", external_chat_id, text)` para WhatsApp.

## R15
SI el formulario de `POST /asesor/reply` no trae exactamente uno de `text` o
`template` ENTONCES el sistema DEBE responder `422` `validation_error` sin
autorizar ni enviar.

## R16
MIENTRAS la ventana WhatsApp del contacto del caso está cerrada, el sistema
DEBE rechazar una respuesta de texto libre con `409` `channel_window_closed`
sin llamar al gateway ni guardar mensaje.

## R17
CUANDO un asesor envía `template` con la ventana WhatsApp cerrada y el nombre
pertenece a `ADVISOR_WHATSAPP_TEMPLATES`, el sistema DEBE enviar
`gateway.send_channel_blocks("whatsapp", external_chat_id,
[TemplateBlock(type="template", name=<nombre>)])`.

## R18
CUANDO se envía con éxito una plantilla (R17), el sistema DEBE guardar el
mensaje `advisor` con el texto `[plantilla:<nombre>]` y el evento
`advisor_reply` igual que una respuesta de texto.

## R19
SI el nombre de plantilla no pertenece a `ADVISOR_WHATSAPP_TEMPLATES`
ENTONCES el sistema DEBE responder `422` `validation_error` sin llamar al
gateway.

## R20
SI se pide una plantilla para un contacto Telegram o con la ventana WhatsApp
abierta ENTONCES el sistema DEBE responder `422` `validation_error` sin llamar
al gateway.

## R21
SI el gateway responde `422` a un envío del panel ENTONCES el cliente HTTP del
gateway DEBE lanzar `ChannelRejected` (subclase de `ServiceUnavailable`) y el
panel DEBE responder `409` `channel_window_closed` sin guardar mensaje.

## R22
CUANDO el comando Telegram `/responder` apunta a un caso WhatsApp con la
ventana cerrada, el sistema DEBE contestar al asesor con
`ADVISOR_COMMAND_FAILED_REPLY` sin enviar texto al cliente.

## R23
El sistema DEBE autorizar con `handover.authorize(case_id, advisor_id,
"reply")` antes de comprobar la ventana o enviar cualquier respuesta o
plantilla.

## R24
CUANDO se muestra la vista de un caso WhatsApp con la ventana cerrada, el
sistema DEBE pintar un selector con las plantillas de
`ADVISOR_WHATSAPP_TEMPLATES` en lugar del campo de texto libre.

## R25
CUANDO se muestra la vista de un caso Telegram o WhatsApp con ventana abierta,
el sistema DEBE pintar el campo de texto libre y NO DEBE pintar el selector de
plantillas.

## Transferencia (contracts, handover, orchestrator)

## R26
`lazaro_contracts` DEBE exponer `CaseTransferRequest(advisor_id: Identifier,
target_advisor_id: Identifier)` y `CaseTransferResponse(status:
Literal["assigned"], case_id: Identifier, advisor_id: Identifier)`, con
ejemplos en `contracts/examples/` y la ruta documentada en
`contracts/CONTRATOS.md`.

## R27
CUANDO handover recibe `POST /cases/{id}/transfer` con `X-Service-Token`
válido, el caso está `assigned` al `advisor_id` y `target_advisor_id` es un
asesor registrado distinto, handover DEBE reasignar el caso a
`target_advisor_id` con `assigned_at = now` y responder `200`
`CaseTransferResponse`.

## R28
SI `advisor_id` no es asesor registrado o el caso no está `assigned` a ese
`advisor_id` ENTONCES handover DEBE registrar una denegación con acción
`transfer` y responder `403` `forbidden` sin modificar el caso.

## R29
SI `target_advisor_id` no es asesor registrado o es igual a `advisor_id`
ENTONCES handover DEBE responder `422` `validation_error` sin modificar el
caso.

## R30
SI el caso no existe ENTONCES handover DEBE responder `404` `not_found`; SI está
cerrado ENTONCES DEBE responder `409` `case_closed`.

## R31
SI la escritura condicional de transferencia no modifica filas ENTONCES
handover DEBE releer el caso y responder `200` si ya está asignado a
`target_advisor_id`, o `403` `forbidden` en otro caso.

## R32
CUANDO un asesor del panel envía `POST /asesor/transfer` con `case_id` y
`target_profile_id`, el orchestrator DEBE llamar
`handover.transfer(case_id, advisor_id, str(target.telegram_user_id))` solo si
el destino es un perfil `asesor` con `telegram_user_id`, distinto del actor y
con presencia efectiva `available`.

## R33
SI el perfil destino no existe, no es `asesor`, no tiene `telegram_user_id` o
es el propio actor ENTONCES el orchestrator DEBE responder `422`
`validation_error` sin llamar a handover.

## R34
SI el perfil destino tiene presencia efectiva `away` ENTONCES el orchestrator
DEBE responder `409` `advisor_unavailable` sin llamar a handover.

## R35
CUANDO la transferencia termina con éxito, el orchestrator DEBE registrar el
evento `advisor_transfer` en el contacto del caso con
`case:<id> from:<advisor_id> to:<target_advisor_id>`.

## Resolver y devolver (orchestrator)

## R36
CUANDO un asesor del panel envía `POST /asesor/close`, el sistema DEBE
conservar el comportamiento de resolver: autorizar `close`, cerrar en
handover, avisar con `CASE_CLOSED_REPLY` y aplicar `ADVISOR_RESOLVED`.

## R37
CUANDO un asesor del panel envía `POST /asesor/return` con un caso autorizado
para `close`, el sistema DEBE cerrar el caso en handover, enviar
`ADVISOR_RETURN_REPLY` por el canal del contacto y aplicar
`ADVISOR_RETURNED` (estado `with_advisor` → `active`).

## R38
CUANDO se devuelve un caso, el sistema DEBE registrar el evento
`advisor_returned` con `case:<id> advisor:<advisor_id>` en el contacto.

## R39
MIENTRAS la ventana WhatsApp del contacto está cerrada, el aviso de resolver o
devolver NO DEBE enviarse al gateway; el sistema DEBE cerrar el caso igual y
registrar el evento `notice_skipped` con `window_closed`.

## Vista de conversación (orchestrator)

## R40
CUANDO un asesor del panel pide `GET /asesor/cases/{case_id}`, el sistema DEBE
autorizar con `handover.authorize(case_id, advisor_id, "reply")` antes de leer
contacto, mensajes, memoria o datos de cliente.

## R41
SI la autorización de R40 es denegada ENTONCES el sistema DEBE responder la
página de error correspondiente (`403` / `404` / `409` / `502`) sin leer
mensajes, memoria ni datos de cliente.

## R42
CUANDO la vista se autoriza, el sistema DEBE mostrar los mensajes del contacto
del caso con `at >= case_links.created_at - ADVISOR_HISTORY_LOOKBACK_MINUTES`,
como máximo los últimos `ADVISOR_HISTORY_MAX_MESSAGES`, en orden cronológico.

## R43
El sistema DEBE marcar cada mensaje del historial con una etiqueta distinta por
rol: `Cliente` (`user`), `Bot` (`bot`) y `Asesor` (`advisor`).

## R44
El historial NO DEBE incluir mensajes cuyo `at` cae dentro de la ventana de
sesión (`session_window`, #40) de un perfil distinto del perfil del caso; si el
caso no tiene perfil, NO DEBE incluir mensajes dentro de la ventana de sesión de
ningún perfil.

## R45
CUANDO la vista se autoriza y el caso tiene perfil, el sistema DEBE mostrar la
memoria y los resúmenes del cliente obtenidos con la misma lógica que
`advisor_client_memory` (#40).

## R46
CUANDO la vista se autoriza, el sistema DEBE mostrar como datos permitidos del
cliente únicamente: canal, identificador externo enmascarado (`…` y los 4
últimos caracteres), estado de conversación, último resultado/versión/fecha de
consentimiento del par `(canal, external_user_id)` y, si hay perfil,
`username`, estado de credencial, días restantes y si tiene sesión activa.

## R47
SI el caso no tiene perfil ENTONCES la vista DEBE mostrar `Sin cliente
autenticado` y NO DEBE mostrar credencial, memoria ni resúmenes.

## R48
El sistema DEBE escapar con `html.escape` todo texto de mensajes, memoria,
resúmenes, nombres y plantillas en la bandeja, la vista y la cola de supresión.

## R49
CUANDO se muestra la vista, el sistema DEBE ofrecer como destinos de
transferencia los demás perfiles `asesor` con `telegram_user_id`, cada uno con
su presencia efectiva.

## Auditoría (orchestrator)

## R50
CUANDO un asesor o ejecutor lee la bandeja, la vista de un caso, la memoria de
un caso o la cola de supresión, el sistema DEBE registrar en `panel_audit` una
fila con acción `inbox_viewed`, `case_viewed`, `memory_viewed` o
`suppression_queue_viewed`, el `profile_id` y rol del actor y el `case_id`
cuando aplica.

## R51
CUANDO un asesor o ejecutor ejecuta `reply`, `template`, `assign`, `transfer`,
`resolve`, `return`, `presence` o `suppression_execute`, el sistema DEBE
registrar en `panel_audit` una fila con esa acción y resultado `ok`.

## R52
SI una acción o lectura del panel termina en error de dominio (`forbidden`,
`not_found`, `case_closed`, `channel_window_closed`, `advisor_unavailable`,
`validation_error`, `upstream_error`, `suppression_not_pending`) ENTONCES el
sistema DEBE registrar la fila de auditoría con ese código como resultado.

## R53
La auditoría del panel NO DEBE guardar texto de mensajes, nombres de usuario de
clientes, identificadores externos de canal ni notas; solo identificadores
internos (`profile_id`, `case_id`, `request_id`), acción, destino (`profile_id`
o nombre de plantilla) y resultado.

## R54
CUANDO un asesor es denegado por handover en el panel, el sistema DEBE
conservar además el evento `advisor_forbidden` existente en el contacto del
caso.

## R55
El repositorio (Fake y Postgres) DEBE exponer `add_panel_audit` y
`list_panel_audit(limit)` sobre la tabla `panel_audit` creada de forma aditiva e
idempotente.

## Presencia (orchestrator)

## R56
CUANDO un asesor del panel envía `POST /asesor/presence` con
`status=available|away`, el sistema DEBE guardar ese estado y `last_seen_at =
now` para su perfil.

## R57
SI `status` no es `available` ni `away` ENTONCES el sistema DEBE responder
`422` `validation_error` sin cambiar la presencia.

## R58
CUANDO un asesor con sesión válida hace cualquier petición `/asesor/...`
protegida, el sistema DEBE actualizar su `last_seen_at` sin cambiar su estado.

## R59
CUANDO un asesor cierra sesión con `POST /asesor/logout`, el sistema DEBE
guardar su presencia como `away`.

## Cola de supresión (orchestrator)

## R60
CUANDO un perfil con rol en `SUPPRESSION_EXECUTOR_ROLES` pide
`GET /admin/supresiones` (sesión `admin`) o `GET /asesor/supresiones` (sesión
`asesor`), el sistema DEBE mostrar la cola de solicitudes de supresión.

## R61
SI el rol del perfil de la sesión no pertenece a `SUPPRESSION_EXECUTOR_ROLES`
ENTONCES el sistema DEBE responder `403` `forbidden` en las rutas de cola y
ejecución sin leer solicitudes.

## R62
El sistema DEBE ordenar la cola con las solicitudes `pending` primero, por
fecha límite ascendente, seguidas de las últimas
`SUPPRESSION_QUEUE_EXECUTED_LIMIT` solicitudes `executed` por `executed_at`
descendente.

## R63
El sistema DEBE calcular la fecha límite con la función pura
`business_deadline(created_at, SUPPRESSION_DEADLINE_BUSINESS_DAYS)` que salta
sábados y domingos.

## R64
El sistema DEBE asignar a cada solicitud `pending` la prioridad `vencida` si
`now > fecha límite`, `urgente` si quedan como máximo
`SUPPRESSION_DUE_SOON_BUSINESS_DAYS` días hábiles y `alta` en otro caso.

## R65
El sistema DEBE mostrar por solicitud solo: id, `username` del cliente, canal,
fecha de creación, fecha límite, prioridad, estado, caso vinculado y, si está
ejecutada, fecha, `username` del ejecutor, conteos borrados, nota y resultado
de notificación.

## R66
CUANDO un ejecutor envía `POST /admin/supresiones/{id}/execute` o
`POST /asesor/supresiones/{id}/execute` con CSRF válido, el sistema DEBE llamar
`execute_suppression(request_id, actor_profile_id, ...)` (#40) y guardar la nota
y el resultado de notificación en la solicitud.

## R67
SI la nota supera 500 caracteres ENTONCES el sistema DEBE responder `422`
`validation_error` sin ejecutar la supresión.

## R68
CUANDO la supresión se ejecuta, el sistema DEBE avisar al cliente por el canal
de la solicitud: texto `SUPPRESSION_DONE_REPLY` en Telegram o en WhatsApp con
ventana abierta (calculada antes del borrado), o
`TemplateBlock(name=SUPPRESSION_RESULT_TEMPLATE)` en WhatsApp con ventana
cerrada, sin guardar ese aviso en `messages`.

## R69
SI el aviso de R68 falla o el contacto no existe ENTONCES el sistema DEBE
mantener la ejecución y guardar `notification_result = "failed"` o
`"skipped"`; con éxito DEBE guardar `"text"` o `"template"`.

## R70
SI `execute_suppression` lanza `SuppressionNotFound`, `SuppressionNotPending` o
`SuppressionForbidden` ENTONCES el sistema DEBE responder la página de error
`404`, `409` o `403` sin enviar avisos.

## Configuración y compatibilidad (orchestrator)

## R71
El orchestrator DEBE leer y validar `WHATSAPP_WINDOW_HOURS` (1–24, 24),
`ADVISOR_WHATSAPP_TEMPLATES` (CSV no vacía de nombres `^[a-z0-9_]{1,64}$`,
`respuesta_asesor`), `ADVISOR_RETURN_REPLY` (texto no vacío),
`ADVISOR_HISTORY_LOOKBACK_MINUTES` (0–1440, 60),
`ADVISOR_HISTORY_MAX_MESSAGES` (10–500, 100),
`ADVISOR_PRESENCE_TTL_MINUTES` (1–240, 15), `ADVISOR_INBOX_REFRESH_SECONDS`
(0–600, 30), `SUPPRESSION_DEADLINE_BUSINESS_DAYS` (1–60, 15),
`SUPPRESSION_DUE_SOON_BUSINESS_DAYS` (0–30, 3),
`SUPPRESSION_QUEUE_EXECUTED_LIMIT` (0–200, 20), `SUPPRESSION_DONE_REPLY`
(texto no vacío) y `SUPPRESSION_RESULT_TEMPLATE` (`^[a-z0-9_]{1,64}$`,
`resultado_supresion`).

## R72
SI alguna variable de R71 está fuera de rango o con forma inválida ENTONCES
`Settings` DEBE fallar al construirse nombrando la variable.

## R73
El sistema DEBE conservar el comportamiento de los comandos Telegram
`/responder` y `/cerrar` y de las rutas `/asesor/reply`, `/asesor/assign`,
`/asesor/close` y `/asesor/cases/{id}/memoria` para casos Telegram.

## R74
SI `POST /cases/{id}/transfer` de handover llega sin `X-Service-Token` válido
ENTONCES handover DEBE responder `401` `unauthorized`, y SI su cuerpo no cumple
`CaseTransferRequest` ENTONCES DEBE responder `422` `validation_error`.
