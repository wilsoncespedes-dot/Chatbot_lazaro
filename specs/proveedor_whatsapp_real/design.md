# Design — proveedor_whatsapp_real (feature #43)

## Contexto y decisión

Decisión del dueño 2026-11-03: **Meta WhatsApp Cloud API**. Esta feature
implementa el adaptador de producción detrás de la interfaz `ChannelAdapter`
de #36, en el servicio `telegram_gateway` (gateway multicanal que ya enruta
`POST /send` con `channel = "whatsapp"` hacia `Adapters.whatsapp`). Twilio y
360dialog quedan fuera de alcance; la interfaz no se restringe.

No cambia el orquestador: ya decide la ventana (`panel.channel_window`,
`WHATSAPP_WINDOW_HOURS`), envía `TemplateBlock` fuera de ventana (#41/#42),
responde a `kind = "unsupported"` (#37) y deduplica de forma persistente por
`(canal, external_message_id)` (#36). El gateway añade una segunda barrera de
ventana (basada en entrantes reales recibidos por Meta) y traduce los errores
del proveedor.

## Archivos a crear o modificar

Nuevos:

- `services/telegram_gateway/telegram_gateway/whatsapp_cloud.py` — lógica
  **pura** (sin IO): verificación de firma, verificación GET, parseo del
  webhook, separación `button_id`/`button_proof`, construcción de cuerpos de
  envío y traducción de códigos de error/estados. Se separa de `domain.py`
  para no inflarlo; cumple la regla de capas (no hace IO).
- `services/telegram_gateway/telegram_gateway/adapters/whatsapp_cloud.py` —
  `WhatsAppCloudConfig` y `WhatsAppCloudAdapter` (HTTP con `httpx.Client`
  inyectado).
- `services/telegram_gateway/telegram_gateway/adapters/whatsapp_window.py` —
  protocolo `WhatsAppWindowStore`, `RedisWhatsAppWindowStore` y
  `FakeWhatsAppWindowStore`.
- `services/telegram_gateway/tests/test_whatsapp_cloud.py` — pruebas unitarias
  de funciones puras y del adaptador con `httpx.MockTransport`.
- `services/telegram_gateway/tests/test_whatsapp_webhook.py` — pruebas de la
  app (`TestClient`) para GET/POST del webhook, firma, deduplicación, ventana,
  estados y `POST /send`.
- `services/telegram_gateway/tests/test_whatsapp_config.py` — pruebas de
  `Settings`, `build_default_adapters` y `.env.example`.

Modificados:

- `services/telegram_gateway/telegram_gateway/config.py` — nuevas variables
  (§Configuración) y validador de R3.
- `services/telegram_gateway/telegram_gateway/domain.py` — `Adapters` gana
  `whatsapp_window: "WhatsAppWindowStore | None" = None`; `send_response` usa
  `capabilities_for(destination)` si el adaptador lo expone (R31). Se añade
  `WebhookForbidden(DomainError)` con `code = "forbidden"`, `status_code =
  403` (R9).
- `services/telegram_gateway/telegram_gateway/main.py` — rutas
  `GET/POST /whatsapp/webhook`, exención de `X-Service-Token` para esa ruta y
  construcción del adaptador real en `build_default_adapters`.
- `.env.example` — bloque `# WhatsApp Cloud API (#43)` (R7). Secretos vacíos.
- `docker-compose.yml` — pasar las variables `WHATSAPP_*` al servicio
  `telegram_gateway` (sin valores literales de secretos).
- `render.yaml` — mismas variables en el servicio `telegram_gateway`;
  `WHATSAPP_ACCESS_TOKEN`, `WHATSAPP_APP_SECRET` y `WHATSAPP_VERIFY_TOKEN` con
  `sync: false` y sin `value`; añadirlas a `SECRET_KEYS`/`THIRD_PARTY_SECRETS`
  de `scripts/tests/test_render_blueprint.py` para que R8 de despliegue las
  cubra.
- `docs/architecture.md` §3.8 — añadir la excepción del webhook WhatsApp (valida
  `X-Hub-Signature-256` y `hub.verify_token`).
- `docs/proyecto.md` §12/§13 — registrar la decisión del dueño 2026-11-03
  (Meta Cloud API) y retirar la duda abierta del proveedor; el coste de
  plantillas sigue como duda.
- `docs/despliegue.md` — pasos de alta en Meta: URL pública
  `{PUBLIC_BASE_URL}/whatsapp/webhook`, verify token, suscripción al campo
  `messages`, token de sistema permanente, phone number id.

No se tocan `contracts/`, `orchestrator`, `handover`, `rag` ni `eval`.

## Configuración (telegram_gateway `Settings`)

| Variable | Tipo / default | Notas |
|---|---|---|
| `WHATSAPP_ENABLED` | bool, `false` | Apagado: `Adapters.whatsapp = None`, webhook 404. |
| `WHATSAPP_ACCESS_TOKEN` | str, `""` | Secreto. Token de sistema de Meta. |
| `WHATSAPP_APP_SECRET` | str, `""` | Secreto. Clave del HMAC de la firma. |
| `WHATSAPP_VERIFY_TOKEN` | str, `""` | Secreto. Verificación GET. |
| `WHATSAPP_PHONE_NUMBER_ID` | str, `""` | Identificador del número emisor. |
| `WHATSAPP_GRAPH_BASE_URL` | str, `https://graph.facebook.com` | Sin barra final (se normaliza). |
| `WHATSAPP_GRAPH_API_VERSION` | str, `v21.0` | Patrón `^v\d+\.\d+$`. |
| `WHATSAPP_TEMPLATE_LANGUAGE` | str, `es` | Patrón `^[a-z]{2}(_[A-Z]{2})?$` (mismo que #42). |
| `WHATSAPP_INTERACTIVE_BODY_TEXT` | str, `Elige una opción:` | 1–1024 caracteres. |
| `WHATSAPP_WINDOW_HOURS` | int 1–24, `24` | Ya existe en `.env.example` (#41); el gateway lo lee también. |

Los tres secretos se declaran como `SecretStr` de Pydantic (no aparecen en
`repr`/`model_dump` por defecto); el adaptador recibe `str` vía
`get_secret_value()` y su `__repr__` no los incluye (R5). El validador de R3 se
aplica con `WHATSAPP_ENABLED=true` en cualquier `APP_ENV` y lanza `ValueError`
con los nombres de variable faltantes (con `hide_input_in_errors=True` ya
configurado no se filtran valores). `HTTP_TIMEOUT_SECONDS` existente se reutiliza
como timeout del cliente Meta.

## Tipos y firmas nuevas

`telegram_gateway/whatsapp_cloud.py` (puro):

```python
SIGNATURE_HEADER = "X-Hub-Signature-256"
WINDOW_CLOSED_CODES: frozenset[int] = frozenset({131047})
TEMPLATE_ERROR_CODES: frozenset[int] = frozenset(
    {132000, 132001, 132005, 132007, 132012, 132015, 132016}
)
MAX_REPLY_ID_LENGTH = 256
MAX_INTERACTIVE_BODY = 1024

def verify_signature(app_secret: str, body: bytes, header: str | None) -> bool
def verify_subscription(params: Mapping[str, str], verify_token: str) -> str | None
    # devuelve el challenge si es válido; None en otro caso

@dataclass(frozen=True)
class CloudStatus:
    wamid: str
    status: str            # valor crudo de Meta
    error_codes: tuple[int, ...]

@dataclass(frozen=True)
class CloudWebhook:
    messages: tuple[NormalizedMessage, ...]   # ya normalizados, en orden
    inbound_wa_ids: tuple[str, ...]           # para registrar ventana (incluye reaction)
    statuses: tuple[CloudStatus, ...]
    discarded: int                            # mensajes descartados (R21)

def parse_webhook(payload: object, phone_number_id: str, received_at: datetime) -> CloudWebhook
def split_button_id(raw: str) -> tuple[str, str | None]
def build_send_payloads(
    destination: str,
    blocks: Sequence[ResponseBlock],
    template_language: str,
    interactive_body_text: str,
) -> list[dict]   # lanza ChannelSendFailed si reply.id > 256 (R38)
def translate_error(status_code: int, body: object) -> DomainError  # R43–R45
def to_delivery_status(raw: str) -> DeliveryStatus                 # R48
```

`build_send_payloads` reutiliza `render_blocks` de
`adapters/telegram.py` para un solo bloque (R39) — se importa la función, no
se duplica; si la importación cruzada crea ciclo, se mueve `render_blocks` a
`domain.py` y `adapters/telegram.py` la reexporta con el mismo nombre (sin
cambiar su comportamiento, R50).

`adapters/whatsapp_window.py`:

```python
class WhatsAppWindowStore(Protocol):
    def record_inbound(self, wa_id: str, at: datetime) -> None: ...
    def last_inbound(self, wa_id: str) -> datetime | None: ...

class RedisWhatsAppWindowStore:      # clave gw:whatsapp:last_inbound:<wa_id>,
    def __init__(self, redis_url: str, ttl_seconds: int) -> None  # valor ISO-8601 UTC, EX = ttl

class FakeWhatsAppWindowStore:       # dict en memoria; fail=True lanza ConnectionError
    def __init__(self, fail: bool = False) -> None
```

`record_inbound` sobrescribe siempre el valor guardado con `SET ... EX` (sin
comparar con el anterior): los webhooks fuera de orden con diferencia de
segundos no afectan a una ventana de horas. La decisión abierto/cerrado se
toma en el adaptador con el reloj inyectado, no por expiración de Redis, para
que las pruebas controlen el tiempo.

`adapters/whatsapp_cloud.py`:

```python
@dataclass(frozen=True)
class WhatsAppCloudConfig:
    access_token: str = field(repr=False)
    phone_number_id: str
    graph_base_url: str
    api_version: str
    template_language: str
    interactive_body_text: str
    window_hours: int

class WhatsAppCloudAdapter:
    channel = "whatsapp"
    def __init__(
        self,
        config: WhatsAppCloudConfig,
        http: httpx.Client,
        window: WhatsAppWindowStore,
        clock: Callable[[], datetime],
    ) -> None
    def capabilities(self) -> ChannelCapabilities                       # R30
    def capabilities_for(self, destination: str) -> ChannelCapabilities # R28, R29, R42
    def normalize_incoming(self, raw: dict, received_at: datetime) -> NormalizedMessage | None
        # raw = un objeto `message` de Meta; delega en whatsapp_cloud
    def send(self, destination: str, blocks: Sequence[ResponseBlock]) -> DeliveryStatus
        # revalida ventana (R33), construye payloads, POST secuenciales (R40, R41)
    def delivery_status(self, raw: str) -> DeliveryStatus                 # R48
```

Las capacidades de opciones/listas/enlaces son las mismas constantes que usa
`FakeWhatsAppAdapter` (`MAX_OPTION_COUNT`, `MIN_LIST_OPTIONS`,
`MAX_LIST_OPTIONS`, `supports_links=True`).

## Flujo del webhook (main.py)

- `WHATSAPP_WEBHOOK_PATH = "/whatsapp/webhook"`; el middleware deja pasar esa
  ruta sin `X-Service-Token` (R10). Con `WHATSAPP_ENABLED=false` las rutas
  responden `404 not_found` (R2) mediante el manejador de `DomainError`/HTTP
  existente.
- `GET`: `verify_subscription(request.query_params, verify_token)`; válido →
  `PlainTextResponse(challenge)`; inválido → `WebhookForbidden` (403).
- `POST` es `async def` y lee `await request.body()` **antes** de cualquier
  parseo (R13). Firma inválida → `401 unauthorized` (R12). Con firma válida,
  `json.loads` protegido (R14) y el resto del procesamiento síncrono
  (dedup Redis, `post_message` httpx) se ejecuta en
  `starlette.concurrency.run_in_threadpool` para no bloquear el event loop.
- Orden por cuerpo: (1) `parse_webhook`; (2) `window.record_inbound` por cada
  `inbound_wa_ids` (errores del almacén se registran y no detienen); (3) para
  cada mensaje en orden: `dedup.mark_message_if_new("whatsapp", wamid,
  DEDUP_TTL_SECONDS)` (R23–R25) y `orchestrator.post_message(normalized)`
  (R26); (4) cada estado → `to_delivery_status` + log `whatsapp_status` (R47).
  Siempre `200 {"ok": true}` tras firma válida, para que Meta no reintente en
  bucle.
- No se aplica la agrupación de mensajes (#30) a WhatsApp: su buffer está
  tipado con IDs enteros de Telegram (ver supuesto S6).

## Envío (POST /send)

`send` ya elige `adapters.whatsapp` para `channel = "whatsapp"`. El único
cambio es en `domain.send_response`:

```python
capabilities_for = getattr(adapter, "capabilities_for", None)
capabilities = (
    capabilities_for(destination) if callable(capabilities_for) else adapter.capabilities()
)
```

Las excepciones de `WhatsAppCloudAdapter.send` son las existentes del gateway,
de modo que `POST /send` responde `422 validation_error`
(`ChannelWindowClosed`, `TemplateNotApproved`) o `502 upstream_error`
(`ChannelSendFailed`), que el orquestador ya traduce en `ChannelRejected` /
`ServiceUnavailable` (`orchestrator/adapters/gateway.py`).

Cuerpos de Meta (Graph API `/{phone_number_id}/messages`):

- Texto: `{"messaging_product":"whatsapp","recipient_type":"individual","to":D,"type":"text","text":{"body":T,"preview_url":false}}`.
- Plantilla: `{"messaging_product":"whatsapp","recipient_type":"individual","to":D,"type":"template","template":{"name":N,"language":{"code":L},"components":[{"type":"body","parameters":[{"type":"text","text":V}...]}]}}` (sin `components` si no hay variables).
- Botones: `{"messaging_product":"whatsapp","recipient_type":"individual","to":D,"type":"interactive","interactive":{"type":"button","body":{"text":B},"action":{"buttons":[{"type":"reply","reply":{"id":"<id>:<proof>","title":"<label>"}}...]}}}`.

## Excepciones

Se reutilizan `ChannelWindowClosed`, `TemplateNotApproved`, `ChannelSendFailed`
y `ChannelNotConfigured`. Nueva: `WebhookForbidden` (403, `forbidden`) solo
para la verificación GET. Los mensajes de excepción son genéricos en español
(p. ej. «Meta rechazó el envío.»); el detalle (estado HTTP, `code`,
`error_subcode`, `fbtrace_id`) va solo al log (R46). Errores 401/código 190
(token caducado) se registran como `whatsapp_auth_error` y se traducen a
`ChannelSendFailed`.

## Dependencias

Ninguna nueva. `httpx>=0.27,<1` (BSD-3) y `redis>=5,<7` (MIT) ya están en
`services/telegram_gateway/requirements.txt`; `hmac`/`hashlib`/`json` son de la
biblioteca estándar. No se copia código de terceros.

## Alternativas descartadas

1. **SDK de terceros (`pywa`, `heyoo`) o `requests`.** Añaden dependencias
   nuevas y ocultan el manejo de errores/firma que debemos probar; la API REST
   es pequeña y `httpx` ya está disponible.
2. **Confiar solo en la ventana calculada por el orquestador** y en el error
   131047 de Meta. Se descarta como única defensa porque #36 exige que el
   núcleo consulte la capacidad del adaptador antes de enviar texto libre y que
   la política falle cerrada; el almacén de ventana del gateway evita la
   llamada a Meta cuando la ventana está claramente cerrada. Se conserva la
   traducción de 131047 como respaldo.
3. **Validar la firma en el middleware HTTP.** Leer el cuerpo en un middleware
   de Starlette complica el reenvío del stream; se valida en el endpoint con
   `await request.body()`.
4. **Reenviar los estados de entrega al orquestador.** No existe contrato para
   ello y ninguna feature lo consume; crear uno es una feature de contrato
   propia. Se registran en log (R47).

## Supuestos a confirmar

- **S1 — Versión Graph API:** `WHATSAPP_GRAPH_API_VERSION=v21.0`
  configurable. El dueño ajusta la versión vigente al desplegar.
- **S2 — Idioma de plantilla:** `TemplateBlock` no lleva idioma en el contrato;
  se usa un idioma único `WHATSAPP_TEMPLATE_LANGUAGE=es`. Si se registran
  plantillas en varios idiomas, añadir `language` a `TemplateBlock` será una
  feature de contrato posterior.
- **S3 — Ventana ante fallo de Redis:** si el almacén de ventana no responde, se
  trata como abierta (R42), delegando en la comprobación del orquestador y en
  el error 131047 de Meta. Evita bloquear respuestas de asesores por una caída
  de infraestructura.
- **S4 — Reacciones:** `type = "reaction"` abre/renueva la ventana (Meta la
  cuenta como mensaje del usuario) pero no se reenvía al orquestador, para no
  responder «solo texto» a un emoji.
- **S5 — Sin reintentos automáticos:** el adaptador no reintenta envíos
  (incluidos 429/130429/131056) para no duplicar mensajes; los workers que ya
  tienen reintentos (#42) siguen gobernándolos.
- **S6 — Sin agrupación en WhatsApp:** los mensajes WhatsApp se reenvían uno a
  uno; extender la agrupación de #30 a IDs de texto queda fuera de alcance.
- **S7 — Estados desconocidos:** valores como `deleted` o `warning` se traducen
  a `"failed"`, igual que `FakeWhatsAppAdapter` y el adaptador Telegram, para
  respetar el vocabulario cerrado `DeliveryStatus`.
- **S8 — Coste de plantillas:** sigue como duda abierta de `docs/proyecto.md`
  §12; no afecta al código.
