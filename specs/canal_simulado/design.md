# Design — #63 `canal_simulado`

## 1. Resumen

El canal simulado es **un adaptador más** del registry (`simulado`) que, en lugar
de llamar a una red, escribe en un buzón del gateway. La entrada reutiliza el
camino del webhook de #62 (se extrae un método de entrega compartido) y el panel
(orquestador) lo maneja solo por HTTP con `X-Service-Token`: nunca ve secretos.

```
gateway
  adapters/channels/simulado.py   SimuladoChannel (tipo "simulado", has_mailbox=True)
  adapters/mailbox.py             MailboxRepository (Protocol), PostgresMailboxRepository, FakeMailboxRepository
  webhook_service.py              receive() -> _deliver(); inject() para /simulate; hooks opcionales
  channel_service.py              mailbox_channel(channel_id) -> Canal; simulate()
  main.py                         GET /channels/{id}/mailbox, POST /channels/{id}/simulate
orchestrator
  adapters/simulator.py           SimulatorClient (Protocol), HttpSimulatorClient, FakeSimulatorClient
  simulator_page.py               funciones puras de render (cuerpo HTML escapado)
  simulator_routes.py             rutas /admin/simulador y /asesor/simulador
scripts/simular_canal.py          herramienta de línea de comandos (firma y envía)
contracts
  lazaro_contracts/channel_simulator.py   4 modelos + CONTRATOS.md
```

Frontera con `docs/conventions.md`: código en inglés salvo el puerto y el slug del
tipo `simulado` (nombre del encargo). `main.py`, `webhook_service.py` y
`channel_service.py` no comparan con nombres de canal; la prueba de #61 R10 se
extiende a los archivos nuevos.

Decisión de datos: nombre, ícono y color ya viven en las columnas de `canales`
(los edita #66 desde el panel); duplicarlos en `config` crearía dos fuentes. Por
eso `config` del canal simulado solo lleva `capabilities`. Se interpreta
«toma nombre, ícono, color y capacidades de config» como «de la configuración del
registro del canal» (`canales`).

## 2. Archivos

Rutas del gateway relativas a `services/telegram_gateway/`; del orquestador, a
`services/orchestrator/`.

| Archivo | Acción | Requirements |
|---|---|---|
| `contracts/lazaro_contracts/channel_simulator.py` | crear | R1 |
| `contracts/lazaro_contracts/__init__.py` | exportar | R1 |
| `contracts/CONTRATOS.md` | sección «Canal simulado» | R2 |
| `contracts/tests/test_canal_simulado_contrato.py` | crear | R1, R2 |
| `telegram_gateway/adapters/channels/simulado.py` | crear | R3–R11, R40 |
| `telegram_gateway/adapters/channels/__init__.py` | importar el módulo | R3 |
| `telegram_gateway/adapters/mailbox.py` | crear | R12–R17 |
| `telegram_gateway/webhook_service.py` | extraer `_deliver`, `inject`, hooks | R20–R26 |
| `telegram_gateway/channel_service.py` | `mailbox_channel`, `simulate` | R19–R20 |
| `telegram_gateway/domain.py` | `Adapters.mailbox` (al final, `None`) | R11, R16 |
| `telegram_gateway/config.py` | 2 ajustes | R13, R14, R18 |
| `telegram_gateway/main.py` | 2 rutas; `build_default_adapters`/`create_app` | R16, R19–R20 |
| `.env.example` | 2 variables | R39 |
| `orchestrator/adapters/simulator.py` | crear | R35 |
| `orchestrator/simulator_page.py` | crear | R29, R32, R33, R40 |
| `orchestrator/simulator_routes.py` | crear; registrar en `main.py` | R28–R35 |
| `orchestrator/admin.py` | enlace «Simulador» en `ADMIN_NAV_LINKS` | R35 |
| `orchestrator/domain.py` | `Adapters.simulator` (al final, `None`) | R35 |
| `scripts/simular_canal.py` | crear | R36–R38, R40 |
| tests (ver tasks) | crear | todos |

Sin dependencias nuevas (`httpx`, `pg8000` ya existen en cada servicio; el
script usa solo biblioteca estándar y `lazaro_contracts`).

## 3. Firmas nuevas

```python
# contracts/lazaro_contracts/channel_simulator.py
MailboxKind = Literal["client", "reply", "rejected"]
class MailboxEntry(BaseModel):            # extra="forbid"
    id: int = Field(ge=1); channel: Channel; destination: str
    kind: MailboxKind; text: str = Field(min_length=1, max_length=MAX_TEXT_LENGTH)
    created_at: datetime
class MailboxResponse(BaseModel):         channel: Channel; entries: list[MailboxEntry]
class SimulatedInboundRequest(BaseModel): external_user_id: str (patrón R30); text: str (1..MAX_TEXT_LENGTH)
class SimulatedInboundResponse(BaseModel):
    status: Literal["accepted","duplicate"]; forwarded: bool; reason: str | None = Field(None, max_length=200)

# gateway adapters/mailbox.py
class MailboxRepository(Protocol):
    def append(self, channel_id: str, destination: str, kind: str, text: str, now: datetime) -> int
    def list(self, channel_id: str, destination: str | None, after_id: int, limit: int,
             now: datetime) -> list[MailboxEntry]
class PostgresMailboxRepository:  # (database_url, retention_seconds, max_entries)
class FakeMailboxRepository:      # (retention_seconds=3600, max_entries=500)

# gateway adapters/channels/simulado.py
@CHANNEL_REGISTRY.register("simulado")
class SimuladoChannel:
    """SIMULADO: ... nunca llama a la red; deja las respuestas en el buzón."""
    managed_by_environment = False
    has_mailbox = True                                  # marcador de clase (R19, R20)
    def __init__(self, channel_id, capabilities: ChannelCapabilities, mailbox, clock, ...)
    @classmethod validate_config(config, context)       # R6 (hook opcional existente de #62)
    @classmethod build(record, context, secrets)        # R11 (mailbox None -> ChannelNotConfigured)
    def recibir_mensaje / identificar_usuario / capacidades / enviar_mensaje   # R5, R8, R9, R10
    def registrar_entrada(message) -> None              # hook opcional, R21–R22
    def registrar_rechazo(message, reason: str) -> None # hook opcional, R21, R23

# gateway webhook_service.py
class WebhookService:
    def inject(self, channel_id: str, canal: Canal, message: NormalizedMessage) -> DeliveryResult
    def _deliver(self, channel_id, canal, message) -> DeliveryResult   # dedup -> hook entrada -> post_message -> hook rechazo
@dataclass(frozen=True)
class DeliveryResult: status: Literal["accepted","duplicate"]; forwarded: bool; reason: str | None

# gateway channel_service.py
def mailbox_channel(self, channel_id: str) -> Canal       # 404 uniforme: sin fila o sin has_mailbox
def active_mailbox_channel(self, channel_id: str) -> Canal  # además exige activo (ChannelInactive 422)

# orchestrator adapters/simulator.py
class SimulatorClient(Protocol):
    def list_channels(self) -> list[ChannelInfo]            # filtra adapter_type == "simulado" en el cliente
    def simulate(self, channel_id: str, external_user_id: str, text: str) -> SimulatedInboundResponse
    def mailbox(self, channel_id: str, destination: str, after: int = 0) -> MailboxResponse
class SimulatorUnavailable(ServiceUnavailable)             # transporte, 5xx o JSON inválido

# orchestrator simulator_page.py (puras)
def simulated_label(name: str) -> str        # "<name> [SIMULADO]" (siempre, sin duplicar si ya termina así)
def render_simulator(channels, selected, user_id, entries, csrf, base_path, error=None) -> str
```

`mailbox_channel` construye el canal con `factory.build` y lo usa solo para leer
(el buzón se lee del repositorio con el `channel_id`); comprueba
`getattr(factory, "has_mailbox", False)` y devuelve `ChannelNotFound` uniforme si
falta. Un tipo sin buzón (telegram, webhook_generico) responde igual que un canal
inexistente (R19).

### Flujo de entrada compartido

`WebhookService.receive` conserva el orden de #62 (404 → 413 → 401 → 422) y, tras
validar `channel`/`direction`, delega en `_deliver`: `dedup.mark_message_if_new`
(fallo = nuevo, ERROR) → si es duplicado, `DeliveryResult("duplicate")` sin hooks
→ hook `registrar_entrada` → `orchestrator.post_message` → en
`OrchestratorError`/`ValidationError`, ERROR `webhook_forward_failed` (como hoy),
hook `registrar_rechazo(message, reason[:200])` y `forwarded=False`. Los hooks se
buscan con `getattr` y se envuelven en `try/except Exception` (R26). `inject`
(para `/simulate`) construye el `NormalizedMessage`, llama a `_deliver` y
traduce a `SimulatedInboundResponse`; no verifica firma porque la ruta ya pasó
por el middleware de `X-Service-Token`. `receive` devuelve igual
`WebhookResult(status)` que antes.

### Buzón

Postgres, misma conexión/patrón que `PostgresChannelRepository` (reutiliza
`_pg_connect`, reconexión tras `is_connection_error`):

```sql
CREATE TABLE IF NOT EXISTS buzon_simulado (
  id BIGSERIAL PRIMARY KEY, canal_id TEXT NOT NULL, destino TEXT NOT NULL,
  tipo TEXT NOT NULL, texto TEXT NOT NULL, creado_en TIMESTAMPTZ NOT NULL)
CREATE INDEX IF NOT EXISTS buzon_simulado_canal_id ON buzon_simulado (canal_id, id)
```

`append` inserta y, en la misma transacción, elimina con parámetros `%s` las filas
del canal con `creado_en < now - retention` y las que superan `max_entries`
(`DELETE ... WHERE canal_id=%s AND id <= (SELECT id ... ORDER BY id DESC OFFSET %s LIMIT 1)`).
`list` aplica el mismo filtro de retención en el `WHERE` (no devuelve vencidas
aunque aún no se hayan borrado) y ordena por `id`. El buzón no se purga por
supresión legal porque solo guarda texto de pruebas con ids de prueba (se avisa
en `.env.example` y en CONTRATOS.md: no usar datos reales).

### Panel

`simulator_routes.create_simulator_router(settings, adapters)` registra, como los
demás routers (`app.router.routes.extend(...)`), cuatro rutas que comparten
lógica en funciones internas parametrizadas por el panel:

| Ruta | Sesión | Rechazo |
|---|---|---|
| `GET/POST /admin/simulador` | `admin_routes._require_any_session(... {"admin"})` (cookie del panel admin) | `LoginRequired` |
| `GET/POST /asesor/simulador` | `advisor_routes._require_session(..., SUPERVISOR_ROLES)` | `LoginRequired` / `AdvisorAccessDenied` |

`admin.py` no permite supervisores y `advisor_routes` tiene su propia cookie y
política de roles; por eso hay dos rutas con el mismo renderizador
(`render_simulator`) y envoltura distinta: `admin.render_page(...)` y el helper de
página equivalente de `advisor_panel`. El CSRF usa `_require_csrf` del panel
correspondiente; `GET` y `POST` pasan siempre por la sesión antes de tocar el
cliente. Solo se aceptan los canales devueltos por `list_channels()` filtrados por
`adapter_type == "simulado"`: el `canal` del formulario se valida contra esa lista
(nunca se reenvía un id arbitrario). `POST` hace `PRG` (`303`) a
`GET …?canal=<id>&usuario=<id>`. Sin JavaScript: botón «Actualizar» (un enlace) y
no se usa `<meta refresh>`, para no perder lo que se escribe.

La etiqueta del canal en la lista es `simulated_label(name)`; la conversación
se pinta con un `<ol>` por entrada (`client`: «Cliente de prueba», `reply`:
«Plataforma (bot o asesor)», `rejected`: bloque de rechazo). Todo valor pasa por
`html.escape` (`admin._esc`).

### Script

`scripts/simular_canal.py` (biblioteca estándar + `lazaro_contracts`):

```python
def build_body(channel: str, user: str, text: str, message_id: str, now: datetime) -> bytes
def sign(secret: str, timestamp: int, body: bytes) -> str       # HMAC-SHA256 hex de b"<ts>." + body
def send(url, channel, secret, body, now, post=urllib_post) -> tuple[int, str]   # post inyectable
def main(argv=None, env=os.environ, post=urllib_post, now=_utcnow) -> int
```

`main` devuelve `0` (HTTP 200), `1` (otro HTTP), `2` (uso: secreto ausente, red).
El mensaje se serializa **una vez** a bytes y se firma esa misma cadena.

### Configuración

`SIMULATED_MAILBOX_RETENTION_SECONDS: int = Field(3600, ge=60, le=86400)` y
`SIMULATED_MAILBOX_MAX_ENTRIES: int = Field(500, ge=10, le=5000)` en `Settings`
del gateway. `build_default_adapters` añade
`mailbox=PostgresMailboxRepository(settings.database_url, retention, max_entries)`;
`create_app` usa `FakeMailboxRepository(retention, max_entries)` si es `None`.

## 4. Precedencia de errores

- `POST /webhooks/{id}` hacia un canal simulado: igual que #62 (503 → 404 → 413 →
  401 → 422 → dedup → entrega). Un rechazo del orquestador no cambia el `200`.
- `GET /channels/{id}/mailbox`: 401 (token) → 503 (almacén de canales o buzón) → 404
  → 200. `limit`/`after` inválidos → `422 validation_error` (handler existente).
- `POST /channels/{id}/simulate`: 401 → 422 (cuerpo) → 503 → 404 → 422
  `channel_inactive` → 200.

## 5. Alternativas descartadas

1. **Que el panel firme el webhook con el secreto del canal**: obligaría a que el
   orquestador conozca secretos; `docs/architecture.md` lo prohíbe. `/simulate`
   usa el token de servicio ya existente.
2. **Guardar el buzón en Redis**: el gateway ya usa Postgres para canales y la
   retención/orden por id y el filtro por canal son triviales en SQL; Redis exige
   claves por canal y TTL por entrada.
3. **Buzón solo en memoria**: se perdería con varias instancias o reinicios y el
   panel (otro proceso) vería datos distintos; se conserva el falso solo para
   pruebas.
4. **Un solo router con ruta `/simulador` para ambos roles**: el panel admin y el
   de asesores tienen cookies, `path` y políticas de rol distintas (#41, #42);
   mezclarlas debilitaría ambas.
5. **Comparar `tipo_adaptador == "simulado"` en el servicio para registrar el buzón**:
   rompería R10 de #61. Se usan hooks opcionales (`registrar_entrada`,
   `registrar_rechazo`) y el marcador de clase `has_mailbox`.
6. **Detectar el rechazo 422 en el orquestador y devolver un código propio**: tocaría
   la guarda temporal que #65 retira; se registra el motivo textual del
   `OrchestratorError` existente.
7. **Duplicar nombre/ícono/color en `config`**: dos fuentes de verdad (R de #66).

## 6. Supuestos a confirmar (defaults seguros y editables)

- **S1** Retención 3600 s y 500 entradas por canal (configurables).
- **S2** El buzón no distingue bot de asesor (ambos usan `POST /send`); la página
  lo rotula «Plataforma (bot o asesor)». Distinguir el origen llegará con el
  outbox (#64) y la etiqueta de origen (#67).
- **S3** La palabra `SIMULADO` de la etiqueta se añade siempre en la página
  (`[SIMULADO]`), sin depender del nombre que dé el usuario al crear el canal.
- **S4** Un canal simulado inactivo se puede leer (historial) pero no recibe
  mensajes por `/simulate` (`422 channel_inactive`), igual que `POST /send`.
- **S5** El id externo de prueba permite letras, dígitos y `_ . : -` hasta 64
  caracteres; el texto, hasta 4096.

## 7. Tests existentes sustituidos

Registrar el tipo real `simulado` en `CHANNEL_REGISTRY` choca con tests que lo usan
como nombre de un adaptador de prueba sobre una copia del registry
(`DuplicateAdapterType`). Se renombra el tipo de prueba a `tipo_prueba`, sin
debilitar ninguna afirmación, en el mismo paso que importa el módulo en
`channels/__init__.py` (T3; la nav de `/admin` va en T7), y se anota en `progress/impl_canal_simulado.md`:

| Test | Cambio |
|---|---|
| `tests/test_canales_rutas.py` (registro de prueba `@registry.register("simulado")`, `adapter_type: "simulado"` en sus peticiones, y `body["adapter_types"] == ["webhook_generico", "simulado"]`) | tipo de prueba `tipo_prueba`; la lista esperada pasa a `["webhook_generico", "simulado", "tipo_prueba"]` |
| `tests/test_canales_secretos.py` (registro de prueba y peticiones con `"simulado"`) | tipo de prueba `tipo_prueba` |
| `tests/test_registro_canales.py::test_default_registry…` (contenido exacto del registry y `creatable_types`) | añade `simulado` (`creatable_types() == ("webhook_generico", "simulado")`) |
| `tests/test_webhook_canal.py` y otros que fijen la lista de tipos | se ajustan igual si fallan; se anotan |
| nav de `/admin` (tests que cuenten `ADMIN_NAV_LINKS`, p. ej. en `test_admin*.py`) | se añade el enlace «Simulador» al esperado |

`test_canales_repositorio.py` y el contrato usan `"simulado"` solo como cadena de
datos y no cambian. Si `./init.sh` revela otro test que dependa de estas listas,
se trata igual y se anota.
