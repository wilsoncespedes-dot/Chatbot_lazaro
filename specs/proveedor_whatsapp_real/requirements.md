# #43 proveedor_whatsapp_real — Requirements

## Decisión de proveedor (criterio 1 del acceptance)

**Decisión del dueño 2026-11-03: Meta Cloud API.** El proveedor de producción de
WhatsApp es **Meta WhatsApp Cloud API** (Graph API). Twilio y 360dialog quedan
**fuera de alcance** de esta feature; la interfaz `ChannelAdapter` de #36 no se
restringe y sigue permitiendo incorporarlos en features posteriores. No se
incorpora ningún proveedor por suposición.

## Alcance

Servicio afectado: **telegram_gateway** (único servicio con código nuevo; es el
gateway multicanal que ya expone `POST /send` con `ChannelSendRequest` y
`Adapters.whatsapp`). `orchestrator`, `handover`, `rag`, `contracts` (código) y
`eval` no cambian: el orquestador ya decide la ventana con `channel_window`
(#41), envía `TemplateBlock` fuera de ventana (#41, #42), atiende `kind =
"unsupported"` con el texto fijo de #37 y deduplica de forma persistente por
`(canal, external_message_id)` (#36).

Se respeta la interfaz de #36 (`ChannelAdapter`: `channel`, `capabilities()`,
`normalize_incoming()`, `send()`, `delivery_status()`), los modelos de
`lazaro_contracts.channels` (`NormalizedMessage`, `ResponseBlock`,
`TemplateBlock`, `ChannelCapabilities`, `DeliveryStatus`) y las excepciones del
gateway (`ChannelWindowClosed`, `TemplateNotApproved`, `ChannelSendFailed`,
`ChannelNotConfigured`). `FakeWhatsAppAdapter` se conserva sin cambios.

Vocabulario:

- **Webhook WhatsApp**: rutas `GET /whatsapp/webhook` y `POST
  /whatsapp/webhook` del gateway.
- **Firma válida**: encabezado `X-Hub-Signature-256` con forma
  `sha256=<hex>` donde `<hex>` es igual (comparación en tiempo constante,
  hex sin distinguir mayúsculas) a `HMAC-SHA256(WHATSAPP_APP_SECRET, cuerpo
  crudo en bytes)`.
- **wa_id**: valor `from` del mensaje entrante de Meta (opaco, texto).
- **wamid**: valor `id` del mensaje o del estado de Meta (opaco, texto).
- **Cambio aplicable**: elemento `entry[].changes[]` con `field ==
  "messages"` y `value.metadata.phone_number_id ==
  WHATSAPP_PHONE_NUMBER_ID`.
- **Ventana abierta** para un wa_id: existe un último mensaje entrante
  registrado `t` y `now - t < WHATSAPP_WINDOW_HOURS` horas.
- **URL de mensajes**: `{WHATSAPP_GRAPH_BASE_URL}/{WHATSAPP_GRAPH_API_VERSION}/{WHATSAPP_PHONE_NUMBER_ID}/messages`.
- **Código de error Meta**: `error.code` del cuerpo JSON de error de Graph API.

---

## Configuración y secretos (telegram_gateway)

### R1
DONDE `WHATSAPP_ENABLED` es `false` (valor por defecto), el sistema DEBE
construir `Adapters.whatsapp = None`, de modo que `POST /send` con `channel =
"whatsapp"` siga respondiendo `502` con `error = "upstream_error"`
(`ChannelNotConfigured`).

### R2
DONDE `WHATSAPP_ENABLED` es `false`, el sistema DEBE responder `404` con
`{"error": "not_found", ...}` a `GET /whatsapp/webhook` y a `POST
/whatsapp/webhook`.

### R3
SI `WHATSAPP_ENABLED` es `true` y alguna de `WHATSAPP_ACCESS_TOKEN`,
`WHATSAPP_APP_SECRET`, `WHATSAPP_VERIFY_TOKEN` o `WHATSAPP_PHONE_NUMBER_ID` está
vacía ENTONCES la construcción de `Settings` DEBE fallar con un error que
nombra solo las variables faltantes, sin incluir ningún valor.

### R4
CUANDO `WHATSAPP_ENABLED` es `true` y la configuración es válida,
`build_default_adapters` DEBE asignar a `Adapters.whatsapp` un
`WhatsAppCloudAdapter` configurado con los valores de entorno.

### R5
El sistema NO DEBE incluir `WHATSAPP_ACCESS_TOKEN`, `WHATSAPP_APP_SECRET` ni
`WHATSAPP_VERIFY_TOKEN` en registros (`logging`), cuerpos de error HTTP, mensajes
de excepción ni en el `repr` del adaptador.

### R6
El sistema NO DEBE registrar en logs el wa_id ni el texto de los mensajes
entrantes o salientes de WhatsApp; los registros del proveedor identifican el
mensaje solo por wamid, tipo y códigos de error.

### R7
El archivo `.env.example` DEBE declarar `WHATSAPP_ENABLED=false`,
`WHATSAPP_ACCESS_TOKEN=`, `WHATSAPP_APP_SECRET=`, `WHATSAPP_VERIFY_TOKEN=`,
`WHATSAPP_PHONE_NUMBER_ID=` (las cuatro últimas vacías),
`WHATSAPP_GRAPH_BASE_URL`, `WHATSAPP_GRAPH_API_VERSION`,
`WHATSAPP_TEMPLATE_LANGUAGE` y `WHATSAPP_INTERACTIVE_BODY_TEXT` con sus valores
por defecto.

---

## Verificación del webhook (GET)

### R8
CUANDO llega `GET /whatsapp/webhook` con `hub.mode = "subscribe"`,
`hub.verify_token` igual a `WHATSAPP_VERIFY_TOKEN` (comparación en tiempo
constante) y `hub.challenge` no vacío, el sistema DEBE responder `200` con
`Content-Type: text/plain` y cuerpo exactamente igual a `hub.challenge`.

### R9
SI `GET /whatsapp/webhook` llega con `hub.mode` distinto de `"subscribe"`, con
`hub.verify_token` ausente o distinto, o sin `hub.challenge` ENTONCES el sistema
DEBE responder `403` con `{"error": "forbidden", ...}`.

### R10
El sistema DEBE atender `GET /whatsapp/webhook` y `POST /whatsapp/webhook` sin
exigir `X-Service-Token`; su autenticación es exclusivamente la de R8/R11.

---

## Firma del webhook (POST)

### R11
CUANDO llega `POST /whatsapp/webhook` con firma válida, el sistema DEBE
procesar el cuerpo y responder `200` con `{"ok": true}`.

### R12
SI `POST /whatsapp/webhook` llega sin `X-Hub-Signature-256`, con un valor sin
prefijo `sha256=` o con un HMAC distinto ENTONCES el sistema DEBE responder
`401` con `{"error": "unauthorized", ...}` sin tocar el almacén de
deduplicación, el almacén de ventana ni el orquestador.

### R13
El sistema DEBE calcular el HMAC sobre los bytes crudos recibidos, de modo que un
cuerpo JSON semánticamente igual pero con bytes distintos a los firmados se
rechace con `401`.

### R14
SI un `POST /whatsapp/webhook` con firma válida trae un cuerpo que no es JSON,
no es un objeto o tiene `object` distinto de `"whatsapp_business_account"`
ENTONCES el sistema DEBE responder `200` con `{"ok": true}` sin reenviar nada al
orquestador.

### R15
SI un cambio no es aplicable (otro `field` u otro `phone_number_id`) ENTONCES el
sistema DEBE ignorarlo sin reenviar sus mensajes ni registrar ventana.

### R51
SI un cuerpo contiene un cambio no aplicable seguido de un cambio aplicable
ENTONCES el sistema DEBE procesar los mensajes del cambio aplicable como si el
no aplicable no existiera.

---

## Normalización de entrantes

### R16
CUANDO un cambio aplicable contiene un mensaje `type = "text"` con `from`, `id`
y `text.body` no vacío, el sistema DEBE reenviar al orquestador un
`NormalizedMessage` con `channel = "whatsapp"`, `external_user_id = from`,
`external_chat_id = from`, `external_message_id = id`, `kind = "text"`, `text =
text.body` y `received_at` igual al reloj inyectado (`Adapters.clock()`).

### R17
CUANDO un mensaje `type = "interactive"` trae `button_reply.id` o
`list_reply.id`, el sistema DEBE reenviar un `NormalizedMessage` con `kind =
"button"`, `button_id` igual a la parte anterior al primer `:` del id y
`button_proof` igual a la parte posterior (o `None` si no hay `:` o está vacía).

### R18
CUANDO un mensaje `type = "button"` (respuesta rápida de plantilla) trae
`button.payload`, el sistema DEBE reenviar un `NormalizedMessage` con `kind =
"button"` aplicando la misma separación `button_id`/`button_proof` de R17 sobre
`payload`.

### R19
CUANDO un mensaje tiene un `type` distinto de `text`, `interactive`, `button` y
`reaction` (p. ej. `image`, `audio`, `video`, `document`, `sticker`,
`location`, `contacts` o un tipo desconocido), el sistema DEBE reenviar un
`NormalizedMessage` con `kind = "unsupported"` y `text = None`.

### R20
CUANDO un mensaje tiene `type = "reaction"`, el sistema NO DEBE reenviarlo al
orquestador.

### R21
SI un mensaje carece de `from` o `id`, trae texto vacío, o el
`NormalizedMessage` resultante no supera la validación del contrato ENTONCES el
sistema NO DEBE reenviar ese mensaje al orquestador.

### R52
SI un cuerpo contiene un mensaje inválido (según R21) seguido de un mensaje
válido ENTONCES el sistema DEBE reenviar el mensaje válido al orquestador.

### R22
CUANDO un cuerpo contiene varios mensajes válidos, el sistema DEBE reenviarlos
al orquestador en el orden en que aparecen en el cuerpo.

---

## Idempotencia

### R23
CUANDO llega un mensaje cuyo par `("whatsapp", wamid)` ya fue marcado en
`Adapters.dedup` (`mark_message_if_new` con `DEDUP_TTL_SECONDS`), el sistema NO
DEBE reenviarlo al orquestador.

### R53
CUANDO un `POST /whatsapp/webhook` con firma válida contiene solo mensajes ya
marcados en `Adapters.dedup`, el sistema DEBE responder `200` con
`{"ok": true}`.

### R24
El sistema DEBE deduplicar con la clave compuesta, de modo que un wamid igual a
un `update_id` o `callback_id` ya procesado de Telegram no se descarte.

### R25
SI `Adapters.dedup` lanza una excepción ENTONCES el sistema DEBE tratar el
mensaje como nuevo y reenviarlo (misma política que Telegram; la barrera
autoritativa es la deduplicación persistente del orquestador).

### R26
SI el orquestador falla al recibir un mensaje WhatsApp ENTONCES el sistema DEBE
registrar el fallo y responder `200` con `{"ok": true}` al webhook.

---

## Ventana de 24 horas y envío

### R27
CUANDO se procesa un mensaje entrante con `from` de un cambio aplicable (de
cualquier tipo, incluido `reaction`), el sistema DEBE registrar en el almacén de
ventana el instante `Adapters.clock()` como último entrante de ese wa_id.

### R28
MIENTRAS la ventana del destino está abierta, `capabilities_for(destination)`
del adaptador DEBE devolver `free_text_allowed = true` y `requires_template =
false`.

### R29
MIENTRAS la ventana del destino está cerrada (o no hay entrante registrado),
`capabilities_for(destination)` del adaptador DEBE devolver `free_text_allowed =
false` y `requires_template = true`.

### R30
El método `capabilities()` sin destino del adaptador real DEBE devolver las
capacidades de ventana cerrada (R29).

### R31
CUANDO `send_response` recibe un adaptador que expone `capabilities_for`, el
sistema DEBE usar `capabilities_for(destination)` en lugar de `capabilities()`.

### R61
CUANDO `send_response` recibe un adaptador sin `capabilities_for` (Telegram,
`FakeWhatsAppAdapter`), el sistema DEBE usar `capabilities()`.

### R32
CUANDO se envía un `TextBlock` a un destino con ventana abierta, el adaptador
DEBE hacer un único `POST` a la URL de mensajes con encabezado `Authorization:
Bearer <WHATSAPP_ACCESS_TOKEN>` y cuerpo `{"messaging_product": "whatsapp",
"recipient_type": "individual", "to": destination, "type": "text", "text":
{"body": <texto>, "preview_url": false}}`.

### R62
CUANDO Meta responde 2xx al envío de un único bloque, el adaptador DEBE devolver
`"sent"`.

### R33
SI se intenta enviar un bloque distinto de `TemplateBlock` a un destino con
ventana cerrada ENTONCES el sistema DEBE lanzar `ChannelWindowClosed` (`POST
/send` responde `422` `validation_error`) sin realizar ninguna petición HTTP a
Meta.

### R34
CUANDO se envía un `TemplateBlock` (con ventana abierta o cerrada), el adaptador
DEBE hacer un `POST` con `"type": "template"`, `template.name = block.name`,
`template.language.code = WHATSAPP_TEMPLATE_LANGUAGE` y, si `block.variables`
no está vacío, `components = [{"type": "body", "parameters": [{"type": "text",
"text": v}, ...]}]` en el orden de `variables`.

### R35
CUANDO se envía un `TemplateBlock` sin variables, el adaptador NO DEBE incluir la
clave `components` en el cuerpo.

### R36
CUANDO se envía un `OptionsBlock` con `option_ids`, el adaptador DEBE enviar un
mensaje `"type": "interactive"` de tipo `"button"` con un botón `reply` por
opción, `reply.title = options[i]` y `reply.id = option_ids[i]` seguido de
`":" + option_proofs[i]` cuando exista prueba.

### R37
CUANDO el bloque inmediatamente anterior a un `OptionsBlock` con `option_ids` es
un `TextBlock` de hasta 1024 caracteres, el adaptador DEBE usar ese texto como
`interactive.body.text`.

### R54
CUANDO un `TextBlock` se fusiona como cuerpo interactivo según R37, el adaptador
NO DEBE enviarlo además como mensaje de texto aparte.

### R55
CUANDO el bloque anterior a un `OptionsBlock` con `option_ids` no existe, no es
un `TextBlock` o supera 1024 caracteres, el adaptador DEBE usar
`WHATSAPP_INTERACTIVE_BODY_TEXT` como `interactive.body.text`.

### R38
SI el `reply.id` compuesto de R36 supera 256 caracteres ENTONCES el adaptador
DEBE lanzar `ChannelSendFailed` sin realizar petición HTTP.

### R39
CUANDO se envía un `OptionsBlock` sin `option_ids`, un `ListBlock` o un
`LinkBlock`, el adaptador DEBE enviarlo como mensaje de texto con la misma
representación de `render_blocks` de Telegram (opciones en líneas, lista
numerada, `"<texto>: <url>"`), con `preview_url = true` solo para `LinkBlock`.

### R40
CUANDO una respuesta tiene varios bloques, el adaptador DEBE enviarlos en orden,
uno por petición (salvo la fusión de R37).

### R56
CUANDO todas las peticiones de una respuesta con varios bloques responden 2xx,
el adaptador DEBE devolver `"sent"`.

### R41
SI una petición de una respuesta con varios bloques falla ENTONCES el adaptador
NO DEBE enviar los bloques siguientes.

### R57
SI una petición a Meta falla ENTONCES el adaptador NO DEBE repetir esa petición.

### R58
SI una petición a Meta falla ENTONCES el adaptador DEBE propagar la excepción
traducida según R43–R45.

### R42
SI el almacén de ventana lanza una excepción al consultar el destino ENTONCES el
adaptador DEBE registrar un aviso y tratar la ventana como abierta, delegando en
la validación del orquestador (#41) y en la traducción del error 131047 (R43).

---

## Traducción de errores y estados

### R43
SI Meta responde no-2xx con código de error `131047` (fuera de la ventana de
atención) ENTONCES el adaptador DEBE lanzar `ChannelWindowClosed`.

### R44
SI Meta responde no-2xx con código de error `132000`, `132001`, `132005`,
`132007`, `132012`, `132015` o `132016` (plantilla inexistente, no aprobada,
pausada, deshabilitada o con parámetros incorrectos) ENTONCES el adaptador DEBE
lanzar `TemplateNotApproved`.

### R45
SI Meta responde no-2xx con cualquier otro código, con cuerpo no JSON, o la
petición falla por red o tiempo de espera (`httpx.HTTPError`) ENTONCES el
adaptador DEBE lanzar `ChannelSendFailed` (`POST /send` responde `502`
`upstream_error`).

### R46
CUANDO el adaptador traduce un error de Meta, DEBE registrar un log con el
estado HTTP, el código y el `error_subcode` de Meta y `fbtrace_id`.

### R59
CUANDO el adaptador traduce un error de Meta, el mensaje de la excepción
propagada NO DEBE contener el cuerpo de la respuesta de Meta.

### R47
CUANDO un cambio aplicable contiene `statuses[]`, el sistema DEBE traducir cada
`status` con `delivery_status()` y registrar `whatsapp_status` con wamid,
estado traducido y códigos de `errors[]`, sin reenviar nada al orquestador ni
marcar deduplicación.

### R48
El método `delivery_status(raw)` del adaptador real DEBE devolver `"sent"`,
`"delivered"`, `"read"` o `"failed"` para esos valores (sin distinguir
mayúsculas ni espacios) y `"failed"` para cualquier otro valor.

---

## Pruebas sin red

### R49
El `WhatsAppCloudAdapter` DEBE recibir por inyección un `httpx.Client`, de modo
que las pruebas usen `httpx.MockTransport` y ninguna prueba abra conexiones a
`graph.facebook.com`.

### R50
Las pruebas existentes de Telegram (`POST /telegram/webhook`, `POST /send`
legacy y canónico para `telegram`) DEBEN pasar sin modificaciones.

### R60
Las pruebas existentes de `FakeWhatsAppAdapter` DEBEN pasar sin modificaciones.

---

## Matriz de cobertura del acceptance

| Criterio de #43 | Requirements |
|---|---|
| 1. El dueño selecciona proveedor antes del spec | Decisión del dueño 2026-11-03 (sección inicial) |
| 2. Firma, normalización, texto/plantillas según ventana, estados y errores | R8–R22, R27–R48, R51, R52, R54–R59, R61, R62 |
| 3. Secretos y parámetros por entorno, no en repositorio | R1–R7 |
| 4. Pruebas con cliente falso: firma válida/inválida, duplicado, dentro/fuera de ventana, plantillas, fallos, estados; `./init.sh` verde | R11–R13, R23–R26, R32–R35, R41–R49, R50, R53, R56–R60, R62 |
