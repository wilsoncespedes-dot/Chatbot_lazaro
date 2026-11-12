# Implementación #44 confirmar_callback_telegram

## Resumen

Solo `telegram_gateway`. El webhook confirma los `callback_query` de Telegram
con `answerCallbackQuery` al inicio del endpoint, antes de deduplicar y de
llamar al orquestador. El id se toma del propio update (nunca `str(update_id)`),
el cliente HTTP usa un timeout propio configurable y cualquier fallo al
confirmar se registra por tipo (sin token) sin alterar el resto del flujo.

Archivos tocados:

- `services/telegram_gateway/telegram_gateway/config.py`:
  `telegram_answer_callback_timeout_seconds` (default `3.0`, validador `> 0`).
- `.env.example`: `TELEGRAM_ANSWER_CALLBACK_TIMEOUT_SECONDS=3`.
- `services/telegram_gateway/telegram_gateway/adapters/telegram.py`:
  `answer_callback_query` en `TelegramClient`, `HttpTelegramClient` y
  `FakeTelegramClient` (`answered`, `fail_answer`); `TelegramError` sin token.
- `services/telegram_gateway/telegram_gateway/domain.py`:
  `extract_callback_query_id`.
- `services/telegram_gateway/telegram_gateway/main.py`: confirmación al inicio
  del webhook y paso del timeout a `build_default_adapters`.
- `services/telegram_gateway/tests/test_webhook.py`: tests R1–R8.

## Trazabilidad

- R1 → `services/telegram_gateway/tests/test_webhook.py::test_callback_valid_is_answered_and_forwarded`
- R2 → `services/telegram_gateway/tests/test_webhook.py::test_http_answer_callback_query_posts_exact_body_and_timeout`
- R2 → `services/telegram_gateway/tests/test_webhook.py::test_answer_callback_timeout_setting_default_and_env`
- R2 → `services/telegram_gateway/tests/test_webhook.py::test_answer_callback_timeout_rejects_non_positive`
- R3 → `services/telegram_gateway/tests/test_webhook.py::test_http_answer_callback_query_status_error_hides_bot_token`
- R3 → `services/telegram_gateway/tests/test_webhook.py::test_http_answer_callback_query_transport_errors_hide_bot_token`
- R4 → `services/telegram_gateway/tests/test_webhook.py::test_callback_answer_failure_still_forwards_and_returns_200`
- R4 → `services/telegram_gateway/tests/test_webhook.py::test_callback_answer_unexpected_exception_still_forwards`
- R5 → `services/telegram_gateway/tests/test_webhook.py::test_duplicate_callback_is_answered_every_time_but_forwarded_once`
- R6 → `services/telegram_gateway/tests/test_webhook.py::test_callback_without_data_but_real_id_is_answered_and_not_forwarded`
- R6 → `services/telegram_gateway/tests/test_webhook.py::test_callback_with_invalid_data_but_real_id_is_answered_and_not_forwarded`
- R7 → `services/telegram_gateway/tests/test_webhook.py::test_callback_without_real_id_is_not_answered`
- R8 → `services/telegram_gateway/tests/test_webhook.py::test_text_update_does_not_answer_callback`

## Tasks

- T1–T5 completadas.
- T6 (`./init.sh` verde) queda para Claude, que ejecuta la verificación al
  cerrar la sesión.

## Verificación (Claude implementer)

- Escritor: OpenCode/DeepSeek vía `scripts/run_opencode_writer.sh confirmar_callback_telegram` (1 invocación, respuesta `done`).
- `./init.sh` ejecutado con Git Bash (`C:\Program Files\Git\bin\bash.exe`): **verde** — 3048 passed, 1 skipped, 2 warnings (deprecaciones preexistentes) en 110.80s; modo supervisado.
- T6 marcada `[x]`. Trazabilidad R1–R8 → test presente arriba.
- Comprobado: el secreto del webhook se valida en el middleware antes de confirmar el callback; `feature_list.json` sigue `in_progress` (OpenCode no lo tocó).
- Fuera de alcance: error 500 del panel asesor (no tocado).
