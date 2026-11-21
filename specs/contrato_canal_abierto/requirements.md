# Requirements — #60 `contrato_canal_abierto`

Fase 1 de la ampliación multicanal genérica (`docs/especificacion.md`,
«Ampliación multicanal genérica y multiagente»). El contrato deja de tener una
lista fija de canales, transporta tipos multimedia con metadatos de adjuntos,
`metadata` acotada y `direction`, añade capacidades y el bloque `image`, y
`CONTRATOS.md` documenta el webhook genérico firmado que se implementa en #62.

Quién cumple cada requirement:

- **contracts** (`contracts/lazaro_contracts`, `contracts/CONTRATOS.md`): R1–R38 y R48.
- **telegram_gateway**: R39–R42 (cambios mínimos para seguir fallando cerrado).
- **orchestrator**: R43–R46 (cambios mínimos para seguir fallando cerrado y
  conservar «solo texto»).
- **Todos**: R47.

Definiciones usadas abajo:

- **Slug de canal**: texto de 2 a 32 caracteres que cumple
  `^[a-z][a-z0-9]*(?:[-_][a-z0-9]+)*$` (minúsculas, dígitos y separadores `-`
  o `_` simples, sin separador inicial, final ni doble). Corresponde a
  `canales.id` (#61).
- **Tipo multimedia**: `kind` ∈ {`image`, `file`, `audio`}.
- **URL https válida**: texto de 1 a 2048 caracteres, sin espacios ni caracteres
  de control (U+0000–U+001F, U+007F), con esquema `https` (sin distinguir
  mayúsculas), host no vacío y sin credenciales (`usuario@` o
  `usuario:clave@`) en la autoridad.
- **Tamaño de `metadata`**: bytes de
  `json.dumps(metadata, ensure_ascii=False, separators=(",", ":")).encode("utf-8")`.
- **Profundidad de `metadata`**: el objeto `metadata` cuenta 1 y cada objeto o
  lista anidada suma 1 (`{"a": {"b": [1]}}` tiene profundidad 3).
- **Claves históricas de `NormalizedMessage`**: `channel`, `external_user_id`,
  `external_chat_id`, `external_message_id`, `kind`, `text`, `button_id`,
  `button_proof`, `received_at`.
- **Canal atendido**: `telegram` o `whatsapp` (los únicos con adaptador hoy).

## Cobertura del acceptance de #60

| Criterio del acceptance | Requirements |
|---|---|
| 1. `canal` es un slug acotado; `telegram`/`whatsapp` y todo lo actual siguen pasando | R1, R2, R24, R25, R39, R42, R43, R47 |
| 2. `MessageKind` con `image`/`file`/`audio`; `attachments` sin binario; `metadata` acotada | R3–R18, R48 |
| 3. `direction` `inbound`/`outbound`, por defecto `inbound` | R19, R20, R26, R44 |
| 4. Capacidades nuevas con defaults que conservan Telegram y WhatsApp | R21, R41 |
| 5. Bloque `image` (url https y texto alternativo); degradación en #61 | R22, R23, R40 |
| 6. `CONTRATOS.md`: webhook, callback, firma, ventana y equivalencia con el encargo | R28–R38 |
| 7. «Solo texto» no cambia (lo aplica el núcleo) | R45, R46 |
| 8. Pruebas en `contracts/tests/`; `./init.sh` verde | R1–R48 (tests de `tasks.md`) |

## Identificador de canal (contracts)

### R1
El paquete `lazaro_contracts` DEBE aceptar como `channel` de
`NormalizedMessage` y de `ChannelSendRequest` cualquier slug de canal,
incluidos `telegram`, `whatsapp`, `canal-externo`, `tiktok_simulado`, `n8n`,
`wa` y un slug de exactamente 32 caracteres.

### R2
SI el `channel` de `NormalizedMessage` o de `ChannelSendRequest` no es un slug
de canal (vacío, de 1 carácter, de 33 caracteres, con mayúsculas, espacios,
separador inicial, final o doble, primer carácter numérico, `.`, `/`,
caracteres no ASCII, salto de línea final o un valor que no es texto)
ENTONCES el paquete DEBE rechazarlo con `ValidationError`.

## Tipos y adjuntos (contracts)

### R3
El paquete DEBE admitir en `kind` exactamente los valores `text`, `button`,
`unsupported`, `image`, `file` y `audio`, y rechazar con `ValidationError`
cualquier otro (p. ej. `video`).

### R4
SI un `NormalizedMessage` tiene un tipo multimedia y `attachments` vacío
ENTONCES el paquete DEBE rechazarlo con `ValidationError`.

### R5
SI un `NormalizedMessage` tiene un tipo multimedia y algún adjunto tiene un
`type` distinto de `kind` ENTONCES el paquete DEBE rechazarlo con
`ValidationError`.

### R6
SI un `NormalizedMessage` tiene `kind` `text`, `button` o `unsupported` y
`attachments` no está vacío ENTONCES el paquete DEBE rechazarlo con
`ValidationError`.

### R7
CUANDO un `NormalizedMessage` tiene un tipo multimedia con al menos un adjunto
válido, el paquete DEBE aceptarlo tanto sin `text` como con un `text` de 1 a
4096 caracteres (pie del adjunto).

### R8
SI `attachments` tiene más de 10 elementos ENTONCES el paquete DEBE rechazar
el `NormalizedMessage` con `ValidationError`.

### R9
El paquete DEBE aceptar un adjunto (`Attachment`) con solo `type` (`image`,
`file` o `audio`) y `mime_type`, y también con `name`, `size_bytes` y `url`
opcionales.

### R10
SI el `mime_type` de un adjunto no cumple
`^[A-Za-z0-9][A-Za-z0-9!#$&^_.+-]*/[A-Za-z0-9][A-Za-z0-9!#$&^_.+-]*(?:;[ -~]*)?$`
o no mide de 3 a 255 caracteres ENTONCES el paquete DEBE rechazarlo con
`ValidationError` (`image/jpeg` y `audio/ogg; codecs=opus` son válidos).

### R11
SI el `name` de un adjunto está vacío, supera 255 caracteres o contiene `/`,
`\` o caracteres de control ENTONCES el paquete DEBE rechazarlo con
`ValidationError`.

### R12
SI el `size_bytes` de un adjunto es negativo o mayor que 2 GiB
(2 147 483 648) ENTONCES el paquete DEBE rechazarlo con `ValidationError`.

### R13
SI la `url` de un adjunto no es una URL https válida ENTONCES el paquete DEBE
rechazarla con `ValidationError`.

### R14
SI un adjunto trae un campo no declarado (p. ej. `data`, `content` o `bytes`
con el binario) ENTONCES el paquete DEBE rechazarlo con `ValidationError`.

## Metadata (contracts)

### R15
El paquete DEBE aceptar en `NormalizedMessage.metadata` un objeto JSON cuyo
tamaño no supere 4096 bytes y cuya profundidad no supere 5, con `{}` cuando el
campo falta.

### R16
SI el tamaño de `metadata` supera 4096 bytes ENTONCES el paquete DEBE
rechazar el `NormalizedMessage` con `ValidationError`.

### R17
SI la profundidad de `metadata` supera 5 ENTONCES el paquete DEBE rechazar el
`NormalizedMessage` con `ValidationError`.

### R18
SI `metadata` no es un objeto JSON (lista, texto, número o `null`) ENTONCES
el paquete DEBE rechazar el `NormalizedMessage` con `ValidationError`.

## Dirección (contracts)

### R19
El paquete DEBE aceptar en `NormalizedMessage.direction` únicamente `inbound`
y `outbound`, con `inbound` cuando el campo falta.

### R20
SI un `NormalizedMessage` tiene `direction` = `outbound` y `kind` `button` o
`unsupported` ENTONCES el paquete DEBE rechazarlo con `ValidationError`.

## Capacidades (contracts)

### R21
El paquete DEBE aceptar en `ChannelCapabilities` los booleanos
`supports_buttons`, `supports_images`, `supports_files` y `supports_audio`,
con los valores `true`, `false`, `false` y `false` cuando faltan.

## Bloque imagen (contracts)

### R22
El paquete DEBE aceptar el bloque `ImageBlock` (`type` = `image`, `url` y
`alt_text`) como miembro de `ResponseBlock` dentro de `ResponseBlocks` y de
`ChannelSendRequest`, sin contarlo en el límite de un enlace por respuesta.

### R23
SI un `ImageBlock` llega sin `url` o sin `alt_text`, con una `url` que no es
URL https válida, o con un `alt_text` vacío o de más de 1024 caracteres
ENTONCES el paquete DEBE rechazarlo con `ValidationError`.

## Compatibilidad (contracts)

### R24
CUANDO se valida un payload histórico (los ejemplos actuales
`normalized_message.json`, `normalized_button_message.json`,
`channel_send_request.json`, `channel_capabilities.json` y
`response_blocks.json`), el paquete DEBE aceptarlo con `attachments` = `[]`,
`metadata` = `{}`, `direction` = `inbound` y las capacidades nuevas de R21.

### R25
CUANDO se serializa (`model_dump` o `model_dump_json`) un `NormalizedMessage`
con `attachments` vacío, `metadata` vacío y `direction` = `inbound`, la
salida NO DEBE contener claves distintas de las claves históricas.

### R26
CUANDO se serializa un `NormalizedMessage` con `attachments`, `metadata` o
`direction` distintos de su valor por defecto, la salida DEBE incluir esos
campos y validar de nuevo a un modelo igual al original.

### R27
El paquete DEBE exportar en `__all__` `Attachment`, `AttachmentKind`,
`MessageDirection`, `ImageBlock`, `HttpsUrl`, `CHANNEL_ID_PATTERN`,
`MIN_CHANNEL_ID_LENGTH` (2), `MAX_CHANNEL_ID_LENGTH` (32), `MAX_ATTACHMENTS`
(10), `MAX_ATTACHMENT_SIZE_BYTES` (2 147 483 648), `MAX_METADATA_BYTES`
(4096), `MAX_METADATA_DEPTH` (5), `MAX_URL_LENGTH` (2048),
`MAX_IMAGE_ALT_LENGTH` (1024), `LAZARO_TIMESTAMP_HEADER`
(`X-Lazaro-Timestamp`), `LAZARO_SIGNATURE_HEADER` (`X-Lazaro-Signature`) y
`DEFAULT_SIGNATURE_WINDOW_SECONDS` (300), con esos valores.

## Documento `CONTRATOS.md` (contracts)

### R28
`contracts/CONTRATOS.md` DEBE listar en la tabla de `### NormalizedMessage`
todos los campos de `NormalizedMessage` y en la tabla de `### Attachment`
todos los campos de `Attachment`.

### R29
`contracts/CONTRATOS.md` DEBE incluir `ImageBlock` en la tabla de
`### ResponseBlocks` y una tabla en `### ChannelCapabilities` con todos los
campos de `ChannelCapabilities`, indicando el valor por defecto de los cuatro
campos de R21.

### R30
`contracts/CONTRATOS.md` DEBE tener la sección
`## Canal genérico (webhook firmado)` con la subsección
`### POST /webhooks/{canal_id}` que indique que la expone `telegram_gateway`,
que se implementa en #62, quién la llama, los modelos
`NormalizedMessage` → `MessageResponse`, la respuesta `200 OK` y los errores
`401 unauthorized`, `404 not_found`, `422 validation_error` y
`500 internal_error`.

### R31
`contracts/CONTRATOS.md` DEBE incluir en la sección
`## Canal genérico (webhook firmado)` al menos un ejemplo de entrada con
adjunto y `metadata` y uno de callback con `direction` = `outbound`, de modo
que todos sus bloques de ejemplo (el JSON de los bloques `json` y el cuerpo de
los bloques `http`) validen como `NormalizedMessage`.

### R32
`contracts/CONTRATOS.md` DEBE documentar en
`### Firma y ventana anti-repetición` los encabezados `X-Lazaro-Timestamp`
(segundos Unix) y `X-Lazaro-Signature` (HMAC-SHA256 en 64 caracteres
hexadecimales en minúsculas de `<timestamp>.<cuerpo>` sobre los bytes exactos
del cuerpo), la ventana de 300 s por defecto
(`DEFAULT_SIGNATURE_WINDOW_SECONDS`), la comparación en tiempo constante y la
respuesta `401` fuera de ventana o con firma ausente o incorrecta.

### R33
CUANDO se recalcula HMAC-SHA256 con el secreto de ejemplo documentado sobre
`<X-Lazaro-Timestamp>.<cuerpo>` de cada ejemplo firmado de `CONTRATOS.md`
(entrada y callback), el resultado hexadecimal DEBE ser igual al
`X-Lazaro-Signature` documentado en ese ejemplo.

### R34
`contracts/CONTRATOS.md` DEBE documentar en `### Callback saliente` el `POST`
a `config.callback_url` (https), el cuerpo `NormalizedMessage` con
`direction` = `outbound`, los mismos encabezados de firma, que una respuesta
2xx es entrega y cualquier otra o un error de red es envío fallido, que el
receptor deduplica por `external_message_id` y que se implementa en #62.

### R35
`contracts/CONTRATOS.md` DEBE tener en
`### Equivalencia con los nombres del encargo` una tabla que asocie `canalId`
→ `channel`, `idExternoUsuario` → `external_user_id`, `idExternoMensaje` →
`external_message_id`, `direccion` → `direction`, `tipo` → `kind`,
`contenido` → `text`, `adjuntos` → `attachments`, `timestamp` →
`received_at` y `metadata` → `metadata`.

### R36
`contracts/CONTRATOS.md` DEBE listar en `### Autenticación` el webhook
`POST /webhooks/{canal_id}` como excepción al `X-Service-Token`, protegido por
`X-Lazaro-Signature`.

### R37
`contracts/CONTRATOS.md` DEBE documentar, en `### Variante canónica de POST /send`
y en la fila `422` de `### POST /send`, el rechazo `422 validation_error` de un
canal distinto de `telegram` y `whatsapp` y de un bloque `image` en un canal
sin `supports_images` (hasta #61), y en la fila `422` de `### POST /messages`
el rechazo de un `NormalizedMessage` de canal no atendido o con
`direction` = `outbound`.

### R38
`contracts/CONTRATOS.md` DEBE tener en «Supuestos a confirmar» la fila `S17`
con el formato del slug (R1, R2), los límites de R8, R10–R13, R15–R17 y R23,
que los adjuntos nunca llevan el binario, la regla «solo texto» con
`unsupported_reply` y el rechazo `422` temporal de R37.

## Gateway (telegram_gateway)

### R39
SI `POST /send` recibe un `ChannelSendRequest` válido cuyo `channel` no es
`telegram` ni `whatsapp` ENTONCES el `telegram_gateway` DEBE responder `422`
con `error` = `validation_error` sin invocar ningún adaptador de canal, esté
o no configurado WhatsApp.

### R40
SI `POST /send` recibe un `ChannelSendRequest` con al menos un bloque `image`
para un canal cuyas capacidades tienen `supports_images` = `false` ENTONCES el
`telegram_gateway` DEBE responder `422` con `error` = `validation_error` sin
enviar ninguno de los bloques.

### R41
CUANDO se consultan las capacidades de `TelegramChannelAdapter`, de WhatsApp
Cloud (ventana abierta y cerrada, `ChannelCapabilities(**whatsapp_capabilities(...))`,
como hace el adaptador) y de
`FakeWhatsAppAdapter`, el `telegram_gateway` DEBE informar
`supports_buttons` = `true` y `supports_images` = `supports_files` =
`supports_audio` = `false`, con el resto de capacidades iguales a hoy.

### R42
CUANDO el `telegram_gateway` reenvía al orquestador un mensaje normalizado de
Telegram o de WhatsApp con `HttpOrchestratorClient`, el cuerpo JSON de
`POST /messages` NO DEBE contener claves distintas de las claves históricas.

## Orquestador (orchestrator)

### R43
SI `POST /messages` recibe un `NormalizedMessage` cuyo `channel` no es un canal
atendido ENTONCES el `orchestrator` DEBE responder `422` con `error` =
`validation_error` sin registrar la clave del mensaje, sin procesarlo y sin
enviar nada al gateway.

### R44
SI `POST /messages` recibe un `NormalizedMessage` con `direction` = `outbound`
ENTONCES el `orchestrator` DEBE responder `422` con `error` =
`validation_error` sin registrar la clave del mensaje, sin procesarlo y sin
enviar nada al gateway.

### R45
CUANDO el `orchestrator` procesa un `NormalizedMessage` de un canal atendido
con un tipo multimedia, DEBE tratarlo igual que `kind` = `unsupported`: enviar
por el mismo canal y chat el texto fijo `unsupported_reply`, sin cambiar el
estado de la conversación, sin guardar el mensaje, sus adjuntos ni su
`metadata`, y sin llamar a RAG ni a la IA.

### R46
CUANDO `POST /messages` recibe un `NormalizedMessage` válido de un canal
atendido con un tipo multimedia, el `orchestrator` DEBE responder `202` con
`status` = `accepted`.

## Todos

### R47
Los tests y ejemplos existentes de `contracts/tests/`, `contracts/examples/` y
`services/*/tests/` DEBEN pasar sin ninguna modificación.

## Adjuntos: campos obligatorios (contracts)

### R48
SI un adjunto (`Attachment`) llega sin `type` o sin `mime_type` ENTONCES el
paquete DEBE rechazarlo con `ValidationError`.
