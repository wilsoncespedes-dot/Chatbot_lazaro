# #44 confirmar_callback_telegram — Requirements

Servicio: **telegram_gateway** (único). Autenticación del webhook, forma de
errores y deduplicación siguen #37 y `contracts/CONTRATOS.md`; no se repiten aquí.
"Id real" = `callback_query.id` del update, de tipo `str` y no vacío tras `strip()`.

## R1
CUANDO `POST /telegram/webhook` recibe un update con `callback_query` cuyo id es
real, el sistema DEBE invocar `TelegramClient.answer_callback_query(<id real>)`
exactamente una vez, antes de deduplicar y antes de llamar a
`orchestrator.post_message`.

## R2
CUANDO `HttpTelegramClient.answer_callback_query(callback_query_id)` se invoca,
el sistema DEBE hacer `POST https://api.telegram.org/bot<token>/answerCallbackQuery`
con cuerpo JSON exactamente `{"callback_query_id": <id>}` (sin `text`) y
`timeout` = `TELEGRAM_ANSWER_CALLBACK_TIMEOUT_SECONDS` (default `3.0`, `> 0`).

## R3
SI la llamada HTTP de R2 recibe un estado no 2xx, un timeout o cualquier
`httpx.HTTPError` ENTONCES el cliente DEBE lanzar `TelegramError` cuyo mensaje
y causa no contengan el token del bot ni la URL.

## R4
SI `answer_callback_query` lanza cualquier excepción ENTONCES el webhook DEBE
registrar un log de nivel WARNING o ERROR con el tipo de excepción (sin token
del bot), continuar con la deduplicación y el reenvío del botón al orquestador
como si no hubiera fallado, y responder `200 {"ok": true}`.

## R5
CUANDO el callback con id real es un duplicado (dedupe devuelve no nuevo), el
sistema DEBE haberlo confirmado igualmente (R1) y NO DEBE reenviarlo al orquestador.

## R6
CUANDO el `callback_query` tiene id real pero es inválido (`extract_callback`
devuelve `None` o `normalize_callback` lanza `ValidationError`), el sistema DEBE
confirmarlo igualmente (R1) y responder `200` sin reenviarlo.

## R7
SI `callback_query.id` falta, no es `str` o está vacío ENTONCES el sistema NO DEBE
invocar `answer_callback_query` (en particular nunca con `str(update_id)`), y el
resto del procesamiento del callback no cambia respecto a #37.

## R8
CUANDO el update no contiene `callback_query` (mensaje de texto u otro), el
sistema NO DEBE invocar `answer_callback_query`.

## Cobertura del acceptance
- answerCallbackQuery con el id, cliente HTTP y falso → R1, R2.
- Fallo/excepción/timeout registrado sin secretos, no impide dedupe ni reenvío, 200 → R3, R4.
- Duplicados e inválidos confirmados con id real; nunca con id sintético → R5, R6, R7, R8.
- Pruebas de llamada, fallo sin perder el botón y contrato HTTP → R1–R4 (tests en tasks T4–T5).
