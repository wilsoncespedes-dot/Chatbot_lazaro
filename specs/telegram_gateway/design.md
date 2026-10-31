# Design — telegram_gateway

## Archivos

Crear en `services/telegram_gateway/telegram_gateway/`:

- `adapters/__init__.py`
- `adapters/telegram.py` — `TelegramClient` (Protocol), `HttpTelegramClient` (httpx, `sendMessage` de la Bot API), `FakeTelegramClient` (guarda `sent: list[tuple[int, str]]`, con `fail: bool`).
- `adapters/dedup.py` — `DedupStore` (Protocol), `RedisDedupStore`, `FakeDedupStore` (dict en memoria, con `fail: bool`).
- `adapters/orchestrator.py` — `OrchestratorClient` (Protocol), `HttpOrchestratorClient` (httpx, `POST {ORCHESTRATOR_URL}/messages` con `X-Service-Token`), `FakeOrchestratorClient` (guarda `received`, con `fail: bool`).

Modificar:

- `config.py` — añadir `telegram_webhook_secret`, `telegram_bot_token`, `redis_url`, `orchestrator_url`, `dedup_ttl_seconds: int = 86400`, `non_text_reply: str`.
- `domain.py` — excepciones y lógica pura.
- `main.py` — ruta `/telegram/webhook` y `/send`; `create_app(settings=None, adapters=None)`; añadir `/telegram/webhook` a `PUBLIC_PATHS` del middleware de token de servicio (el webhook se protege con su propio secreto, comparado con `hmac.compare_digest`).
- `requirements.txt` — añadir `httpx` y `redis`.
- `/.env.example` — añadir `DEDUP_TTL_SECONDS`, `NON_TEXT_REPLY` (el resto ya existe).
- Tests: `tests/fakes.py` (o reexporta los fakes), `tests/test_webhook.py`, `tests/test_send.py`.

## Firmas

```python
# domain.py
class TelegramError(DomainError):   # code="telegram_error", status_code=502
class OrchestratorError(Exception): ...   # interna; el webhook la captura

class Adapters:  # dataclass: telegram, dedup, orchestrator, clock
    ...

def extract_incoming(update: dict) -> IncomingUpdate | None
    # None si no hay `message`; IncomingUpdate(update_id, chat_id, user_id, text | None). `text` se normaliza a None si está vacío o es solo espacios (R13)

def build_message_request(incoming: IncomingUpdate, now: datetime) -> MessageRequest

# adapters
class TelegramClient(Protocol):   def send_message(self, chat_id: int, text: str) -> None   # lanza TelegramError
class DedupStore(Protocol):       def mark_if_new(self, update_id: int, ttl_seconds: int) -> bool
class OrchestratorClient(Protocol): def post_message(self, request: MessageRequest) -> None  # lanza OrchestratorError
```

Las funciones de adaptadores son síncronas; las rutas FastAPI se declaran con `def` (hilos de Starlette) para no bloquear el bucle con httpx/redis síncronos. `RedisDedupStore.mark_if_new` usa `SET gw:update:<id> 1 NX EX ttl`.

## Flujo del webhook

1. Verificar secreto (R1-R3). Validar `update_id` entero (R17).
2. `extract_incoming`; si `None` → `200` (R16).
3. `dedup.mark_if_new`; si ya existía → `200` (R8). Si Redis falla → log y continuar (R10).
4. Con texto → `orchestrator.post_message`; captura `OrchestratorError` y registra (R11, R12). Sin texto → `telegram.send_message(NON_TEXT_REPLY)`, captura `TelegramError` (R13-R15).
5. Siempre `200` con `{"ok": true}`.

El `update_id` se marca antes de reenviar: si el orquestador falla no se reintenta desde el gateway (Telegram no reintenta tampoco porque recibe `200`). Es una pérdida aceptada en la versión mínima.

## Excepciones

Se reutiliza `DomainError`. Se añade `TelegramError` (502, `telegram_error`). `OrchestratorError` nunca llega al cliente. Errores 401/422/500 los dan los handlers existentes en `main.py`. El `unauthorized` del webhook se genera con el mismo helper `_error`.

## Alternativas descartadas

- **Marcar el `update_id` solo tras éxito del orquestador (permitir reintento).** Descartada: el webhook debe devolver `200` aunque falle (si no, Telegram reintenta sin fin) y un reintento propio exigiría cola/worker, fuera de alcance (ver «Agrupar mensajes con worker y caché» en `later`).
- **Deduplicar solo en el orquestador.** Descartada: el acceptance exige que el gateway no reenvíe repetidos y así se ahorra una llamada.
- **Cliente async (httpx.AsyncClient, redis.asyncio).** Descartada por simplicidad de fakes y tests; el volumen de la versión mínima no lo requiere.

## Dependencias nuevas (las instala el humano antes de implementar)

| Nombre | Versión | Licencia |
|---|---|---|
| httpx | `>=0.27,<1` | BSD-3 |
| redis (redis-py) | `>=5,<7` | MIT |

`httpx` ya es necesario para `TestClient`; se declara también en `requirements.txt` de ejecución.

## Supuestos a confirmar

| Supuesto | Valor por defecto configurable |
|---|---|
| Updates sin texto no se reenvían y se responde con texto fijo | `NON_TEXT_REPLY` = «Por ahora solo puedo leer mensajes de texto.» |
| Caducidad de la clave de deduplicación | `DEDUP_TTL_SECONDS=86400` (24 h) |
| Solo se procesa `message`; `edited_message`, `callback_query`, etc. se ignoran con `200` | — (cambiarlo es nueva feature) |
| Si Redis cae, se prefiere procesar (posible duplicado, que el orquestador descarta) a perder mensajes | — |
| Tiempo máximo de llamada al orquestador y a Telegram | `HTTP_TIMEOUT_SECONDS=10` (añadir a `.env.example`) |
| Mensajes de texto de más de 4096 caracteres no pasan (Telegram ya los limita); si llegaran, la validación de `MessageRequest` falla y se trata como fallo del orquestador (log, `200`) | — |
| Registro del webhook en Telegram (`setWebhook` con `secret_token`) es manual, fuera de alcance | — |
