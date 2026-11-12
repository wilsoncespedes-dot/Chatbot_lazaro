# Spec review — feature #44 confirmar_callback_telegram

**Veredicto:** APPROVED

## Trazabilidad acceptance -> R -> T
- A1 (answerCallbackQuery con id real, cliente HTTP y falso) -> R1, R2 -> T2, T3, T4, T5.
- A2 (fallo/timeout sin secretos, no impide dedupe/reenvío, 200) -> R3, R4 -> T2, T3, T4, T5 (`fail_answer`, `RuntimeError`, `caplog` sin `BOT_TOKEN`).
- A3 (duplicados/inválidos confirmados; nunca id sintético de update_id) -> R5, R6, R7, R8 -> T3, T5 (`answered == []`, nunca `"50"`).
- A4 (pruebas + init verde) -> T4 (contrato HTTP con `httpx.post` monkeypatched, sin red), T5, T6.
- Tasks todas en `[ ]`, en orden, y entre todas cubren R1–R8.

## Implementabilidad
- `TelegramUpdate` tiene `extra="allow"`, así que `model_dump()` conserva `callback_query`; `extract_callback_query_id` sobre el update crudo es viable y cubre los callbacks que `extract_callback` (domain.py:192) rechaza.
- Cambios acotados a domain.py, adapters/telegram.py, config.py, main.py (`build_default_adapters` línea 108 y webhook línea 196) y `.env.example`; respeta las 3 capas y no añade dependencias.
- Hay alternativas descartadas documentadas. El error 500 del panel asesor queda fuera de alcance.

## Observaciones no bloqueantes
1. R7 define el "id real" tras `strip()`, pero no aclara si se envía a Telegram el id original o el recortado. Recomendado: enviar el id original sin modificar.
2. R4 permite WARNING o ERROR; el design fija WARNING. Es coherente, basta con que el test acepte `>= WARNING`.
