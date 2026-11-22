# Design — #65 `nucleo_sin_nombres_canal`

## 1. Resumen

El orquestador deja de decidir por nombre de canal. Lo que antes era
`channel == "whatsapp"` pasa a ser «el canal informa capacidades de canal con
ventana» y `channel in TEXT_CONSENT_CHANNELS` pasa a ser «`config.consent_mode`».
Los metadatos llegan por HTTP desde el gateway (`GET /channels`, ya existente en
#61); el orquestador nunca lee `canales` (`docs/architecture.md` §3, principio 1).

```
gateway  GET /channels  ->  ChannelInfo(+capabilities, config.consent_mode)
orchestrator  adapters/channels.py   ChannelDirectory (HTTP + TTL) / FakeChannelDirectory
orchestrator  channels.py            ChannelPolicy, política derivada (puro)
orchestrator  legacy.py              única capa con los nombres «telegram»/«whatsapp»
```

Derivación (puro, `channels.py`):

- `windowed = capabilities is not None and not free_text_allowed and requires_template`
- `consent_mode = config.get("consent_mode")` si es `texto`/`boton`, si no `texto`.

`whatsapp_window_hours` y `settings.whatsapp_window_hours` conservan el nombre
(es configuración desplegada); su doc pasa a «horas de ventana de los canales con
ventana». No se renombra para no tocar `.env` de producción.

## 2. Archivos

Crear:

| Archivo | Contenido |
|---|---|
| `services/orchestrator/orchestrator/channels.py` | `ChannelPolicy`, `policy_from_info`, `DEFAULT_CONSENT_MODE`, `is_windowed`, `consent_mode` (puro, sin IO) |
| `services/orchestrator/orchestrator/legacy.py` | `LEGACY_CHANNEL = "telegram"`, `legacy_from_normalized`, `legacy_chat_id` (capa legacy) |
| `services/orchestrator/orchestrator/adapters/channels.py` | `ChannelDirectory` (Protocol), `HttpChannelDirectory`, `FakeChannelDirectory` |
| `services/orchestrator/tests/test_nucleo_sin_nombres.py` | R36–R37 |
| `services/orchestrator/tests/test_directorio_canales.py` | R10–R18 |
| `services/orchestrator/tests/test_ventana_por_capacidades.py` | R19–R21 |
| `services/orchestrator/tests/test_consentimiento_por_ajuste.py` | R22–R25 |
| `services/orchestrator/tests/test_canal_id_migracion.py` | R31–R35 |
| `services/orchestrator/tests/test_nucleo_canal_nuevo.py` | R26–R30, R38–R42 |
| `contracts/tests/test_capacidades_canal_info.py` | R1, R5, R9 |
| `services/telegram_gateway/tests/test_canales_capacidades.py` | R2–R4, R6–R8 |

Modificar:

- `contracts/lazaro_contracts/channel_registry.py`: `ChannelInfo.capabilities`,
  validación de `consent_mode` en `config`; `__init__.py` exporta
  `CONSENT_MODES`, `DEFAULT_CONSENT_MODE`; `contracts/CONTRATOS.md`.
- Gateway: `registry.py` (`ChannelFactory.default_capabilities`), cada módulo de
  `adapters/channels/` (`telegram.py`, `whatsapp_cloud.py`, `simulado.py`,
  `webhook_generico.py`), `channel_service.py::_info`, `domain.py` (`ChannelSeed.config`
  y semillas), `adapters/channel_repository.py` (siembra de `consent_mode`).
- Orquestador: `domain.py` (todas las comparaciones por nombre, `Adapters.channels`,
  `ATTENDED_CHANNELS`/`INBOX_CHANNELS` fuera), `panel.py::channel_window`,
  `privacy.py` (`TEXT_CONSENT_CHANNELS` fuera), `advisor_panel.py` (opciones del
  filtro), `main.py`, `queue.py`, `adapters/outbox.py`, `adapters/gateway.py`
  (`FakeGatewayClient`), `adapters/repository.py` (`canal_id`, migración, literales),
  `config.py` (`channel_directory_ttl_seconds`), `.env.example`.
- `services/orchestrator/tests/fakes.py` y `tests/conftest.py`: `default_channel_infos()`
  y el fixture `autouse` que puebla `FakeChannelDirectory.default_infos` (único
  lugar con `ChannelInfo` de telegram/whatsapp/simulado para pruebas).
- Tests existentes: solo se tocan los que importan lo retirado
  (`ATTENDED_CHANNELS`, `INBOX_CHANNELS`, `TEXT_CONSENT_CHANNELS`,
  `channel_window(channel, …)`, `consent_text_pending(message, settings)`) y los
  que asertan el rechazo `422` de un canal desconocido en `POST /messages`
  (p. ej. `test_canal_abierto.py` del orquestador, y el texto temporal de
  `contracts/tests/test_canal_abierto_doc.py` y `CONTRATOS.md`). Se adaptan sin
  debilitar el aserto de comportamiento y se listan en
  `progress/impl_nucleo_sin_nombres_canal.md`. Ningún otro se toca.

## 3. Firmas nuevas

### Contrato

```python
CONSENT_MODES = ("texto", "boton")
DEFAULT_CONSENT_MODE = "texto"

class ChannelInfo(ContractModel):
    ...                                   # campos actuales
    capabilities: ChannelCapabilities | None = None
```

`_check_config` (ya usado por `ChannelConfig`) añade: si existe `consent_mode`,
debe ser una de `CONSENT_MODES` (`ValueError` → 422 en los modelos de petición).
Un `config` ya guardado con otro valor no rompe la lectura: el orquestador usa
`texto` (R13).

### Gateway

```python
# registry.py: se añade al protocolo ChannelFactory
@classmethod
def default_capabilities(cls) -> ChannelCapabilities: ...
```

Telegram, WhatsApp (`whatsapp_capabilities(window_open=False)`), simulado y webhook
genérico lo implementan con sus valores estáticos actuales (reutilizando las
mismas funciones/constantes que ya usa su `capacidades`, sin duplicar números).
`_info` usa `getattr(factory, "default_capabilities", None)`; si no existe o no
hay factory, `capabilities=None` (R3; los tipos falsos de pruebas siguen
funcionando).

```python
@dataclass(frozen=True)
class ChannelSeed:
    id: str; name: str; adapter_type: str; icon: str; color: str
    config: Mapping[str, Any] = field(default_factory=dict)   # nuevo, con default
```

`BUILTIN_CHANNEL_SEEDS`: `telegram` → `{"consent_mode": "texto"}`,
`whatsapp` → `{"consent_mode": "boton"}`. `PostgresChannelRepository.seed` inserta
`config` en el `INSERT … ON CONFLICT DO NOTHING` y añade, por cada semilla con
config, una sentencia idempotente que solo rellena claves ausentes:

```sql
UPDATE canales SET config = CAST(%s AS JSONB) || config WHERE id = %s
  AND NOT (CAST(%s AS JSONB) <@ config)
```

`semilla || config` deja ganar a las claves ya guardadas (R8) y completa las que
faltan (R7). `FakeChannelRepository.seed` replica la semántica.

### Orquestador

```python
# channels.py (puro)
@dataclass(frozen=True)
class ChannelPolicy:
    id: str; name: str; icon: str; color: str; active: bool
    windowed: bool
    consent_mode: Literal["texto", "boton"]

def policy_from_info(info: ChannelInfo) -> ChannelPolicy
def default_policy(channel_id: str) -> ChannelPolicy      # R14

# adapters/channels.py
class ChannelDirectory(Protocol):
    def policy(self, channel_id: str) -> ChannelPolicy
    def list_policies(self) -> list[ChannelPolicy]          # activos primero, orden de creación

class HttpChannelDirectory:
    def __init__(self, base_url: str, service_token: str, ttl_seconds: float,
                 timeout: float = 10, clock: Callable[[], float] = time.monotonic) -> None
class FakeChannelDirectory:
    def __init__(self, infos: Sequence[ChannelInfo] | None = None, fail: bool = False) -> None
    default_infos: ClassVar[Sequence[ChannelInfo]] = ()   # vacío en producción: sin nombres de canal
```

`FakeChannelDirectory` no contiene ningún nombre de canal (R36). Con `infos=None`
usa `default_infos`, vacío en el código de producción (todo canal resulta ausente
y cae en `default_policy`, R14). Los `ChannelInfo` de prueba (telegram: `texto`,
sin ventana; whatsapp: `boton`, con ventana; `simulado`: `texto`, sin ventana)
viven solo en `services/orchestrator/tests/fakes.py` (`default_channel_infos()`).
Un fixture `autouse` de `tests/conftest.py` hace
`monkeypatch.setattr(FakeChannelDirectory, "default_infos", default_channel_infos())`,
de modo que los tests que construyen `Adapters(...)` sin pasar `channels` reciben
el directorio de prueba sin editarse. `adapters/channels.py` no importa
`LEGACY_CHANNEL` ni necesita constantes legacy.

`HttpChannelDirectory` usa `httpx.get(f"{base}/channels")` con
`SERVICE_TOKEN_HEADER` y `ChannelListResponse.model_validate`. Caché por proceso
con `threading.Lock`; TTL por reloj monotónico inyectable (R15). Fallo con copia:
WARNING `channel_directory_stale code=<Tipo>` y devuelve la copia (R16); sin copia:
`ServiceUnavailable` (R17). Nunca se loguean tokens ni cuerpo.

```python
# domain.py
Adapters.channels: "ChannelDirectory" = field(default_factory=FakeChannelDirectory)

def channel_policy(adapters: Adapters, channel: str) -> ChannelPolicy
def consent_text_pending(message, settings, adapters) -> bool       # firma ampliada
def channel_window(policy: ChannelPolicy, last_user_at, now, hours) -> WindowState   # panel.py
```

El default `FakeChannelDirectory` en `Adapters` está vacío en producción y lo puebla
el fixture de `tests/conftest.py` (ver arriba); `build_default_adapters`
siempre lo sustituye por `HttpChannelDirectory(settings.gateway_url, settings.service_token,
settings.channel_directory_ttl_seconds)` (misma URL y token que `HttpGatewayClient`).
`ServiceUnavailable` del directorio se convierte en `UpstreamError` en
`POST /messages` (R18) y en la ruta del panel; en los workers la fila se reintenta
con el backoff de #64.

`InboxFilter`: `advisor_inbox` valida `channel` contra
`{p.id for p in adapters.channels.list_policies()}` (R27); `advisor_panel.py`
construye las opciones `(id, name)` desde el mismo listado (R26).

### Migración `canal_id`

El orquestador ya guarda el id de canal en `contacts.channel` (y los mensajes lo
heredan por `contact_id`). El acceptance pide `canal_id` explícito; en lugar de
renombrar `channel` (≈120 consultas y toda la batería), se añade la columna y se
escribe en paralelo:

```sql
ALTER TABLE contacts ADD COLUMN IF NOT EXISTS canal_id TEXT
ALTER TABLE messages ADD COLUMN IF NOT EXISTS canal_id TEXT
UPDATE contacts SET canal_id = channel WHERE canal_id IS NULL
UPDATE messages SET canal_id = c.channel FROM contacts c
  WHERE messages.contact_id = c.id AND messages.canal_id IS NULL
CREATE INDEX IF NOT EXISTS messages_canal_id ON messages (canal_id)
```

Se añaden al final de `_MIGRATIONS` (tras `UPDATE contacts SET channel = 'telegram'
WHERE channel IS NULL`, que pasa a usar `LEGACY_CHANNEL`). Los `INSERT` de
`contacts` y `messages` (Postgres y fake) escriben `canal_id` igual a `channel`.
`channel` sigue siendo la fuente de lectura; `canal_id` es el dato persistente que
usarán #66/#67 (el renombrado de lectura queda como deuda declarada).

## 4. Capa legacy documentada

Los únicos literales `"telegram"`/`"whatsapp"` permitidos viven en `legacy.py`
(`LEGACY_CHANNEL = "telegram"`). `LEGACY_CHANNEL` solo puede importarse desde:

| Archivo | Motivo |
|---|---|
| `legacy.py` | definición |
| `main.py` | rama `MessageRequest` (`telegram_user_id`) |
| `queue.py` | `legacy_from_normalized` (se importa de `legacy.py`, no se duplica) |
| `domain.py` | `process_message` histórico y `Contact.channel` por defecto |
| `adapters/repository.py` | columnas `telegram_user_id`/`chat_id` y migración `channel IS NULL` |
| `adapters/outbox.py` | `send(chat_id, text)` histórico |
| `adapters/gateway.py` | `FakeGatewayClient` (espejo de `send`) |

`test_nucleo_sin_nombres.py` recorre con `ast` todos los `.py` de
`services/orchestrator/orchestrator/`, recoge `Constant` `str` cuyo valor en
minúsculas sin espacios sea exactamente `telegram` o `whatsapp` (incluye los
dentro de f-strings y comparaciones) y exige que solo aparezcan en `legacy.py`
(R36); y que el conjunto de archivos con `from .legacy import LEGACY_CHANNEL` (o
equivalente `…legacy`) sea subconjunto de la tabla (R37). Etiquetas visibles
(«WhatsApp») y nombres como `whatsapp_templates` o `whatsapp_window_hours` no son
igualdad exacta y no cuentan. La prueba no compara `LEGACY_CHANNEL` contra
variables: ese uso en los archivos permitidos queda revisado por el reviewer.

Los literales `"telegram"` de texto de consentimiento en `domain.py` (líneas 2440-2737),
`panel.py:18`, `domain.py:3148/3192/3346/3910/4636` y el filtro
`INBOX_CHANNELS` desaparecen: pasan a `channel_policy(...)`.

## 5. Precedencia y comportamiento sin cambios

- WhatsApp: `windowed=True` por sus capacidades por defecto, así que
  `channel_window`, plantillas, avisos y `notice_skipped` dan los mismos resultados.
  Telegram (`windowed=False`) mantiene `not_applicable`.
- Consentimiento: Telegram (`texto`) y WhatsApp (`boton`) conservan exactamente los
  textos y desafíos actuales; solo cambia de dónde sale la decisión.
- `POST /messages` conserva el rechazo `422` de mensajes no entrantes; desaparece el
  rechazo por canal desconocido (el gateway ya validó que existe y está activo).
- `consent_text_pending` se llama con `adapters`; si el directorio no responde,
  `POST /messages` falla cerrado con `upstream_error` (el gateway reintenta o #64
  mantiene la entrada; ningún mensaje se pierde).

## 6. Alternativas descartadas

1. **Leer `canales` directamente desde el orquestador** (misma base Postgres):
   viola el principio 1 de `docs/architecture.md` y acopla esquemas.
2. **Capacidades por destino en cada decisión** (llamar al gateway por mensaje):
   añade latencia y un punto de fallo por mensaje; el orquestador ya calcula la
   ventana con `last_user_at` y `whatsapp_window_hours`, así que las capacidades por
   defecto bastan para saber *si* el canal tiene ventana.
3. **Renombrar `channel` → `canal_id` en todo el código**: ~120 consultas y toda la
   batería; el riesgo supera el beneficio. Se añade la columna y se escribe en
   paralelo (§3).
4. **Hardcodear un `consent_mode` por defecto por tipo de adaptador en el
   orquestador**: reintroduce nombres de canal; el ajuste vive en `canales.config`.
5. **Fallar abierto con política por defecto cuando el directorio cae**: un
   WhatsApp mal tratado como sin ventana enviaría texto libre rechazado por Meta;
   se prefiere copia obsoleta o reintento.

## 7. Dependencias

Ninguna nueva (`httpx` y `pydantic` ya están en el orquestador).

## 8. Supuestos a confirmar (defaults seguros y editables)

- **S1** `CHANNEL_DIRECTORY_TTL_SECONDS=30` (configurable; entre 1 y 3600). Un cambio
  de `consent_mode` o de activación tarda hasta ese tiempo en notarse.
- **S2** Canal ausente del directorio: sin ventana y `texto` (R14), el default del
  acceptance para canales nuevos.
- **S3** `consent_mode` inválido ya guardado se trata como `texto`; no se bloquea.
- **S4** `windowed` se deduce de las capacidades por defecto del tipo de adaptador;
  si #62/#63 o un futuro adaptador necesita ventana distinta, la informa el propio
  adaptador en `default_capabilities`.
- **S5** `canal_id` se escribe en paralelo a `channel`; la lectura por `canal_id`
  queda para #66/#67.
- **S6** Acción del dueño: ninguna. El gateway siembra `consent_mode` al arrancar y
  el orquestador toma `GATEWAY_URL`/`SERVICE_TOKEN` ya presentes en el `.env`.
