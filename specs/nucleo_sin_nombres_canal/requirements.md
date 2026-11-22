# Requirements — #65 `nucleo_sin_nombres_canal`

Servicios: **contracts** (`lazaro_contracts`), **gateway** (`services/telegram_gateway`) y
**orchestrator** (`services/orchestrator`). Sigue `docs/specs.md` (EARS). Las
pruebas del orquestador usan `FakeChannelDirectory`; el id de canal «nuevo» de las
pruebas es `simulado` (canal #63), que no existe en el código del núcleo.

Vocabulario: *canal con ventana* = canal cuyas capacidades por defecto (sin
destino) informan `free_text_allowed=false` y `requires_template=true`. *Modo de
consentimiento* = `config.consent_mode`, `texto` o `boton`.

## A. Contrato y gateway: lo que el canal informa

## R1 (contracts)
El sistema DEBE incluir en `ChannelInfo` el campo opcional
`capabilities: ChannelCapabilities | None` con valor por defecto `None`.

## R2 (gateway)
CUANDO el gateway construye un `ChannelInfo` de un canal cuyo tipo de adaptador
está registrado, el sistema DEBE rellenar `capabilities` con las capacidades por
defecto (sin destino) de ese tipo, sin construir el cliente ni leer secretos.

## R3 (gateway)
CUANDO el tipo de adaptador de un canal no está registrado, el sistema DEBE
devolver `capabilities` igual a `None` en su `ChannelInfo`.

## R4 (gateway)
El sistema DEBE informar para el canal `whatsapp` capacidades por defecto con
`free_text_allowed=false` y `requires_template=true`, y para el canal `telegram`
con `free_text_allowed=true` y `requires_template=false`.

## R5 (contracts)
SI `config.consent_mode` de `POST /channels` o `PATCH /channels/{id}` no es
`texto` ni `boton` ENTONCES el sistema DEBE responder `422 validation_error`.

## R6 (gateway)
CUANDO el gateway siembra los canales, el sistema DEBE crear `telegram` con
`config.consent_mode="texto"` y `whatsapp` con `config.consent_mode="boton"`.

## R7 (gateway)
CUANDO el gateway siembra una fila existente cuyo `config` no contiene
`consent_mode`, el sistema DEBE añadir el valor sembrado sin alterar el resto de
`config`.

## R8 (gateway)
CUANDO el gateway siembra una fila existente cuyo `config` ya contiene
`consent_mode`, el sistema NO DEBE modificar ese valor.

## R9 (contracts)
El sistema DEBE documentar en `contracts/CONTRATOS.md` el campo `capabilities` de
`ChannelInfo` y las claves `consent_mode` (`texto`|`boton`, por defecto `texto`)
de `config`.

## B. Orquestador: directorio de canales y decisiones por capacidades

## R10 (orchestrator)
CUANDO el orquestador necesita la política de un canal, el sistema DEBE obtenerla
de `GET /channels` del gateway con `X-Service-Token`, sin leer la base del
gateway.

## R11 (orchestrator)
CUANDO el `ChannelInfo` de un canal trae `capabilities` con
`free_text_allowed=false` y `requires_template=true`, el sistema DEBE tratar el
canal como canal con ventana.

## R12 (orchestrator)
CUANDO el `ChannelInfo` de un canal trae `capabilities` distintas de las de canal
con ventana, o `None`, el sistema DEBE tratar el canal como sin ventana.

## R13 (orchestrator)
El sistema DEBE tomar el modo de consentimiento de `config.consent_mode` del
canal y usar `texto` cuando la clave no existe.

## R14 (orchestrator)
CUANDO se solicita la política de un id ausente del directorio, el sistema DEBE
devolver una política sin ventana, con modo `texto` y nombre igual al id.

## R15 (orchestrator)
MIENTRAS la copia del directorio tiene menos de `CHANNEL_DIRECTORY_TTL_SECONDS`
(30 por defecto), el sistema NO DEBE volver a llamar a `GET /channels`.

## R16 (orchestrator)
SI `GET /channels` falla y existe una copia anterior ENTONCES el sistema DEBE
usar esa copia y registrar un WARNING `channel_directory_stale` sin datos
personales.

## R17 (orchestrator)
SI `GET /channels` falla y no existe copia anterior ENTONCES el sistema DEBE
lanzar `ServiceUnavailable`.

## R18 (orchestrator)
SI `POST /messages` recibe un mensaje y el directorio lanza `ServiceUnavailable`
ENTONCES el sistema DEBE responder con el error `upstream_error` de
`UpstreamError` sin encolar el mensaje.

## R19 (orchestrator)
El sistema DEBE calcular la ventana de texto libre de un contacto con el mismo
algoritmo actual (sin `last_user_at` es `closed`; abierta mientras haya menos de
`whatsapp_window_hours` desde el último mensaje del usuario) solo cuando el canal
es un canal con ventana, y devolver `not_applicable` en otro caso.

## R20 (orchestrator)
CUANDO el contacto pertenece a un canal con ventana cerrada, el sistema DEBE
reemplazar el envío de texto libre por la plantilla aprobada o registrar
`window_closed`, con las mismas reglas actuales de WhatsApp en caso de respuesta
de asesor, avisos de caducidad, avisos de cierre y de casos vencidos.

## R21 (orchestrator)
CUANDO el contacto pertenece a un canal sin ventana, el sistema NO DEBE exigir
plantilla ni bloquear el texto libre por ventana.

## R22 (orchestrator)
CUANDO un canal tiene modo `texto`, el sistema DEBE presentar el aviso de
privacidad con la instrucción de frase de aceptación y registrar el desafío de
consentimiento.

## R23 (orchestrator)
CUANDO un canal tiene modo `boton`, el sistema DEBE presentar el aviso de
privacidad con las opciones `Acepto` y `No acepto`.

## R24 (orchestrator)
CUANDO llega un mensaje de texto con la frase de aceptación o rechazo por un
canal en modo `texto` sin consentimiento vigente, el sistema DEBE procesarlo en la
petición HTTP.

## R25 (orchestrator)
CUANDO llega un mensaje de texto con la frase de aceptación por un canal en modo
`boton`, el sistema NO DEBE tratarlo como consentimiento.

## R26 (orchestrator)
El sistema DEBE ofrecer el filtro de canal de la bandeja y sus opciones a partir
de los canales del directorio, con su `name` como etiqueta.

## R27 (orchestrator)
SI el filtro de canal de la bandeja no es un id del directorio ENTONCES el
sistema DEBE rechazarlo con `PanelValidationError`.

## C. Entrada sin guarda temporal

## R28 (orchestrator)
El sistema NO DEBE definir `ATTENDED_CHANNELS` ni ninguna lista fija de canales
aceptados en `POST /messages`.

## R29 (orchestrator)
CUANDO `POST /messages` recibe un `NormalizedMessage` entrante de cualquier
`channel` válido, el sistema DEBE responder `202`.

## R30 (orchestrator)
SI `POST /messages` recibe un `NormalizedMessage` con `direction` distinta de
`inbound` ENTONCES el sistema DEBE responder `422`.

## D. `canal_id` y migración

## R31 (orchestrator)
CUANDO el sistema crea un contacto, el sistema DEBE guardar `canal_id` igual al
canal del contacto.

## R32 (orchestrator)
CUANDO el sistema guarda un mensaje de una conversación, el sistema DEBE guardar
`canal_id` igual al canal de su contacto.

## R33 (orchestrator)
CUANDO arranca el esquema, el sistema DEBE rellenar `canal_id` en los contactos y
mensajes existentes a partir de `contacts.channel`, sin borrar ni modificar
ninguna otra columna.

## R34 (orchestrator)
CUANDO el esquema se ejecuta una segunda vez, el sistema NO DEBE modificar ninguna
fila ni fallar.

## R35 (orchestrator)
CUANDO existen contactos de `telegram` y `whatsapp` sin `canal_id`, el sistema
DEBE conservar su número de filas, ids y contenido tras la migración.

## E. Barrido de nombres de canal

## R36 (orchestrator)
El sistema NO DEBE contener literales de cadena iguales a `telegram` o `whatsapp`
(sin distinguir mayúsculas, valor completo) en `services/orchestrator/orchestrator/`
fuera de `legacy.py`.

## R37 (orchestrator)
El sistema NO DEBE importar `LEGACY_CHANNEL` fuera de la lista de archivos de la
capa legacy documentada en `design.md` §4.

## R38 (orchestrator)
CUANDO llega el payload histórico `MessageRequest` o un `NormalizedMessage` de
Telegram con texto e ids numéricos, el sistema DEBE procesarlo con el flujo
histórico y las mismas respuestas que antes.

## F. Canal nuevo de punta a punta

## R39 (orchestrator)
CUANDO un canal con id ausente de la capa legacy (`simulado`) envía su primer
mensaje, el sistema DEBE pedir consentimiento por su mismo canal y destino.

## R40 (orchestrator)
CUANDO el cliente del canal `simulado` acepta el consentimiento, completa el login
por enlace y escribe, el sistema DEBE responder por el mismo canal y destino.

## R41 (orchestrator)
CUANDO el cliente del canal `simulado` pide hablar con un asesor, el sistema DEBE
crear el caso con el contacto de ese canal.

## R42 (orchestrator)
CUANDO un asesor responde un caso de un contacto del canal `simulado`, el sistema
DEBE encolar la respuesta por el canal y destino de esa conversación.

## R43 (orchestrator)
El sistema DEBE conservar verde toda la batería existente de
`services/orchestrator/tests`, `services/telegram_gateway/tests` y
`contracts/tests`.
