# Design — agrupacion_mensajes (#30)

Todo vive en `telegram_gateway`. El orquestador, el handover y los contratos no cambian: un
grupo llega como un `MessageRequest` normal, así que privacidad, `/start`, `/consultar`,
`/responder`, `/cerrar`, reenvío al asesor durante un traspaso y deduplicación del orquestador
siguen intactos.

## Archivos

| Archivo | Cambio |
|---|---|
| `services/telegram_gateway/telegram_gateway/config.py` | Campos `message_grouping_*` y `privacy_accept_phrase`; validador R2. |
| `services/telegram_gateway/telegram_gateway/domain.py` | Dataclasses y funciones puras (abajo); `Adapters.buffer: MessageBuffer \| None = None`. |
| `services/telegram_gateway/telegram_gateway/adapters/message_buffer.py` (nuevo) | `MessageBuffer` (Protocol), `RedisMessageBuffer`, `FakeMessageBuffer`. |
| `services/telegram_gateway/telegram_gateway/grouping.py` (nuevo) | Orquestación con IO: `enqueue_text`, `flush_chat`, `flush_due`, `GroupingWorker` (hilo). |
| `services/telegram_gateway/telegram_gateway/main.py` | Rama de texto del webhook delega en `grouping` si hay buffer; lifespan arranca/para el worker. |
| `.env.example`, `render.yaml` (servicio gateway) | Variables de R1/R3; `PRIVACY_ACCEPT_PHRASE` también para el gateway. |
| `services/telegram_gateway/tests/test_grouping.py` (nuevo), `test_message_buffer.py` (nuevo) | Tests de R1–R27. Los tests existentes siguen sin buffer (R16). |

Sin dependencias nuevas (`redis>=5,<7` ya está). Sin rutas ni contratos nuevos.

## Firmas

```python
# domain.py (puro)
@dataclass(frozen=True)
class BufferedMessage: update_id: int; user_id: int; text: str; received_at: datetime
@dataclass(frozen=True)
class ClaimedGroup: chat_id: int; claim_id: str; attempts: int; messages: tuple[BufferedMessage, ...]

def is_immediate(text: str, accept_phrase: str) -> bool            # "/"... o igualdad normalizada
def compute_due(first: datetime, last: datetime, window: float, max_wait: float) -> datetime
def must_flush_before(pending: Sequence[BufferedMessage], new: BufferedMessage,
                      max_messages: int) -> bool                     # R9: otro usuario o desborde
def build_group_request(chat_id: int, messages: Sequence[BufferedMessage]) -> MessageRequest

# adapters/message_buffer.py
class MessageBuffer(Protocol):
    def append(self, chat_id: int, msg: BufferedMessage, window: float, max_wait: float,
               ttl_seconds: int) -> bool                           # False si update_id ya estaba
    def pending(self, chat_id: int) -> list[BufferedMessage]
    def claim_chat(self, chat_id: int, now: datetime, lease_seconds: float,
                   ttl_seconds: int) -> ClaimedGroup | None         # ignora vencimiento
    def claim_due(self, now: datetime, lease_seconds: float, ttl_seconds: int,
                  limit: int) -> list[ClaimedGroup]                 # vencidos + leases caducadas
    def ack(self, group: ClaimedGroup) -> None
    def release(self, group: ClaimedGroup, now: datetime) -> None   # attempts += 1, reintento ya

# grouping.py
def enqueue_text(incoming: IncomingUpdate, settings: Settings, adapters: Adapters) -> None
def flush_chat(chat_id: int, settings: Settings, adapters: Adapters) -> None
def flush_due(settings: Settings, adapters: Adapters) -> int        # una iteración del worker
class GroupingWorker:  def start(self) -> None; def stop(self, timeout: float = 5) -> None
```

## Flujo

Webhook (tras secreto, `extract_incoming` y `dedup.mark_if_new` de #3, R11):

1. Sin texto → igual que hoy (R15). Sin buffer o desactivado → reenvío directo (R16).
2. `is_immediate` → `flush_chat(chat_id)` y luego `post_message` individual (R13, R14).
3. Si el texto solo ya excede 4096 → camino actual de `ValidationError` (R10).
4. Si `must_flush_before(pending, new)` → `flush_chat` (R9). Después `append` (R4, R5, R12).
5. Cualquier excepción de Redis en 2–4 → log `grouping_redis_error update_id=…` y reenvío
   individual (R17). Siempre `200`.

`flush_chat`/`flush_due` envían cada `ClaimedGroup` con `build_group_request`: éxito → `ack`;
`OrchestratorError` → `release` si `attempts + 1 < MAX_ATTEMPTS`, si no `ack` + log de descarte
(R20, R21); `ValidationError` → `ack` + log de descarte. Logs solo con `chat_id`, `update_id`,
número de mensajes, intentos y tipo de excepción (R26).

`GroupingWorker`: hilo daemon con `threading.Event`; cada `POLL_SECONDS` llama a `flush_due` en
`try/except Exception` (R24). Arranca/para en el `lifespan` de `create_app` (R25). Al arrancar,
la primera iteración recoge buffers vencidos y grupos con lease caducada de una ejecución
anterior (R22).

## Redis (`RedisMessageBuffer`)

Claves (todas con `EXPIRE BUFFER_TTL_SECONDS`, renovado en cada escritura, R23):

- `gw:grp:buf:<chat_id>` — hash `update_id → JSON(BufferedMessage)` (orden por `update_id`; la
  clave de hash hace idempotente `append`, R12) + campos `first`/`last`.
- `gw:grp:due` — ZSET `chat_id → vencimiento epoch`.
- `gw:grp:inflight:<chat_id>` — hash `claim_id`, `attempts`, `messages`.
- `gw:grp:leases` — ZSET `chat_id → caducidad del lease`.

`append`, `claim_*`, `ack` y `release` son scripts Lua (`register_script`): atómicos en Redis, lo
que da R18 con varias instancias. `claim_*` solo reclama un chat si no existe su `inflight`
(R19); renombra el buffer a `inflight` y quita el chat de `due`. `release` deja el lease vencido
para que la siguiente iteración lo reclame. `ack` borra `inflight` y, si quedó un buffer
nuevo del chat, conserva su entrada en `due`.

`FakeMessageBuffer` replica la semántica en memoria con un `threading.Lock`, reloj inyectable y
caducidad simulada, y admite `fail=True` (lanza `ConnectionError`).

## Comportamiento con comandos, traspaso y datos personales

- Comandos (`/start`, `/consultar`, `/responder`, `/cerrar` y cualquier `/…`) y la frase de
  aceptación son inmediatos: no esperan la ventana y no se mezclan, así el parser de comandos y
  la igualdad de `is_acceptance` del orquestador ven el texto exacto. El buffer previo del chat
  se envía antes para conservar el orden.
- Durante un traspaso, los mensajes del cliente agrupados se reenvían al asesor como un solo
  texto con saltos de línea (mismo contenido, menos fragmentos). Los asesores interactúan con
  comandos, que son inmediatos.
- El texto queda en Redis como máximo `BUFFER_TTL_SECONDS` (300 s); nunca se registra en logs.
  La purga de #27 no necesita tocar Redis porque el TTL es muy inferior a la retención.

## Excepciones

Se reutilizan `OrchestratorError` y `ValidationError` de Pydantic. No se añaden excepciones
públicas ni códigos HTTP; el webhook sigue respondiendo siempre `200` tras autenticar.

## Alternativas descartadas

- **Agrupar en el orquestador.** Exigiría cambiar `POST /messages` (202 inmediato y
  procesamiento diferido de varios `update_id`): es un cambio de contrato que necesita feature
  propia. En el gateway el contrato queda intacto.
- **Servicio/worker separado.** Añade un servicio no previsto en `docs/architecture.md` §1 y
  otro despliegue en Render; un hilo dentro del gateway más Lua atómico cubre varias instancias.
- **Esperar la ventana dentro de la petición del webhook.** Bloquea a Telegram y no sobrevive a
  reinicios.
- **`BackgroundTasks` con `sleep`.** Se pierde al reiniciar y no coordina instancias.

## Supuestos a confirmar (defaults configurables)

| Supuesto | Default |
|---|---|
| Ventana corta: agrupa ráfagas sin retrasar mucho la respuesta (latencia extra ≈ ventana + sondeo) | `MESSAGE_GROUPING_WINDOW_SECONDS=2.0`, `MESSAGE_GROUPING_POLL_SECONDS=0.5` |
| Tope de espera para que una ráfaga larga no retrase indefinidamente | `MESSAGE_GROUPING_MAX_WAIT_SECONDS=8.0` |
| Tamaño máximo de grupo | `MESSAGE_GROUPING_MAX_MESSAGES=10` y 4096 caracteres del contrato |
| Retención de texto en Redis | `MESSAGE_GROUPING_BUFFER_TTL_SECONDS=300` |
| Reintentos ante fallo del orquestador; después se descarta con log (antes se perdía al primer fallo) | `MESSAGE_GROUPING_MAX_ATTEMPTS=3`, `MESSAGE_GROUPING_LEASE_SECONDS=30` |
| El grupo usa el menor `update_id`: el reintento con los mismos mensajes lo deduplica el orquestador | — |
| Si el webhook encuentra un grupo del chat ya en vuelo en otro worker, envía el mensaje inmediato sin esperar (reordenación posible y rara, se registra `grouping_inflight_race`) | — |
| Activable/desactivable sin redeploy de código | `MESSAGE_GROUPING_ENABLED=true` |
