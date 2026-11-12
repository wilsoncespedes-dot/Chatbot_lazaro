# #44 confirmar_callback_telegram — Design

Solo telegram_gateway. Fuera de alcance: el error 500 del panel asesor y
cualquier texto/alerta en la confirmación.

## Archivos

| Archivo | Cambio |
|---------|--------|
| `services/telegram_gateway/telegram_gateway/domain.py` | Nueva función pura `extract_callback_query_id(update) -> str \| None`. `extract_callback` e `IncomingCallback` no cambian (el `callback_id` sintético sigue sirviendo solo para dedupe/`external_message_id`). |
| `services/telegram_gateway/telegram_gateway/adapters/telegram.py` | `answer_callback_query` en `TelegramClient` (Protocol), `HttpTelegramClient` y `FakeTelegramClient`; `HttpTelegramClient.__init__` acepta `answer_callback_timeout`. |
| `services/telegram_gateway/telegram_gateway/config.py` + `.env.example` | `telegram_answer_callback_timeout_seconds: float = 3.0` (validador `> 0`) / `TELEGRAM_ANSWER_CALLBACK_TIMEOUT_SECONDS=3`. |
| `services/telegram_gateway/telegram_gateway/main.py` | `build_default_adapters` pasa el timeout; el webhook confirma al inicio (abajo). |
| `services/telegram_gateway/tests/test_webhook.py` | Tests R1–R8 (junto a los de callback de #37 y a `test_http_telegram_error_hides_bot_token`). |

## Firmas

```python
# domain.py
def extract_callback_query_id(update: dict) -> str | None
    # callback_query dict y id str con strip() no vacío -> id; si no -> None (R7)

# adapters/telegram.py
class TelegramClient(Protocol):
    def answer_callback_query(self, callback_query_id: str) -> None: ...  # lanza TelegramError

class HttpTelegramClient:
    def __init__(self, bot_token: str, timeout: float = 10,
                 answer_callback_timeout: float = 3.0) -> None
    def answer_callback_query(self, callback_query_id: str) -> None
        # httpx.post(f".../bot{token}/answerCallbackQuery",
        #            json={"callback_query_id": id}, timeout=answer_callback_timeout)
        # errores -> TelegramError con el mismo patrón que send_message (`from None`)

class FakeTelegramClient:
    answered: list[str]          # ids confirmados, en orden
    fail_answer: bool = False    # si True, answer_callback_query lanza TelegramError
```

`FakeTelegramClient.__init__(fail=False, fail_answer=False)`: `fail` sigue
afectando solo a `send_message`.

## Flujo del webhook

```python
raw = update.model_dump()
callback_query_id = extract_callback_query_id(raw)
if callback_query_id is not None:
    try:
        adapters.telegram.answer_callback_query(callback_query_id)
    except Exception as exc:   # amplio a propósito (R4)
        logger.warning("Fallo al confirmar callback update_id=%s (%s)",
                       update.update_id, type(exc).__name__)
callback = extract_callback(raw)
... # resto idéntico a #37 (normalize, dedupe, post_message)
```

- Se confirma antes de dedupe/orquestador: minimiza latencia del indicador y
  cubre duplicados (R5) e inválidos (R6) sin ramas extra.
- El log no incluye `str(exc)` ni el id del callback; solo el tipo, así no hay
  riesgo de filtrar URL/token aunque llegue una excepción no `TelegramError`.
- La llamada es síncrona dentro del endpoint `def` (threadpool de FastAPI);
  el timeout corto (3 s) acota el peor caso.

## Excepciones

Ninguna nueva. `TelegramError` existente para fallos del cliente; el webhook
nunca la propaga en esta rama.

## Alternativas descartadas

- **Campo `callback_query_id: str | None` en `IncomingCallback`**: no cubre los
  callbacks que `extract_callback` rechaza (sin `data`/chat) y que también deben
  confirmarse (R6). Una función aparte sobre el update crudo cubre todos los casos.
- **Confirmar tras reenviar al orquestador**: el indicador seguiría girando
  durante RAG/LLM y un fallo del orquestador podría saltarse la confirmación.
- **Reutilizar `http_timeout_seconds` (10 s)**: demasiado largo para algo que
  Telegram solo usa para parar el indicador; se usa uno propio configurable.
