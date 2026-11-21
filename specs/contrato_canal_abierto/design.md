# Design — #60 `contrato_canal_abierto`

Cambio de contrato en `contracts/` más dos guardas mínimas en
`telegram_gateway` y `orchestrator` para que el comportamiento actual no
cambie: hoy un canal o un tipo desconocido lo rechaza el contrato (`Literal`);
al abrir el contrato, esa barrera pasa a cada servicio que recibe un canal.

Sin dependencias nuevas, sin variables de entorno nuevas, sin rutas nuevas, sin
tablas nuevas y sin código de terceros (no hay licencias que confirmar).

## Alcance y fuera de alcance

Dentro: tipos y modelos del contrato (R1–R27, R48), `CONTRATOS.md` (R28–R38),
guarda de canal y de imagen en `POST /send` del gateway (R39–R42), guarda de
canal y de dirección en `POST /messages` del orquestador y prueba de «solo
texto» (R43–R46).

Fuera (no se adelanta):

- #61: tabla `canales`, `ChannelRegistry`, puerto `Canal`, degradación
  (botones → lista, imagen → enlace). La guarda de imagen de R40 es un rechazo
  que #61 sustituye por la degradación.
- #62: la ruta `POST /webhooks/{canal_id}`, la verificación real de la firma,
  la ventana configurable, el callback y el anti-SSRF. #60 solo documenta el
  contrato y exporta los nombres de encabezado y la ventana por defecto.
- #65: quitar los nombres de canal del núcleo (`INBOX_CHANNELS`, ramas por
  `"whatsapp"`). `INBOX_CHANNELS` no se toca.
- Emitir `image`/`file`/`audio` desde los adaptadores de Telegram y WhatsApp:
  siguen emitiendo `unsupported` sin adjuntos (lo fijan
  `test_non_text_types_are_forwarded_as_unsupported` y
  `test_non_text_telegram_update_is_normalized_as_unsupported`). Lo hará la
  feature que muestre en el panel qué llegó.
- Guardar adjuntos o `metadata` en el orquestador.

## Archivos

| Archivo | Cambio |
|---|---|
| `contracts/lazaro_contracts/common.py` | Constantes de firma (R27) |
| `contracts/lazaro_contracts/channels.py` | `Channel` slug, `HttpsUrl`, `Attachment`, `MessageKind`, `MessageDirection`, campos nuevos de `NormalizedMessage`, capacidades, `ImageBlock` |
| `contracts/lazaro_contracts/__init__.py` | Exportaciones nuevas (R27) |
| `contracts/CONTRATOS.md` | Tablas, sección «Canal genérico (webhook firmado)», filas 422, S17 |
| `contracts/tests/test_canal_abierto.py` | **Nuevo**: modelos (R1–R27) |
| `contracts/tests/test_canal_abierto_doc.py` | **Nuevo**: documento (R28–R38) |
| `services/telegram_gateway/telegram_gateway/domain.py` | Excepciones `UnknownChannel`, `UnsupportedBlock`; guarda de imagen en `send_response` |
| `services/telegram_gateway/telegram_gateway/main.py` | `POST /send` resuelve `telegram`/`whatsapp` explícitamente; otro canal → `UnknownChannel` |
| `services/telegram_gateway/tests/test_canal_abierto.py` | **Nuevo**: R39–R42 |
| `services/orchestrator/orchestrator/domain.py` | Constante `ATTENDED_CHANNELS` |
| `services/orchestrator/orchestrator/main.py` | Guarda de canal y dirección al inicio de `post_message` |
| `services/orchestrator/tests/test_canal_abierto.py` | **Nuevo**: R43–R46 |
| `progress/impl_contrato_canal_abierto.md` | **Nuevo**: trazabilidad R → test |

No se crean archivos en `contracts/examples/` (así `test_examples.py` no
cambia, R47): los ejemplos nuevos viven en `CONTRATOS.md` y los valida
`test_canal_abierto_doc.py` (R31, R33). No se modifica ningún test ni ejemplo
existente. `LinkBlock` no cambia (su `url` sigue admitiendo cualquier texto de
1 a 2048 caracteres, por compatibilidad).

El paquete sigue importando solo stdlib y pydantic (`test_packaging.py`): se
usan `json` y `urllib.parse`.

## `common.py`

```python
# #60: firma del webhook genérico (se verifica en #62).
LAZARO_TIMESTAMP_HEADER = "X-Lazaro-Timestamp"
LAZARO_SIGNATURE_HEADER = "X-Lazaro-Signature"
DEFAULT_SIGNATURE_WINDOW_SECONDS = 300
```

## `channels.py`

### Constantes y tipos

```python
CHANNEL_ID_PATTERN = r"^[a-z][a-z0-9]*(?:[-_][a-z0-9]+)*$"
MIN_CHANNEL_ID_LENGTH = 2
MAX_CHANNEL_ID_LENGTH = 32
MAX_ATTACHMENTS = 10
MAX_ATTACHMENT_SIZE_BYTES = 2 * 1024**3          # 2 147 483 648
MAX_MIME_TYPE_LENGTH = 255
MAX_ATTACHMENT_NAME_LENGTH = 255
MAX_METADATA_BYTES = 4096
MAX_METADATA_DEPTH = 5
MAX_URL_LENGTH = 2048
MAX_IMAGE_ALT_LENGTH = 1024
MIME_TYPE_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9!#$&^_.+-]*/[A-Za-z0-9][A-Za-z0-9!#$&^_.+-]*(?:;[ -~]*)?$"

Channel = Annotated[str, StringConstraints(
    min_length=MIN_CHANNEL_ID_LENGTH, max_length=MAX_CHANNEL_ID_LENGTH,
    pattern=CHANNEL_ID_PATTERN)]
MessageKind = Literal["text", "button", "unsupported", "image", "file", "audio"]
AttachmentKind = Literal["image", "file", "audio"]
MessageDirection = Literal["inbound", "outbound"]

def _check_https_url(value: str) -> str: ...      # ValueError si no es URL https válida
HttpsUrl = Annotated[str, StringConstraints(min_length=1, max_length=MAX_URL_LENGTH),
                     AfterValidator(_check_https_url)]

def _check_attachment_name(value: str) -> str: ...  # rechaza "/", "\\" y control
def _json_depth(value: JsonValue) -> int: ...       # iterativo (pila), sin recursión
def _check_metadata(value: dict[str, JsonValue]) -> dict[str, JsonValue]: ...
```

- `Channel` conserva su nombre: los imports actuales siguen funcionando. Se
  usa el motor de regex por defecto de pydantic (Rust), donde `$` no acepta un
  salto de línea final (`"telegram\n"` se rechaza; lo prueba R2). Se rechaza en
  vez de normalizar a minúsculas: falla cerrado igual que hoy.
- `_check_https_url`: rechaza si hay algún carácter con `ch.isspace()` o
  código < 32 o = 127; con `urllib.parse.urlsplit(value)` exige
  `scheme.lower() == "https"`, `hostname` no vacío y `"@" not in netloc`.
  Un `ValueError` de `urlsplit` se propaga como `ValidationError`. No
  normaliza ni reescribe el valor. No resuelve DNS (el anti-SSRF del callback
  es de #62; la plataforma no descarga `url` en esta versión).
- `_check_metadata`: calcula el tamaño definido en `requirements.md` y la
  profundidad (objeto raíz = 1, cada objeto o lista anidada +1); lanza
  `ValueError` si supera `MAX_METADATA_BYTES` o `MAX_METADATA_DEPTH`.

### Adjunto

```python
class Attachment(ContractModel):
    """Metadatos de un adjunto; nunca el binario (extra="forbid")."""
    type: AttachmentKind
    mime_type: Annotated[str, StringConstraints(min_length=3, max_length=MAX_MIME_TYPE_LENGTH,
                                                pattern=MIME_TYPE_PATTERN)]
    name: Annotated[str, StringConstraints(min_length=1, max_length=MAX_ATTACHMENT_NAME_LENGTH),
                    AfterValidator(_check_attachment_name)] | None = None
    size_bytes: Annotated[int, Field(ge=0, le=MAX_ATTACHMENT_SIZE_BYTES)] | None = None
    url: HttpsUrl | None = None
```

`mime_type` es obligatorio (el adaptador lo conoce o usa
`application/octet-stream`); `name`, `size_bytes` y `url` son opcionales
porque Telegram y WhatsApp no siempre los dan. El id de medio del proveedor,
si hiciera falta, va en `metadata`.

### `NormalizedMessage`

Campos nuevos (los históricos no cambian):

```python
    direction: MessageDirection = Field(
        default="inbound", exclude_if=lambda value: value == "inbound")
    attachments: Annotated[list[Attachment], Field(max_length=MAX_ATTACHMENTS)] = Field(
        default_factory=list, exclude_if=lambda value: not value)
    metadata: Annotated[dict[str, JsonValue], AfterValidator(_check_metadata)] = Field(
        default_factory=dict, exclude_if=lambda value: not value)
```

`exclude_if` (existe desde pydantic 2.12, comprobado en el wheel 2.12.0;
`contracts/requirements.txt` ya fija `>=2.12,<3`) hace que un mensaje sin datos nuevos se serialice con las mismas
claves que hoy (R25), en `model_dump` y en `model_dump_json`. Los campos
`text`, `button_id` y `button_proof` siguen saliendo como `null` igual que hoy.

Validador `_content_matches_kind` ampliado (orden de comprobación):

1. Reglas actuales (`text` exige `text`, `button` exige `button_id`,
   `button_proof` solo con `button`).
2. Tipo multimedia sin adjuntos → error (R4).
3. Tipo multimedia con algún `attachment.type != kind` → error (R5).
4. `kind` ∈ {`text`, `button`, `unsupported`} con adjuntos → error (R6).
5. `direction == "outbound"` y `kind` ∈ {`button`, `unsupported`} → error (R20).

En un tipo multimedia `text` es opcional (pie del adjunto, R7). En un mensaje
`outbound`, `received_at` es el momento en que la plataforma generó el
mensaje (se documenta en `CONTRATOS.md`).

### `ChannelCapabilities`

```python
    supports_buttons: bool = True
    supports_images: bool = False
    supports_files: bool = False
    supports_audio: bool = False
```

`True` en botones porque Telegram (teclado inline) y WhatsApp (botones
interactivos) ya los pintan; `False` en el resto porque ninguno envía
multimedia hoy. `TelegramChannelAdapter`, `whatsapp_capabilities` y
`FakeWhatsAppAdapter` no se tocan: heredan estos valores (R41).

### `ImageBlock`

```python
class ImageBlock(ContractModel):
    type: Literal["image"]
    url: HttpsUrl
    alt_text: Annotated[str, StringConstraints(min_length=1, max_length=MAX_IMAGE_ALT_LENGTH)]

ResponseBlock = Annotated[
    TextBlock | OptionsBlock | ListBlock | LinkBlock | TemplateBlock | ImageBlock,
    Field(discriminator="type"),
]
```

`ResponseBlocks` y `ChannelSendRequest` no cambian su lógica: el límite de un
enlace cuenta solo `LinkBlock` (R22).

## Límites elegidos (S17)

| Límite | Valor | Justificación |
|---|---|---|
| Slug de canal | 2–32, `^[a-z][a-z0-9]*(?:[-_][a-z0-9]+)*$` | Va en la URL `/webhooks/{canal_id}`, en claves de deduplicación, logs y la prueba S15: solo caracteres seguros sin codificar; 32 basta para nombres como `tiktok-simulado-demo` y cabe en `Identifier` (64); empieza por letra para no confundirse con ids numéricos |
| Adjuntos por mensaje | 10 | Álbum máximo de Telegram (`sendMediaGroup`) |
| `metadata` | 4096 bytes, profundidad 5 | Mismo orden que `MAX_TEXT_LENGTH`; sobra para ids y banderas del canal y acota filas, logs y el parseo |
| URL | 2048 | Igual que `LinkBlock.url` y el límite práctico de navegadores |
| `alt_text` | 1024 | Pie de foto máximo de Telegram y de WhatsApp (#61 lo usa como texto del enlace) |
| `mime_type`, `name` | 255 | Límite habitual de tipos MIME y de nombres de archivo |
| `size_bytes` | 2 GiB | Máximo de Telegram; WhatsApp admite 100 MB |

## `telegram_gateway`

`domain.py`:

```python
class UnknownChannel(DomainError):
    """#60: canal sin adaptador en este servicio (hasta el registry de #61)."""
    code = "validation_error"
    status_code = 422

class UnsupportedBlock(DomainError):
    """#60: bloque que el canal no admite; #61 lo sustituye por degradación."""
    code = "validation_error"
    status_code = 422
```

En `send_response`, tras obtener `capabilities` y **antes** de las
comprobaciones de ventana y de `adapter.send`:

```python
if not capabilities.supports_images and any(isinstance(b, ImageBlock) for b in block_list):
    raise UnsupportedBlock("Este canal no admite imágenes.")
```

`main.py`, `send` (rama `ChannelSendRequest`):

```python
if body.channel == "telegram":
    adapter = TelegramChannelAdapter(adapters.telegram)
elif body.channel == "whatsapp":
    adapter = adapters.whatsapp
else:
    raise UnknownChannel("El canal no está disponible en este servicio.")
```

El resto de la función no cambia (WhatsApp sin configurar sigue dando
`502 upstream_error`). La rama legacy `SendRequest` no cambia. El
manejador `DomainError` existente produce `{"error": "validation_error", ...}`.

## `orchestrator`

`domain.py`, junto a `INBOX_CHANNELS`:

```python
# #60: canales con adaptador hoy. La retira #65 (nucleo_sin_nombres_canal);
# hasta entonces un canal nuevo (#62/#63) recibe 422 en POST /messages.
ATTENDED_CHANNELS: frozenset[str] = frozenset({"telegram", "whatsapp"})
```

Decisión del leader: la guarda la retira la feature #65
`nucleo_sin_nombres_canal` (ya está en su acceptance en `feature_list.json`;
#63 también se actualizó). Hasta entonces, el webhook genérico (#62) y el
canal simulado (#63) reciben `422 validation_error` del orquestador para
cualquier canal que no sea `telegram` ni `whatsapp`.

`main.py`, primera instrucción de `post_message`:

```python
if isinstance(body, NormalizedMessage) and (
    body.channel not in ATTENDED_CHANNELS or body.direction != "inbound"
):
    raise RequestValidationError([])
```

Así no se llama a `mark_message_if_new`, ni a `consent_*`, ni se encola nada
(R43, R44). El manejador existente responde `422 validation_error`.

Los tipos multimedia no necesitan código: `_legacy_from_normalized` devuelve
`None` para `kind != "text"` y `process_channel_message` ya responde
`unsupported_reply` a todo `kind` distinto de `text` y `button`, sin
persistir. R45 y R46 se cubren con tests nuevos.

## `CONTRATOS.md`

Encabezados y fragmentos exactos (los comprueba `test_canal_abierto_doc.py`).
Las tablas de campos usan la cabecera `| Campo | Tipo | Obligatorio | Descripción |`
y las de errores `| HTTP | error | Cuándo |`.

1. `### Autenticación`, lista de excepciones: añadir la viñeta
   «`POST /webhooks/{canal_id}` del `telegram_gateway` (desde #62): lo llama un
   sistema externo que no conoce el token; se protege con `X-Lazaro-Signature`
   (ver «Canal genérico (webhook firmado)»).» (R36).
2. `### NormalizedMessage`: fila `channel` con tipo «slug de canal (2–32,
   `^[a-z][a-z0-9]*(?:[-_][a-z0-9]+)*$`)» y descripción «`id` del canal en
   `canales`»; fila `kind` con los seis valores; filas nuevas `direction`
   (`inbound` \| `outbound`, no, por defecto `inbound`), `attachments` (lista de
   `Attachment`, máx. 10, no) y `metadata` (objeto JSON ≤ 4096 bytes y
   profundidad 5, no). Párrafo: reglas R4–R7 y R20, y que la serialización
   omite los campos nuevos con su valor por defecto (R25) (R28).
3. Nuevo `### Attachment` tras `### NormalizedMessage`, con tabla de `type`,
   `mime_type`, `name`, `size_bytes`, `url` y la frase «nunca el binario»
   (R28).
4. `### ResponseBlocks`: fila `ImageBlock` | `image` | «URL https (hasta 2048)
   y `alt_text` (1–1024); un canal sin `supports_images` la rechaza con `422`
   hasta que #61 la degrade a enlace» (R29).
5. `### ChannelCapabilities`: tabla con los 10 campos; las filas nuevas dicen
   «por defecto `true`» (`supports_buttons`) o «por defecto `false`» (las otras
   tres) (R29).
6. `### Variante canónica de POST /send`: añadir «Hasta el registry de #61,
   solo `telegram` y `whatsapp` tienen adaptador: otro `channel` responde
   `422 validation_error` sin enviar nada. Un bloque `image` en un canal sin
   `supports_images` responde `422 validation_error` (#61 lo degradará a
   enlace).» (R37).
7. Fila 422 de `### POST /send` → `| 422 | validation_error | el cuerpo no
   valida contra `SendRequest` o `ChannelSendRequest`; el canal no puede
   enviar texto libre; el `channel` no es `telegram` ni `whatsapp`; un bloque
   `image` en un canal sin `supports_images` |` (R37).
8. Fila 422 de `### POST /messages` → `| 422 | validation_error | el cuerpo no
   valida contra `MessageRequest` ni `NormalizedMessage`; el `channel` del
   `NormalizedMessage` no es un canal atendido (`telegram`, `whatsapp`) o su
   `direction` es `outbound` |` (R37).
9. Nueva sección `## Canal genérico (webhook firmado)` entre «Mensaje
   normalizado y respuesta abstracta» y `## Rutas` (R30–R35), con esta
   estructura:

~~~markdown
## Canal genérico (webhook firmado)

(Introducción: cualquier sistema o puente —n8n, Zapier, Make, Twilio— conecta
un canal sin adaptador propio. La ruta y el callback se implementan en #62;
hasta entonces no existen. Formato por defecto: el `NormalizedMessage` de este
contrato; si el adaptador del canal define otro formato, lo traduce (#62).)

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

(`{canal_id}` es el `id` del canal en `canales`; el `channel` del cuerpo debe
ser igual a `{canal_id}` y `direction` debe ser `inbound`. Público: sin
`X-Service-Token`. Idempotente por `(channel, external_message_id)`.)

#### Request
(tabla de encabezados `X-Lazaro-Timestamp`, `X-Lazaro-Signature`,
`Content-Type: application/json`; cuerpo: `NormalizedMessage`.)

#### Respuesta
`200 OK` — tabla `| Campo | Tipo | Obligatorio | Descripción |` con `status`
(`accepted` \| `duplicate`).

#### Errores
| HTTP | error | Cuándo |
|------|-------|--------|
| 401 | unauthorized | firma ausente o incorrecta, o `X-Lazaro-Timestamp` fuera de la ventana |
| 404 | not_found | el canal no existe o está inactivo (no se distingue cuál) |
| 422 | validation_error | el cuerpo no valida, `channel` ≠ `{canal_id}` o `direction` ≠ `inbound` |
| 500 | internal_error | error inesperado |

#### Ejemplo firmado
(bloque http de entrada, abajo)

#### Ejemplo con adjunto
(bloque json de entrada con imagen, abajo)

### Callback saliente

- **Expone:** el sistema externo (`config.callback_url`, https)
- **Llama:** telegram_gateway (desde #62)
- **Modelos:** `NormalizedMessage` con `direction` = `outbound`

(Cuando la plataforma responde por un canal genérico hace `POST` a
`config.callback_url` con los mismos encabezados de firma. 2xx = entregado;
cualquier otra respuesta o un error de red = envío fallido. La entrega es al
menos una vez: el receptor deduplica por `external_message_id`. En `outbound`,
`received_at` es el momento en que la plataforma generó el mensaje. Se
implementa en #62.)

#### Ejemplo firmado
(bloque http del callback, abajo)

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

(`external_chat_id` no tiene nombre en el encargo: en canales sin chat
separado es igual a `external_user_id`.)
~~~

Bloques de ejemplo (copiar byte a byte; las firmas ya están calculadas con el
secreto `secreto-de-ejemplo` y las verifica R33). Cada bloque firmado es un
bloque de código con lenguaje `http` cuya **última línea** es el cuerpo exacto.
**Delimitadores:** en este design los bloques aparecen con `~~~` solo porque
van anidados; en `CONTRATOS.md` todos los bloques de ejemplo (`http` y `json`)
se escriben con tres comillas invertidas (`` ```http `` / `` ```json `` y
cierre `` ``` ``), que es lo que busca la expresión de T11:

Entrada (`#### Ejemplo firmado` de `### POST /webhooks/{canal_id}`):

~~~http
POST /webhooks/canal-externo HTTP/1.1
Host: lazaro.example.com
Content-Type: application/json
X-Lazaro-Timestamp: 1795273200
X-Lazaro-Signature: 0812c9aa0ad1983b42a1a4a122fdf3741469c299ef746fcbf3a55a858be97acd

{"channel":"canal-externo","external_user_id":"usuario-123","external_chat_id":"usuario-123","external_message_id":"msg-0001","kind":"text","text":"Hola, necesito ayuda con mi pedido","received_at":"2026-11-21T15:00:00Z"}
~~~

Callback (`#### Ejemplo firmado` de `### Callback saliente`):

~~~http
POST /lazaro/callback HTTP/1.1
Host: puente.example.com
Content-Type: application/json
X-Lazaro-Timestamp: 1795273205
X-Lazaro-Signature: 20dbabb2d55dc0b43c41f73c600c519989ecb737691d17a5b2e77156426d180a

{"channel":"canal-externo","external_user_id":"usuario-123","external_chat_id":"usuario-123","external_message_id":"out-0001","kind":"text","text":"Hola, con gusto te ayudo. Escribe tu numero de pedido.","received_at":"2026-11-21T15:00:05Z","direction":"outbound"}
~~~

Entrada con adjunto (`#### Ejemplo con adjunto`, bloque `json`):

~~~json
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
~~~

10. «Supuestos a confirmar»: fila nueva (R38), con estos fragmentos literales:

~~~markdown
| S17 | Canal abierto (#60). `channel` es el `id` de un canal de `canales`: de 2 a 32 caracteres, minúsculas, dígitos y separadores `-` o `_` simples (`^[a-z][a-z0-9]*(?:[-_][a-z0-9]+)*$`). Límites: como máximo 10 adjuntos por mensaje; `metadata` de hasta 4096 bytes en JSON compacto UTF-8 y profundidad 5; URL https de hasta 2048 caracteres; `alt_text` de hasta 1024; `mime_type` y `name` de hasta 255; `size_bytes` hasta 2 GiB. Los adjuntos llevan metadatos, nunca el binario. Solo texto: el orquestador responde a `image`, `file` y `audio` con el texto fijo `unsupported_reply`, igual que a `unsupported`, sin guardar adjuntos ni `metadata`. Hasta que una feature habilite canales nuevos de punta a punta, gateway y orquestador responden `422` a un `channel` distinto de `telegram` y `whatsapp`, y el gateway responde `422` a un bloque `image` en un canal sin `supports_images` (la degradación a enlace llega en #61). | `MAX_CHANNEL_ID_LENGTH = 32`, `MAX_ATTACHMENTS = 10`, `MAX_METADATA_BYTES = 4096`, `MAX_METADATA_DEPTH = 5`, `MAX_URL_LENGTH = 2048`, `MAX_IMAGE_ALT_LENGTH = 1024`, `DEFAULT_SIGNATURE_WINDOW_SECONDS = 300` |
~~~

Los nuevos encabezados `###` no chocan con los que usan los tests de
`test_contratos_doc.py` (`_section` busca la primera aparición exacta y
`ROUTES` no cambia).

## Tests: ayudantes de `test_canal_abierto_doc.py`

Locales al archivo (no se importan de `test_contratos_doc.py`): `_section`
equivalente, celdas de la primera columna con `^\| `([a-z_]+)` \|`, filas de
errores con `^\| (\d{3})\s+\| `?([a-z_]+)`? \|`, bloques con
`re.findall(r"```(json|http)\n(.*?)\n```", section, re.DOTALL)`. En un bloque
`http`: la ruta sale de la primera línea, los encabezados de las líneas
`Nombre: valor` y el cuerpo es la última línea; el secreto, de
`` secreto de ejemplo `([^`]+)` ``. R33 recalcula
`hmac.new(secreto, f"{ts}.".encode() + cuerpo.encode("utf-8"), hashlib.sha256).hexdigest()`
y comprueba además que `/webhooks/<channel>` coincide con el `channel` del
cuerpo de entrada.

## Excepciones

- Reutilizadas: `ValidationError` de pydantic (contrato),
  `RequestValidationError` (orquestador, mismo patrón que `/profiles`),
  `ChannelNotConfigured` (gateway, sin cambios).
- Añadidas (gateway): `UnknownChannel` y `UnsupportedBlock`, ambas
  `422 validation_error`.

## Alternativas descartadas

1. **Mantener `Literal` y añadir cada canal al contrato.** Contradice el
   acceptance: cada canal nuevo exigiría una feature de contrato.
2. **Canal desconocido en `POST /send` → `502` con `ChannelNotConfigured`.**
   Hoy ese cuerpo da `422 validation_error`; `502` cambiaría lo observable y el
   orquestador lo trataría como fallo transitorio (`ServiceUnavailable`) en vez
   de rechazo definitivo (`ChannelRejected`), y #64 lo reintentaría. Se elige
   `422` con `UnknownChannel`.
3. **Degradar la imagen a enlace dentro de cada adaptador actual.** Duplicaría
   en dos renderizadores la degradación pura que #61 centraliza; hoy ninguno
   envía imágenes. Se elige el rechazo explícito `422` por capacidad en
   `send_response`: una línea, falla cerrado y #61 la sustituye.
4. **Campos nuevos con `None` por defecto.** Seguirían saliendo como `null`
   en el JSON y un orquestador aún sin actualizar (`extra="forbid"`) los
   rechazaría. Se eligen `[]`/`{}`/`inbound` con `exclude_if`.
5. **Validar `channel` contra un registro dentro del contrato.** El contrato
   es puro (sin IO); el registro es #61.
6. **Ejemplos nuevos en `contracts/examples/`.** Obligaría a modificar
   `test_examples.py` (R47); los ejemplos van en `CONTRATOS.md`, validados por
   tests nuevos.

## Compatibilidad y despliegue

Gateway y orquestador pueden desplegarse en cualquier orden: el gateway nuevo
sigue enviando las mismas claves (R25, R42) y solo `telegram`/`whatsapp`
con `unsupported`; el orquestador nuevo acepta los payloads antiguos (R24);
`ChannelSendRequest` del orquestador nunca lleva `image` en esta feature.
`ChannelCapabilities` no viaja entre servicios.

## Dependencias

Ninguna. Sin variables de entorno nuevas (la ventana configurable es de #62).

## Supuestos a confirmar

Ninguna duda abierta de `docs/proyecto.md` §12 afecta a esta feature. Defaults
elegidos (todos documentados en S17 y cambiables como cambio de contrato):

- Límites de la tabla «Límites elegidos».
- `mime_type` obligatorio; `name`, `size_bytes` y `url` opcionales.
- El webhook responde con el modelo existente `MessageResponse`
  (`accepted`/`duplicate`) y exige `channel` = `{canal_id}` y
  `direction` = `inbound`.
- La guarda de canal del orquestador (`ATTENDED_CHANNELS`) es temporal: la
  retira #65 `nucleo_sin_nombres_canal` (decisión del leader). Hasta entonces
  #62 y #63 reciben `422 validation_error` del orquestador para canales nuevos.
- El secreto de los ejemplos es ficticio y solo sirve para verificar la firma.
