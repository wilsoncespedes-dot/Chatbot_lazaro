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
| 415  | `unsupported_format` | `/manuals` | el archivo no es PDF ni DOCX |
| 422  | `empty_document`     | `/manuals` | archivo vacío o sin texto extraíble |
| 502  | `telegram_error`     | `/send` | la API de Telegram falla |
| 502  | `upstream_error`     | `/send` (variante canónica), `/cases/{id}/reply` | falla el adaptador del canal o la llamada a `POST /send` del gateway |
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
(`HEALTHCHECK_TIMEOUT_SECONDS`): Redis en `telegram_gateway` y PostgreSQL en
`orchestrator`, `rag` y `handover`.

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
| `ImageBlock` | `image` | URL https (hasta 2048) y `alt_text` (1–1024); un canal sin `supports_images` la rechaza con `422` hasta que #61 la degrade a enlace |

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
elige el adaptador y aplica el control de capacidad antes de enviar. Si el canal
no puede enviar texto libre responde `422 validation_error`; si el adaptador
falla o no está configurado, `502 upstream_error`.

Hasta el registry de #61, solo `telegram` y `whatsapp` tienen adaptador: un
`channel` que no es `telegram` ni `whatsapp` responde `422 validation_error` sin
enviar nada. Un bloque `image` en un canal sin `supports_images` responde `422
validation_error` (#61 lo degradará a enlace).

## Canal genérico (webhook firmado)

Cualquier sistema externo o puente —n8n, Zapier, Make, Twilio— conecta un canal
sin adaptador propio. La ruta y el callback se implementan en #62; hasta
entonces no existen. El formato por defecto es el `NormalizedMessage` de este
contrato; si el adaptador del canal define otro formato, lo traduce (#62).

### Firma y ventana anti-repetición

- `X-Lazaro-Timestamp`: segundos Unix (entero decimal, UTC) del envío.
- `X-Lazaro-Signature`: HMAC-SHA256 con el secreto del canal de
  `<timestamp>.<cuerpo>`, en 64 caracteres hexadecimales en minúsculas,
  calculado sobre los bytes exactos del cuerpo (UTF-8, sin reformatear).
- Ventana: 300 s por defecto (`DEFAULT_SIGNATURE_WINDOW_SECONDS`), configurable
  en #62; si |ahora − timestamp| la supera, `401`.
- Firma ausente o incorrecta: `401`. La comparación es en tiempo constante.
- Cada canal tiene su secreto (#61); nunca viaja en el cuerpo ni en logs.
- Los ejemplos usan el secreto de ejemplo `secreto-de-ejemplo`.

### POST /webhooks/{canal_id}

- **Expone:** telegram_gateway (desde #62)
- **Llama:** el sistema externo o puente del canal
- **Modelos:** `NormalizedMessage` → `MessageResponse`

`{canal_id}` es el `id` del canal en `canales`; el `channel` del cuerpo debe ser
igual a `{canal_id}` y `direction` debe ser `inbound`. Público: sin
`X-Service-Token`. Idempotente por `(channel, external_message_id)`.

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
| 404 | not_found | el canal no existe o está inactivo (no se distingue cuál) |
| 422 | validation_error | el cuerpo no valida, `channel` ≠ `{canal_id}` o `direction` ≠ `inbound` |
| 500 | internal_error | error inesperado |

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
entrega y cualquier otra respuesta o un error de red es envío fallido. La
entrega es al menos una vez: el receptor deduplica por `external_message_id`. En
`outbound`, `received_at` es el momento en que la plataforma generó el mensaje.
Se implementa en #62.

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
| 422 | validation_error | el cuerpo no valida contra `SendRequest` o `ChannelSendRequest`; el canal no puede enviar texto libre; el `channel` no es `telegram` ni `whatsapp`; un bloque `image` en un canal sin `supports_images` |
| 502 | telegram_error | la API de Telegram falla |
| 502 | upstream_error | el adaptador del canal falla o no está configurado |
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
| `reason` | `no_relevant_chunks` \| `user_request` \| `invalid_answer` | sí | motivo del traspaso (S5) |
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
Entre los válidos elige el de menor número de casos `assigned` y, a igual carga,
el menor `advisor_id` lexicográfico. Solo asigna si el caso sigue `open` y sin
asesor: si una persona lo asignó, respondió o cerró antes, no lo modifica y
responde `skipped`. Sin candidatos válidos responde `queued` sin modificar el
caso. Un caso cerrado responde `409` con `error` = `case_closed`. Exige
`X-Service-Token`.

#### Request

| Campo | Tipo | Obligatorio | Descripción |
|-------|------|-------------|-------------|
| `candidate_ids` | lista de identificadores (1–200) | sí | perfiles atendedores disponibles, sin repetir |

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
| 422 | validation_error | el cuerpo no valida contra `CaseAutoAssignRequest` |
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
supresión y se informa en `deleted` con la clave `privacy_consents`.

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

### GET /cases

- **Expone:** handover
- **Llama:** orchestrator (panel de asesores, #29)
- **Modelos:** `CaseListQuery` → `CaseListResponse` (elementos `CaseListItem`)

Lista de solo lectura de los casos que un asesor puede gestionar según S12 y la
regla de huérfanos (S14). Exige `X-Service-Token`. Con `scope=mine` (por
defecto), un `advisor_id` que no es un perfil atendedor del roster sincronizado
recibe `200` con la lista vacía. Con `scope=all`, solo un supervisor registrado
recibe todos los casos de cualquier estado; otro perfil recibe `403` con
`error` = `forbidden`.

#### Request

Los parámetros viajan en la query; un parámetro no declarado se rechaza con
`422 validation_error`. La generación del roster viaja en
`X-Advisor-Roster-Generation`.

| Campo | Tipo | Obligatorio | Descripción |
|-------|------|-------------|-------------|
| `advisor_id` | identificador (1–64) | sí | `profile_id` del asesor o supervisor que pide el listado (S6) |
| `scope` | `mine` \| `all` | no | `mine` lista lo gestionable por el solicitante; `all` es la vista global del supervisor (S14) |

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
| `actions` | lista no vacía y sin repetidos de `reply` \| `assign` \| `close` \| `reassign` | sí | acciones que el solicitante puede hacer hoy; `reassign` solo aparece en la vista global del supervisor (S14) |
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
| S17 | Canal abierto (#60). `channel` es el `id` de un canal de `canales`: de 2 a 32 caracteres, minúsculas, dígitos y separadores `-` o `_` simples (`^[a-z][a-z0-9]*(?:[-_][a-z0-9]+)*$`). Límites: como máximo 10 adjuntos por mensaje; `metadata` de hasta 4096 bytes en JSON compacto UTF-8 y profundidad 5; URL https de hasta 2048 caracteres; `alt_text` de hasta 1024; `mime_type` y `name` de hasta 255; `size_bytes` hasta 2 GiB. Los adjuntos llevan metadatos, nunca el binario. Solo texto: el orquestador responde a `image`, `file` y `audio` con el texto fijo `unsupported_reply`, igual que a `unsupported`, sin guardar adjuntos ni `metadata`. Hasta que una feature habilite canales nuevos de punta a punta, gateway y orquestador responden `422` a un `channel` distinto de `telegram` y `whatsapp`, y el gateway responde `422` a un bloque `image` en un canal sin `supports_images` (la degradación a enlace llega en #61). | `MAX_CHANNEL_ID_LENGTH = 32`, `MAX_ATTACHMENTS = 10`, `MAX_METADATA_BYTES = 4096`, `MAX_METADATA_DEPTH = 5`, `MAX_URL_LENGTH = 2048`, `MAX_IMAGE_ALT_LENGTH = 1024`, `DEFAULT_SIGNATURE_WINDOW_SECONDS = 300` |
