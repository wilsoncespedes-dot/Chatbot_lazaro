# Requirements — telegram_gateway

Servicio: `telegram_gateway` (puerto 8001). Llama al `orchestrator` (`POST /messages`).
Contratos: `contracts/CONTRATOS.md` (`POST /messages`, `POST /send`, reglas comunes).

## Webhook

## R1
SI `POST /telegram/webhook` llega sin el encabezado `X-Telegram-Bot-Api-Secret-Token` o con un valor distinto de `TELEGRAM_WEBHOOK_SECRET` ENTONCES el sistema DEBE responder `401` con `{"error": "unauthorized", "message": "..."}` sin llamar al orquestador.

## R2
SI `TELEGRAM_WEBHOOK_SECRET` está vacío ENTONCES el sistema DEBE responder `401` a toda petición a `POST /telegram/webhook`.

## R3
CUANDO `POST /telegram/webhook` llega con el secreto correcto, el sistema DEBE aceptarla sin exigir `X-Service-Token`.

## R4
CUANDO llega un update nuevo con `message.text` que contiene al menos un carácter no blanco, el sistema DEBE llamar a `POST /messages` del orquestador con `update_id`, `telegram_user_id` (`message.from.id`), `chat_id` (`message.chat.id`), `text` y `received_at`, conforme a `lazaro_contracts.MessageRequest`.

## R5
CUANDO el gateway construye `received_at`, el sistema DEBE usar la hora actual con zona horaria (UTC) obtenida de un reloj inyectable.

## R6
CUANDO el gateway llama al orquestador, el sistema DEBE enviar el encabezado `X-Service-Token` con el valor de `SERVICE_TOKEN`.

## R7
CUANDO un update nuevo se acepta, el sistema DEBE responder `200` a Telegram.

## Deduplicación

## R8
CUANDO llega un update cuyo `update_id` ya está guardado en Redis, el sistema DEBE responder `200` sin llamar al orquestador y sin enviar ningún mensaje a Telegram.

## R9
CUANDO el gateway procesa un `update_id` por primera vez, el sistema DEBE guardarlo en Redis con caducidad de `DEDUP_TTL_SECONDS` segundos mediante una operación atómica (set-if-not-exists) antes de reenviarlo.

## R10
SI Redis falla al comprobar el `update_id` ENTONCES el sistema DEBE registrar el error y tratar el update como nuevo (el orquestador también descarta repetidos).

## Fallo del orquestador

## R11
SI la llamada a `POST /messages` del orquestador falla (error de red, tiempo agotado o respuesta distinta de `2xx`) ENTONCES el sistema DEBE responder `200` a Telegram.

## R12
SI la llamada a `POST /messages` del orquestador falla ENTONCES el sistema DEBE registrar el error con `logging` incluyendo el `update_id`, sin incluir el texto del mensaje ni el token.

## Updates sin texto

## R13
CUANDO llega un update nuevo con `message` pero sin `text`, o con `text` vacío o formado solo por espacios en blanco (audio, imagen, sticker u otro), el sistema DEBE enviar `NON_TEXT_REPLY` a ese `chat_id` mediante el adaptador de Telegram.

## R14
CUANDO llega un update sin texto, el sistema NO DEBE llamar al orquestador.

## R15
SI el envío de `NON_TEXT_REPLY` falla ENTONCES el sistema DEBE registrar el error y responder `200` igualmente.

## R16
CUANDO llega un update sin `message` (p. ej. `edited_message`, `callback_query`), el sistema DEBE responder `200` sin llamar al orquestador ni enviar nada.

## R17
SI el cuerpo del webhook no contiene un `update_id` entero ENTONCES el sistema DEBE responder `422` con `{"error": "validation_error", ...}`.

## POST /send

## R18
CUANDO `POST /send` recibe un `SendRequest` válido con `X-Service-Token` correcto, el sistema DEBE enviar `text` a `chat_id` mediante el adaptador de Telegram y responder `200` con `{"sent": true}`.

## R19
SI el adaptador de Telegram falla al enviar desde `POST /send` ENTONCES el sistema DEBE responder `502` con `{"error": "telegram_error", "message": "..."}`.

## R20
SI `POST /send` llega sin `X-Service-Token` válido ENTONCES el sistema DEBE responder `401` con `{"error": "unauthorized", ...}`.

## R21
SI el cuerpo de `POST /send` no valida contra `SendRequest` ENTONCES el sistema DEBE responder `422` con `{"error": "validation_error", ...}`.

## Configuración y adaptadores

## R22
El sistema DEBE leer de variables de entorno `TELEGRAM_WEBHOOK_SECRET`, `TELEGRAM_BOT_TOKEN`, `REDIS_URL`, `ORCHESTRATOR_URL`, `DEDUP_TTL_SECONDS` (por defecto 86400), `HTTP_TIMEOUT_SECONDS` (por defecto 10) y `NON_TEXT_REPLY` (por defecto «Por ahora solo puedo leer mensajes de texto.»).

## R25
`.env.example` DEBE listar todas las variables de R22.

## R23
El sistema DEBE acceder a Telegram, Redis y al orquestador únicamente a través de adaptadores con interfaz (`Protocol`) y versión falsa, de modo que los tests no usen red ni Redis real.

## R24
El sistema NO DEBE incluir `TELEGRAM_BOT_TOKEN` en logs, respuestas ni mensajes de error.

## Cobertura del acceptance

| Criterio de `feature_list.json` | Requirements |
|---|---|
| Secreto del webhook, `401` | R1, R2, R3 |
| Reenvío al orquestador con campos del contrato | R4, R5, R6, R7 |
| Deduplicación en Redis con TTL | R8, R9, R10 |
| `200` aunque falle el orquestador, con log | R11, R12 |
| Updates sin texto y `NON_TEXT_REPLY` | R13, R14, R15, R16 |
| `POST /send` y `502` | R18, R19, R20, R21 |
| Adaptadores con fakes y casos de test | R17, R22, R23, R24, R25 |
