# Design — #64 `cola_entrada_outbox`

## 1. Resumen

Dos tablas en el Postgres del orquestador (sin infraestructura nueva, decisión del
dueño 2026-11-21) y dos workers con la imagen del orquestador:

```
gateway --POST /messages--> orquestador --(1 tx: dedup + INSERT inbox)--> 202
                                  inbox --procesar_entrantes--> flujo actual (bot, IA, asignación)
flujo --(1 tx: INSERT messages + INSERT outbox)--> outbox --enviar_salientes--> gateway POST /send
```

Idea clave para limitar el cambio en el dominio: **`Adapters.gateway` pasa a ser solo
el cliente de entrega que usa el worker de salida** (`HttpGatewayClient` en
producción, `FakeGatewayClient` en pruebas), y el dominio escribe por un nuevo
`Adapters.outbound` (`OutboxGatewayClient`) con la misma interfaz
(`send`, `send_channel`, `send_channel_blocks`) que inserta filas en `outbox`. Los ~8
puntos de `domain.py` que hoy llaman `adapters.gateway.send*` pasan a llamar
`adapters.outbound.send*` sin cambiar su forma; donde el envío va seguido de
`add_message`, se usa la operación transaccional (§4).

## 2. Archivos

Crear:

| Archivo | Contenido |
|---|---|
| `services/orchestrator/orchestrator/queue.py` | entidades (`InboundEntry`, `InboxRow`, `OutboxEntry`, `OutboxRow`), `compute_backoff`, `conversation_key`, `destination_key`, `mask_destination`, `process_inbound`, `deliver_outbox_row`, `run_inbox_once`, `run_outbox_once` |
| `services/orchestrator/orchestrator/adapters/outbox.py` | `OutboxGatewayClient` (implementa `GatewayClient` escribiendo en `outbox`) |
| `services/orchestrator/orchestrator/workers.py` | `main(argv)` con modos `procesar_entrantes` y `enviar_salientes`, bucle con `--una-vez` (para pruebas y operación) y `WORKER_POLL_SECONDS` |
| `services/orchestrator/orchestrator/envios_routes.py` | rutas `/admin/envios` (patrón de `identity_routes.py`) y `render_failed_sends` |
| `contracts/tests/test_cola_doc.py` | R42 |
| `services/orchestrator/tests/test_cola_entrada.py` | R1–R8 |
| `…/test_worker_entrantes.py` | R9–R16 |
| `…/test_outbox_encolado.py` | R17–R21 |
| `…/test_worker_salientes.py` | R22–R28 |
| `…/test_envios_fallidos_panel.py` | R29–R34 |
| `…/test_cola_retencion.py` | R38–R39 |
| `…/test_cola_despliegue.py` | R36, R37, R40, R41 |

Modificar: `orchestrator/main.py` (`POST /messages`, sin `BackgroundTasks`; registra
`envios_routes`), `domain.py` (`Adapters.outbound`, sustitución de llamadas,
`_send`, `advisor_*`, supresión), `config.py` (9 variables), `adapters/repository.py`
(protocolo, `FakeRepository`, `PostgresRepository`, `_SCHEMA`, purga y supresión),
`admin_routes.py` solo si hace falta exportar helpers (`_audit`, `_require_session`),
`docker-compose.yml`, `.env.example`, `contracts/CONTRATOS.md`,
`services/orchestrator/tests/conftest.py` y `fakes.py` (`drain_queues`, §8). El
`Dockerfile` no cambia: copia el paquete `orchestrator` completo.

## 3. Esquema (`_SCHEMA`, `IF NOT EXISTS`)

```sql
CREATE TABLE IF NOT EXISTS inbox (
  id BIGSERIAL PRIMARY KEY,
  conversation_key TEXT NOT NULL, channel TEXT NOT NULL, external_user_id TEXT NOT NULL,
  payload_kind TEXT NOT NULL,            -- 'legacy' | 'channel'
  payload JSONB NOT NULL,                -- se vacía ('{}') al llegar a estado terminal
  status TEXT NOT NULL DEFAULT 'pending',-- pending | processing | done | failed
  attempts INTEGER NOT NULL DEFAULT 0,
  next_attempt_at TIMESTAMPTZ NOT NULL, locked_until TIMESTAMPTZ NULL,
  last_error TEXT NULL, created_at TIMESTAMPTZ NOT NULL, finished_at TIMESTAMPTZ NULL);
CREATE INDEX IF NOT EXISTS inbox_conversation ON inbox (conversation_key, id);
CREATE INDEX IF NOT EXISTS inbox_created ON inbox (created_at);

CREATE TABLE IF NOT EXISTS outbox (
  id BIGSERIAL PRIMARY KEY,
  contact_id TEXT NULL, destination_key TEXT NOT NULL,
  channel TEXT NOT NULL, destination TEXT NOT NULL,
  kind TEXT NOT NULL,                    -- bot | advisor | notice
  blocks JSONB NOT NULL,                 -- se vacía ('[]') al quedar 'sent'
  status TEXT NOT NULL DEFAULT 'pending',-- pending | sending | sent | failed
  attempts INTEGER NOT NULL DEFAULT 0,
  next_attempt_at TIMESTAMPTZ NOT NULL, locked_until TIMESTAMPTZ NULL,
  last_error TEXT NULL, created_at TIMESTAMPTZ NOT NULL, finished_at TIMESTAMPTZ NULL);
CREATE INDEX IF NOT EXISTS outbox_destination ON outbox (destination_key, id);
CREATE INDEX IF NOT EXISTS outbox_status ON outbox (status, created_at);
```

`blocks` guarda `[b.model_dump(mode="json") ...]` de `ResponseBlock`; el worker los
reconstruye con el `TypeAdapter` del contrato (#60).

## 4. Firmas nuevas

```python
# queue.py (puro salvo run_*)
def conversation_key(channel: str, external_user_id: str) -> str       # f"{channel}:{id}"
def destination_key(channel: str, destination: str) -> str
def mask_destination(destination: str) -> str                           # "****" + últimos 4
def compute_backoff(attempts: int, base: float, cap: float, jitter: float,
                    rng: Callable[[], float] = random.random) -> float
    # d = min(cap, base * 2 ** (attempts - 1)); retorna d * (1 + jitter * (2*rng() - 1))
def process_inbound(row: InboxRow, settings: Settings, adapters: Adapters) -> None
def run_inbox_once(settings, adapters) -> bool       # True si procesó una fila
def run_outbox_once(settings, adapters) -> bool      # True si entregó o falló una fila
```

Protocolo `Repository` (más `FakeRepository` y `PostgresRepository`):

```python
def enqueue_inbound(self, entry: InboundEntry, dedup: DedupKey | None) -> bool
    # una transacción: marca (processed_messages / processed_updates) + INSERT inbox.
    # False si la marca ya existía (no inserta). dedup=None: solo INSERT (R7).
def claim_inbound(self, now: datetime, lease_seconds: float) -> InboxRow | None
def finish_inbound(self, row_id: int, now: datetime) -> None                 # done + payload '{}'
def retry_inbound(self, row_id: int, next_attempt_at: datetime, error: str) -> None
def fail_inbound(self, row_id: int, now: datetime, error: str) -> None       # failed + payload '{}'

def enqueue_outbound(self, entry: OutboxEntry) -> int
def add_message_with_outbox(self, contact_id: str, role: str, text: str,
                            at: datetime, entry: OutboxEntry) -> None        # 1 transacción (R17, R18, R20)
def claim_outbound(self, now: datetime, lease_seconds: float) -> OutboxRow | None
def finish_outbound(self, row_id: int, now: datetime) -> None                # sent + blocks '[]'
def retry_outbound(self, row_id: int, next_attempt_at: datetime, error: str) -> None
def fail_outbound(self, row_id: int, now: datetime, error: str) -> None
def list_failed_outbound(self, limit: int) -> list[FailedSend]               # sin blocks
def requeue_outbound(self, row_id: int, now: datetime) -> str                # 'ok' | 'not_found' | 'not_failed'
```

`add_message_with_outbox` reutiliza la lógica de `add_message` (incluido el evento de
panel para roles de panel, §R18) dentro de la misma transacción. Los intentos se
incrementan al reclamar (`attempts = attempts + 1`).

**Reclamo atómico (misma forma para ambas tablas; ejemplo `inbox`):**

```sql
UPDATE inbox SET status = 'processing', attempts = attempts + 1, locked_until = %s
WHERE id = (
  SELECT i.id FROM inbox i
  WHERE (i.status = 'pending' AND i.next_attempt_at <= %s
         OR i.status = 'processing' AND i.locked_until < %s)
    AND NOT EXISTS (SELECT 1 FROM inbox e
                    WHERE e.conversation_key = i.conversation_key AND e.id < i.id
                      AND e.status IN ('pending', 'processing'))
  ORDER BY i.id FOR UPDATE SKIP LOCKED LIMIT 1)
RETURNING id, conversation_key, payload_kind, payload, attempts, created_at;
```

Solo la **cabeza** de cada clave (el menor id no terminal) es elegible, lo que da el
orden por conversación/destino (R10, R26). Cambia `inbox`→`outbox`, `conversation_key`
→`destination_key`, `processing`→`sending` para la salida. La concesión vencida
(`locked_until < now`) cubre el worker caído (R15, R28).

**Flujo del worker de entrada (`run_inbox_once`)**: `claim_inbound` → `process_inbound`
(deserializa; `legacy` → `process_message`; `channel` → decide `_legacy_from_normalized`
como hoy y llama `process_message` o `process_channel_message`) → `finish_inbound`. Ante
excepción: si `row.attempts >= INBOX_MAX_ATTEMPTS` → `fail_inbound(type(exc).__name__)`;
si no → `retry_inbound(now + compute_backoff(row.attempts, INBOX_BACKOFF_BASE_SECONDS,
cap = OUTBOX_BACKOFF_MAX_SECONDS, jitter))`. Cada fila usa el `Adapters` del proceso;
una excepción nunca sale del bucle.

**Flujo del worker de salida (`run_outbox_once`)**: `claim_outbound` →
`adapters.gateway.send_channel_blocks(channel, destination, blocks)` → `finish_outbound`;
`ChannelRejected` → `fail_outbound("ChannelRejected")` (sin reintento, R25; se evalúa
**antes** que `ServiceUnavailable` porque hereda de ella); `ServiceUnavailable` →
`fail_outbound` si `attempts >= OUTBOX_MAX_ATTEMPTS`, si no `retry_outbound` con
backoff exponencial con jitter.

```python
# adapters/outbox.py
class OutboxGatewayClient:               # implementa GatewayClient
    def __init__(self, repository: Repository, clock: Callable[[], datetime],
                 kind: str = "notice") -> None
    def send(self, chat_id: int, text: str) -> None                  # canal "telegram", destino str(chat_id)
    def send_channel(self, channel: str, destination: str, text: str) -> None
    def send_channel_blocks(self, channel, destination, blocks) -> None
    def with_message(self, contact: Contact, role: str, text: str, kind: str) -> ...
        # inserta mensaje + outbox en una transacción (add_message_with_outbox)
```

Todo error de inserción se eleva como `ServiceUnavailable` para que los llamadores
conserven su manejo actual (`except ServiceUnavailable`).

`Adapters` (`domain.py`): se añade al final `outbound: "GatewayClient | None" = None`;
`__post_init__` asigna `OutboxGatewayClient(self.repository, self.clock)` si es `None`
(no rompe las construcciones existentes, que siguen pasando `gateway=` para la entrega).

**Cambios en `domain.py`:** `_deliver`, `_notify_channel`, `_notify_sender`,
`_send_identity_blocks`, los `send_blocks` de consentimiento (≈2371), `advisor_send_*`
(≈3089/3139), supresión (≈3797) y expiración (≈4552) usan `adapters.outbound`. `_send`
(respuesta del bot): en lugar de «enviar y luego `add_message`», llama
`add_message_with_outbox` (R17) y devuelve `True`; el mensaje del bot ya no se pierde
ni se duplica si el gateway cae. `advisor_*` usan `add_message_with_outbox` con
`kind="advisor"` (R18). La rama `except ChannelRejected` de `advisor_send_template` ya
no es alcanzable; la validación previa (`_ensure_window_open`, plantilla aprobada) se
conserva y **sigue respondiendo `422` síncrono**; un rechazo tardío queda como envío
fallido visible en el panel (R25, R29).

**`POST /messages` (`main.py`)**: se conserva la lógica de `consent_ready`/`pending`.
`pending` (aceptación) → `direct()` como hoy (excepción de #35 R4/R5/R18: un fallo al
guardar la evidencia responde 500 en la petición). Resto → `enqueue_inbound(entry,
dedup)` con `dedup = None` si `not consent_ready` (R7), o la marca de mensaje
(`("message", channel, id)`) / de update legacy (`("update", update_id)`); `False` →
`duplicate`. La carga es `body.model_dump(mode="json")`.

## 5. Config (`config.py`, `.env.example`)

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

## 6. Panel `/admin/envios`

`GET /admin/envios` (admin y supervisor; el resto 403 con `render_error`) y
`POST /admin/envios/{id}/reintentar` (CSRF obligatorio con `_require_csrf_audited`,
mismo patrón que `/admin/supresiones`). La vista usa `render_failed_sends` con
`html.escape`, id, canal, `mask_destination`, tipo, intentos, `last_error` (nombre de
excepción) y fecha; no recibe `blocks` (el SQL de `list_failed_outbound` no los
selecciona). Auditoría con `record_panel_audit(profile, "outbox_retry", result, adapters,
target=str(id))`; el reintento solo mueve `failed → pending` con `attempts = 0`
(`UPDATE ... WHERE id = %s AND status = 'failed'`). Se enlaza desde la barra del panel
existente (sin tocar su CSS).

## 7. Retención y supresión

`purge_personal_data` añade `DELETE FROM inbox WHERE created_at < cutoff RETURNING id` y
lo mismo para `outbox`; `deleted` suma las claves `inbox` y `outbox` (el
`dict[str, int]` del contrato no cambia). `delete_contact_content(channel,
external_user_id)` borra `inbox` por `conversation_key` y `outbox` por `contact_id` **y**
por `destination_key` del contacto (cubre avisos sin contact_id). El aviso de
confirmación de la supresión se encola **después** del borrado y solo contiene texto
fijo, por lo que no reintroduce datos del contacto.

## 8. Pruebas

- Concurrencia: `FakeRepository.claim_*` se protege con `threading.Lock` y replica la
  semántica del SQL; una prueba lanza varios hilos de `run_outbox_once` sobre 20 filas
  y comprueba que cada fila se entrega una vez (R27). El SQL real se comprueba con
  conexión falsa como `handover/tests/test_repository.py`: la sentencia contiene
  `FOR UPDATE SKIP LOCKED`, `NOT EXISTS` y no selecciona `blocks` en el listado (R9,
  R10, R26, R30).
- «Sin pérdida ante caída»: se reclama una fila, se avanza el reloj falso más allá de
  `locked_until` y otro worker la procesa (R15, R28). Backoff: `compute_backoff` con
  `rng` fijo y reloj falso (R23).
- Orden: dos filas al mismo destino, la primera con fallo transitorio; la segunda no
  sale hasta que la primera llega a `sent` o `failed` (R26).
- **Tests existentes que se adaptan** (no se debilitan): los que hacen `POST /messages`
  y luego leen `gateway.sent`/`channel_sent`/`blocks_sent` añaden `drain_queues(settings,
  adapters)` (helper de `fakes.py`: ejecuta `run_inbox_once` y `run_outbox_once` hasta
  vaciar); los que esperaban `ChannelRejected` síncrono en `advisor_send_template` se
  sustituyen por prueba del envío fallido (R25). Se listan en
  `progress/impl_cola_entrada_outbox.md`.

## 9. Ventana de duplicado y límites (documentar en `CONTRATOS.md`)

- La entrega es **al menos una vez**: el worker puede caer entre `send_channel_blocks`
  exitoso y `finish_outbound`, o expirar la concesión durante un envío lento; en ambos
  casos otro worker reenvía y el cliente puede ver el mensaje dos veces. La ventana es
  como máximo `WORKER_LEASE_SECONDS` y es la contrapartida aceptada de no perder
  mensajes.
- La entrada es igualmente al menos una vez: el flujo hace varias escrituras
  independientes; si cae a mitad, el reintento puede repetir efectos ya hechos.
- **Bloqueo por orden:** un mensaje que reintenta bloquea los posteriores de su misma
  conversación/destino hasta agotar intentos (máximo de unos minutos con los defectos).
- Los envíos fallidos se pueden reintentar a mano; los mensajes de entrada fallidos no
  (se conserva solo el motivo; su carga se vacía por privacidad).

## 10. Alternativas descartadas

1. **Broker (Redis Streams, RabbitMQ, Celery):** decisión del dueño: sin
   infraestructura nueva; Postgres con `SKIP LOCKED` basta para el volumen de un
   chatbot.
2. **Bloqueos consultivos (`pg_advisory_lock`) por conversación en vez del `NOT EXISTS`:**
   atan el orden a la vida de la conexión y complican la concesión por tiempo y las
   pruebas con repositorio falso.
3. **Hilo/worker dentro del proceso del orquestador:** reaparece el problema de
   `BackgroundTasks` (se detiene con el proceso y compite con el servidor HTTP);
   los workers separados escalan y reinician de forma independiente.
4. **Mantener `adapters.gateway` en el dominio y añadir un decorador de reintentos
   síncrono:** no cumple la atomicidad con el mensaje guardado ni sobrevive a reinicios.
5. **Procesar también la aceptación de consentimiento por la cola:** rompería R18 de
   #35 (el 500 por fallo de evidencia debe ocurrir en la petición).

## 11. Dependencias

Ninguna nueva (`pg8000`, `httpx`, `fastapi` ya presentes).

## 12. Supuestos a confirmar (defaults seguros y editables)

- **S1** Valores de la tabla de §5 (editables por entorno).
- **S2** Un mensaje de entrada fallido no se puede reintentar desde el panel; solo se
  ve el motivo en logs (`inbox_failed id=… channel=… code=…`). Ampliarlo es trivial si
  el dueño lo pide.
- **S3** Las cargas se vacían al llegar a estado terminal para no conservar texto de
  clientes más allá de lo necesario; las filas (sin contenido) viven hasta la
  retención `PRIVACY_RETENTION_DAYS`.
- **S4** El destino se enmascara en el panel (`****` + últimos 4); el id de fila basta
  para reintentar.
- **S5** Sin worker de limpieza propio: la purga diaria existente (`retention_worker`)
  borra las filas por antigüedad.
- **S6** Sin healthcheck de compose para los workers: el fallo se ve en logs y en la
  acumulación de filas `pending`/`failed` (el panel #66 puede mostrar métricas después).
