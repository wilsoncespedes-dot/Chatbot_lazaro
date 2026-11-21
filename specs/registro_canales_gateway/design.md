# Design — #61 `registro_canales_gateway`

## 1. Resumen

Hexagonal dentro de `services/telegram_gateway/telegram_gateway/` (nombre del
servicio y rutas `/telegram/webhook` y `/whatsapp/webhook` sin cambios):

```
ports/canal.py              puerto Canal (Protocol, métodos en español por decisión)
registry.py                 ChannelRegistry + CHANNEL_REGISTRY + ChannelContext
adapters/channels/          un módulo por canal que implementa Canal y se registra
  telegram.py               TelegramChannel   (tipo "telegram")
  whatsapp_cloud.py         WhatsAppCloudChannel (tipo "whatsapp_cloud")
adapters/channel_repository.py  ChannelRepository / PostgresChannelRepository / FakeChannelRepository
secret_cipher.py            SecretCipher (Fernet)
channel_service.py          ChannelService: siembra, resolución y administración
domain.py                   entidades, excepciones y degradación (puro)
main.py                     rutas HTTP (sin lógica)
```

Frontera con `docs/conventions.md` (código en inglés): el puerto conserva el
nombre `Canal` y los métodos `recibir_mensaje`, `enviar_mensaje`,
`identificar_usuario` y `capacidades` (acceptance y decisión del leader); el
resto del código y el JSON de las rutas siguen en inglés, igual que el contrato
de #60. Las columnas de la tabla son las del acceptance (español); la
equivalencia JSON ↔ columna se documenta en `CONTRATOS.md`.

Los clientes de protocolo actuales **no se mueven**: `adapters/telegram.py`
(`HttpTelegramClient`, `FakeTelegramClient`, `render_blocks`,
`build_inline_keyboard`, `TelegramChannelAdapter`), `adapters/whatsapp.py`
(`ChannelAdapter`, `FakeWhatsAppAdapter`), `adapters/whatsapp_cloud.py`
(`WhatsAppCloudAdapter`) y `whatsapp_cloud.py` quedan donde están y los
adaptadores del puerto los componen. Así ningún import ni `monkeypatch` de la
batería actual cambia y no hacen falta módulos de reexportación.

## 2. Archivos

Crear:

| Archivo | Contenido |
|---|---|
| `contracts/lazaro_contracts/channel_registry.py` | modelos y constantes de R1–R2 |
| `contracts/tests/test_registro_canales_contrato.py` | R1–R4 |
| `telegram_gateway/ports/__init__.py`, `ports/canal.py` | puerto `Canal` |
| `telegram_gateway/registry.py` | registry, contexto, errores del registry |
| `telegram_gateway/adapters/channels/__init__.py` | importa `telegram` y `whatsapp_cloud` (registro por import) |
| `telegram_gateway/adapters/channels/telegram.py`, `whatsapp_cloud.py` | adaptadores del puerto |
| `telegram_gateway/adapters/channel_repository.py` | repositorio Postgres y falso |
| `telegram_gateway/secret_cipher.py` | cifrado |
| `telegram_gateway/channel_service.py` | servicio |
| `tests/test_registro_canales.py` | R5–R15 |
| `tests/test_degradacion.py` | R16–R21 |
| `tests/test_canales_repositorio.py` | R27–R31 (SQL con conexión falsa, como `handover/tests/test_repository.py`) |
| `tests/test_canales_secretos.py` | R33–R37 |
| `tests/test_canales_rutas.py` | R22–R26, R32, R38–R50 |
| `tests/test_canales_despliegue.py` | R51–R54 |

Modificar: `contracts/lazaro_contracts/__init__.py` (exports),
`contracts/lazaro_contracts/channels.py` (extrae `check_json_object`),
`contracts/CONTRATOS.md`, `telegram_gateway/domain.py`, `main.py`, `config.py`,
`adapters/telegram.py` y `whatsapp_cloud.py` (capacidades explícitas, R11),
`services/telegram_gateway/requirements.txt`, `.env.example`,
`docker-compose.yml`, `render.yaml` y los cuatro tests de §7. El `Dockerfile` no
cambia (copia el paquete completo).

## 3. Firmas nuevas

### Contrato (`lazaro_contracts/channel_registry.py`)

Constantes: `MAX_CHANNEL_NAME_LENGTH = 60`, `MAX_CHANNEL_ICON_LENGTH = 32`,
`CHANNEL_COLOR_PATTERN = r"^#[0-9A-Fa-f]{6}$"`, `MAX_CHANNEL_CONFIG_BYTES = 4096`,
`MAX_CHANNEL_CONFIG_DEPTH = 5`, `MAX_CHANNEL_CREDENTIALS = 20`,
`CREDENTIAL_NAME_PATTERN = r"^[a-z][a-z0-9_]{0,63}$"`,
`MAX_CREDENTIAL_VALUE_LENGTH = 4096`, `CHANNEL_SECRET_PATTERN = r"^[A-Za-z0-9_-]{43}$"`.
`config` reutiliza el cálculo de tamaño y profundidad de `metadata` (#60): se
extrae a una función pública `check_json_object(value, max_bytes, max_depth)` en
`channels.py` sin cambiar su comportamiento.

| Modelo | Campos |
|---|---|
| `ChannelInfo` | `id: Channel`, `name`, `adapter_type: Channel`, `icon`, `color`, `config: dict[str, JsonValue]`, `active: bool`, `configured: bool`, `has_secrets: bool`, `managed_by_environment: bool`, `created_at: AwareDatetime` |
| `ChannelListResponse` | `channels: list[ChannelInfo]`, `adapter_types: list[Channel]` |
| `ChannelCreateRequest` | `id`, `name`, `adapter_type`, `icon`, `color`, `config = {}`, `credentials: dict[CredentialName, CredentialValue] = {}`, `active: StrictBool = True` |
| `ChannelCreateResponse` | `channel: ChannelInfo`, `secret: ChannelSecret` |
| `ChannelUpdateRequest` | `name`, `icon`, `color`, `config`, `credentials`, todos opcionales; al menos uno |
| `ChannelActiveRequest` | `active: StrictBool` |
| `ChannelSecretResponse` | `channel_id: Channel`, `secret: ChannelSecret` |

Equivalencia con la tabla: `name`↔`nombre`, `adapter_type`↔`tipo_adaptador`,
`icon`↔`icono`, `active`↔`activo`, `created_at`↔`creado_en`; `credentials` y
`secret` ↔ `config_secreta` (cifrado).

### Rutas (`main.py`, todas con `X-Service-Token` por el middleware actual)

| Ruta | Éxito | Errores propios |
|---|---|---|
| `GET /channels` | 200 `ChannelListResponse` | 503 `channel_store_unavailable` |
| `POST /channels` | 201 `ChannelCreateResponse` | 409 `channel_exists`, 422, 503 (`channel_secrets_unavailable`, `channel_store_unavailable`) |
| `PATCH /channels/{channel_id}` | 200 `ChannelInfo` | 404, 409 `channel_managed_by_environment`, 503 |
| `PATCH /channels/{channel_id}/active` | 200 `ChannelInfo` | 404, 503 |
| `POST /channels/{channel_id}/secret` (regenerar) | 200 `ChannelSecretResponse` | 404, 409, 503 |
| `GET /channels/{channel_id}/secret` (revelar) | 200 `ChannelSecretResponse` | 404, 409, 503 |

`PATCH …/active` sigue el precedente de `PATCH /chunks/{id}/active`.

### Gateway

```python
# ports/canal.py
@runtime_checkable
class Canal(Protocol):
    def recibir_mensaje(self, payload: Mapping[str, Any]) -> NormalizedMessage | None: ...
    def enviar_mensaje(self, destino: str, bloques: Sequence[ResponseBlock]) -> DeliveryStatus: ...
    def identificar_usuario(self, payload: Mapping[str, Any]) -> str | None: ...
    def capacidades(self, destino: str | None = None) -> ChannelCapabilities: ...

# registry.py
@dataclass(frozen=True)
class ChannelContext:
    settings: Settings
    adapters: Adapters          # telegram, whatsapp, clock

class ChannelFactory(Protocol):  # lo que guarda el registry: una clase que implementa Canal
    managed_by_environment: ClassVar[bool]
    @classmethod
    def is_available(cls, context: ChannelContext) -> bool: ...
    @classmethod
    def build(cls, record: ChannelRecord, context: ChannelContext,
              secrets: ChannelSecrets | None) -> Canal: ...

class DuplicateAdapterType(ValueError): ...
class UnknownAdapterType(DomainError): code = "validation_error"; status_code = 422

class ChannelRegistry:
    def register(self, adapter_type: str) -> Callable[[type[T]], type[T]]   # decorador
    def get(self, adapter_type: str) -> type[ChannelFactory]
    def adapter_types(self) -> tuple[str, ...]
    def creatable_types(self) -> tuple[str, ...]     # managed_by_environment = False
    def copy(self) -> "ChannelRegistry"               # pruebas: añadir un tipo falso sin tocar el global

CHANNEL_REGISTRY = ChannelRegistry()
```

`register` valida que el tipo sea un slug de canal (si no, `ValueError`) y que no
esté repetido (`DuplicateAdapterType`). Las pruebas registran un tipo falso no
gestionado por el entorno en `CHANNEL_REGISTRY.copy()` y lo inyectan por
`Adapters.channel_registry`; no se añade ningún tipo creable en producción (eso
llega con #62/#63).

```python
# adapters/channels/telegram.py
@CHANNEL_REGISTRY.register("telegram")
class TelegramChannel:
    managed_by_environment = True
    def __init__(self, client: TelegramClient, clock: Callable[[], datetime]) -> None
    # is_available -> True; build -> TelegramChannel(context.adapters.telegram, context.adapters.clock)

# adapters/channels/whatsapp_cloud.py
@CHANNEL_REGISTRY.register("whatsapp_cloud")
class WhatsAppCloudChannel:
    managed_by_environment = True
    def __init__(self, client: ChannelAdapter, clock: Callable[[], datetime]) -> None
    # is_available -> context.adapters.whatsapp is not None
    # capacidades(destino): client.capabilities_for(destino) si existe y hay destino; si no, client.capabilities()
```

`recibir_mensaje` de Telegram exige `update_id` entero y reutiliza
`extract_callback`/`normalize_callback` y `extract_incoming`/`normalize_incoming`
(captura `ValidationError` → `None`); el de WhatsApp recibe un objeto `message`
de Meta y usa `normalize_message`. Los webhooks heredados conservan su flujo
(R15) y no llaman al puerto (§8).

```python
# domain.py (puro)
@dataclass(frozen=True)
class ChannelRecord:            # fila sin secretos
    id: str; name: str; adapter_type: str; icon: str; color: str
    config: Mapping[str, Any]; active: bool; created_at: datetime
    has_secrets: bool; active_follows_environment: bool

@dataclass(frozen=True)
class ChannelSecrets:           # repr sin valores
    secret: str | None = field(default=None, repr=False)
    credentials: Mapping[str, str] = field(default_factory=dict, repr=False)

@dataclass(frozen=True)
class ChannelSeed: id: str; name: str; adapter_type: str; icon: str; color: str
BUILTIN_CHANNEL_SEEDS: tuple[ChannelSeed, ...]   # telegram, whatsapp (R29)

def degrade_blocks(blocks: Sequence[ResponseBlock], capabilities: ChannelCapabilities) -> list[ResponseBlock]
def prepare_blocks(blocks, capabilities) -> list[ResponseBlock]     # degrade + ChannelWindowClosed (lógica actual)
def send_response(adapter, destination, blocks) -> DeliveryStatus   # firma intacta; usa prepare_blocks
def send_through_channel(channel: Canal, destination: str, blocks) -> DeliveryStatus

@dataclass
class Adapters:                 # se añaden al final, con default: no rompe construcciones posicionales
    ...
    channels: "ChannelRepository | None" = None
    channel_registry: "ChannelRegistry | None" = None
```

```python
# adapters/channel_repository.py
@dataclass(frozen=True)
class ChannelChanges:
    name: str | None = None; icon: str | None = None; color: str | None = None
    config: Mapping[str, Any] | None = None; encrypted_secrets: str | None = None

class ChannelRepository(Protocol):
    def health_check(self, timeout_seconds: float) -> None
    def seed(self, rows: Sequence[tuple[ChannelSeed, bool]]) -> None   # (semilla, disponible)
    def list_channels(self) -> list[ChannelRecord]
    def get(self, channel_id: str) -> ChannelRecord | None
    def get_encrypted_secrets(self, channel_id: str) -> str | None
    def create(self, record: ChannelRecord, encrypted_secrets: str | None) -> bool   # False si el id existe
    def update(self, channel_id: str, changes: ChannelChanges) -> ChannelRecord | None
    def set_active(self, channel_id: str, active: bool) -> ChannelRecord | None   # y activo_segun_entorno=false
    def set_encrypted_secrets(self, channel_id: str, token: str) -> bool

class PostgresChannelRepository:   # (database_url, connect=None, connect_health=None)
class FakeChannelRepository:       # (fail=False, health_ok=True, health_error=None, clock=...)
```

`PostgresChannelRepository` replica el patrón de
`handover/adapters/repository.py` (sin importarlo): conexión perezosa con
`pg8000.dbapi` importado dentro de `_pg_connect`, esquema en la primera
conexión, `threading.Lock`, `is_connection_error` + descarte, sondeo
`SELECT 1` tras `IDLE_PROBE_SECONDS = 10` sin uso (reconexión del 2026-11-16) y
`health_check` en conexión independiente con timeout. Ninguna consulta de
`list_channels`/`get` selecciona `config_secreta` (solo
`config_secreta IS NOT NULL AS has_secrets`).

```python
# secret_cipher.py
class SecretCipher:
    def __init__(self, key: str) -> None          # nunca lanza; clave mala = no disponible
    status: Literal["ok", "missing", "invalid"]
    available: bool
    def encrypt(self, secrets: ChannelSecrets) -> str     # ChannelSecretsUnavailable si no hay clave
    def decrypt(self, token: str) -> ChannelSecrets       # ChannelSecretsUnavailable si no hay clave o InvalidToken
    # __repr__ -> "SecretCipher(status='ok')"

# channel_service.py
class ChannelService:
    def __init__(self, repository: ChannelRepository, registry: ChannelRegistry,
                 cipher: SecretCipher, context: ChannelContext,
                 seeds: Sequence[ChannelSeed] = BUILTIN_CHANNEL_SEEDS,
                 new_secret: Callable[[], str] = lambda: secrets.token_urlsafe(32)) -> None
    def ensure_seeded(self) -> None          # idempotente, con lock; marca hecho solo si tuvo éxito
    def list_channels(self) -> ChannelListResponse
    def resolve(self, channel_id: str) -> Canal
    def create(self, request: ChannelCreateRequest) -> ChannelCreateResponse
    def update(self, channel_id: str, request: ChannelUpdateRequest) -> ChannelInfo
    def set_active(self, channel_id: str, active: bool) -> ChannelInfo
    def regenerate_secret(self, channel_id: str) -> ChannelSecretResponse
    def reveal_secret(self, channel_id: str) -> ChannelSecretResponse
```

Todo método público llama primero a `ensure_seeded()` y convierte cualquier
excepción del repositorio que no sea `DomainError` en `ChannelStoreUnavailable`
(log ERROR `channel_store_error code=<TipoExcepción>`).

`main.py`: importa `telegram_gateway.adapters.channels` (registra los tipos);
`build_default_adapters` añade `channels=PostgresChannelRepository(settings.database_url)`;
`create_app` usa `adapters.channels or FakeChannelRepository()` y
`adapters.channel_registry or CHANNEL_REGISTRY`, crea `SecretCipher`, emite el
WARNING de R36, intenta `ensure_seeded()` en el `lifespan` (fallo → WARNING
`channels_seed_deferred` y sigue, R32), añade Postgres a `/health` (secuencial
tras Redis; peor caso 2 × timeout) y las rutas de §3. `POST /send` usa
`LEGACY_SEND_CHANNEL = "telegram"` para `SendRequest` y
`send_through_channel(service.resolve(channel), …)`; desaparecen las ramas
`telegram`/`whatsapp`.

## 4. Precedencia de errores

`POST /send`: almacén (503 `channel_store_unavailable`) → sin fila (422
`validation_error`) → tipo no registrado o adaptador no disponible (502
`upstream_error`) → inactivo (422 `channel_inactive`) → secretos guardados
ilegibles (503 `channel_secrets_unavailable`) → ventana/plantilla (422) → envío
(502). «No disponible» precede a «inactivo» para que WhatsApp con
`WHATSAPP_ENABLED=false` siga respondiendo `502` como hoy
(`test_whatsapp_config.py`, `test_multicanal.py`).

`POST /channels`: 422 (cuerpo, tipo desconocido o gestionado por el entorno) →
409 (`get` encuentra el id) → 503 (clave) → `create` devuelve `False` por carrera
→ 409. Rutas con `{channel_id}`: 404 → 409 (gestionado por el entorno, solo
operaciones de secretos) → 503 (clave). Regenerar con un token guardado que no se
descifra responde 503 y no destruye las credenciales.

## 5. Tabla, migración y siembra

```sql
CREATE TABLE IF NOT EXISTS canales (
  id TEXT PRIMARY KEY, nombre TEXT NOT NULL, tipo_adaptador TEXT NOT NULL,
  icono TEXT NOT NULL, color TEXT NOT NULL, config JSONB NOT NULL DEFAULT '{}'::jsonb,
  activo BOOLEAN NOT NULL DEFAULT TRUE, creado_en TIMESTAMPTZ NOT NULL DEFAULT now());
ALTER TABLE canales ADD COLUMN IF NOT EXISTS config_secreta TEXT NULL;
ALTER TABLE canales ADD COLUMN IF NOT EXISTS activo_segun_entorno BOOLEAN NOT NULL DEFAULT FALSE;
```

`config_secreta` es la parte secreta de `config`, guardada aparte y cifrada:
`config` queda solo con ajustes públicos y el listado nunca puede filtrar el
token. Siembra, en una transacción por llamada:

```sql
INSERT INTO canales (id, nombre, tipo_adaptador, icono, color, config, activo, activo_segun_entorno)
VALUES (%s, %s, %s, %s, %s, CAST(%s AS JSONB), %s, TRUE) ON CONFLICT (id) DO NOTHING;
UPDATE canales SET activo = %s WHERE id = %s AND activo_segun_entorno AND activo IS DISTINCT FROM %s;
```

Es idempotente y segura con varias instancias. Las credenciales de Telegram y
WhatsApp **no se copian** a la base: los adaptadores siguen leyendo
`TELEGRAM_*` y `WHATSAPP_*` desde `Settings`/`Adapters`, así que el despliegue no
necesita la clave nueva. `activo_segun_entorno` hace que la fila siga a
`WHATSAPP_ENABLED` hasta que alguien cambie `activo` por la API (R30, R45).

## 6. Secretos y clave

- **Fernet** (`cryptography.fernet`): AES-128-CBC + HMAC-SHA256 con IV
  aleatorio, formato de token versionado y API de alto nivel; la clave es una
  cadena estándar de 44 caracteres (`Fernet.generate_key()`) y `MultiFernet`
  permite rotar más adelante sin cambiar el formato guardado.
- Se cifra `json.dumps({"secret": ..., "credentials": {...}})`; el secreto de
  canal se genera con `secrets.token_urlsafe(32)`. En #62 la clave HMAC será el
  UTF-8 de ese texto.
- **Sin clave o con clave inválida** el servicio arranca siempre (R34): la
  validación de formato la hace `SecretCipher`, no `Settings`, para que un valor
  mal pegado no tumbe Telegram. Solo fallan cerrado (503) las operaciones de
  R35; editar campos públicos y activar no necesitan clave.
- **Producción** (`lazaro_contracts/production.py`): `CHANNEL_SECRETS_KEY` **no**
  entra en `REQUIRED_IN_PRODUCTION`. El servidor de AWS se actualiza solo y su
  `.env` lo sube el dueño a mano: exigirla haría que el gateway no arrancara
  (Telegram caído) hasta subir el `.env`, aunque ningún canal sembrado la usa. Se
  vuelve necesaria cuando existan canales con secretos (#62/#63/#66), y entonces
  la falta se ve en el WARNING de arranque y en el 503 de la operación.
  Tampoco se añade `DATABASE_URL`: un DSN ausente o mal escrito no debe impedir
  que los webhooks entrantes (que no usan Postgres) sigan atendiendo; se ve como
  `postgres: unavailable` en `/health`, y el mismo `DATABASE_URL` del `.env`
  compartido ya lo validan en producción orchestrator, rag y handover. Así
  `test_production_config.py` no cambia.
- Logs permitidos: `channel_secrets_key_unavailable reason=…`,
  `channel_secret_regenerated channel_id=…`, `channel_secret_revealed channel_id=…`,
  `channel_store_error code=…`, `channels_seed_deferred code=…`,
  `healthcheck_postgres_unavailable code=…`. Nunca valores, tokens, DSN ni la
  clave (`Settings.channel_secrets_key` es `SecretStr`). La auditoría por persona
  (quién vio o regeneró) la añade el panel en #66.

## 7. Tests existentes sustituidos

Fijan comportamiento que el acceptance de #61 reemplaza; se sustituyen por
pruebas del comportamiento nuevo (no se debilitan) y se listan en
`progress/impl_registro_canales_gateway.md`. Ningún otro test existente se toca.

| Test | Motivo | Sustituto |
|---|---|---|
| `services/telegram_gateway/tests/test_canal_abierto.py::test_send_image_block_is_rejected_on_current_channels` | R40 de #60 era temporal («hasta que #61 la degrade») | mismo archivo y parametrización: 200 y el enlace llega al canal (R21) |
| `…/test_canal_abierto.py::test_send_response_rejects_image_without_capability` | idem | `send_response` entrega un `LinkBlock` (R18, R21) |
| `…/test_telegram_gateway_app.py::test_requirements_txt_matches_design` | lista exacta de 6 dependencias; el dueño decidió `pg8000` y `cryptography` | lista de 8 (R52) |
| `contracts/tests/test_canal_abierto_doc.py::test_send_and_messages_document_temporary_rejections` | exige el texto temporal de `/send` («no es `telegram` ni `whatsapp`», rechazo de `image`) | la parte de `/send` comprueba el texto de R4; la parte de `POST /messages` se conserva literal (la guarda sigue hasta #65) |

`UnsupportedBlock` se conserva en `domain.py` (ya no se lanza) para no romper
imports.

## 8. Alternativas descartadas

1. **AES-GCM** en vez de Fernet: exige gestionar nonces y definir un formato
   propio; el beneficio (AES-256, datos asociados) no compensa el riesgo de mal
   uso en un equipo principiante.
2. **Copiar `TELEGRAM_*`/`WHATSAPP_*` a `canales.config` al sembrar**: obligaría a
   tener la clave en el primer despliegue y duplicaría secretos que hoy se rotan
   en un solo sitio.
3. **Exigir `CHANNEL_SECRETS_KEY` en producción**: ver §6.
4. **Mover los clientes a `adapters/channels/` con módulos que reexporten**: dos
   rutas de import para los mismos objetos y riesgo con los `monkeypatch` por
   ruta de módulo, sin ganancia funcional.
5. **Reescribir `/telegram/webhook` y `/whatsapp/webhook` sobre el puerto**: su
   lógica de protocolo (confirmar callbacks, agrupación, payload legacy
   `MessageRequest`, verificación de suscripción, lotes y estados de Meta) no
   cabe en `recibir_mensaje` y el acceptance exige respuestas idénticas; el
   puerto reutiliza las mismas funciones puras y una prueba demuestra la
   equivalencia (R12). La primera ruta que llama a `recibir_mensaje` es la de #62.
6. **Secretos dentro de `config` con una clave reservada**: el listado tendría que
   filtrarla y la API validar el nombre reservado; una columna aparte lo hace
   imposible por construcción.
7. **Siembra solo «si no existe»**: activar WhatsApp después exigiría una llamada
   manual a la API; `activo_segun_entorno` lo evita.

## 9. Dependencias

| Paquete | Cota | Licencia | Notas |
|---|---|---|---|
| `cryptography` | `>=44,<48` | Apache-2.0 OR BSD-3-Clause | trae `cffi` (MIT) y `pycparser` (BSD); en `.venv` ya está la 47.0.0 |
| `pg8000` | `>=1.31,<2` (misma cota que orchestrator, rag y handover) | BSD-3-Clause | trae `scramp` (MIT), `asn1crypto` (MIT), `python-dateutil` (Apache-2.0/BSD); en `.venv` ya está la 1.31.6 |

No hay que instalar nada nuevo en el `.venv`.

## 10. Supuestos a confirmar (defaults seguros y editables)

- **S1** Valores visuales sembrados: «Telegram» `#1B6FA8` y «WhatsApp»
  `#0E7A5F` (contraste ≥ 4.5:1 con texto blanco), íconos `telegram` y `whatsapp`;
  editables por `PATCH /channels/{id}` y por el panel en #66.
- **S2** Un canal inactivo responde `422 channel_inactive`: rechazo definitivo
  (el orquestador lo trata como `ChannelRejected` y #64 no lo reintenta).
- **S3** Las filas sembradas siguen la disponibilidad del entorno hasta el primer
  `PATCH …/active`.
- **S4** Desactivar `telegram` o `whatsapp` en #61 solo corta la salida; que sus
  webhooks heredados respondan 404 lo decide #66.
- **S5** En producción, hasta #62/#63 `POST /channels` responde 422 porque no hay
  tipos creables registrados.
- **S6** Sin rotación de clave en #61; cambiar `CHANNEL_SECRETS_KEY` deja ilegibles
  los secretos guardados (503 al usarlos).

## 11. Acción del dueño en el servidor

Opcional para este despliegue: añadir al `.env` del servidor
`CHANNEL_SECRETS_KEY=<python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())">`.
Sin ella, Telegram y WhatsApp funcionan igual, el arranque registra
`channel_secrets_key_unavailable reason=missing` y solo crear canales o
ver/regenerar secretos responde 503. `DATABASE_URL` ya está en el `.env`
compartido; con `depends_on` el gateway espera a que `postgres` esté sano.
