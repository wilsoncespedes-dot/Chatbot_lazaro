# Design — #62 `webhook_generico_firmado`

## 1. Resumen

Sobre la arquitectura hexagonal de #61, el canal genérico es **un adaptador más**
del registry (`webhook_generico`) más una ruta pública de entrada. La firma y la
protección anti-SSRF son módulos puros y sin IO; el cliente HTTP del callback es
un puerto con versión falsa.

```
signature.py                  sign_payload / verify_signature (puro)
url_guard.py                  validate_callback_url + resolvedor (anti-SSRF)
adapters/callback.py          CallbackClient (Protocol), HttpCallbackClient, FakeCallbackClient
adapters/channels/webhook_generico.py   WebhookGenericoChannel (tipo "webhook_generico")
webhook_service.py            WebhookService.receive(...): orden 404 → 413 → 401 → 422 → dedup → entrega
channel_service.py            + resolve_for_webhook(channel_id) y validación de config al crear/editar
main.py                       ruta POST /webhooks/{canal_id}, sin lógica
```

Frontera con `docs/conventions.md`: código en inglés salvo los nombres del puerto
y el slug del tipo `webhook_generico` (nombre del encargo, como `whatsapp_cloud`).
`main.py`, `webhook_service.py` y `channel_service.py` no comparan con nombres de
canal concretos (la prueba de #61 R10 sigue vigente y se extiende a
`webhook_service.py`).

## 2. Archivos

Crear (rutas del gateway relativas a `services/telegram_gateway/`):

| Archivo | Contenido |
|---|---|
| `telegram_gateway/signature.py` | R3–R5 |
| `telegram_gateway/url_guard.py` | R41–R44, R48 |
| `telegram_gateway/adapters/callback.py` | R35–R39, R45 |
| `telegram_gateway/adapters/channels/webhook_generico.py` | R19, R31–R33, R35–R40, R46–R47 |
| `telegram_gateway/webhook_service.py` | R7–R30 |
| `tests/test_webhook_firma.py` | R3–R5 |
| `tests/test_webhook_ruta.py` | R6–R30 |
| `tests/test_webhook_canal.py` | R19, R31–R34, R35–R40, R46–R47 |
| `tests/test_webhook_ssrf.py` | R41–R45, R48 |
| `tests/test_webhook_config.py` | R49–R51 |
| `contracts/tests/test_webhook_generico_doc.py` | R1–R2 |

Modificar: `adapters/channels/__init__.py` (importa el módulo nuevo para
registrarlo), `domain.py` (excepciones y `Adapters.callback`), `channel_service.py`,
`main.py`, `config.py`, `.env.example`, `contracts/CONTRATOS.md` y los tests de §6.
`contracts/lazaro_contracts` no cambia: `LAZARO_TIMESTAMP_HEADER`,
`LAZARO_SIGNATURE_HEADER`, `DEFAULT_SIGNATURE_WINDOW_SECONDS` y `MessageResponse`
ya existen (#60). Sin dependencias nuevas (`httpx` ya está; `ipaddress`, `socket`,
`hmac` son de la biblioteca estándar).

## 3. Firmas nuevas

```python
# signature.py
def sign_payload(secret: str, timestamp: int | str, body: bytes) -> str
def verify_signature(secret: str, timestamp_header: str | None, signature_header: str | None,
                     body: bytes, now: datetime, window_seconds: int) -> bool

# url_guard.py
class CallbackUrlRejected(ValueError): ...
Resolver = Callable[[str], Sequence[str]]          # host -> direcciones IP como texto
def system_resolver(host: str) -> list[str]        # socket.getaddrinfo, solo IPs
def is_blocked_address(address: str) -> bool       # ipaddress; mapeadas IPv4-in-IPv6 incluidas
def validate_callback_url(url: str, resolver: Resolver, allow_private: bool = False) -> tuple[str, list[str]]
    # devuelve (host, direcciones validadas); lanza CallbackUrlRejected

# adapters/callback.py
class CallbackClient(Protocol):
    def post(self, url: str, body: bytes, headers: Mapping[str, str]) -> int   # código HTTP; lanza CallbackUrlRejected o CallbackNetworkError
class HttpCallbackClient:     # (timeout, allow_private=False, resolver=system_resolver, transport=None)
class FakeCallbackClient:     # (status=200, error=None); .requests: list[(url, body, headers)]

# domain.py (añadir)
class PayloadTooLarge(DomainError):       code = "payload_too_large"; status_code = 413
class WebhookUnauthorized(DomainError):   code = "unauthorized";      status_code = 401
class InvalidWebhookPayload(DomainError): code = "validation_error";  status_code = 422
class CallbackNetworkError(Exception): ...
Adapters.callback: "CallbackClient | None" = None      # al final, con default

# channel_service.py (añadir)
def resolve_for_webhook(self, channel_id: str) -> tuple[Canal, str]
    # (canal, secreto). Lanza ChannelNotFound uniforme (mismo mensaje) en: sin fila,
    # inactivo, tipo no registrado o no disponible, o sin secreto guardado.
    # Propaga ChannelStoreUnavailable y ChannelSecretsUnavailable (503).

# webhook_service.py
@dataclass(frozen=True)
class WebhookResult: status: Literal["accepted", "duplicate"]
class WebhookService:
    def __init__(self, channels: ChannelService, settings: Settings, adapters: Adapters) -> None
    def receive(self, channel_id: str, timestamp: str | None, signature: str | None, body: bytes) -> WebhookResult
```

`WebhookService.receive`: `resolve_for_webhook` (404) → `len(body)` > límite (413)
→ `verify_signature` (401 `WebhookUnauthorized`) → `json.loads` objeto (422) →
`canal.recibir_mensaje(payload)` (`None` → 422) → `channel` = `channel_id` y
`direction` = `inbound` (422) → `dedup.mark_message_if_new(channel_id,
external_message_id, ttl)` (fallo = nuevo, ERROR) → `orchestrator.post_message`
(`OrchestratorError`/`ValidationError` → ERROR `webhook_forward_failed
channel_id=… code=…`, sin reintento). La ruta es `def` síncrona de FastAPI (hilo
del pool) y recibe el cuerpo con `await request.body()` + `run_in_threadpool`,
como `/whatsapp/webhook`. Una comprobación previa de `Content-Length` > límite
evita leer cuerpos enormes pero se aplica **después** de resolver el canal (R14).

### Adaptador

```python
@CHANNEL_REGISTRY.register("webhook_generico")
class WebhookGenericoChannel:
    managed_by_environment = False
    def __init__(self, channel_id, callback_url: str | None, secret: str,
                 client: CallbackClient, clock) -> None
    # is_available -> True
    # build: record.config.get("callback_url"), secrets.secret (None -> ChannelNotConfigured),
    #        context.adapters.callback (None -> ChannelNotConfigured), context.adapters.clock
    # validate_config(config, context): hook opcional del registry
    def recibir_mensaje(payload) -> NormalizedMessage | None        # model_validate, inbound
    def identificar_usuario(payload) -> str | None                  # external_user_id si valida
    def capacidades(destino=None) -> ChannelCapabilities            # R32
    def enviar_mensaje(destino, bloques) -> DeliveryStatus
```

`enviar_mensaje` reutiliza `render_blocks` (puro, de `adapters/telegram.py`) para
obtener el texto, lo parte en trozos ≤ `MAX_TEXT_LENGTH`, y por trozo construye el
`NormalizedMessage` outbound, lo serializa **una vez** a bytes
(`model_dump_json(exclude_none=True)`), firma esos mismos bytes y llama a
`client.post`. `CallbackUrlRejected` → WARNING `callback_blocked channel_id=…` y
`failed`; `CallbackNetworkError` → WARNING con el tipo y `failed`; código no 2xx →
`failed`; todos 2xx → `sent`.

`validate_config` es un hook **opcional** (`getattr`) que `ChannelService.create`
y `.update` llaman si la fábrica lo define; lanza `InvalidChannelConfig`
(`DomainError`, 422 `validation_error`). Solo comprueba la sintaxis de la URL
(esquema, host, credenciales, longitud, modo de desarrollo); la resolución DNS
solo ocurre al enviar (la DNS puede cambiar entre el alta y el envío). El
registry no se modifica y Telegram y WhatsApp no definen el hook.

### Anti-SSRF

`HttpCallbackClient.post`: 1) `validate_callback_url` resuelve el host y
comprueba **todas** las direcciones; 2) se elige la primera y la petición
httpx se hace a `https://<ip>/<ruta>` con cabecera `Host: <host>` y
`extensions={"sni_hostname": host}` (la verificación del certificado sigue siendo
contra el nombre original), de modo que no hay segunda resolución ni
reenlace DNS (DNS rebinding); 3) `follow_redirects=False`; 4) timeout =
`http_timeout_seconds`. `is_blocked_address` usa `ipaddress`
(`is_private`, `is_loopback`, `is_link_local`, `is_unspecified`, `is_multicast`,
`is_reserved`, más `100.64.0.0/10` explícito y `ipv4_mapped`). En modo de
desarrollo se admiten `http` y direcciones bloqueadas.

### Configuración

`Settings`: `webhook_signature_window_seconds: int = Field(300, ge=1, le=3600)`,
`webhook_max_body_bytes: int = Field(1_048_576, ge=1024, le=10_485_760)`,
`webhook_allow_private_callbacks: bool = False`; un `model_validator` lanza
`ProductionConfigError(["WEBHOOK_ALLOW_PRIVATE_CALLBACKS"])` en producción si es
`true`. `build_default_adapters` añade
`callback=HttpCallbackClient(settings.http_timeout_seconds, settings.webhook_allow_private_callbacks)`;
`create_app` usa `FakeCallbackClient()` si `adapters.callback` es `None`.
`main.py` añade `"/webhooks/"` como prefijo público en el middleware
(`request.url.path.startswith("/webhooks/")`) y la ruta
`POST /webhooks/{canal_id}` → `WebhookService.receive`, que responde
`MessageResponse(status=…)`.

## 4. Precedencia de errores

`POST /webhooks/{canal_id}`: almacén o secretos (503) → 404 uniforme → 413 → 401
(firma o ventana) → 422 (JSON, adaptador, `channel`, `direction`) → dedup →
entrega. El 503 antecede al 404 porque sin almacén no se puede saber si el canal
existe. Un canal sin secreto (`telegram`, `whatsapp`) responde 404: sus webhooks
propios siguen siendo `/telegram/webhook` y `/whatsapp/webhook`.

`POST /send` por un canal genérico: sin cambios respecto a #61 (422
`channel_inactive`, 502 si el adaptador no está disponible); un callback fallido o
bloqueado devuelve `failed` y la ruta lo convierte en `502 upstream_error`
(`ChannelSendFailed` existente). Sin `callback_url`: `ChannelNotConfigured` (502).

## 5. Alternativas descartadas

1. **Entregar al orquestador en segundo plano (`BackgroundTasks`) y responder
   antes**: se perdería el mensaje con el proceso reiniciado y el emisor creería
   que se aceptó. `POST /messages` del orquestador ya responde `202` sin esperar
   al bot, así que la llamada síncrona es rápida; la cola durable llega en #64.
2. **Validar la URL de callback solo al guardarla**: la DNS puede cambiar
   después (rebinding). Se valida sintaxis al guardar y se resuelve y fija la IP
   en cada envío.
3. **Comprobar la IP y luego dejar que httpx vuelva a resolver el nombre**:
   ventana de DNS rebinding; se conecta a la IP ya validada con `Host`/SNI
   originales.
4. **Una ruta propia por tipo de canal (`/webhooks/{tipo}/{id}`)**: el contrato
   de #60 fija `POST /webhooks/{canal_id}` y el comportamiento por tipo vive en
   `recibir_mensaje`.
5. **Devolver 401 cuando falta el secreto/canal inactivo**: revelaría qué canales
   existen; el acceptance exige 404 uniforme.
6. **Reintentar el reenvío al orquestador en el gateway**: duplicaría la
   responsabilidad de #64 y chocaría con la guarda temporal (422 definitivo).

## 6. Tests existentes sustituidos

Fijan que `webhook_generico` no existe; se sustituyen por la versión nueva (no se
debilitan) y se listan en `progress/impl_webhook_generico_firmado.md`:

| Test | Motivo | Sustituto |
|---|---|---|
| `tests/test_registro_canales.py::test_default_registry_contains_only_environment_managed_adapters` | espera `("telegram", "whatsapp_cloud")` y `creatable_types() == ()` | espera además `webhook_generico` y `creatable_types() == ("webhook_generico",)` (R31) |
| `tests/test_canales_rutas.py` (afirmación `body["adapter_types"] == ["simulado"]`) | el registry copiado ya incluye `webhook_generico` | `== ["webhook_generico", "simulado"]` |
| `contracts/tests/test_canal_abierto_doc.py` (aserciones sobre «hasta #62 / se implementa en #62») | solo si alguna exige esas frases | se reemplazan por las frases de R1 conservando las demás (`DEFAULT_SIGNATURE_WINDOW_SECONDS`, `config.callback_url`) |

Si `./init.sh` revela otro test que dependa de la lista de tipos o del texto
«no existen», se trata igual y se anota. Los S5 de #61 («`POST /channels` responde
422 en producción») deja de cumplirse: ahora `webhook_generico` es creable.

## 7. Supuestos a confirmar (defaults seguros y editables)

- **S1** Ventana 300 s (`WEBHOOK_SIGNATURE_WINDOW_SECONDS`), límite de cuerpo 1 MiB
  (`WEBHOOK_MAX_BODY_BYTES`): configurables.
- **S2** Un fallo del orquestador tras aceptar el mensaje no se reintenta y el
  emisor recibe `200 accepted` (lo pide el acceptance); el mensaje queda sin
  procesar hasta la cola de #64. Está registrado en logs (`webhook_forward_failed`).
- **S3** El tipo se llama `webhook_generico` (nombre del encargo) y el callback
  es opcional: un canal sin `callback_url` recibe pero no responde (502).
- **S4** `WEBHOOK_ALLOW_PRIVATE_CALLBACKS` solo en desarrollo; en producción
  impide arrancar.
- **S5** Sin allowlist de dominios de callback: el bloqueo por dirección cubre el
  riesgo SSRF; una allowlist por canal puede añadirla #66.
- **S6** Entrega del callback al menos una vez sin reintentos propios (los
  reintentos con backoff son de #64 con el outbox).
