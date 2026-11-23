# Contratos entre servicios

> Versión 1 (versión mínima del chatbot). Fuente de verdad: los modelos Pydantic
> del paquete `lazaro_contracts`; este documento es su versión legible y los tests
> de `contracts/tests/` comprueban que ambos coinciden.

- Todas las rutas son HTTP + JSON en UTF-8 (salvo `POST /manuals`, que es
  `multipart/form-data`, ver supuesto S1).
- Las fechas van en ISO 8601 **con zona horaria** (p. ej. `2026-10-30T19:05:00Z`);
  una fecha sin zona se rechaza con `422 validation_error`.
- Los identificadores (`case_id`, `contact_id`, `advisor_id`, `chunk_id`,
  `manual_id`) son texto de 1 a 64 caracteres. Los ids de Telegram
  (`update_id`, `telegram_user_id`, `chat_id`) son enteros.
- Los textos de mensajes (`text`) tienen de 1 a 4096 caracteres.
- Un campo no declarado en el modelo se rechaza con `422 validation_error`.

## Reglas comunes

### Autenticación

Toda ruta del contrato exige el encabezado `X-Service-Token` (constante
`SERVICE_TOKEN_HEADER`) con un valor igual a la variable de entorno
`SERVICE_TOKEN`. Si falta o no coincide, la respuesta es `401` con
`error` = `unauthorized`.

Excepciones (no piden token):

- `GET /health` de cada servicio.
- El webhook de Telegram del `telegram_gateway` (lo llama Telegram, que no conoce
  el token; su protección la fija la feature del gateway).
- `POST /webhooks/{canal_id}` del `telegram_gateway` (desde #62): lo llama un
  sistema externo que no conoce el token; se protege con `X-Lazaro-Signature`
  (ver «Canal genérico (webhook firmado)»).

### Errores

Todo error tiene la forma `{"error": "<codigo>", "message": "<texto>"}` (modelo
`ErrorResponse`). `error` es un código en `snake_case` (`^[a-z][a-z0-9_]*$`) y
`message` un texto no vacío para personas. Nunca se devuelve el stack trace.

| HTTP | `error`              | Dónde | Cuándo |
|------|----------------------|-------|--------|
| 401  | `unauthorized`       | todas las rutas del contrato | falta `X-Service-Token` o no coincide con `SERVICE_TOKEN` |
| 422  | `validation_error`   | todas | el cuerpo no valida contra el modelo (el servicio sustituye la respuesta 422 por defecto de FastAPI por `{error, message}`) |
| 403  | `forbidden`          | `GET /cases` (`scope=all`), `/cases/{id}/authorize`, `/cases/{id}/reply`, `/cases/{id}/close`, `/cases/{id}/assign`, `/cases/{id}/transfer`, `/cases/{id}/reassign` | el perfil no está autorizado para esa acción (S12) |
| 404  | `not_found`          | `/cases/{id}/reply`, `/cases/{id}/close`, `/cases/{id}/reassign`, `/cases/{id}/auto-assign` | el caso no existe |
| 409  | `case_closed`        | `/cases/{id}/assign`, `/cases/{id}/reply`, `/cases/{id}/reassign`, `/cases/{id}/auto-assign` | el caso está cerrado (S11) |
| 409  | `case_not_assigned`  | `/cases/{id}/reassign` | el caso no está `assigned` y no se puede reasignar (S12) |
| 409  | `case_changed`       | `/cases/{id}/reassign` | el caso cambió entre la lectura y la escritura condicional (S12) |
| 409  | `channel_exists` | `POST /channels` | ya existe el `id` solicitado |
| 409  | `channel_managed_by_environment` | `/channels/{channel_id}` (secretos) | la operación intenta cambiar secretos de un canal gestionado por el entorno |
| 415  | `unsupported_format` | `/manuals` | el archivo no es PDF ni DOCX |
| 422  | `empty_document`     | `/manuals` | archivo vacío o sin texto extraíble |
| 422  | `channel_inactive` | `/send` | el canal existe, pero está inactivo |
| 422  | `channel_window_closed` | `/send` | la ventana de atención del canal está cerrada (la outbox marca `fuera_de_ventana`) |
| 502  | `telegram_error`     | `/send` | la API de Telegram falla |
| 502  | `upstream_error`     | `/send` (variante canónica), `/cases/{id}/reply` | falla el adaptador del canal o la llamada a `POST /send` del gateway |
| 503  | `channel_secrets_unavailable` | `/send`, `/channels…` | falta la clave de secretos, es inválida o no permite descifrar un secreto guardado |
| 503  | `channel_store_unavailable` | `/send`, `/channels…` | el almacén PostgreSQL de canales no está disponible |
| 503  | `roster_out_of_sync` | `/handover`, `/cases`, `/cases/{id}/authorize`, `/cases/{id}/assign`, `/cases/{id}/auto-assign`, `/cases/{id}/transfer`, `/cases/{id}/reassign`, `/cases/{id}/close` | la generación del roster indicada en `X-Advisor-Roster-Generation` no coincide con la sincronizada (S12) |
| 503  | `privacy_not_configured` | `/privacy/purge` | falta `PRIVACY_RETENTION_DAYS` (o, en handover, `PRIVACY_ACTIVE_CASE_MAX_DAYS`); no se borra nada |
| 500  | `internal_error`     | todas | error inesperado; nunca se devuelve el stack trace |

### Mensajes repetidos

`update_id` (el id que Telegram asigna a cada actualización) es el
identificador único por mensaje en el payload Telegram histórico. El
orquestador guarda los `update_id` ya vistos; ante un `update_id` ya visto
responde `202` con `status` = `duplicate` sin reprocesar el mensaje (no busca,
no responde, no crea casos).

En el vocabulario multicanal la clave de idempotencia es la pareja no ambigua
`(channel, external_message_id)`, tanto en Redis como en el orquestador. El
mismo `external_message_id` en dos canales distintos son dos mensajes
distintos. El payload Telegram histórico se traduce a `channel = telegram` y
`external_message_id = str(update_id)`.

### Salud

Los 4 servicios (`telegram_gateway`, `orchestrator`, `rag`, `handover`) exponen
`GET /health` sin token. La ruta comprueba las dependencias críticas del
servicio con una operación de solo lectura y un timeout finito
(`HEALTHCHECK_TIMEOUT_SECONDS`): Redis y, desde #61, PostgreSQL en
`telegram_gateway`; PostgreSQL en `orchestrator`, `rag` y `handover`.

- Saludable: `200` con `{"status": "ok", "service": "<nombre>"}` (modelo
  `HealthResponse`), donde `<nombre>` es el nombre del servicio.
- No saludable: `503` con `status` = `unhealthy`, el nombre del servicio y el
  mapa `dependencies` con el nombre de cada dependencia fallida. Una dependencia
  que falla o excede el timeout se representa como `unavailable`, por ejemplo
  `{"status": "unhealthy", "service": "orchestrator", "dependencies":
  {"postgres": "unavailable"}}`.

La respuesta nunca incluye URLs, credenciales, DSN, hostnames, usuarios ni
mensajes de excepción. La ruta sigue siendo pública, no exige
`X-Service-Token` y no ejecuta operaciones de negocio.


## Mensaje normalizado y respuesta abstracta

El núcleo no interpreta protocolos de canal. Los adaptadores traducen la
entrada a `NormalizedMessage` y la salida a una lista de bloques
(`ResponseBlocks`). Telegram conserva su payload histórico; WhatsApp usa el
adaptador falso hasta que exista el proveedor real (#43).

### NormalizedMessage

`POST /messages` acepta el payload legacy `MessageRequest` o un
`NormalizedMessage` canónico. La unión se decide por los campos presentes.

| Campo | Tipo | Obligatorio | Descripción |
|-------|------|-------------|-------------|
| `channel` | slug de canal (2–32, `^[a-z][a-z0-9]*(?:[-_][a-z0-9]+)*$`) | sí | `id` del canal en `canales` |
| `external_user_id` | texto (1–128) | sí | id de usuario del canal |
| `external_chat_id` | texto (1–128) | sí | chat del canal |
| `external_message_id` | texto (1–128) | sí | id del mensaje del proveedor; en Telegram es `update_id` |
| `kind` | `text` \| `button` \| `unsupported` \| `image` \| `file` \| `audio` | sí | tipo de contenido |
| `text` | texto (1–4096) | si `kind = text` | contenido de texto; en un tipo multimedia es el pie opcional |
| `button_id` | texto (1–128) | si `kind = button` | id canónico del botón pulsado |
| `button_proof` | texto (1–128) | no | prueba HMAC truncada de la versión/hash del aviso que originó el botón (S15) |
| `received_at` | fecha ISO 8601 con zona | sí | momento de recepción en UTC; en `outbound`, el momento en que la plataforma generó el mensaje |
| `direction` | `inbound` \| `outbound` | no | sentido del mensaje; por defecto `inbound` |
| `attachments` | lista de `Attachment` (máx. 10) | no | metadatos de imagen, archivo o audio; nunca el binario; por defecto `[]` |
| `metadata` | objeto JSON (≤ 4096 bytes y profundidad 5) | no | datos específicos del canal; por defecto `{}` |

En Telegram, un `callback_query` se normaliza con el id del callback como
`external_message_id` y con el id canónico del botón (no el texto visible) como
`button_id`. La prueba `button_proof` viaja junto al botón y permite al
orquestador descartar clics de avisos obsoletos o manipulados (S15).

Los tipos multimedia (`image`, `file` y `audio`) exigen al menos un adjunto y
todos sus adjuntos deben tener el mismo `type`; `text`, `button` y `unsupported`
no llevan adjuntos. Un mensaje `outbound` no puede ser `button` ni
`unsupported`. Al serializar, `direction`, `attachments` y `metadata` se omiten
cuando tienen su valor por defecto (`inbound`, `[]` y `{}`), así los payloads
antiguos conservan sus claves.

### Attachment

| Campo | Tipo | Obligatorio | Descripción |
|-------|------|-------------|-------------|
| `type` | `image` \| `file` \| `audio` | sí | tipo del adjunto; coincide con `kind` del mensaje |
| `mime_type` | texto (3–255, `tipo/subtipo` con parámetros opcionales) | sí | tipo MIME del contenido |
| `name` | texto (1–255) | no | nombre del archivo; no es una ruta ni lleva controles |
| `size_bytes` | entero (0–2 147 483 648) | no | tamaño en bytes |
| `url` | URL https (1–2048) | no | enlace externo al contenido |

Los adjuntos llevan metadatos: nunca el binario. `mime_type` es obligatorio
(el adaptador lo conoce o usa `application/octet-stream`); `name`, `size_bytes`
y `url` son opcionales.

`client_id` no viaja desde los adaptadores: lo resuelve el flujo de identidad
posterior. Un campo no declarado se rechaza con `422 validation_error`.

### ResponseBlocks

La respuesta abstracta es una lista no vacía de bloques con discriminador
`type`; como máximo un bloque de enlace por respuesta.

| Bloque | Campo `type` | Regla |
|--------|--------------|-------|
| `TextBlock` | `text` | texto de 1 a 4096 caracteres |
| `OptionsBlock` | `options` | máximo 3 opciones y 20 caracteres por opción; `option_ids` y `option_proofs` opcionales, alineados con `options`, para pintar botones interactivos (S15) |
| `ListBlock` | `list` | de 4 a 10 opciones |
| `LinkBlock` | `link` | un texto y una URL; máximo un enlace por respuesta |
| `TemplateBlock` | `template` | nombre y variables de una plantilla aprobada |
| `ImageBlock` | `image` | URL https (hasta 2048) y `alt_text` (1–1024); un canal sin `supports_images` la degrada a enlace o texto (#61) |

### ChannelCapabilities

Antes de enviar texto libre, el núcleo consulta las capacidades del adaptador.
Fuera de la ventana de 24 horas de WhatsApp (`free_text_allowed = false`,
`requires_template = true`) solo se envía una plantilla aprobada. Los estados de
entrega se normalizan al vocabulario `sent`, `delivered`, `read` o `failed`.

| Campo | Tipo | Obligatorio | Descripción |
|-------|------|-------------|-------------|
| `free_text_allowed` | booleano | sí | si el canal admite texto libre ahora |
| `max_options` | entero (0–3) | sí | máximo de opciones de un `OptionsBlock` |
| `min_list_options` | entero (0–10) | sí | mínimo de opciones de un `ListBlock` |
| `max_list_options` | entero (0–10) | sí | máximo de opciones de un `ListBlock` |
| `supports_links` | booleano | sí | si el canal representa enlaces |
| `requires_template` | booleano | sí | si exige una plantilla aprobada |
| `supports_buttons` | booleano | no | botones interactivos; por defecto `true` |
| `supports_images` | booleano | no | imágenes; por defecto `false` |
| `supports_files` | booleano | no | archivos; por defecto `false` |
| `supports_audio` | booleano | no | audio; por defecto `false` |

### Variante canónica de POST /send

Además del `SendRequest` legacy, `POST /send` acepta `ChannelSendRequest` con
`channel`, `destination` y `blocks` (lista de `ResponseBlock`). El `telegram_gateway`
busca el canal en PostgreSQL, resuelve su adaptador mediante `ChannelRegistry` y
degrada los bloques según las capacidades antes de comprobar ventana o plantilla.
`SendRequest` legacy usa el canal `telegram`. Si no existe una fila, responde
`422 validation_error`; si está inactivo, `422 channel_inactive`; si el adaptador
no está disponible, `502 upstream_error`; si PostgreSQL falla,
`503 channel_store_unavailable`; y si los secretos guardados no se pueden
descifrar, `503 channel_secrets_unavailable`. Una respuesta que el adaptador no
puede enviar porque la ventana de atención está cerrada (Meta 24 h, WhatsApp,
cupo de TikTok) responde `422 channel_window_closed`, y el worker de la outbox
deja la fila en estado `fuera_de_ventana` sin reintentarla. Si exige una
plantilla no aprobada responde `422 validation_error`; si falla el envío,
`502 upstream_error`.

### Degradación por capacidades

Antes de enviar, `telegram_gateway` conserva el orden de los bloques y los que
el canal admite. Los bloques que no puede representar se degradan así:

| Bloque | Capacidad ausente o límites incumplidos | Degradación |
|--------|------------------------------------------|-------------|
| `OptionsBlock` | `supports_buttons=false` o más de `max_options` | `TextBlock` con opciones numeradas (`1. A`, `2. B`, …) |
| `ListBlock` | menos de `min_list_options` o más de `max_list_options` | `TextBlock` con opciones numeradas |
| `ImageBlock` | `supports_images=false` | `LinkBlock` con `text=alt_text`, `url=url` si admite enlaces; si no, `TextBlock` con `<alt_text>: <url>` |
| `LinkBlock` | `supports_links=false` | `TextBlock` con `<text>: <url>`; si supera 4096 caracteres, dos bloques de texto (texto y URL) |

La degradación es pura: no hace IO ni modifica la lista de entrada. Después de
degradar, se validan las capacidades de texto libre, la ventana de WhatsApp y
las plantillas.

## Canal genérico (webhook firmado)

Cualquier sistema externo o puente —n8n, Zapier, Make, Twilio— conecta un canal
sin adaptador propio. La ruta y el callback se implementan en #62. El formato por
defecto es el `NormalizedMessage` de este contrato; si el adaptador del canal
define otro formato, lo traduce (#62).

El tipo de adaptador es `webhook_generico` (registrado por el gateway, no
gestionado por el entorno). Su `config` puede incluir `callback_url` (opcional):
una URL `https` de hasta 2048 caracteres, con host y sin credenciales
incrustadas. Sin `callback_url` el canal recibe mensajes pero no puede responder
(ver «Callback saliente»).

### Firma y ventana anti-repetición

- `X-Lazaro-Timestamp`: segundos Unix (entero decimal, UTC) del envío.
- `X-Lazaro-Signature`: HMAC-SHA256 con el secreto del canal de
  `<timestamp>.<cuerpo>`, en 64 caracteres hexadecimales en minúsculas,
  calculado sobre los bytes exactos del cuerpo (UTF-8, sin reformatear).
- Ventana: 300 s por defecto (`DEFAULT_SIGNATURE_WINDOW_SECONDS`), configurable
  con `WEBHOOK_SIGNATURE_WINDOW_SECONDS` (entero, 1-3600); si
  |ahora − timestamp| la supera, `401`.
- Firma ausente o incorrecta: `401`. La comparación es en tiempo constante.
- Tamaño máximo del cuerpo: `WEBHOOK_MAX_BODY_BYTES` (entero, 1024-10485760,
  1 MiB por defecto); por encima, `413 payload_too_large`.
- Cada canal tiene su secreto (#61); nunca viaja en el cuerpo ni en logs.
- Los ejemplos usan el secreto de ejemplo `secreto-de-ejemplo`.

### POST /webhooks/{canal_id}

- **Expone:** telegram_gateway (desde #62)
- **Llama:** el sistema externo o puente del canal
- **Modelos:** `NormalizedMessage` → `MessageResponse`

`{canal_id}` es el `id` del canal en `canales`; el `channel` del cuerpo debe ser
igual a `{canal_id}` y `direction` debe ser `inbound`. Público: sin
`X-Service-Token`. Idempotente por `(channel, external_message_id)`.

Los errores se aplican en este orden: `404` (canal inexistente, inactivo, sin
secreto o sin adaptador), `413` (cuerpo demasiado grande), `401` (firma o
ventana) y `422` (cuerpo inválido). Un cuerpo inválido con firma incorrecta
responde `401`, nunca `422`. Un canal inexistente o inactivo responde el mismo
`404 not_found` sin revelar cuál de los dos casos es.

#### Request

| Campo | Tipo | Obligatorio | Descripción |
|-------|------|-------------|-------------|
| `X-Lazaro-Timestamp` | segundos Unix | sí | instante del envío |
| `X-Lazaro-Signature` | hexadecimal (64) | sí | HMAC-SHA256 de `<timestamp>.<cuerpo>` |
| `Content-Type: application/json` | encabezado | sí | cuerpo JSON |

El cuerpo es un `NormalizedMessage`.

#### Respuesta

`200 OK`

| Campo | Tipo | Obligatorio | Descripción |
|-------|------|-------------|-------------|
| `status` | `accepted` \| `duplicate` | sí | `accepted` si se procesa; `duplicate` si ya se vio |

#### Errores

| HTTP | error | Cuándo |
|------|-------|--------|
| 401 | unauthorized | firma ausente o incorrecta, o `X-Lazaro-Timestamp` fuera de la ventana |
| 404 | not_found | el canal no existe, está inactivo, no tiene secreto o su adaptador no está disponible (no se distingue cuál) |
| 413 | payload_too_large | el cuerpo supera `WEBHOOK_MAX_BODY_BYTES` |
| 422 | validation_error | el cuerpo no valida, `channel` ≠ `{canal_id}` o `direction` ≠ `inbound` |
| 500 | internal_error | error inesperado |
| 503 | channel_store_unavailable | no se pudo consultar la tabla `canales` |
| 503 | channel_secrets_unavailable | no se pudieron descifrar los secretos del canal |

#### Ejemplo firmado

```http
POST /webhooks/canal-externo HTTP/1.1
Host: lazaro.example.com
Content-Type: application/json
X-Lazaro-Timestamp: 1795273200
X-Lazaro-Signature: 0812c9aa0ad1983b42a1a4a122fdf3741469c299ef746fcbf3a55a858be97acd

{"channel":"canal-externo","external_user_id":"usuario-123","external_chat_id":"usuario-123","external_message_id":"msg-0001","kind":"text","text":"Hola, necesito ayuda con mi pedido","received_at":"2026-11-21T15:00:00Z"}
```

#### Ejemplo con adjunto

```json
{
  "channel": "canal-externo",
  "external_user_id": "usuario-123",
  "external_chat_id": "usuario-123",
  "external_message_id": "msg-0002",
  "direction": "inbound",
  "kind": "image",
  "text": "Foto del producto dañado",
  "attachments": [
    {
      "type": "image",
      "mime_type": "image/jpeg",
      "name": "producto.jpg",
      "size_bytes": 248133,
      "url": "https://archivos.example.com/m/abc123.jpg"
    }
  ],
  "metadata": {"plataforma": "n8n", "flujo": "soporte-web"},
  "received_at": "2026-11-21T15:01:00Z"
}
```

### Callback saliente

- **Expone:** el sistema externo (`config.callback_url`, https)
- **Llama:** telegram_gateway (desde #62)
- **Modelos:** `NormalizedMessage` con `direction` = `outbound`

Cuando la plataforma responde por un canal genérico hace `POST` a
`config.callback_url` con los mismos encabezados de firma. Una respuesta 2xx es
entrega y cualquier otra respuesta (incluidos `3xx`, que no se siguen) o un
error de red es envío fallido. La entrega es al menos una vez: el receptor
deduplica por `external_message_id`. En `outbound`, `received_at` es el momento
en que la plataforma generó el mensaje. Se implementa en #62. Un callback
fallido o bloqueado hace que `POST /send` responda `502 upstream_error`.

Anti-SSRF: la URL debe ser `https` con host y sin credenciales; antes de enviar
se resuelve y todas sus direcciones deben ser públicas (se rechazan privadas
RFC 1918, loopback, link-local y metadatos como `169.254.169.254`, CGNAT
`100.64.0.0/10`, no especificadas, multicast, reservadas e IPv4 mapeada en IPv6
que cumpla lo anterior). Se conecta a la dirección ya validada conservando el
`Host` y el SNI originales y no se siguen redirecciones. Un canal sin
`callback_url` no puede responder (`502 upstream_error`). Solo en desarrollo,
`WEBHOOK_ALLOW_PRIVATE_CALLBACKS=true` admite `http` y direcciones bloqueadas;
en producción el servicio no arranca con ese ajuste.

#### Ejemplo firmado

```http
POST /lazaro/callback HTTP/1.1
Host: puente.example.com
Content-Type: application/json
X-Lazaro-Timestamp: 1795273205
X-Lazaro-Signature: 20dbabb2d55dc0b43c41f73c600c519989ecb737691d17a5b2e77156426d180a

{"channel":"canal-externo","external_user_id":"usuario-123","external_chat_id":"usuario-123","external_message_id":"out-0001","kind":"text","text":"Hola, con gusto te ayudo. Escribe tu numero de pedido.","received_at":"2026-11-21T15:00:05Z","direction":"outbound"}
```

### Equivalencia con los nombres del encargo

| Nombre del encargo | Campo del contrato | Notas |
|---|---|---|
| `canalId` | `channel` | también `{canal_id}` de la ruta; deben coincidir |
| `idExternoUsuario` | `external_user_id` | |
| `idExternoMensaje` | `external_message_id` | clave de idempotencia junto con `channel` |
| `direccion` | `direction` | `entrante` = `inbound`, `saliente` = `outbound` |
| `tipo` | `kind` | `texto`, `boton`, `no_soportado`, `imagen`, `archivo`, `audio` = `text`, `button`, `unsupported`, `image`, `file`, `audio` |
| `contenido` | `text` | en `kind` = `button`, el contenido es `button_id` |
| `adjuntos` | `attachments` | metadatos, nunca el binario |
| `timestamp` | `received_at` | ISO 8601 con zona; distinto de `X-Lazaro-Timestamp` (segundos Unix de la firma) |
| `metadata` | `metadata` | objeto JSON ≤ 4096 bytes |

(`external_chat_id` no tiene nombre en el encargo: en canales sin chat separado
es igual a `external_user_id`.)

## Canal simulado

Un canal de **DEMOSTRACIÓN** que se hace pasar por cualquier plataforma (por
ejemplo «TikTok (simulado)») sin credenciales ni llamadas de red. El tipo de
adaptador es `simulado`; la palabra `SIMULADO` aparece en su clase, su docstring
y en la etiqueta que muestra el panel. Sus respuestas salientes no viajan a
ninguna red: quedan en un buzón propio que el panel y
`scripts/simular_canal.py` pueden consultar.

El `id` del canal es un slug normal de `canales`; nombre, ícono y color salen de
las columnas de esa fila (no se duplican en `config`). `config` solo admite la
clave `capabilities`; cualquier otra clave responde `422 validation_error` y no
se persiste. `config.capabilities` es un objeto cuyas claves ausentes toman estos
valores por defecto:

| Clave | Por defecto |
|---|---|
| `free_text_allowed` | `true` |
| `supports_buttons` | `false` |
| `supports_links` | `false` |
| `supports_images` | `false` |
| `supports_files` | `false` |
| `supports_audio` | `false` |
| `requires_template` | `false` |
| `max_options` | `0` |
| `min_list_options` | `0` |
| `max_list_options` | `0` |

Dos canales simulados con `capabilities` distintas informan capacidades
distintas. Los bloques que un canal no admite se degradan como en cualquier
otro canal (por ejemplo `ImageBlock` con `supports_images=false` pasa a enlace o
texto). La retención y el tamaño del buzón se ajustan con
`SIMULATED_MAILBOX_RETENTION_SECONDS` (por defecto 3600, entre 60 y 86400) y
`SIMULATED_MAILBOX_MAX_ENTRIES` (por defecto 500, entre 10 y 5000). El buzón es
**solo de pruebas**: no se deben usar datos personales reales.

Desde #65 el orquestador atiende cualquier canal registrado: un mensaje
simulado recorre el flujo completo (consentimiento, login, bot y asesor) y las
respuestas vuelven al buzón del mismo canal y destino. Si el orquestador
rechaza la entrega, el buzón la registra como `rejected` con el motivo y el
webhook firmado sigue respondiendo `200 accepted`.

### GET /channels/{channel_id}/mailbox

- **Expone:** telegram_gateway (desde #63)
- **Llama:** el panel del orquestador y `scripts/simular_canal.py`
- **Modelos:** parámetros de consulta → `MailboxResponse`
- **Autenticación:** `X-Service-Token`

Ruta interna: exige `X-Service-Token`. Devuelve las entradas del canal con
`id > after` en orden ascendente, filtradas por `destination` si se indica.
Acepta `destination` (opcional), `after` (por defecto `0`, entero ≥ 0) y
`limit` (por defecto `100`, entre 1 y 500). Un canal inexistente o de un tipo
sin buzón responde el mismo `404 not_found`; un canal simulado inactivo sí se
puede leer.

#### Request

| Parámetro | Tipo | Obligatorio | Descripción |
|-----------|------|-------------|-------------|
| `destination` | texto | no | id externo de prueba a filtrar |
| `after` | entero ≥ 0 | no | devuelve solo entradas con `id` mayor |
| `limit` | entero 1-500 | no | máximo de entradas (por defecto 100) |

#### Respuesta

`200 OK`

```json
{
  "channel": "tiktok-simulado",
  "entries": [
    {
      "id": 1,
      "channel": "tiktok-simulado",
      "destination": "cliente-demo",
      "kind": "client",
      "text": "Hola, quiero información",
      "created_at": "2026-11-21T15:00:00Z"
    },
    {
      "id": 2,
      "channel": "tiktok-simulado",
      "destination": "cliente-demo",
      "kind": "reply",
      "text": "Plataforma (bot o asesor): Hola, con gusto te ayudo.",
      "created_at": "2026-11-21T15:00:01Z"
    }
  ]
}
```

#### Errores

| HTTP | error | Cuándo |
|------|-------|--------|
| 401 | unauthorized | falta `X-Service-Token` o no es válido |
| 404 | not_found | el canal no existe o su tipo no tiene buzón (no se distingue cuál) |
| 422 | validation_error | `after` o `limit` fuera de rango |
| 503 | channel_store_unavailable | no se pudo consultar el almacén de canales o el buzón |

### POST /channels/{channel_id}/simulate

- **Expone:** telegram_gateway (desde #63)
- **Llama:** el panel del orquestador (página del simulador)
- **Modelos:** `SimulatedInboundRequest` → `SimulatedInboundResponse`
- **Autenticación:** `X-Service-Token`

Ruta interna: exige `X-Service-Token`; no exige firma porque el token autentica
al panel. Construye un `NormalizedMessage` de entrada
(`external_chat_id` = `external_user_id`, `kind` = `text`,
`external_message_id` con prefijo `sim-`) y lo entrega por el mismo camino que
el webhook firmado. El resultado indica si el orquestador lo aceptó. Un canal
simulado inactivo no recibe mensajes (`422 channel_inactive`).

#### Request

```json
{"external_user_id": "cliente-demo", "text": "Hola, quiero información"}
```

#### Respuesta

`200 OK`

```json
{"status": "accepted", "forwarded": true}
```

Si el orquestador rechaza o falla, `forwarded` es `false` y `reason` trae el
motivo (hasta 200 caracteres), por ejemplo:

```json
{"status": "accepted", "forwarded": false, "reason": "El orquestador respondió 422."}
```

#### Errores

| HTTP | error | Cuándo |
|------|-------|--------|
| 401 | unauthorized | falta `X-Service-Token` o no es válido |
| 404 | not_found | el canal no existe o su tipo no tiene buzón (no se distingue cuál) |
| 422 | validation_error | el cuerpo no valida contra `SimulatedInboundRequest` |
| 422 | channel_inactive | el canal simulado está inactivo |
| 503 | channel_store_unavailable | no se pudo consultar el almacén de canales o el buzón |

### Ejemplo firmado con scripts/simular_canal.py

El script envía al webhook genérico con los mismos encabezados y la misma firma
de «Canal genérico (webhook firmado)»: `X-Lazaro-Timestamp` en segundos Unix y
`X-Lazaro-Signature` = HMAC-SHA256 hexadecimal de `<timestamp>.<cuerpo>`, sobre
los bytes exactos del cuerpo. El secreto se lee de la variable de entorno
`LAZARO_CANAL_SECRETO` (o la indicada con `--secreto-env`) y nunca se pasa como
argumento ni se imprime. La firma se verifica con el ejemplo firmado de la
sección anterior usando el secreto de ejemplo `secreto-de-ejemplo`.

## Media público de respuestas rápidas

### GET /media/respuestas/{image_id}

- **Expone:** orchestrator (desde #71)
- **Llama:** el canal o el navegador que pinta la respuesta rápida
- **Autenticación:** ninguna (ruta pública del mismo origen)

No es una ruta entre servicios ni añade modelos al contrato. Sirve una imagen
subida desde el panel de respuestas rápidas del bot (`ImageBlock` con `url`
https). `image_id` es un `uuid4().hex` de 32 caracteres hex; un id con otro
formato o inexistente responde `404`. La respuesta lleva el `Content-Type`
detectado por la firma binaria (PNG, JPEG o WebP) y
`X-Content-Type-Options: nosniff`.

## Servidor MCP de solo lectura (#74)

No añade rutas HTTP entre servicios: el protocolo es MCP por streamable HTTP en
la red interna. `mcp_lectura` expone solo las herramientas `buscar_manuales` y
`ofertas_demo`, ambas con `readOnlyHint=true`; toda petición exige
`X-Service-Token` (salvo `GET /health`) y el orquestador envía `X-Cliente-Id`
desde la sesión, fuera del esquema de la herramienta. `buscar_manuales` consume
`POST /search` del RAG y `ofertas_demo` solo lee la tabla de DEMOSTRACIÓN. Ver
`docs/mcp.md`.

## Canales (registro del gateway)

`telegram_gateway` es propietario de la tabla `canales`. El `id` es un slug de
canal; `name`, `adapter_type`, `icon`, `color`, `config`, `active` y `created_at`
se corresponden con `nombre`, `tipo_adaptador`, `icono`, `color`, `config`,
`activo` y `creado_en`. `config` solo contiene opciones públicas. `credentials`
y el secreto de webhook se guardan juntos, cifrados, en `config_secreta` y nunca
se devuelven en listados, errores ni logs. `has_secrets` solo indica si existe
un secreto cifrado; `configured` indica si el adaptador registrado está
disponible en esta instancia.

Las filas `telegram` y `whatsapp` se crean automáticamente a partir de la
configuración actual. Son `managed_by_environment=true`; sus credenciales siguen
en variables de entorno y no se copian a la base. Mientras
`activo_segun_entorno=true`, `active` sigue la disponibilidad del adaptador;
`PATCH /channels/{channel_id}/active` fija el valor manualmente y desactiva ese
seguimiento. Solo se pueden crear canales con un `adapter_type` registrado y no
gestionado por el entorno. Todas las rutas exigen `X-Service-Token`.

| Campo JSON | Columna `canales` |
|------------|-------------------|
| `name` | `nombre` |
| `adapter_type` | `tipo_adaptador` |
| `icon` | `icono` |
| `active` | `activo` |
| `created_at` | `creado_en` |
| `credentials` y `secret` | `config_secreta` (cifrado) |

### ChannelInfo y ChannelListResponse

| Campo | Tipo | Obligatorio | Descripción |
|-------|------|-------------|-------------|
| `id` | slug de canal (2–32) | sí | id único del canal |
| `name` | texto (1–60) | sí | nombre visible, sin controles ni solo espacios |
| `adapter_type` | slug de canal (2–32) | sí | tipo de adaptador registrado |
| `icon` | texto (1–32) | sí | identificador visual, sin controles |
| `color` | `#RRGGBB` | sí | color hexadecimal |
| `config` | objeto JSON (≤ 4096 bytes, profundidad 5) | sí | configuración pública, nunca credenciales |
| `active` | booleano | sí | si el canal puede enviar |
| `configured` | booleano | sí | si el adaptador está disponible en esta instancia |
| `has_secrets` | booleano | sí | si hay secreto o credenciales cifrados guardados |
| `managed_by_environment` | booleano | sí | si el canal lo gestiona la configuración del entorno |
| `created_at` | fecha ISO 8601 con zona | sí | fecha de creación |
| `capabilities` | `ChannelCapabilities` o `null` | no (por defecto `null`) | capacidades por defecto (sin destino) del tipo de adaptador; `null` si el tipo no está registrado |
| `credential_hints` | objeto `nombre → pista` | no (por defecto `{}`) | pista de cada credencial guardada: `…` y sus últimos 4 caracteres si mide 8 o más, o solo `…`; nunca el valor completo (#66) |

Íconos (#66): el panel de administración solo ofrece los ids de
`CHANNEL_ICONS` (`chat`, `telegram`, `whatsapp`, `web`, `correo`, `telefono`,
`sms`, `instagram`, `facebook`, `tienda`, `bot`, `soporte`), que se muestran como
emoji. Un ícono guardado fuera de la lista se muestra como `chat`.

Claves reservadas de `config`:

| Clave | Valores | Por defecto | Uso |
|-------|---------|-------------|-----|
| `consent_mode` | `texto` \| `boton` | `texto` | cómo pide el orquestador el consentimiento: `texto` con frase de aceptación; `boton` con las opciones `Acepto` y `No acepto` |

`POST /channels` y `PATCH /channels/{id}` responden `422 validation_error` si
`config.consent_mode` no es `texto` ni `boton`. Al leer, un valor guardado
inválido o ausente se trata como `texto`. El gateway siembra `telegram` con
`consent_mode="texto"` y `whatsapp` con `consent_mode="boton"`, y solo completa
la clave cuando falta (nunca sobrescribe un valor ya guardado).

El orquestador trata como *canal con ventana* (plantilla aprobada fuera de la
ventana de texto libre) a todo canal cuyas `capabilities` informan
`free_text_allowed=false` y `requires_template=true`; el resto, o `null`, no
tiene ventana. Consulta `GET /channels` con `X-Service-Token` y guarda una copia
durante `CHANNEL_DIRECTORY_TTL_SECONDS` (30 por defecto).

`ChannelListResponse` tiene `channels` (lista de `ChannelInfo`) y
`adapter_types` (tipos registrados que admiten canales nuevos). La lista se
ordena por `created_at` y después por `id`.

### POST /channels

- **Expone:** `telegram_gateway`
- **Llama:** panel de administración (#66) o cliente interno autorizado
- **Modelos:** `ChannelCreateRequest` → `ChannelCreateResponse`

Crea un canal con un tipo de adaptador registrado no gestionado por el entorno.
El secreto nuevo solo aparece en esta respuesta y en la ruta explícita para
revelarlo. Si el `id` ya existe responde `409 channel_exists`; si el adaptador
no admite creación en esta instancia, `422 validation_error`. Requiere
`CHANNEL_SECRETS_KEY` válida; si falta o no se puede cifrar responde
`503 channel_secrets_unavailable` sin guardar nada.

#### Request

| Campo | Tipo | Obligatorio | Descripción |
|-------|------|-------------|-------------|
| `id` | slug (2–32) | sí | id único del canal |
| `name` | texto (1–60) | sí | nombre visible |
| `adapter_type` | slug | sí | tipo registrado y no gestionado por el entorno |
| `icon` | texto (1–32) | sí | identificador visual |
| `color` | `#RRGGBB` | sí | color hexadecimal |
| `config` | objeto JSON ≤ 4096 bytes, profundidad 5 | no | configuración pública; por defecto `{}` |
| `credentials` | objeto de hasta 20 pares | no | credenciales; se cifran y reemplazan completas; por defecto `{}` |
| `active` | booleano estricto | no | estado inicial; por defecto `true` |

```json
{
  "id": "canal-demo",
  "name": "Canal de demostración",
  "adapter_type": "simulado",
  "icon": "chat",
  "color": "#1B6FA8",
  "config": {"modo": "demo"},
  "credentials": {"api_token": "valor-de-ejemplo"},
  "active": true
}
```

#### Respuesta

`201 Created`, cuerpo `ChannelCreateResponse`:

| Campo | Tipo | Obligatorio | Descripción |
|-------|------|-------------|-------------|
| `channel` | `ChannelInfo` | sí | metadatos públicos del canal creado |
| `secret` | texto URL-safe de 43 caracteres | sí | secreto de canal; guárdalo en un lugar seguro |

```json
{
  "channel": {
    "id": "canal-demo",
    "name": "Canal de demostración",
    "adapter_type": "simulado",
    "icon": "chat",
    "color": "#1B6FA8",
    "config": {"modo": "demo"},
    "active": true,
    "configured": true,
    "has_secrets": true,
    "managed_by_environment": false,
    "created_at": "2026-11-21T12:00:00Z"
  },
  "secret": "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
}
```

#### Errores

| HTTP | error | Cuándo |
|------|-------|--------|
| 401 | unauthorized | falta `X-Service-Token` o no es válido |
| 409 | channel_exists | el `id` ya existe |
| 422 | validation_error | el cuerpo no valida o el tipo no está registrado/no admite creación |
| 503 | channel_secrets_unavailable | la clave no está disponible para cifrar |
| 503 | channel_store_unavailable | PostgreSQL no está disponible |

### GET /channels

- **Expone:** `telegram_gateway`
- **Llama:** panel de administración (#66) o cliente interno autorizado
- **Modelos:** sin request body → `ChannelListResponse`

Devuelve metadatos públicos de los canales registrados; no devuelve secretos ni
credenciales.

#### Request

No lleva cuerpo. Requiere `X-Service-Token`.

#### Respuesta

`200 OK`, cuerpo `ChannelListResponse`:

| Campo | Tipo | Obligatorio | Descripción |
|-------|------|-------------|-------------|
| `channels` | lista de `ChannelInfo` | sí | canales ordenados por `created_at` e `id` |
| `adapter_types` | lista de slug | sí | adaptadores registrados que admiten creación |

```json
{
  "channels": [
    {
      "id": "canal-demo",
      "name": "Canal de demostración",
      "adapter_type": "simulado",
      "icon": "chat",
      "color": "#1B6FA8",
      "config": {"modo": "demo"},
      "active": true,
      "configured": true,
      "has_secrets": true,
      "managed_by_environment": false,
      "created_at": "2026-11-21T12:00:00Z"
    }
  ],
  "adapter_types": ["simulado"]
}
```

#### Errores

| HTTP | error | Cuándo |
|------|-------|--------|
| 401 | unauthorized | falta `X-Service-Token` o no es válido |
| 422 | validation_error | la petición no valida |
| 503 | channel_store_unavailable | PostgreSQL no está disponible |

### PATCH /channels/{channel_id}

- **Expone:** `telegram_gateway`
- **Llama:** panel de administración (#66) o cliente interno autorizado
- **Modelos:** `ChannelUpdateRequest` → `ChannelInfo`

Actualiza solo los campos enviados. `config` y `credentials` reemplazan por
completo sus valores anteriores; el secreto del canal se conserva. No se puede
enviar `null` como valor. `credentials` se cifra con `CHANNEL_SECRETS_KEY`.

#### Request

| Campo | Tipo | Obligatorio | Descripción |
|-------|------|-------------|-------------|
| `name` | texto (1–60) | no | nuevo nombre |
| `icon` | texto (1–32) | no | nuevo identificador visual |
| `color` | `#RRGGBB` | no | nuevo color |
| `config` | objeto JSON ≤ 4096 bytes, profundidad 5 | no | reemplaza toda la configuración pública |
| `credentials` | objeto de hasta 20 pares | no | reemplaza todas las credenciales; se cifra |

Debe enviarse al menos un campo.

```json
{"name": "Canal actualizado", "credentials": {"api_token": "nuevo-valor"}}
```

#### Respuesta

`200 OK`, cuerpo `ChannelInfo`:

```json
{
  "id": "canal-demo",
  "name": "Canal actualizado",
  "adapter_type": "simulado",
  "icon": "chat",
  "color": "#1B6FA8",
  "config": {"modo": "demo"},
  "active": true,
  "configured": true,
  "has_secrets": true,
  "managed_by_environment": false,
  "created_at": "2026-11-21T12:00:00Z"
}
```

#### Errores

| HTTP | error | Cuándo |
|------|-------|--------|
| 401 | unauthorized | falta `X-Service-Token` o no es válido |
| 404 | not_found | el canal no existe |
| 409 | channel_managed_by_environment | se intentan cambiar credenciales de un canal gestionado por el entorno |
| 422 | validation_error | no se envió ningún campo o algún valor no valida |
| 503 | channel_secrets_unavailable | no se pueden cifrar o descifrar las credenciales |
| 503 | channel_store_unavailable | PostgreSQL no está disponible |

### PATCH /channels/{channel_id}/active

- **Expone:** `telegram_gateway`
- **Llama:** panel de administración (#66) o cliente interno autorizado
- **Modelos:** `ChannelActiveRequest` → `ChannelInfo`

Fija el estado activo/inactivo y desactiva el seguimiento de la configuración
del entorno (`activo_segun_entorno=false`).

#### Request

| Campo | Tipo | Obligatorio | Descripción |
|-------|------|-------------|-------------|
| `active` | booleano estricto | sí | nuevo estado del canal |

```json
{"active": false}
```

#### Respuesta

`200 OK`, cuerpo `ChannelInfo`:

```json
{
  "id": "canal-demo",
  "name": "Canal de demostración",
  "adapter_type": "simulado",
  "icon": "chat",
  "color": "#1B6FA8",
  "config": {"modo": "demo"},
  "active": false,
  "configured": true,
  "has_secrets": true,
  "managed_by_environment": false,
  "created_at": "2026-11-21T12:00:00Z"
}
```

#### Errores

| HTTP | error | Cuándo |
|------|-------|--------|
| 401 | unauthorized | falta `X-Service-Token` o no es válido |
| 404 | not_found | el canal no existe |
| 422 | validation_error | `active` no es un booleano |
| 503 | channel_store_unavailable | PostgreSQL no está disponible |

### POST /channels/{channel_id}/secret

- **Expone:** `telegram_gateway`
- **Llama:** panel de administración (#66) o cliente interno autorizado
- **Modelos:** sin request body → `ChannelSecretResponse`

Genera un secreto nuevo e invalida el anterior; conserva las credenciales. La
operación registra `channel_secret_regenerated` con el `channel_id`, nunca el
secreto. Solo se permite después de una acción explícita autorizada.

#### Request

No lleva cuerpo. Requiere `X-Service-Token`.

#### Respuesta

`200 OK`, cuerpo `ChannelSecretResponse`:

| Campo | Tipo | Obligatorio | Descripción |
|-------|------|-------------|-------------|
| `channel_id` | slug de canal | sí | canal del secreto |
| `secret` | texto URL-safe de 43 caracteres | sí | secreto nuevo; el anterior deja de ser válido |

```json
{
  "channel_id": "canal-demo",
  "secret": "BBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBB"
}
```

#### Errores

| HTTP | error | Cuándo |
|------|-------|--------|
| 401 | unauthorized | falta `X-Service-Token` o no es válido |
| 404 | not_found | el canal no existe |
| 409 | channel_managed_by_environment | el canal lo gestiona el entorno |
| 422 | validation_error | la petición no valida |
| 503 | channel_secrets_unavailable | no se puede cifrar o descifrar el secreto |
| 503 | channel_store_unavailable | PostgreSQL no está disponible |

### GET /channels/{channel_id}/secret

- **Expone:** `telegram_gateway`
- **Llama:** panel de administración (#66) o cliente interno autorizado
- **Modelos:** sin request body → `ChannelSecretResponse`

Revela el secreto vigente solo por esta ruta explícita; registra
`channel_secret_revealed` con el `channel_id`, nunca el secreto. Las credenciales
del proveedor no se revelan.

#### Request

No lleva cuerpo. Requiere `X-Service-Token`.

#### Respuesta

`200 OK`, cuerpo `ChannelSecretResponse`:

| Campo | Tipo | Obligatorio | Descripción |
|-------|------|-------------|-------------|
| `channel_id` | slug de canal | sí | canal del secreto |
| `secret` | texto URL-safe de 43 caracteres | sí | secreto vigente |

```json
{
  "channel_id": "canal-demo",
  "secret": "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
}
```

#### Errores

| HTTP | error | Cuándo |
|------|-------|--------|
| 401 | unauthorized | falta `X-Service-Token` o no es válido |
| 404 | not_found | el canal o su secreto no existen |
| 409 | channel_managed_by_environment | el canal lo gestiona el entorno |
| 422 | validation_error | la petición no valida |
| 503 | channel_secrets_unavailable | falta la clave o no se puede descifrar el secreto |
| 503 | channel_store_unavailable | PostgreSQL no está disponible |

## Rutas

### POST /messages

- **Expone:** orchestrator
- **Llama:** telegram_gateway (por cada mensaje de texto recibido en el webhook)
- **Modelos:** `MessageRequest` → `MessageResponse`

También acepta el request canónico `NormalizedMessage` (ver «Mensaje
normalizado y respuesta abstracta»). La respuesta y los errores no cambian.

#### Request

| Campo | Tipo | Obligatorio | Descripción |
|-------|------|-------------|-------------|
| `update_id` | entero ≥ 0 | sí | id único de la actualización de Telegram; sirve para descartar repetidos |
| `telegram_user_id` | entero | sí | id de Telegram del cliente |
| `chat_id` | entero | sí | chat al que se responde |
| `text` | texto (1–4096) | sí | texto del mensaje del cliente |
| `received_at` | fecha ISO 8601 con zona | sí | momento en que el gateway recibió el mensaje |

#### Respuesta

`202 Accepted`

| Campo | Tipo | Obligatorio | Descripción |
|-------|------|-------------|-------------|
| `status` | `accepted` \| `duplicate` | sí | `accepted` si se procesa; `duplicate` si el `update_id` ya se vio |

#### Errores

| HTTP | error | Cuándo |
|------|-------|--------|
| 401 | unauthorized | falta `X-Service-Token` o no es válido |
| 422 | validation_error | el cuerpo no valida contra `MessageRequest` ni `NormalizedMessage`; el `channel` del `NormalizedMessage` no es un canal atendido (`telegram`, `whatsapp`) o su `direction` es `outbound` |
| 500 | internal_error | error inesperado |

### POST /send

- **Expone:** telegram_gateway
- **Llama:** orchestrator, handover (aviso de vencimiento al cliente)
- **Modelos:** `SendRequest` → `SendResponse`

También acepta la variante canónica `ChannelSendRequest` (canal, destino y
bloques abstractos), descrita en «Mensaje normalizado y respuesta abstracta».

#### Request

| Campo | Tipo | Obligatorio | Descripción |
|-------|------|-------------|-------------|
| `chat_id` | entero | sí | chat de Telegram de destino |
| `text` | texto (1–4096) | sí | texto a enviar |

#### Respuesta

`200 OK`

| Campo | Tipo | Obligatorio | Descripción |
|-------|------|-------------|-------------|
| `sent` | `true` | sí | siempre `true`; si el envío falla se responde con error |

#### Errores

| HTTP | error | Cuándo |
|------|-------|--------|
| 401 | unauthorized | falta `X-Service-Token` o no es válido |
| 422 | validation_error | el cuerpo no valida contra `SendRequest` o `ChannelSendRequest`; el canal no tiene fila en `canales`; el canal no puede enviar texto libre o no cumple una plantilla requerida |
| 422 | channel_inactive | el canal existe, pero está inactivo |
| 502 | telegram_error | la API de Telegram falla |
| 502 | upstream_error | el tipo de adaptador no está registrado, el adaptador no está disponible o el envío falla |
| 503 | channel_secrets_unavailable | faltan secretos cifrados legibles o `CHANNEL_SECRETS_KEY` no está disponible |
| 503 | channel_store_unavailable | PostgreSQL no está disponible |
| 500 | internal_error | error inesperado |

### POST /search

- **Expone:** rag
- **Llama:** orchestrator (y la evaluación, feature 8)
- **Modelos:** `SearchRequest` → `SearchResponse` (elementos `SearchResult`)

#### Request

| Campo | Tipo | Obligatorio | Descripción |
|-------|------|-------------|-------------|
| `query` | texto (1–4096) | sí | pregunta del cliente |
| `top_k` | entero (1–20) | sí | máximo de fragmentos a devolver |
| `category` | identificador o `null` | no | categoría del manual; por defecto `null`, RAG la ignora por ahora (S7) |

#### Respuesta

`200 OK`. El cuerpo es un **arreglo JSON** de nivel superior (S10) con los
fragmentos que superan el umbral de similitud, ordenados de mayor a menor
`score`; puede ser el arreglo vacío `[]`. Cada elemento (`SearchResult`):

| Campo | Tipo | Obligatorio | Descripción |
|-------|------|-------------|-------------|
| `chunk_id` | identificador | sí | id del fragmento |
| `manual` | texto (1–200) | sí | nombre del manual de origen |
| `text` | texto | sí | contenido del fragmento |
| `score` | número (-1 a 1) | sí | similitud con la consulta |

#### Errores

| HTTP | error | Cuándo |
|------|-------|--------|
| 401 | unauthorized | falta `X-Service-Token` o no es válido |
| 422 | validation_error | el cuerpo no valida contra `SearchRequest` |
| 500 | internal_error | error inesperado |

### POST /handover

- **Expone:** handover
- **Llama:** orchestrator
- **Modelos:** `HandoverRequest` → `HandoverResponse`

`POST /handover` crea o reutiliza el caso abierto del contacto. Si existe al
menos un perfil con rol `asesor` en el roster sincronizado responde `queued`
sin enviar avisos por Telegram; el caso aparece en la bandeja del panel. Si no
hay ningún perfil asesor responde `no_advisors` (S12). Las operaciones
dependientes del roster exigen el encabezado `X-Advisor-Roster-Generation`.

#### Request

| Campo | Tipo | Obligatorio | Descripción |
|-------|------|-------------|-------------|
| `case_id` | identificador | sí | caso propuesto por el orquestador (S3) |
| `contact_id` | identificador | sí | contacto del cliente |
| `chat_id` | entero | sí | chat del cliente, para avisarle si vence la espera (S4) |
| `reason` | `no_relevant_chunks` \| `user_request` \| `invalid_answer` \| `advisor_take` | sí | motivo del traspaso (S5); `advisor_take` lo usa #68 |
| `last_messages` | lista de `LastMessage` (máx. 10) | sí | últimos mensajes en orden cronológico (S2) |

Cada elemento de `last_messages` (`LastMessage`):

| Campo | Tipo | Obligatorio | Descripción |
|-------|------|-------------|-------------|
| `role` | `user` \| `bot` \| `advisor` | sí | quién escribió el mensaje |
| `text` | texto (1–4096) | sí | texto del mensaje |
| `at` | fecha ISO 8601 con zona | sí | momento del mensaje |

#### Respuesta

`200 OK`

| Campo | Tipo | Obligatorio | Descripción |
|-------|------|-------------|-------------|
| `status` | `queued` \| `no_advisors` | sí | `queued` si hay perfiles asesores y el caso queda en la bandeja del panel; `no_advisors` si no hay ninguno |
| `case_id` | identificador | sí | caso efectivo: el nuevo o el abierto que se reutilizó (S3) |

#### Errores

| HTTP | error | Cuándo |
|------|-------|--------|
| 401 | unauthorized | falta `X-Service-Token` o no es válido |
| 422 | validation_error | el cuerpo no valida contra `HandoverRequest` |
| 503 | roster_out_of_sync | la generación del roster no coincide con la sincronizada |
| 500 | internal_error | error inesperado |

### POST /cases/{id}/reply

- **Expone:** orchestrator
- **Llama:** asesor (herramienta interna con token; panel de asesores)
- **Modelos:** `CaseReplyRequest` → `CaseReplyResponse`

`{id}` es el `case_id` (identificador, 1–64 caracteres).

#### Request

| Campo | Tipo | Obligatorio | Descripción |
|-------|------|-------------|-------------|
| `advisor_id` | identificador | sí | asesor que responde (S6) |
| `text` | texto (1–4096) | sí | respuesta que se reenvía al cliente |

#### Respuesta

`200 OK`

| Campo | Tipo | Obligatorio | Descripción |
|-------|------|-------------|-------------|
| `sent` | `true` | sí | siempre `true`; si el reenvío falla se responde con error |

#### Errores

| HTTP | error | Cuándo |
|------|-------|--------|
| 401 | unauthorized | falta `X-Service-Token` o no es válido |
| 422 | validation_error | el cuerpo no valida contra `CaseReplyRequest` |
| 403 | forbidden | el asesor no está autorizado a responder el caso; no se envía nada al cliente (S12) |
| 404 | not_found | el caso no existe |
| 409 | case_closed | el caso está cerrado; no se envía nada al cliente (S12) |
| 502 | upstream_error | la llamada a `POST /send` del gateway falla |
| 500 | internal_error | error inesperado |

### POST /manuals

- **Expone:** rag
- **Llama:** `scripts/cargar_manual.py` (panel de administración en el futuro)
- **Modelos:** `ManualUploadRequest` → `ManualUploadResponse`

#### Request

`multipart/form-data` (S1). El modelo `ManualUploadRequest` solo valida la parte
`name`, porque un archivo binario no se representa en JSON.

| Campo | Tipo | Obligatorio | Descripción |
|-------|------|-------------|-------------|
| `file` | archivo (PDF o DOCX) | sí | manual a cargar |
| `name` | texto (1–200) | sí | nombre legible del manual |

#### Respuesta

`201 Created`

| Campo | Tipo | Obligatorio | Descripción |
|-------|------|-------------|-------------|
| `manual_id` | identificador | sí | id del manual cargado |
| `chunks` | entero ≥ 1 | sí | número de fragmentos indexados |

#### Errores

| HTTP | error | Cuándo |
|------|-------|--------|
| 401 | unauthorized | falta `X-Service-Token` o no es válido |
| 422 | validation_error | falta una parte o `name` no es válido |
| 415 | unsupported_format | el archivo no es PDF ni DOCX |
| 422 | empty_document | archivo vacío o sin texto extraíble |
| 500 | internal_error | error inesperado |

### PATCH /chunks/{id}

- **Expone:** rag
- **Llama:** panel de administración (futuro)
- **Modelos:** `ChunkUpdateRequest` → `ChunkUpdateResponse`

`{id}` es el `chunk_id` (identificador, 1–64 caracteres). Reemplaza el texto
completo del fragmento y recalcula su embedding con el proveedor configurado
antes de persistir; conserva `chunk_id`, `manual_id`, manual, orden y estado
activo. El texto no vacío se guarda exactamente como se recibe (R3).

#### Request

| Campo | Tipo | Obligatorio | Descripción |
|-------|------|-------------|-------------|
| `text` | texto no vacío | sí | texto nuevo del fragmento; vacío o solo espacios se rechaza |

#### Respuesta

`200 OK`

| Campo | Tipo | Obligatorio | Descripción |
|-------|------|-------------|-------------|
| `chunk_id` | identificador | sí | id del fragmento editado |
| `manual_id` | identificador | sí | manual al que pertenece el fragmento |
| `manual` | texto (1–200) | sí | nombre del manual |
| `order` | entero ≥ 1 | sí | orden del fragmento dentro del manual |
| `text` | texto | sí | texto nuevo guardado |
| `active` | booleano | sí | estado activo del fragmento, sin cambios |

#### Errores

| HTTP | error | Cuándo |
|------|-------|--------|
| 401 | unauthorized | falta `X-Service-Token` o no es válido |
| 422 | validation_error | el cuerpo no valida contra `ChunkUpdateRequest` |
| 404 | not_found | el fragmento no existe |
| 500 | internal_error | error inesperado |

### GET /manuals

- **Expone:** rag
- **Llama:** orchestrator (panel de administración, #22)
- **Modelos:** `ManualListResponse` (lista de `ManualSummary`)

Devuelve todos los manuales, el más reciente primero, con el número de
fragmentos de cada uno. Sin cuerpo de petición.

#### Request

Sin cuerpo.

#### Respuesta

`200 OK`. El cuerpo es un **arreglo JSON** de nivel superior (S10) con un
elemento por manual (`ManualSummary`); puede ser el arreglo vacío `[]`.

| Campo | Tipo | Obligatorio | Descripción |
|-------|------|-------------|-------------|
| `manual_id` | identificador | sí | id del manual |
| `name` | texto (1–200) | sí | nombre legible del manual |
| `chunks` | entero ≥ 0 | sí | número de fragmentos del manual, activos e inactivos |

#### Errores

| HTTP | error | Cuándo |
|------|-------|--------|
| 401 | unauthorized | falta `X-Service-Token` o no es válido |
| 500 | internal_error | error inesperado |

### GET /manuals/{id}/chunks

- **Expone:** rag
- **Llama:** orchestrator (panel de administración, #22)
- **Modelos:** `ChunkListResponse` (lista de `ChunkItem`)

`{id}` es el `manual_id` (identificador, 1–64 caracteres). Devuelve todos los
fragmentos del manual, activos e inactivos, en orden ascendente de `order`.

#### Request

Sin cuerpo.

#### Respuesta

`200 OK`. El cuerpo es un **arreglo JSON** de nivel superior (S10) con un
elemento por fragmento (`ChunkItem`); puede ser el arreglo vacío `[]`.

| Campo | Tipo | Obligatorio | Descripción |
|-------|------|-------------|-------------|
| `chunk_id` | identificador | sí | id del fragmento |
| `manual_id` | identificador | sí | manual al que pertenece el fragmento |
| `manual` | texto (1–200) | sí | nombre del manual |
| `order` | entero ≥ 1 | sí | orden del fragmento dentro del manual |
| `text` | texto no vacío | sí | contenido del fragmento |
| `active` | booleano | sí | si el fragmento participa en `POST /search` |

#### Errores

| HTTP | error | Cuándo |
|------|-------|--------|
| 401 | unauthorized | falta `X-Service-Token` o no es válido |
| 404 | not_found | el manual no existe |
| 500 | internal_error | error inesperado |

### PATCH /chunks/{id}/active

- **Expone:** rag
- **Llama:** orchestrator (panel de administración, #22)
- **Modelos:** `ChunkActiveRequest` → `ChunkItem`

`{id}` es el `chunk_id` (identificador, 1–64 caracteres). Guarda el estado
activo del fragmento y devuelve el fragmento completo; no cambia su texto,
embedding, manual ni orden. Desactivar un fragmento solo lo saca de
`POST /search`; no lo borra.

#### Request

| Campo | Tipo | Obligatorio | Descripción |
|-------|------|-------------|-------------|
| `active` | booleano JSON | sí | nuevo estado del fragmento; solo se aceptan `true` y `false` |

#### Respuesta

`200 OK`

| Campo | Tipo | Obligatorio | Descripción |
|-------|------|-------------|-------------|
| `chunk_id` | identificador | sí | id del fragmento |
| `manual_id` | identificador | sí | manual al que pertenece el fragmento |
| `manual` | texto (1–200) | sí | nombre del manual |
| `order` | entero ≥ 1 | sí | orden del fragmento dentro del manual |
| `text` | texto no vacío | sí | contenido del fragmento, sin cambios |
| `active` | booleano | sí | estado activo guardado |

#### Errores

| HTTP | error | Cuándo |
|------|-------|--------|
| 401 | unauthorized | falta `X-Service-Token` o no es válido |
| 404 | not_found | el fragmento no existe |
| 422 | validation_error | el cuerpo no valida contra `ChunkActiveRequest` |
| 500 | internal_error | error inesperado |

### POST /cases/{id}/close

- **Expone:** handover
- **Llama:** orchestrator (panel de asesores)
- **Modelos:** `CaseCloseRequest` → `CaseCloseResponse`

`{id}` es el `case_id` (identificador, 1–64 caracteres). Cerrar un caso ya
cerrado responde igual, `200` con `status` = `closed` (S8).

#### Request

| Campo | Tipo | Obligatorio | Descripción |
|-------|------|-------------|-------------|
| `advisor_id` | identificador | sí | asesor que cierra el caso |

#### Respuesta

`200 OK`

| Campo | Tipo | Obligatorio | Descripción |
|-------|------|-------------|-------------|
| `status` | `closed` | sí | siempre `closed` |
| `case_id` | identificador | sí | caso cerrado |

#### Errores

| HTTP | error | Cuándo |
|------|-------|--------|
| 401 | unauthorized | falta `X-Service-Token` o no es válido |
| 422 | validation_error | el cuerpo no valida contra `CaseCloseRequest` |
| 403 | forbidden | el asesor no está autorizado a cerrar el caso; el caso no cambia (S12) |
| 404 | not_found | el caso no existe |
| 500 | internal_error | error inesperado |

### POST /cases/check-timeouts

- **Expone:** handover
- **Llama:** worker o cron
- **Modelos:** `CheckTimeoutsRequest` → `CheckTimeoutsResponse`

Marca como vencidos los casos cuya espera supera `HANDOVER_TIMEOUT_SECONDS` y
avisa a sus clientes.

#### Request

El cuerpo es el objeto vacío `{}`.

| Campo | Tipo | Obligatorio | Descripción |
|-------|------|-------------|-------------|
| (sin campos) | — | — | — |

#### Respuesta

`200 OK`

| Campo | Tipo | Obligatorio | Descripción |
|-------|------|-------------|-------------|
| `timed_out_cases` | lista de identificadores | sí | casos marcados como vencidos en esta llamada; puede ser `[]` |

#### Errores

| HTTP | error | Cuándo |
|------|-------|--------|
| 401 | unauthorized | falta `X-Service-Token` o no es válido |
| 422 | validation_error | el cuerpo no es `{}` |
| 500 | internal_error | error inesperado |

### POST /cases/{id}/assign

- **Expone:** handover
- **Llama:** orchestrator (al reenviar la respuesta de un asesor con `POST /cases/{id}/reply`)
- **Modelos:** `CaseAssignRequest` → `CaseAssignResponse`

`{id}` es el `case_id` (identificador, 1–64 caracteres). Asignar un caso ya
`assigned` responde igual, `200` con `status` = `assigned`, sin cambiar el asesor
asignado; asignar un caso `closed` responde `409` con `error` = `case_closed`
(S11).

#### Request

| Campo | Tipo | Obligatorio | Descripción |
|-------|------|-------------|-------------|
| `advisor_id` | identificador | sí | asesor al que se asigna el caso (S6) |

#### Respuesta

`200 OK`

| Campo | Tipo | Obligatorio | Descripción |
|-------|------|-------------|-------------|
| `status` | `assigned` | sí | siempre `assigned` |
| `case_id` | identificador | sí | caso asignado |

#### Errores

| HTTP | error | Cuándo |
|------|-------|--------|
| 401 | unauthorized | falta `X-Service-Token` o no es válido |
| 422 | validation_error | el cuerpo no valida contra `CaseAssignRequest` |
| 403 | forbidden | el asesor no está autorizado sobre el caso; el caso no cambia (S12) |
| 404 | not_found | el caso no existe |
| 409 | case_closed | el caso está cerrado (S11) |
| 500 | internal_error | error inesperado |

### POST /cases/{id}/auto-assign

- **Expone:** handover
- **Llama:** orchestrator (al escalar un caso en modo de asignación `automatica`, #52)
- **Modelos:** `CaseAutoAssignRequest` → `CaseAutoAssignResponse`

La ruta `POST /cases/{case_id}/auto-assign` elige y asigna el caso en una sola
transacción serializada (S16). `{id}` es el `case_id` (identificador, 1–64 caracteres).
`candidate_ids` son los perfiles que el orquestador considera
disponibles; handover descarta los que no son asesores atendedores del roster.
La `strategy` elige la regla de reparto: `por_carga` (por defecto) escoge el de
menor número de casos `assigned` y, a igual carga, el menor `advisor_id`
lexicográfico; `round_robin` rota al siguiente asesor en orden lexicográfico y
vuelve al inicio. Una estrategia desconocida responde `422`. Solo asigna si el
caso sigue `open` y sin asesor: si una persona lo asignó, respondió o cerró
antes, no lo modifica y responde `skipped`. Sin candidatos válidos responde
`queued` sin modificar el caso. Un caso cerrado responde `409` con `error` =
`case_closed`. Exige `X-Service-Token`.

#### Request

| Campo | Tipo | Obligatorio | Descripción |
|-------|------|-------------|-------------|
| `candidate_ids` | lista de identificadores (1–200) | sí | perfiles atendedores disponibles, sin repetir |
| `strategy` | `por_carga` \| `round_robin` | no | estrategia de asignación; por defecto `por_carga` (#69) |

#### Respuesta

`200 OK`

| Campo | Tipo | Obligatorio | Descripción |
|-------|------|-------------|-------------|
| `status` | `assigned` \| `queued` \| `skipped` | sí | resultado de la asignación automática |
| `case_id` | identificador | sí | caso solicitado |
| `advisor_id` | identificador o `null` | sí | asesor asignado; `null` si quedó en cola o no se modificó sin asignación |

#### Errores

| HTTP | error | Cuándo |
|------|-------|--------|
| 401 | unauthorized | falta `X-Service-Token` o no es válido |
| 422 | validation_error | el cuerpo no valida contra `CaseAutoAssignRequest` o la `strategy` no está registrada (#69) |
| 404 | not_found | el caso no existe |
| 409 | case_closed | el caso está cerrado |
| 503 | roster_out_of_sync | la generación del roster no coincide con la sincronizada (S12) |
| 500 | internal_error | error inesperado |

### POST /cases/{id}/transfer

- **Expone:** handover
- **Llama:** orchestrator (panel de asesores, #41)
- **Modelos:** `CaseTransferRequest` → `CaseTransferResponse`

`{id}` es el `case_id` (identificador, 1–64 caracteres). Reasigna un caso
`assigned` del asesor que lo tiene al asesor destino. Solo el asesor asignado
puede transferirlo y ambos deben ser perfiles con rol `asesor` del roster
sincronizado; el caso no cambia de estado y no se envía aviso por Telegram al
destino (S6). Asignar a uno mismo o a un asesor no registrado responde `422` sin
modificar el caso.

#### Request

| Campo | Tipo | Obligatorio | Descripción |
|-------|------|-------------|-------------|
| `advisor_id` | identificador | sí | asesor actual del caso (S6) |
| `target_advisor_id` | identificador | sí | asesor registrado que recibe el caso |

#### Respuesta

`200 OK`

| Campo | Tipo | Obligatorio | Descripción |
|-------|------|-------------|-------------|
| `status` | `assigned` | sí | siempre `assigned` |
| `case_id` | identificador | sí | caso transferido |
| `advisor_id` | identificador | sí | nuevo asesor asignado (`target_advisor_id`) |

#### Errores

| HTTP | error | Cuándo |
|------|-------|--------|
| 401 | unauthorized | falta `X-Service-Token` o no es válido |
| 422 | validation_error | el cuerpo no valida o el destino no es un asesor registrado distinto del actor |
| 403 | forbidden | el asesor no está registrado o el caso no está asignado a él; el caso no cambia |
| 404 | not_found | el caso no existe |
| 409 | case_closed | el caso está cerrado |
| 500 | internal_error | error inesperado |

### POST /cases/{id}/reassign

- **Expone:** handover
- **Llama:** orchestrator (panel de asesores, reasignación de un supervisor)
- **Modelos:** `CaseReassignRequest` → `CaseReassignResponse`

`{id}` es el `case_id` (identificador, 1–64 caracteres). Un supervisor
registrado reasigna un caso `assigned` a otro asesor atendedor registrado. Es
una escritura condicional: solo se aplica si el caso sigue `assigned` al asesor
leído. No cambia el estado del caso y no se envía aviso por Telegram al
destino. Reasignar no es responder, asignar ni cerrar; un asesor con rol
`asesor` recibe `403`. El destino debe ser otro perfil del roster y el caso no
puede estar `open`, `timed_out` ni `closed` (S12). Si el caso no está asignado
responde `409` con `error` = `case_not_assigned`; si la escritura condicional
pierde la carrera responde `409` con `error` = `case_changed`.

#### Request

| Campo | Tipo | Obligatorio | Descripción |
|-------|------|-------------|-------------|
| `advisor_id` | identificador | sí | `profile_id` del supervisor que reasigna (S6) |
| `target_advisor_id` | identificador | sí | perfil atendedor registrado que recibe el caso |

#### Respuesta

`200 OK`

| Campo | Tipo | Obligatorio | Descripción |
|-------|------|-------------|-------------|
| `status` | `assigned` | sí | siempre `assigned`; el estado no cambia |
| `case_id` | identificador | sí | caso reasignado |
| `previous_advisor_id` | identificador o `null` | sí | asesor anterior; `null` si el caso era huérfano |
| `advisor_id` | identificador | sí | nuevo asesor asignado (`target_advisor_id`) |

#### Errores

| HTTP | error | Cuándo |
|------|-------|--------|
| 401 | unauthorized | falta `X-Service-Token` o no es válido |
| 422 | validation_error | el cuerpo no valida o el destino no es un asesor atendedor registrado distinto del actual |
| 403 | forbidden | el `advisor_id` no es un supervisor registrado; el caso no cambia |
| 404 | not_found | el caso no existe |
| 409 | case_closed | el caso está cerrado |
| 409 | case_not_assigned | el caso está `open` o `timed_out` |
| 409 | case_changed | el caso cambió entre la lectura y la escritura condicional (respondido y reasignado, transferido o cerrado) |
| 503 | roster_out_of_sync | la generación del roster no coincide con la sincronizada (S12) |
| 500 | internal_error | error inesperado |

### POST /cases/{id}/authorize

- **Expone:** handover
- **Llama:** orchestrator (antes de reenviar la respuesta de un asesor con `POST /cases/{id}/reply` y antes de `POST /cases/{id}/close`)
- **Modelos:** `CaseAuthorizeRequest` → `CaseAuthorizeResponse`

`{id}` es el `case_id` (identificador, 1–64 caracteres). Consulta si el asesor
`advisor_id` puede hacer `action` sobre el caso según las reglas de S12. Si puede,
responde `200` con `allowed` = `true`; si no, responde `403` con `error` =
`forbidden` (nunca `allowed` = `false`). Autorizar sobre un caso `closed` responde
`409` con `error` = `case_closed`.

#### Request

| Campo | Tipo | Obligatorio | Descripción |
|-------|------|-------------|-------------|
| `advisor_id` | identificador | sí | asesor que quiere actuar sobre el caso (S6) |
| `action` | `reply` \| `close` | sí | acción que se quiere autorizar: responder o cerrar |

#### Respuesta

`200 OK`

| Campo | Tipo | Obligatorio | Descripción |
|-------|------|-------------|-------------|
| `allowed` | `true` | sí | siempre `true`; si no está autorizado se responde `403` |
| `case_id` | identificador | sí | caso consultado |

#### Errores

| HTTP | error | Cuándo |
|------|-------|--------|
| 401 | unauthorized | falta `X-Service-Token` o no es válido |
| 422 | validation_error | el cuerpo no valida contra `CaseAuthorizeRequest` |
| 403 | forbidden | el asesor no está autorizado para `action` sobre el caso (S12) |
| 404 | not_found | el caso no existe |
| 409 | case_closed | el caso está cerrado |
| 500 | internal_error | error inesperado |

### POST /cases/{id}/client-message

- **Expone:** handover
- **Llama:** orchestrator (al recibir por `POST /messages` un mensaje de un cliente con caso; S13)
- **Modelos:** `CaseClientMessageRequest` → `CaseClientMessageResponse`

`{id}` es el `case_id` (identificador, 1–64 caracteres). Si el caso está `assigned`,
el mensaje queda disponible en la conversación del panel y handover responde `200`
con `status` = `available_in_panel`, sin enviarlo por Telegram; si el caso existe y
no está `assigned`, responde `200` con `status` = `not_assigned` sin enviar nada
(S13).

#### Request

| Campo | Tipo | Obligatorio | Descripción |
|-------|------|-------------|-------------|
| `text` | texto (1–4096) | sí | mensaje del cliente que queda visible en el panel |
| `at` | fecha ISO 8601 con zona | sí | momento del mensaje del cliente |

#### Respuesta

`200 OK`

| Campo | Tipo | Obligatorio | Descripción |
|-------|------|-------------|-------------|
| `status` | `available_in_panel` \| `not_assigned` | sí | `available_in_panel` si el caso está `assigned`; `not_assigned` si no lo está |
| `case_id` | identificador | sí | caso del mensaje |

#### Errores

| HTTP | error | Cuándo |
|------|-------|--------|
| 401 | unauthorized | falta `X-Service-Token` o no es válido |
| 422 | validation_error | el cuerpo no valida contra `CaseClientMessageRequest` |
| 404 | not_found | el caso no existe |
| 500 | internal_error | error inesperado |

### POST /credentials/expiry-notices

- **Expone:** orchestrator
- **Llama:** `scripts/avisar_vencimientos.py` (worker `expiry_notice_worker`)
- **Modelos:** `ExpiryNoticeRunRequest` → `ExpiryNoticeRunResponse`

Ejecuta una pasada de avisos de vencimiento de credenciales de clientes. No
envía datos personales en el cuerpo ni en la respuesta.

#### Request

El cuerpo es el objeto vacío `{}`.

| Campo | Tipo | Obligatorio | Descripción |
|-------|------|-------------|-------------|
| (sin campos) | — | — | — |

#### Respuesta

`200 OK`

| Campo | Tipo | Obligatorio | Descripción |
|-------|------|-------------|-------------|
| `enabled` | booleano | sí | `false` si `expiry_notice.enabled` está desactivado; no se envía nada |
| `candidates` | entero ≥ 0 | sí | credenciales candidatas consideradas en la pasada |
| `sent_text` | entero ≥ 0 | sí | avisos enviados como texto libre |
| `sent_template` | entero ≥ 0 | sí | avisos enviados con plantilla |
| `failed` | entero ≥ 0 | sí | envíos fallidos |
| `skipped` | objeto `{motivo: entero}` | sí | motivos: `out_of_hours`, `no_chat`, `no_text`, `no_template`, `already_notified` |

#### Errores

| HTTP | error | Cuándo |
|------|-------|--------|
| 401 | unauthorized | falta `X-Service-Token` o no es válido |
| 422 | validation_error | el cuerpo no es `{}` |
| 500 | internal_error | error inesperado |

### POST /privacy/purge

- **Expone:** orchestrator y handover (cada servicio purga solo su propia base)
- **Llama:** `scripts/purgar_datos.py` (servicio `retention_worker`), en el orden
  fijo **handover → orchestrator**: si la purga de handover no responde `200`,
  no se llama al orchestrator en esa iteración.
- **Modelos:** `PrivacyPurgeRequest` → `PrivacyPurgeResponse`

Borra los datos personales más antiguos que el plazo aprobado
(`PRIVACY_RETENTION_DAYS`). Handover cierra y borra además los casos activos
(`open`, `assigned` o `timed_out`) que superan `PRIVACY_ACTIVE_CASE_MAX_DAYS`
(R35). Los registros operativos necesarios se conservan. La evidencia mínima de
consentimiento (`privacy_consents`: canal e id externo, versión/hash del aviso y
fecha) sigue el mismo plazo de 30 días, se elimina antes si se ejecuta una
supresión y se informa en `deleted` con la clave `privacy_consents`. La
aceptación por cliente de #72 solo se purga si `CLIENT_CONSENT_RETENTION_DAYS`
está configurado y aparece entonces en `deleted` como
`consentimientos_cliente`.

#### Request

El cuerpo es el objeto vacío `{}`.

| Campo | Tipo | Obligatorio | Descripción |
|-------|------|-------------|-------------|
| (sin campos) | — | — | — |

#### Respuesta

`200 OK`

| Campo | Tipo | Obligatorio | Descripción |
|-------|------|-------------|-------------|
| `cutoff` | fecha ISO 8601 con zona | sí | instante de corte usado en la purga |
| `deleted` | objeto `{tabla: entero}` | sí | filas borradas por tabla en esta llamada |
| `closed_active_cases` | entero ≥ 0 | sí | handover: casos activos cerrados y borrados; orchestrator: `0` |

#### Errores

| HTTP | error | Cuándo |
|------|-------|--------|
| 401 | `unauthorized` | falta `X-Service-Token` o no es válido (R20, R33) |
| 422 | `validation_error` | el cuerpo no es `{}` |
| 503 | `privacy_not_configured` | falta la configuración de retención; no se borra nada (R21, R32) |
| 500 | `internal_error` | error inesperado; la transacción hace rollback |

### Consentimiento por cliente (#72)

El login verificado vincula la identidad del canal con el cliente y permite que
sus términos aceptados se compartan entre todos sus canales. La evidencia por
canal (`privacy_consents`) no cambia: se conserva como prueba de dónde y cuándo
se aceptó. Las tablas nuevas viven en la base del **orchestrator**:

| Tabla | Columnas | Clave |
|-------|----------|-------|
| `identidades_cliente` | `cliente_id`, `canal_id`, `id_externo`, `vinculado_en` | `(canal_id, id_externo)` |
| `consentimientos_cliente` | `cliente_id`, `notice_version`, `notice_sha256`, `aceptado_en`, `canal_id` | `(cliente_id, notice_version)` |

- `cliente_id` es `profiles.id` con rol `cliente`; las tablas no tienen clave
  foránea a `contacts`, porque la vinculación sobrevive a la purga de inactivos.
- La aceptación por cliente se registra en `consentimientos_cliente` al iniciar
  sesión si la identidad tiene evidencia `accepted` (botón o texto) de la versión
  vigente, y también cuando una identidad ya vinculada acepta una versión nueva.
- Una identidad no vinculada sigue recibiendo el aviso antes de guardar datos
  (#35); el login verificado sigue siendo obligatorio.
- La cobertura entre canales se resuelve por consulta
  (identidad → cliente → versión), sin copiar filas de `privacy_consents`.

`CLIENT_CONSENT_RETENTION_DAYS` es opcional: vacío (valor por defecto) conserva
la aceptación por cliente hasta la supresión; un entero `>= 1` hace que
`POST /privacy/purge` borre de `consentimientos_cliente` las filas con
`aceptado_en` anterior al plazo y las deje de contar como cobertura. Las
identidades (`identidades_cliente`) no caducan por plazo.

La supresión de un cliente borra sus filas de `consentimientos_cliente` e
`identidades_cliente` y la evidencia `privacy_consents` de **todas** sus
identidades vinculadas, no solo de los contactos de sus sesiones. Los conteos
se informan en `removed_counts` con las claves nuevas
`consentimientos_cliente` e `identidades_cliente`, además de las existentes.
La purga por retención solo incluye `consentimientos_cliente` en `deleted`
cuando `CLIENT_CONSENT_RETENTION_DAYS` está configurado.

**Supuesto pendiente de confirmación legal:** la aceptación por cliente se
conserva hasta la supresión del cliente; si legal exige otro plazo, se configura
con `CLIENT_CONSENT_RETENTION_DAYS` sin cambiar el contrato.

### POST /cases/take

- **Expone:** handover
- **Llama:** orchestrator (panel de asesores, #68)
- **Modelos:** `CaseTakeRequest` → `CaseTakeResponse`

Toma la conversación de un contacto en una sola operación atómica por
`contact_id`. Si no hay caso no cerrado, crea uno `assigned` al asesor
(`created=true`); si hay un caso `open` o `timed_out` sin asesor, lo asigna
(`created=false`); si el caso ya está asignado al mismo asesor, lo devuelve sin
crear otro (`created=false`); si está asignado a otro asesor responde
`409 case_changed`. Un `advisor_id` que no es asesor registrado responde `403
forbidden` sin crear caso. No envía avisos al cliente ni a asesores. Exige
`X-Service-Token`.

#### Request

| Campo | Tipo | Obligatorio | Descripción |
|-------|------|-------------|-------------|
| `case_id` | identificador | sí | caso propuesto por el orchestrator si hay que crearlo |
| `contact_id` | identificador | sí | contacto cuya conversación se toma |
| `chat_id` | entero | sí | chat del cliente para el caso creado |
| `advisor_id` | identificador | sí | asesor que toma la conversación (S6) |
| `last_messages` | lista de `LastMessage` (máx. 10) | sí | últimos mensajes en orden cronológico (S2) |

```json
{
  "case_id": "case-200",
  "contact_id": "contact-1",
  "chat_id": 900,
  "advisor_id": "222222222",
  "last_messages": [
    {"role": "user", "text": "Necesito ayuda", "at": "2026-01-02T02:59:00Z"}
  ]
}
```

#### Respuesta

`200 OK`

| Campo | Tipo | Obligatorio | Descripción |
|-------|------|-------------|-------------|
| `status` | `taken` | sí | siempre `taken` |
| `case_id` | identificador | sí | caso creado o reutilizado |
| `created` | booleano | sí | `true` si se creó un caso; `false` si se asignó uno abierto |

```json
{"status": "taken", "case_id": "case-200", "created": true}
```

#### Errores

| HTTP | error | Cuándo |
|------|-------|--------|
| 401 | unauthorized | falta `X-Service-Token` o no es válido |
| 422 | validation_error | el cuerpo no valida contra `CaseTakeRequest` |
| 403 | forbidden | el `advisor_id` no es asesor registrado; no se crea caso |
| 409 | case_changed | el contacto tiene un caso abierto asignado a otro asesor |
| 500 | internal_error | error inesperado |

### GET /cases

- **Expone:** handover
- **Llama:** orchestrator (panel de asesores, #29)
- **Modelos:** `CaseListQuery` → `CaseListResponse` (elementos `CaseListItem`)

Lista de solo lectura de los casos que un asesor puede gestionar según S12 y la
regla de huérfanos (S14). Exige `X-Service-Token`. Con `scope=mine` (por
defecto), un `advisor_id` que no es un perfil atendedor del roster sincronizado
recibe `200` con la lista vacía. Con `scope=all`, solo un supervisor registrado
recibe todos los casos de cualquier estado; otro perfil recibe `403` con
`error` = `forbidden`. Con `scope=overview` (#68), un asesor registrado recibe
todos los casos no cerrados (`open`, `timed_out` y `assigned`) con
`actions` = `[]`; un perfil no registrado recibe `200` con la lista vacía.

#### Request

Los parámetros viajan en la query; un parámetro no declarado se rechaza con
`422 validation_error`. La generación del roster viaja en
`X-Advisor-Roster-Generation`.

| Campo | Tipo | Obligatorio | Descripción |
|-------|------|-------------|-------------|
| `advisor_id` | identificador (1–64) | sí | `profile_id` del asesor o supervisor que pide el listado (S6) |
| `scope` | `mine` \| `all` \| `overview` | no | `mine` lista lo gestionable por el solicitante; `all` es la vista global del supervisor (S14); `overview` lista los casos no cerrados sin acciones (#68) |

#### Respuesta

`200 OK`. El cuerpo es un **arreglo JSON** de nivel superior (S10) con como
máximo `CASE_LIST_LIMIT` casos (por defecto 50, máximo 200), ordenados por
`created_at` ascendente y, a igual `created_at`, por `case_id` ascendente. Cada
elemento (`CaseListItem`):

| Campo | Tipo | Obligatorio | Descripción |
|-------|------|-------------|-------------|
| `case_id` | identificador | sí | caso listado |
| `status` | `open` \| `timed_out` \| `assigned` \| `closed` | sí | estado actual del caso |
| `created_at` | fecha ISO 8601 con zona | sí | fecha de creación del caso |
| `actions` | lista sin repetidos de `reply` \| `assign` \| `close` \| `reassign`; puede ser `[]` | sí | acciones que el solicitante puede hacer hoy; `reassign` solo aparece en la vista global del supervisor (S14); `overview` siempre la devuelve vacía (#68) |
| `advisor_id` | identificador o `null` | no | asesor actualmente asignado; `null` si no hay ninguno (S14) |

#### Errores

| HTTP | error | Cuándo |
|------|-------|--------|
| 401 | unauthorized | falta `X-Service-Token` o no es válido |
| 422 | validation_error | los parámetros de query no validan contra `CaseListQuery` |
| 403 | forbidden | `scope=all` con un `advisor_id` que no es supervisor registrado |
| 503 | roster_out_of_sync | la generación del roster no coincide con la sincronizada (S12) |
| 500 | internal_error | error inesperado |

### POST /advisors/sync

- **Expone:** handover
- **Llama:** orchestrator (al arrancar y después de crear o cambiar el rol de un perfil)
- **Modelos:** `AdvisorRosterSyncRequest` → `AdvisorRosterSyncResponse`

Reemplaza el roster completo de asesores y migra las asignaciones antiguas en
una única transacción. Es la única fuente que handover usa para decidir quién
es asesor. Exige `X-Service-Token`. El request incluye la generación del
orchestrator; handover guarda esa generación y la usa para rechazar operaciones
atrasadas.

- `role` = `asesor` o `supervisor` habilita al perfil como asesor atendedor y
  conserva el rol en el roster; `responsable_datos` y `otro` no se registran
  como asesores (R7, R24 de #49).
- `telegram_user_id` solo sirve para migrar un caso cuyo `advisor_id` coincide
  con ese valor: se reemplaza por el `profile_id` del mismo perfil. Si el valor
  antiguo no coincide con ningún perfil vinculado, el caso queda huérfano
  (`advisor_id` nulo) sin perder su estado ni su historial.
- Repetir la sincronización del mismo roster es idempotente: un `profile_id` ya
  migrado no se vuelve a interpretar como id Telegram.

#### Request

| Campo | Tipo | Obligatorio | Descripción |
|-------|------|-------------|-------------|
| `generation` | entero ≥ 0 | sí | generación del roster del orchestrator |
| `profiles` | lista de `AdvisorRosterEntry` | sí | snapshot completo de perfiles |

Cada elemento (`AdvisorRosterEntry`):

| Campo | Tipo | Obligatorio | Descripción |
|-------|------|-------------|-------------|
| `profile_id` | identificador | sí | id del perfil |
| `role` | `asesor` \| `supervisor` \| `responsable_datos` \| `otro` | sí | rol del perfil; solo `asesor` y `supervisor` se registran como atendedores |
| `telegram_user_id` | entero o `null` | no | solo para migrar asignaciones anteriores |

#### Respuesta

`200 OK`

| Campo | Tipo | Obligatorio | Descripción |
|-------|------|-------------|-------------|
| `status` | `synced` | sí | siempre `synced` |
| `generation` | entero ≥ 0 | sí | generación aplicada |
| `advisors` | entero ≥ 0 | sí | perfiles atendedores (`asesor` o `supervisor`) del snapshot |
| `orphaned_cases` | entero ≥ 0 | sí | casos asignados que quedaron huérfanos tras migrar |

#### Errores

| HTTP | error | Cuándo |
|------|-------|--------|
| 401 | unauthorized | falta `X-Service-Token` o no es válido |
| 422 | validation_error | el cuerpo no valida contra `AdvisorRosterSyncRequest` |
| 500 | internal_error | falla la persistencia; no se aplica un roster parcial |

## Supuestos a confirmar

Decisiones tomadas sin confirmación humana. Cambiar cualquiera es un cambio de
contrato.

| Id | Supuesto | Valor por defecto |
|----|----------|-------------------|
| S1 | `POST /manuals` es `multipart/form-data` con las partes `file` (archivo) y `name` (texto) | — |
| S2 | `last_messages` de `POST /handover` son como máximo los últimos 10 mensajes, en orden cronológico (más antiguo primero), como lista de `{role, text, at}` con `role` ∈ `user`, `bot`, `advisor` | `MAX_LAST_MESSAGES = 10` |
| S3 | `case_id` lo genera el orquestador (texto, p. ej. UUID). Si el contacto ya tiene un caso abierto, handover lo reutiliza y devuelve en `HandoverResponse.case_id` el caso efectivo | — |
| S4 | `HandoverRequest` añade `chat_id` para que handover pueda avisar al cliente al vencer la espera | — |
| S5 | `reason` ∈ `no_relevant_chunks`, `user_request`, `invalid_answer` (este último reservado para la feature 6) | — |
| S6 | `advisor_id` es texto y contiene el `profile_id` de un perfil con rol `asesor` o `supervisor` del roster sincronizado (`POST /advisors/sync`), no un `telegram_user_id`. Un asesor sin Telegram vinculado puede actuar desde el panel. | — |
| S7 | `category` de `POST /search` es opcional y RAG la ignora hasta que exista el clasificador | `null` |
| S8 | Cerrar un caso ya cerrado es idempotente: `200` con `status` = `closed` | — |
| S9 | Límites: texto ≤ 4096 (límite de `sendMessage` de Telegram), `top_k` ≤ 20, identificadores ≤ 64, nombre de manual ≤ 200 | `MAX_TEXT_LENGTH`, `MAX_TOP_K`, `MAX_IDENTIFIER_LENGTH`, `MAX_MANUAL_NAME_LENGTH` |
| S10 | La respuesta de `POST /search` es un arreglo JSON de nivel superior | — |
| S11 | Asignar con `POST /cases/{id}/assign` un caso ya `assigned` responde `200` con `status` = `assigned` sin cambiar el asesor asignado cuando quien asigna es el asesor asignado; si es otro asesor, responde `403` con `error` = `forbidden` sin cambiar el caso (S12, cambio de la #13); asignar un caso `closed` responde `409` con `error` = `case_closed` | — |
| S12 | Autorización de asesores (`POST /cases/{id}/authorize`). Son asesores atendedores los perfiles con rol `asesor` o `supervisor` del roster sincronizado por `POST /advisors/sync`; un `advisor_id` que no es uno de esos perfiles recibe `403` con `error` = `forbidden`. `responsable_datos`, `admin` y `cliente` no son asesores atendedores. Responder (`reply`): un caso `open` o `timed_out` lo responde cualquier asesor registrado y la primera respuesta lo asigna; un caso `assigned` solo lo responde el asesor asignado. Cerrar (`close`): un caso `open` o `timed_out` lo cierra cualquier asesor registrado; un caso `assigned` solo lo cierra el asesor asignado, salvo un caso huérfano. Caso huérfano: un caso `assigned` cuyo `advisor_id` es nulo o ya no está en el roster de asesores. Un caso huérfano lo cierra cualquier asesor registrado: `POST /cases/{id}/close` lo pasa a `closed` y `authorize` con `action` = `close` responde `200` con `allowed` = `true`; cerrarlo no es reasignarlo. Un caso huérfano no lo responde ni lo asigna ningún otro asesor: `POST /cases/{id}/reply` y `authorize` con `action` = `reply` responden `403` con `error` = `forbidden`, y `POST /cases/{id}/assign` responde `403` con `error` = `forbidden` sin modificar el caso, como con cualquier caso asignado a otro asesor. Reglas del supervisor (cambian la decisión de la #14, que no permitía reasignar ni rol supervisor). Un perfil con rol `supervisor` del roster conserva todas las capacidades de `asesor` de este supuesto y además puede reasignar casos `assigned` y listar todos los casos con `scope=all`. La reasignación la decide handover con `POST /cases/{id}/reassign`: el actor debe ser supervisor registrado (si no, `403`); el caso debe existir (`404`), no estar `closed` (`409 case_closed`) y estar `assigned` (`409 case_not_assigned`); el destino debe ser otro asesor atendedor registrado y distinto del actual (`422 validation_error`). Las mismas reglas se aplican en `POST /cases/{id}/reply` (el orquestador responde `403` sin enviar nada al cliente), `POST /cases/{id}/close` y `POST /cases/{id}/assign` (handover responde `403` sin modificar el caso); asignar un caso ya `assigned` (S11) solo responde `200` al asesor asignado y otro asesor recibe `403`. Esto cambia el `200` sin cambios que S11 daba en la #9 a cualquier asesor: el asesor asignado sigue recibiendo `200` sin cambios. Precedencia de errores en `POST /cases/{id}/authorize`, `POST /cases/{id}/close` y `POST /cases/{id}/assign`: `403` (asesor no registrado) → `404` (caso inexistente) → `409` (caso `closed`; en `POST /cases/{id}/close`, `200` sin cambios por S8) → `403` (caso asignado a otro asesor), escalón que no se aplica a `POST /cases/{id}/close` ni a `authorize` con `action` = `close` sobre un caso huérfano (para ellos, superados los tres primeros escalones, el cierre está permitido). En `POST /cases/{id}/reply` el orquestador autoriza antes de comprobar si el caso existe: un `advisor_id` no registrado recibe `403` con `error` = `forbidden` aunque el caso no exista. `POST /cases/{id}/close` sobre un caso `closed` sigue S8: `200` sin cambios para cualquier asesor registrado, aunque no sea el asignado; `authorize` con `action` = `close` sobre un caso `closed` responde `409`. `POST /cases/{id}/reply` sobre un caso `closed` responde `409` con `error` = `case_closed`, sin enviar nada al cliente (el orquestador propaga el `409` de `authorize`). Si handover no está disponible para autorizar, el orquestador falla cerrado: no envía la respuesta y responde `502` con `error` = `upstream_error`, reutilizando la fila `502 upstream_error` ya publicada de `POST /cases/{id}/reply`. La autorización por HTTP con `SERVICE_TOKEN` no impide que un proceso que ya tenga ese token suplante un `advisor_id` registrado. Retirada de un asesor: antes de quitar un perfil del roster, el asesor cierra sus casos; al arrancar, handover registra cuántos casos huérfanos hay, sin sus ids. El supervisor NO responde, cierra ni asigna un caso asignado a otro asesor: solo lo reasigna con `POST /cases/{id}/reassign`, y un caso `open`, `timed_out` o `closed` responde `409` (`case_not_assigned` en los dos primeros y `case_closed` en el último) y un cambio perdido en la escritura condicional responde `409` `case_changed`. La escritura es condicional al asesor leído: si el caso fue cerrado, respondido-y-reasignado o transferido entre la lectura y la escritura responde `409` (`case_closed` si está `closed`, `case_changed` en otro caso) sin deshacer el cambio. Un caso huérfano `assigned` sí puede reasignarse. El supervisor NO responde, cierra ni asigna un caso asignado a otro asesor: solo lo reasigna. Las mismas reglas de `asesor` se aplican en `POST /cases/{id}/reply` (el orquestador responde `403` sin enviar nada al cliente), `POST /cases/{id}/close` y `POST /cases/{id}/assign` (handover responde `403` sin modificar el caso); asignar un caso ya `assigned` (S11) solo responde `200` al asesor asignado y otro asesor recibe `403`. Esto cambia el `200` sin cambios que S11 daba en la #9 a cualquier asesor: el asesor asignado sigue recibiendo `200` sin cambios. Precedencia de errores en `POST /cases/{id}/authorize`, `POST /cases/{id}/close` y `POST /cases/{id}/assign`: `403` (asesor no registrado) → `404` (caso inexistente) → `409` (caso `closed`; en `POST /cases/{id}/close`, `200` sin cambios por S8) → `403` (caso asignado a otro asesor), escalón que no se aplica a `POST /cases/{id}/close` ni a `authorize` con `action` = `close` sobre un caso huérfano (para ellos, superados los tres primeros escalones, el cierre está permitido). En `POST /cases/{id}/reply` el orquestador autoriza antes de comprobar si el caso existe: un `advisor_id` no registrado recibe `403` con `error` = `forbidden` aunque el caso no exista. `POST /cases/{id}/close` sobre un caso `closed` sigue S8: `200` sin cambios para cualquier asesor registrado, aunque no sea el asignado; `authorize` con `action` = `close` sobre un caso `closed` responde `409`. `POST /cases/{id}/reply` sobre un caso `closed` responde `409` con `error` = `case_closed`, sin enviar nada al cliente (el orquestador propaga el `409` de `authorize`). Si handover no está disponible para autorizar, el orquestador falla cerrado: no envía la respuesta y responde `502` con `upstream_error` (la fila `502 upstream_error` ya publicada de `POST /cases/{id}/reply`). La autorización por HTTP con `SERVICE_TOKEN` no impide que un proceso que ya tenga ese token suplante un `advisor_id` registrado; la identidad por persona llega con la #16 (remitente del webhook validado) o con el panel y la verificación de cuentas. Retirada de un asesor: antes de quitar un perfil del roster, el asesor cierra sus casos; al arrancar, handover registra cuántos casos huérfanos hay, sin sus ids. | — |
| S13 | Con `POST /cases/{id}/client-message`, si el caso está `assigned` el mensaje del cliente queda disponible en la conversación del panel y se responde `available_in_panel`, sin enviarlo por Telegram; con un caso `open`, con `not_assigned` o con `404` sigue el flujo actual (RAG, rechazo o traspaso). Los comandos de asesor `/responder <case_id> <texto>` y `/cerrar <case_id>` ya no existen: un mensaje con ese texto llega por `POST /messages` y se trata como texto ordinario del remitente, con su compuerta de privacidad y el flujo habitual, sin responder, asignar ni cerrar ningún caso. La identidad del asesor es el `profile_id` del panel; un asesor sin `telegram_user_id` vinculado puede atender desde el panel. | — |
| S14 | `GET /cases` con `scope=mine` (por defecto) lista solo los casos que el asesor puede gestionar según S12: `open` y `timed_out` con `actions` = `reply`, `assign`, `close`; `assigned` al solicitante con `actions` = `reply`, `close`; huérfanos (`assigned` con `advisor_id` nulo o fuera del roster de asesores) con `actions` = `close`. Nunca incluye casos `closed` ni `assigned` a otro perfil asesor registrado. Con `scope=all`, un supervisor registrado recibe todos los casos de cualquier estado y asesor, incluidos `closed`; `actions` contiene solo lo que puede hacer (`reply`, `assign`, `close` o `reassign`) y `advisor_id` indica el asesor asignado o `null`. Otro `advisor_id` con `scope=all` recibe `403 forbidden`. Orden por `created_at` ascendente y, a igual `created_at`, por `case_id` ascendente. Límite `CASE_LIST_LIMIT` (default 50, máximo 200) aplicado después de filtrar; sin cursor en v1. Un `advisor_id` que no es un perfil atendedor del roster recibe `200` con la lista vacía en `scope=mine`, sin registrar denegación. | `CASE_LIST_LIMIT = 50` |
| S15 | Los botones de consentimiento viajan como `OptionsBlock` con `options`, `option_ids` y `option_proofs` alineados. Cada `option_proof` es `HMAC-SHA256(service_token, "<channel>:<external_user_id>:<external_chat_id>:<button_id>:<notice_version>:<notice_sha256>:<nonce>")` truncado a 32 hex. El nonce es aleatorio por presentación y el orquestador conserva en memoria los proofs pendientes por identidad/canal/chat; compara identidad, canal, chat y política vigentes, exige ausencia de consentimiento vigente y consume atómicamente el proof aceptado/rechazado. Repeticiones, pruebas viejas o ajenas se descartan sin registrar consentimiento, borrar contenido ni cambiar estado. El gateway pinta teclado inline con `callback_data = "<button_id>:<option_proof>"` y normaliza `callback_query` a `kind=button`, `button_id` canónico y `button_proof`. La prueba no contiene datos personales en claro, mide 32 caracteres y cabe en el límite de 64 bytes de `callback_data` de Telegram. | — |
| S16 | Asignación automática por carga (`POST /cases/{id}/auto-assign`). La decide handover: si el caso sigue `open` y sin asesor, elige entre los `candidate_ids` que son asesores atendedores del roster el de menor número de casos `assigned`, con desempate por menor `advisor_id` lexicográfico, y registra la asignación con motivo `auto`. Dos solicitudes simultáneas se serializan y contabilizan la asignación ya confirmada. Sin candidatos válidos responde `queued`; si el caso ya fue asignado, respondido o cerrado por una persona responde `skipped`; un caso inexistente `404 not_found`; uno cerrado `409 case_closed`. El orquestador solo la invoca con el modo `automatica`, sin casos de supresión ni fuera del horario de atención, y no asigna casos que ya estaban en cola cuando un asesor recupera la disponibilidad. | — |
| S17 | Canal abierto (#60–#61). `channel` es el `id` de un canal de `canales`: de 2 a 32 caracteres, minúsculas, dígitos y separadores `-` o `_` simples (`^[a-z][a-z0-9]*(?:[-_][a-z0-9]+)*$`). Límites: como máximo 10 adjuntos por mensaje; `metadata` de hasta 4096 bytes en JSON compacto UTF-8 y profundidad 5; URL https de hasta 2048 caracteres; `alt_text` de hasta 1024; `mime_type` y `name` de hasta 255; `size_bytes` hasta 2 GiB. Los adjuntos llevan metadatos, nunca el binario. Solo texto: el orquestador responde a `image`, `file` y `audio` con el texto fijo `unsupported_reply`, igual que a `unsupported`, sin guardar adjuntos ni `metadata`. Desde #65 el orquestador acepta cualquier `channel` válido y solo responde `422` a mensajes que no son `inbound`; decide ventana y consentimiento por `ChannelInfo.capabilities` y `config.consent_mode` (ver `GET /channels`), nunca por el nombre del canal; el gateway resuelve `/send` por las filas y adaptadores registrados, rechaza con `422` un canal sin fila y degrada `ImageBlock` a enlace o texto cuando el canal no admite imágenes. | `MAX_CHANNEL_ID_LENGTH = 32`, `MAX_ATTACHMENTS = 10`, `MAX_METADATA_BYTES = 4096`, `MAX_METADATA_DEPTH = 5`, `MAX_URL_LENGTH = 2048`, `MAX_IMAGE_ALT_LENGTH = 1024`, `DEFAULT_SIGNATURE_WINDOW_SECONDS = 300` |

## Cola de entrada y outbox

Desde #64 el orquestador desacopla la recepción del procesamiento con dos tablas
en su PostgreSQL: `inbox` (cola de entrada) y `outbox` (cola de salida). No hay
infraestructura nueva ni broker.

### POST /messages: semántica `202`

`POST /messages` guarda el mensaje en `inbox` y responde `202 Accepted` con
`{"status": "accepted"}` sin ejecutarlo dentro de la petición. La marca de
deduplicación y la fila de `inbox` se escriben en la misma transacción. Si la
marca ya existía, responde `202` con `{"status": "duplicate"}` y no inserta
fila. Si la escritura falla, revierte ambas y responde `500 internal_error`, de
modo que el reintento del gateway no se confunda con un duplicado.

La aceptación de consentimiento pendiente (botón o frase de texto, #35) sigue
procesándose dentro de la petición para que un fallo al guardar la evidencia
responda `500`; no pasa por `inbox`. Sin consentimiento vigente la fila se
encola, pero no se persiste la marca de deduplicación (el gateway deduplica con
TTL).

### Workers

- `procesar_entrantes` toma filas de `inbox` con
  `ORDER BY id FOR UPDATE SKIP LOCKED` y una concesión (`WORKER_LEASE_SECONDS`).
  Solo la cabeza de cada conversación (`<canal>:<id externo>`) es elegible, lo
  que conserva el orden.
  Un fallo se reintenta con backoff hasta `INBOX_MAX_ATTEMPTS` y después queda
  `failed` con el nombre de la excepción; la carga JSON se vacía al terminar.
- `enviar_salientes` toma filas de `outbox` con la misma forma, entrega con
  `send_channel_blocks` al gateway y marca `sent`. Un error transitorio
  (`ServiceUnavailable`) vuelve a `pending` con backoff exponencial y jitter
  hasta `OUTBOX_MAX_ATTEMPTS`; un rechazo definitivo `422` del canal
  (`ChannelRejected`: ventana cerrada, plantilla no aprobada, canal inactivo)
  marca `failed` sin reintentar.

### Entrega al menos una vez y ventana de duplicado

La entrega es **al menos una vez**: el worker puede caer entre el envío
correcto y el `sent`, o expirar la concesión durante un envío lento; otro worker
reenvía y el cliente puede ver el mensaje dos veces. La ventana de duplicado es
como máximo `WORKER_LEASE_SECONDS` y es la contrapartida aceptada de no perder
mensajes. La entrada también es al menos una vez: el flujo hace varias
escrituras y un reintento puede repetir efectos ya hechos.

### Bloqueo por orden

Una fila no terminal bloquea las posteriores de su misma clave
(`conversation_key` en la entrada, `destination_key` en la salida) hasta que
termine, se agote o se reintente. Con los valores por defecto, un mensaje que
reintenta bloquea los posteriores de su conversación o destino unos minutos como
máximo.

### Variables de configuración

| Variable | Defecto | Rango |
|---|---|---|
| `INBOX_MAX_ATTEMPTS` | 3 | ≥ 1 |
| `INBOX_BACKOFF_BASE_SECONDS` | 5 | > 0 |
| `OUTBOX_MAX_ATTEMPTS` | 6 | ≥ 1 |
| `OUTBOX_BACKOFF_BASE_SECONDS` | 2 | > 0 |
| `OUTBOX_BACKOFF_MAX_SECONDS` | 300 | > 0 (tope de ambos backoffs) |
| `OUTBOX_BACKOFF_JITTER` | 0.2 | [0, 1] |
| `WORKER_POLL_SECONDS` | 1 | > 0 |
| `WORKER_LEASE_SECONDS` | 120 | > 0 (debe superar el timeout del gateway de 10 s) |

Una variable fuera de rango impide arrancar el servicio y el error nombra la
variable.

### Panel de envíos fallidos

`GET /admin/envios` (solo `admin` y `supervisor`) lista las filas `failed` más
recientes primero con id, canal, destino enmascarado (`****` + últimos 4), tipo,
intentos, motivo y fecha; nunca el texto, los bloques ni el destino completo.
`POST /admin/envios/{id}/reintentar` exige CSRF, devuelve la fila a `pending`
con intentos en cero y registra `outbox_retry` en `panel_audit` con el resultado
`ok`, `not_found`, `not_failed` o `forbidden`. Las filas se purgan con la
retención vigente y la supresión de un contacto las elimina.

