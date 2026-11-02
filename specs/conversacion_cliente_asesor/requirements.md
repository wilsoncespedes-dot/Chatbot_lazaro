# Requirements — conversacion_cliente_asesor (feature #16)

> Feature: «Conversación bidireccional cliente-asesor por Telegram». Mientras un caso está
> `assigned`, los mensajes del cliente van al asesor en lugar de al RAG, y el asesor responde y
> cierra desde Telegram con `/responder <case_id> <texto>` y `/cerrar <case_id>`.
>
> Fuentes de verdad: acceptance de la #16 en `feature_list.json` (en especial los criterios
> «Decidido por el humano (2026-10-31)») y `progress/propuesta_etapa2.md` §6 (incluida la
> identidad: en Telegram el `advisor_id` es el `telegram_user_id` del update validado con
> `TELEGRAM_WEBHOOK_SECRET`, nunca un id escrito en el texto).
>
> Consume **sin modificarlos**:
> - #15 (`specs/contrato_conversacion_caso/`): `POST /cases/{id}/client-message`,
>   `CaseClientMessageRequest`, `CaseClientMessageResponse`, S13.
> - #13 (`specs/contrato_autorizacion_asesores/`): `POST /cases/{id}/authorize`,
>   `CaseAuthorizeRequest`/`CaseAuthorizeResponse`/`CaseAuthorizeAction`, `403 forbidden`, S12,
>   **C5** (`reply` sobre un caso `closed` → `409 case_closed`, sin enviar nada) y la línea
>   `Llama` de `authorize` que ya nombra el comando `/cerrar` (D4 de esta feature, opción (a)).
> - #14 (`specs/autorizacion_asesores/`, implementada): reglas de autorización en handover,
>   `reply_to_case` que autoriza primero y falla cerrado, `HandoverClient.authorize`,
>   `AuthorizationDenied`, `AdvisorForbidden` (`403`), `CaseClosed` (`409 case_closed`, sin
>   evento `advisor_forbidden`, D5 de la #14), asignación y cierre condicionales (D10) y el
>   candado de `PostgresCaseRepository`.
> - #17 (`specs/contrato_cierre_casos_huerfanos/`): un caso huérfano lo puede cerrar cualquier
>   asesor registrado, pero no responder ni asignar (S12); procedimiento A de retirada.
> - #18 (`specs/candado_repositorio_orquestador/`): `threading.Lock` en `PostgresRepository`
>   del orquestador.
> - #10 (`specs/validacion_config_asesores/`): `ADVISOR_CHAT_IDS` validada al arrancar.
>
> No quedan marcas de revisión pendientes ni decisiones bloqueantes. Los requirements que siguen un
> supuesto del spec_author citan su id (D1-D9, C1-C4) entre paréntesis; cada supuesto se resolvió
> con la opción más conservadora y está justificado en `design.md` §9 (revisión nocturna del
> 2026-11-01).
>
> Notación EARS estricta (`docs/specs.md`). Cada requirement indica el servicio. Ids estables:
> no renumerar (R59-R62 se añadieron tras la revisión de spec y van con su servicio). Los
> nombres de test están en `tasks.md`.
>
> Vocabulario:
> - **Intento de comando**: mensaje cuyo primer token (tras quitar espacios iniciales), pasado a
>   minúsculas, empieza por `/responder` o por `/cerrar`.
> - **Comando bien formado**: intento de comando que cumple R2 o R3.
> - **Remitente**: el `telegram_user_id` y el `chat_id` de la `MessageRequest` recibida en
>   `POST /messages`.
> - **Último caso del contacto**: el `case_id` vinculado más recientemente al contacto en el
>   vínculo caso-contacto del orquestador (R35).
> - **Textos fijos**: las variables nuevas de `design.md` §6.

---

## Servicio orchestrator

### Detección de comandos (función pura)

## R1
SI el primer token del texto, pasado a minúsculas, no empieza por `/responder` ni por `/cerrar`
(o el texto no tiene ningún token) ENTONCES `parse_advisor_command` (orchestrator) DEBE devolver
`None`. (D1)

## R2
CUANDO el primer token del texto es exactamente `/responder` y le siguen un `case_id` de 1 a
`MAX_IDENTIFIER_LENGTH` caracteres sin espacios y un texto no vacío, `parse_advisor_command`
(orchestrator) DEBE devolver `AdvisorCommand(action="reply", case_id=<case_id>, text=<resto>)`,
donde `<resto>` es todo lo que sigue al `case_id` sin los espacios iniciales y con su contenido
interno (incluidos saltos de línea) sin cambios. (D1)

## R3
CUANDO el texto tiene exactamente dos tokens, el primero es exactamente `/cerrar` y el segundo es
un `case_id` de 1 a `MAX_IDENTIFIER_LENGTH` caracteres, `parse_advisor_command` (orchestrator)
DEBE devolver `AdvisorCommand(action="close", case_id=<case_id>, text=None)`. (D1)

## R4
SI el texto es un intento de comando que no cumple R2 ni R3 ENTONCES `parse_advisor_command`
(orchestrator) DEBE devolver `MalformedCommand()`. (D1)

## R5
`parse_advisor_command` (orchestrator) DEBE ser una función de `domain.py` que solo recibe el
texto y no usa adaptadores, reloj ni configuración.

### Enrutado de un intento de comando

## R6
CUANDO el orquestador procesa un mensaje de `POST /messages` que es un intento de comando, el
sistema (orchestrator) NO DEBE llamar a RAG, al LLM ni a `POST /handover`, aunque el texto
contenga palabras clave de traspaso.

## R7
CUANDO el orquestador procesa un intento de comando, el sistema (orchestrator) NO DEBE guardar
el mensaje del comando en el historial del contacto remitente. (D7)

## R8
CUANDO el orquestador procesa un intento de comando, el sistema (orchestrator) NO DEBE llamar a
`POST /cases/{id}/client-message`, aunque el remitente tenga un caso `assigned`. (D8)

## R9
CUANDO el orquestador recibe un comando mal formado (R4), el sistema (orchestrator) DEBE enviar
`ADVISOR_COMMAND_HELP` al `chat_id` del remitente sin llamar a ninguna ruta de handover.

## R10
SI un comando bien formado llega con un `telegram_user_id` menor o igual que 0 ENTONCES el
sistema (orchestrator) DEBE enviar `ADVISOR_COMMAND_FORBIDDEN_REPLY` al `chat_id` del remitente
sin llamar a ninguna ruta de handover. (D2; S13 de la #15: un id de grupo no usa comandos)

### Identidad del asesor

## R11
CUANDO el orquestador ejecuta un comando bien formado, el sistema (orchestrator) DEBE usar como
`advisor_id`, en todas las llamadas a handover, únicamente `str(telegram_user_id)` del
remitente, nunca el `chat_id` ni ningún id escrito en el texto del mensaje. *Decidido por el
humano (2026-10-31) y publicado en S13 de la #15.*

### `/responder <case_id> <texto>`

## R12
CUANDO el orquestador recibe `/responder <case_id> <texto>` bien formado de un remitente con
`telegram_user_id` mayor que 0, el sistema (orchestrator) DEBE ejecutar `reply_to_case` (#14)
con ese `case_id` y `CaseReplyRequest(advisor_id=str(telegram_user_id), text=<texto>)`.

## R13
CUANDO `reply_to_case` termina con `{"sent": true}` para un `/responder`, el sistema
(orchestrator) DEBE enviar `ADVISOR_REPLY_CONFIRMATION` al `chat_id` del remitente.

## R14
SI `reply_to_case` lanza `AdvisorForbidden` para un `/responder` (handover respondió `403
forbidden` a `authorize`) ENTONCES el sistema (orchestrator) DEBE enviar
`ADVISOR_COMMAND_FORBIDDEN_REPLY` al `chat_id` del remitente. (El caso `closed` va por R60.)

## R15
SI `reply_to_case` lanza `CaseNotFound` o `UpstreamError` para un `/responder` ENTONCES el
sistema (orchestrator) DEBE enviar `ADVISOR_COMMAND_FAILED_REPLY` al `chat_id` del remitente.
(D3)

### `/cerrar <case_id>`

## R16
CUANDO el orquestador recibe `/cerrar <case_id>` bien formado de un remitente con
`telegram_user_id` mayor que 0, el sistema (orchestrator) DEBE pedir a handover
`POST /cases/{id}/authorize` con `action` = `close` antes de llamar a `POST /cases/{id}/close`.
*Decidido por el humano (2026-10-31): D4 opción (a), línea `Llama` de `authorize` publicada por
la #13.*

## R17
CUANDO handover autoriza un `/cerrar`, el sistema (orchestrator) DEBE llamar a
`POST /cases/{id}/close` con el mismo `case_id` y `advisor_id`.

## R18
CUANDO `POST /cases/{id}/close` responde `200` a un `/cerrar` y el caso está vinculado a un
contacto, el sistema (orchestrator) DEBE enviar `CASE_CLOSED_REPLY` al `chat_id` de ese contacto
y guardarlo en su historial con rol `bot`.

## R19
CUANDO `POST /cases/{id}/close` responde `200` a un `/cerrar`, el sistema (orchestrator) DEBE
enviar `ADVISOR_CLOSE_CONFIRMATION` al `chat_id` del remitente.

## R20
SI `POST /cases/{id}/close` responde `200` a un `/cerrar` y el caso no está vinculado a ningún
contacto ENTONCES el sistema (orchestrator) DEBE escribir en el log `case_closed_unlinked` con el
`case_id` sin enviar `CASE_CLOSED_REPLY` a nadie.

## R21
SI la autorización o el cierre de un `/cerrar` termina en `AuthorizationDenied("forbidden")`
ENTONCES el sistema (orchestrator) DEBE enviar `ADVISOR_COMMAND_FORBIDDEN_REPLY` al `chat_id`
del remitente sin enviar `CASE_CLOSED_REPLY`. (El caso `closed` va por R61.)

## R22
SI la autorización de un `/cerrar` no termina en `200` ENTONCES el sistema (orchestrator) NO
DEBE llamar a `POST /cases/{id}/close` (fallo cerrado).

## R23
SI la autorización o el cierre de un `/cerrar` termina en `AuthorizationDenied("not_found")` o
en `ServiceUnavailable` ENTONCES el sistema (orchestrator) DEBE enviar
`ADVISOR_COMMAND_FAILED_REPLY` al `chat_id` del remitente sin enviar `CASE_CLOSED_REPLY`.
(D3)

### Comandos sobre un caso `closed` (C5 de la #13, D5 de la #14)

## R60
SI `reply_to_case` lanza `CaseClosed` para un `/responder` (handover respondió `409
case_closed` a `authorize`) ENTONCES el sistema (orchestrator) DEBE enviar
`ADVISOR_COMMAND_CASE_CLOSED_REPLY` al `chat_id` del remitente sin enviar nada al cliente.
*Decidido por el humano (2026-10-31): C5 de la #13.*

## R61
SI la autorización o el cierre de un `/cerrar` termina en `AuthorizationDenied("case_closed")`
ENTONCES el sistema (orchestrator) DEBE enviar `ADVISOR_COMMAND_CASE_CLOSED_REPLY` al `chat_id`
del remitente sin enviar `CASE_CLOSED_REPLY` ni `ADVISOR_CLOSE_CONFIRMATION`. (D4)

## R62
CUANDO un comando termina por R60 o R61, el sistema (orchestrator) NO DEBE registrar el evento
`advisor_forbidden` en ningún contacto. *Decidido por el humano (2026-10-31): un `409` no genera
`advisor_forbidden` (D5 de la #14).*

### Denegaciones, respuestas al asesor y logs de comandos

## R24
CUANDO el orquestador envía `ADVISOR_COMMAND_FORBIDDEN_REPLY` (R10, R14, R21), el sistema
(orchestrator) DEBE registrar en el contacto remitente el evento `advisor_forbidden` con motivo
`command:<responder|cerrar> case:<case_id> advisor:<telegram_user_id> code:<código>` y la fecha
del reloj inyectado, donde `<código>` es `sender_not_user` (R10) o `forbidden` (R14, R21). (D6)

## R25
CUANDO el orquestador envía al remitente de un comando `ADVISOR_COMMAND_HELP`,
`ADVISOR_COMMAND_FORBIDDEN_REPLY`, `ADVISOR_COMMAND_FAILED_REPLY`,
`ADVISOR_COMMAND_CASE_CLOSED_REPLY`, `ADVISOR_REPLY_CONFIRMATION` o
`ADVISOR_CLOSE_CONFIRMATION`, el sistema (orchestrator) NO DEBE guardar ese texto en el
historial del contacto remitente. (D7)

## R26
CUANDO el orquestador procesa un intento de comando, el sistema (orchestrator) NO DEBE escribir
en el log el texto del mensaje ni el `<texto>` de `/responder`.

### Reenvío cliente → asesor

## R27
CUANDO el orquestador procesa un mensaje que no es intento de comando y el contacto tiene un
último caso, el sistema (orchestrator) DEBE llamar a `POST /cases/{id}/client-message` con ese
`case_id`, `text` = el texto recibido sin cambios y `at` = `received_at`, después de guardar el
mensaje en el historial con rol `user` y antes de evaluar las palabras clave de traspaso y de
llamar a RAG. (C1)

## R28
CUANDO handover responde `forwarded`, el sistema (orchestrator) DEBE registrar en el contacto el
evento `forwarded_to_advisor` con motivo `case:<case_id>` sin llamar a RAG, al LLM ni a
`POST /handover` y sin enviar nada al cliente. (C2)

## R29
CUANDO handover responde `not_assigned`, el sistema (orchestrator) DEBE seguir el flujo actual
(palabras clave de traspaso, RAG, rechazo o traspaso) sin cambios.

## R30
CUANDO handover responde `404 not_found` a `POST /cases/{id}/client-message`, el sistema
(orchestrator) DEBE seguir el flujo actual sin cambios.

## R31
CUANDO el contacto no tiene ningún caso vinculado, el sistema (orchestrator) DEBE seguir el flujo
actual sin llamar a `POST /cases/{id}/client-message`.

## R32
SI handover responde `502 upstream_error` a `POST /cases/{id}/client-message` ENTONCES el
sistema (orchestrator) DEBE registrar en el contacto el evento `forward_failed` con motivo
`case:<case_id> code:upstream_error`, enviar `FORWARD_FAILED_REPLY` al cliente (guardado con rol
`bot`) y no llamar a RAG, al LLM ni a `POST /handover`.

## R33
SI `POST /cases/{id}/client-message` falla por red o tiempo o responde algo distinto de `200`
válido, `404 not_found` y `502 upstream_error` ENTONCES el sistema (orchestrator) DEBE registrar
el evento `forward_failed` con motivo `case:<case_id> code:handover_unavailable`, enviar
`FORWARD_FAILED_REPLY` al cliente y no llamar a RAG, al LLM ni a `POST /handover`. (D5)

## R34
CUANDO un asesor envía un mensaje que no es intento de comando, el sistema (orchestrator) DEBE
tratarlo como el de cualquier cliente (R27-R33 y flujo actual), sin consultar
`POST /cases/{id}/authorize`.

## R35
El repositorio del orquestador DEBE ofrecer `get_contact_last_case(contact_id)`, que devuelve el
`case_id` vinculado más recientemente al contacto (o `None`), con versión falsa y versión
PostgreSQL con SQL parametrizado.

## R36
CUANDO el orquestador reenvía un mensaje o falla al reenviarlo, el sistema (orchestrator) NO
DEBE escribir en el log el texto del cliente.

### Cliente HTTP de handover

## R37
El sistema (orchestrator) DEBE reenviar con un `POST` a
`{HANDOVER_URL}/cases/{case_id codificado}/client-message` que lleve `X-Service-Token`, un cuerpo
`CaseClientMessageRequest` y el tiempo máximo `HTTP_TIMEOUT_SECONDS`.

## R38
CUANDO `POST /cases/{id}/client-message` responde `200` con un cuerpo válido de
`CaseClientMessageResponse` y el mismo `case_id`, el cliente HTTP de handover del orquestador
DEBE devolver esa respuesta.

## R39
CUANDO `POST /cases/{id}/client-message` responde `404` o `502` con un `ErrorResponse` cuyo
`error` es respectivamente `not_found` o `upstream_error`, el cliente HTTP de handover del
orquestador DEBE lanzar `ForwardRejected` con ese código.

## R40
SI `POST /cases/{id}/client-message` falla por red o tiempo o responde algo distinto de R38 y
R39 ENTONCES el cliente HTTP de handover del orquestador DEBE lanzar `ServiceUnavailable`.

## R41
El sistema (orchestrator) DEBE cerrar casos con un `POST` a
`{HANDOVER_URL}/cases/{case_id codificado}/close` que lleve `X-Service-Token`, un cuerpo
`CaseCloseRequest` y el tiempo máximo `HTTP_TIMEOUT_SECONDS`, y devolver la
`CaseCloseResponse` cuando la respuesta es `200` válida con el mismo `case_id`.

## R42
CUANDO `POST /cases/{id}/close` responde `403`, `404` o `409` con un `ErrorResponse` cuyo `error`
es respectivamente `forbidden`, `not_found` o `case_closed`, el cliente HTTP de handover del
orquestador DEBE lanzar `AuthorizationDenied` con ese código.

## R43
SI `POST /cases/{id}/close` falla por red o tiempo o responde algo distinto de R41 y R42
ENTONCES el cliente HTTP de handover del orquestador DEBE lanzar `ServiceUnavailable`.

### Configuración

## R44
El sistema (orchestrator) DEBE leer de variables de entorno, con valor por defecto no vacío,
`ADVISOR_REPLY_CONFIRMATION`, `ADVISOR_CLOSE_CONFIRMATION`, `CASE_CLOSED_REPLY`,
`FORWARD_FAILED_REPLY`, `ADVISOR_COMMAND_HELP`, `ADVISOR_COMMAND_FORBIDDEN_REPLY`,
`ADVISOR_COMMAND_FAILED_REPLY` y `ADVISOR_COMMAND_CASE_CLOSED_REPLY`.

## R45
`.env.example` DEBE declarar cada una de las variables de R44 con su valor por defecto.

## R46
El sistema (orchestrator) NO DEBE leer `ADVISOR_CHAT_IDS` ni ninguna lista de asesores.

---

## Servicio handover

### `POST /cases/{id}/client-message`

## R47
CUANDO handover recibe `POST /cases/{id}/client-message` válido sobre un caso `assigned`, el
sistema (handover) DEBE enviar por `POST /send` al chat `int(advisor_id)` del caso el texto plano
`Caso <case_id> | Cliente: <text>` y responder `200` con
`{"status": "forwarded", "case_id": <id>}`.

## R48
SI el texto `Caso <case_id> | Cliente: <text>` supera `MAX_TEXT_LENGTH` (4096) caracteres
ENTONCES el sistema (handover) DEBE recortarlo a sus primeros 4096 caracteres antes de enviarlo.

## R49
CUANDO handover recibe `POST /cases/{id}/client-message` válido sobre un caso que existe y no
está `assigned` (`open`, `timed_out` o `closed`), el sistema (handover) DEBE responder `200` con
`{"status": "not_assigned", "case_id": <id>}` sin enviar nada. (S13 y nota de `closed` de la
#15)

## R50
SI handover recibe `POST /cases/{id}/client-message` sobre un caso que no existe ENTONCES el
sistema (handover) DEBE responder `404` con `{"error": "not_found", ...}` sin enviar nada.

## R51
SI el envío al asesor por `POST /send` falla ENTONCES el sistema (handover) DEBE responder `502`
con `{"error": "upstream_error", ...}`.

## R52
SI el `advisor_id` de un caso `assigned` no es un entero en decimal ENTONCES el sistema
(handover) DEBE responder `502` con `{"error": "upstream_error", ...}` sin llamar a
`POST /send`.

## R53
CUANDO handover atiende `POST /cases/{id}/client-message`, el sistema (handover) NO DEBE
modificar ningún caso ni interpretar el `text` (un `text` con `/cerrar`, `/responder`, Markdown,
HTML o instrucciones se envía tal cual tras el prefijo).

## R54
CUANDO handover reenvía un mensaje al asesor, el sistema (handover) DEBE llamar a `POST /send`
con un cuerpo que contenga solo `chat_id` y `text` (sin `parse_mode` ni otro formato de
Telegram).

## R55
SI una petición a `POST /cases/{id}/client-message` llega sin `X-Service-Token` válido ENTONCES
el sistema (handover) DEBE responder `401` con `{"error": "unauthorized", ...}` sin enviar nada.

## R56
SI el cuerpo de `POST /cases/{id}/client-message` no valida contra `CaseClientMessageRequest`
ENTONCES el sistema (handover) DEBE responder `422` con `{"error": "validation_error", ...}` sin
enviar nada.

## R57
CUANDO handover atiende `POST /cases/{id}/client-message`, el sistema (handover) NO DEBE
escribir en el log el `text` del cliente.

### Cierre por la ruta HTTP

## R59
CUANDO handover cierra un caso por `POST /cases/{id}/close`, el sistema (handover) NO DEBE enviar
ningún aviso al cliente; el aviso `CASE_CLOSED_REPLY` (R18) solo sale del orquestador cuando el
cierre llega por `/cerrar`. (D9)

---

## Transversal

## R58
CUANDO se ejecuta la batería completa de tests tras el cambio, el sistema DEBE pasar todos los
tests que existían antes de la feature sin eliminar ninguno ni debilitar sus aserciones; los
únicos cambios en tests existentes son los listados en `design.md` §8.

---

## Trazabilidad con el `acceptance` de la #16

| Acceptance (resumido) | Requirements |
|---|---|
| Caso `assigned`: se guarda en el historial, `client-message`, sin RAG ni LLM; handover envía `Caso <id> \| Cliente: <texto>` recortado a 4096; evento `forwarded_to_advisor` | R27, R28, R35, R37, R38, R47, R48 |
| `not_assigned` o `404` → flujo actual | R29, R30, R31, R39, R49, R50 |
| `/responder` autorizado = efectos de `POST /cases/{id}/reply`; `/cerrar` cierra con la misma autorización | R12, R13, R16, R17, R18, R19, R20, R41, R42, R43; caso `closed` como C5 de la #13 y D5 de la #14: R60, R61, R62 |
| Decidido: `advisor_id` = `telegram_user_id` del remitente; prueba de seguridad con id de otro asesor en el texto | R10, R11 |
| Comandos sin RAG ni LLM; mal formado → ayuda fija configurable | R1, R2, R3, R4, R5, R6, R8, R9 |
| Seguridad: cliente no autorizado con `/responder` → nada a otro cliente, texto fijo, `advisor_forbidden` | R14, R21, R22, R24 |
| Seguridad: el texto reenviado no se interpreta y va en texto plano | R27, R53, R54 |
| Decidido: solo `assigned` se reenvía; `open` → flujo actual con RAG | R29, R49 |
| Decidido: comandos `/responder` y `/cerrar` | R2, R3, R12, R16 |
| Decidido: mensaje de asesor que no es comando → flujo actual | R1, R34 |
| Decidido: fallo de reenvío `502` → texto fijo, `forward_failed`, sin RAG | R32, R33, R51, R52 |
| Decidido: confirmación al asesor y aviso al cliente al cerrar | R13, R18, R19, R59 (aviso solo con `/cerrar`, D9) |
| Variables nuevas en `.env.example`; el orquestador no lee la lista de asesores | R44, R45, R46 |
| Tests listados en el acceptance | `tasks.md` T11-T68 y T71-T73 (reenvío T36; `not_assigned` T39; caso inexistente T40; fallo de envío T42, T63; `/responder` y `/cerrar` autorizados T22, T27; no autorizado T24, T30, T57; mal formado T19; sin RAG ni LLM T16; recorte T60; seguridad T56, T57, T58, T68; caso `closed` T71-T73) |
| Privacidad de logs y del historial (Ley 1581, `docs/architecture.md` §4) | R7, R25, R26, R36, R57 |
| Errores de comandos no fijados por el humano (caso inexistente, handover caído, caso cerrado) | R15, R23, R60, R61 |
| Casos huérfanos (#17, D11 de la #14): `/cerrar` de cualquier asesor registrado sobre un huérfano cierra; `/responder` recibe `403` | R16-R19 y R14 por construcción (handover decide; `design.md` §7) |
| Seguridad de la ruta nueva (token y cuerpo) y sin regresiones | R55, R56, R58 |
