# Requirements — #62 `webhook_generico_firmado`

Fase 3 de la ampliación multicanal genérica. El gateway recibe mensajes de
cualquier sistema externo (o puente como n8n, Zapier, Make o Twilio) por
`POST /webhooks/{canal_id}` firmado con HMAC-SHA256, y entrega las respuestas por
un callback saliente firmado. Depende de #60 (contrato, `done`) y #61 (puerto
`Canal`, registry, tabla `canales` y secretos, `done`).

Fuera de alcance: adaptador simulado y `scripts/simular_canal.py` (#63); cola
durable y reintentos (#64); retirada de `ATTENDED_CHANNELS` en el orquestador
(#65); interfaz del panel (#66). Hasta #65 el orquestador responde `422` a los
canales que no son `telegram` ni `whatsapp`; esta feature lo contempla (R27).

Quién cumple cada requirement:

- **contracts** (`contracts/CONTRATOS.md`): R1–R2.
- **telegram_gateway**: R3–R49.
- **Configuración** (`config.py`, `.env.example`): R50–R51.
- **Todos**: R52.

Definiciones:

- **Canal genérico**: fila de `canales` con `tipo_adaptador = webhook_generico`
  (tipo nuevo, registrado por esta feature, no gestionado por el entorno).
- **Secreto del canal**: el de #61 (`secrets.token_urlsafe(32)`, 43 caracteres);
  su UTF-8 es la clave HMAC.
- **Dirección bloqueada**: dirección IP privada (RFC 1918), loopback,
  link-local (incluye `169.254.169.254`, metadatos), no especificada, multicast,
  reservada, CGNAT (`100.64.0.0/10`), IPv6 de unicast local único (`fc00::/7`) o
  IPv4 mapeada en IPv6 que cumpla alguna de las anteriores.
- **Modo de desarrollo**: `WEBHOOK_ALLOW_PRIVATE_CALLBACKS=true`.

## Cobertura del acceptance de #62

| Criterio del acceptance | Requirements |
|---|---|
| Ruta pública; solo canales activos; 404 indistinto | R6–R9 |
| HMAC en tiempo constante; 401 por firma o ventana | R3–R5, R10–R15 |
| Formato normalizado o conversión por adaptador; 422 `{error, message}` | R16–R22 |
| Idempotencia por `(canal_id, external_message_id)` | R23–R25 |
| Respuesta rápida; guarda `ATTENDED_CHANNELS` | R26–R28 |
| Callback saliente firmado; fallo = envío fallido | R35–R40 |
| Anti-SSRF | R41–R47 |
| Pruebas y contrato documentado | R1–R2, R29–R34, R48–R52 |

## contracts

**R1.** `CONTRATOS.md` DEBE documentar el comportamiento de #62 en la sección
«Canal genérico (webhook firmado)»: sin la frase «hasta entonces no existen»,
con el tipo de adaptador `webhook_generico` y su `config.callback_url` opcional
(https, ≤ 2048 caracteres), el orden de errores (`404`, `413`, `401`, `422`), las
filas nuevas `413 payload_too_large` y `503` (`channel_store_unavailable`,
`channel_secrets_unavailable`) de `POST /webhooks/{canal_id}`, los ajustes
`WEBHOOK_SIGNATURE_WINDOW_SECONDS`, `WEBHOOK_MAX_BODY_BYTES` y
`WEBHOOK_ALLOW_PRIVATE_CALLBACKS`, la regla anti-SSRF y que `502 upstream_error`
en `POST /send` cubre el callback fallido o bloqueado.

**R2.** Los dos ejemplos firmados de `CONTRATOS.md` DEBEN ser verificables: con el
secreto `secreto-de-ejemplo`, el HMAC-SHA256 de `<X-Lazaro-Timestamp>.<cuerpo>`
del bloque HTTP coincide con su `X-Lazaro-Signature`, calculado por una prueba que
extrae ambos valores del documento.

## telegram_gateway — firma (`signature.py`, puro)

**R3.** `sign_payload(secret, timestamp, body)` DEBE devolver el HMAC-SHA256 en 64
caracteres hexadecimales en minúsculas de los bytes `<timestamp>.` seguidos de
`body`, con la clave `secret` en UTF-8, y reproducir las dos firmas de
`CONTRATOS.md`.

**R4.** `verify_signature(secret, timestamp_header, signature_header, body, now,
window_seconds)` DEBE devolver verdadero solo si el timestamp es un entero
decimal sin signo, la firma coincide (comparada con `hmac.compare_digest`) y
|`now` − timestamp| ≤ `window_seconds`; ante un encabezado ausente (`None`), no
decimal o de longitud distinta de 64 DEBE devolver falso sin lanzar excepciones.

**R5.** SI el timestamp está fuera de la ventana (en el pasado o en el futuro)
ENTONCES `verify_signature` DEBE devolver falso aunque la firma sea correcta.

## telegram_gateway — ruta `POST /webhooks/{canal_id}`

**R6.** CUANDO llega `POST /webhooks/{canal_id}` sin `X-Service-Token`, el sistema
NO DEBE rechazarla por falta de token, y una petición a cualquier otra ruta
no pública sin token DEBE seguir respondiendo `401 unauthorized`.

**R7.** SI `{canal_id}` no tiene fila en `canales` ENTONCES el sistema DEBE
responder `404 not_found`.

**R8.** SI el canal está inactivo ENTONCES el sistema DEBE responder `404
not_found` con el mismo código y el mismo cuerpo que en R7.

**R9.** SI el canal no tiene secreto guardado (`telegram`, `whatsapp`), su tipo de
adaptador no está registrado o no está disponible ENTONCES el sistema DEBE
responder `404 not_found` con el mismo cuerpo que en R7, sin verificar firma.

**R10.** SI falta `X-Lazaro-Signature` ENTONCES el sistema DEBE responder `401
unauthorized` sin entregar nada al orquestador.

**R11.** SI `X-Lazaro-Signature` no corresponde al secreto del canal y al cuerpo
exacto recibido ENTONCES el sistema DEBE responder `401 unauthorized` sin
entregar nada al orquestador.

**R12.** SI `X-Lazaro-Timestamp` falta, no es un entero decimal o está fuera de
`WEBHOOK_SIGNATURE_WINDOW_SECONDS` respecto al reloj del gateway ENTONCES el
sistema DEBE responder `401 unauthorized`, aunque la firma sea correcta.

**R13.** CUANDO la firma es válida y el timestamp está dentro de la ventana, el
sistema DEBE continuar con la validación del cuerpo (R16–R22).

**R14.** El sistema DEBE aplicar los errores en este orden: `404` (R7–R9), `413`
(R15), `401` (R10–R12), `422` (R16–R22), de modo que un cuerpo inválido con firma
incorrecta responde `401` y nunca `422`.

**R15.** SI el cuerpo supera `WEBHOOK_MAX_BODY_BYTES` ENTONCES el sistema DEBE
responder `413 payload_too_large` sin verificar firma ni entregar nada.

## telegram_gateway — formato del cuerpo

**R16.** SI el cuerpo no es JSON UTF-8 o su valor raíz no es un objeto ENTONCES el
sistema DEBE responder `422` con `{"error": "validation_error", "message": ...}`.

**R17.** CUANDO el cuerpo es un objeto, el sistema DEBE pasarlo a
`recibir_mensaje` del adaptador del canal y usar el `NormalizedMessage` devuelto.

**R18.** SI `recibir_mensaje` devuelve `None` ENTONCES el sistema DEBE responder
`422 validation_error` sin entregar nada.

**R19.** El adaptador `webhook_generico`, CUANDO recibe un objeto que valida como
`NormalizedMessage` con `direction` `inbound`, DEBE devolverlo; si no valida,
DEBE devolver `None` sin lanzar excepciones (formato normalizado del contrato).

**R20.** CUANDO el adaptador de un canal define su propio formato (adaptador de
prueba cuyo `recibir_mensaje` traduce un payload propio), el sistema DEBE
entregar al orquestador el `NormalizedMessage` que ese adaptador devuelve.

**R21.** SI el `channel` del mensaje normalizado difiere de `{canal_id}` ENTONCES
el sistema DEBE responder `422 validation_error` sin entregar nada.

**R22.** SI el `direction` del mensaje normalizado no es `inbound` ENTONCES el
sistema DEBE responder `422 validation_error` sin entregar nada.

## telegram_gateway — idempotencia y entrega

**R23.** CUANDO llega un mensaje válido con un par `(canal_id, external_message_id)`
no visto, el sistema DEBE marcarlo, entregar el `NormalizedMessage` una vez al
orquestador y responder `200` con `{"status": "accepted"}`.

**R24.** CUANDO llega un par `(canal_id, external_message_id)` ya visto, el
sistema DEBE responder `200` con `{"status": "duplicate"}` sin volver a entregar.

**R25.** CUANDO el mismo `external_message_id` llega por dos canales genéricos
distintos, el sistema DEBE aceptar ambos.

**R26.** SI el almacén de deduplicación falla ENTONCES el sistema DEBE tratar el
mensaje como nuevo y registrar un ERROR con el tipo de la excepción, igual que
`/telegram/webhook`.

**R27.** SI el orquestador falla o rechaza el mensaje (incluido `422` por la guarda
`ATTENDED_CHANNELS`) ENTONCES el sistema DEBE registrar un ERROR
`webhook_forward_failed` con `channel_id` y el motivo, no reintentar y responder
`200 accepted`.

**R28.** El sistema DEBE entregar el mensaje con una sola llamada a
`POST /messages` y responder al terminar esa llamada, sin esperar al
procesamiento del bot.

**R29.** SI el almacén de canales falla ENTONCES el sistema DEBE responder `503
channel_store_unavailable`; SI los secretos guardados no se pueden descifrar
ENTONCES DEBE responder `503 channel_secrets_unavailable`; ninguno entrega nada.

**R30.** El sistema NO DEBE incluir el secreto del canal, la firma recibida ni el
cuerpo del mensaje en logs ni en respuestas de error del webhook y del callback.

## telegram_gateway — tipo de adaptador `webhook_generico`

**R31.** El `CHANNEL_REGISTRY` por defecto DEBE contener `webhook_generico`
(`managed_by_environment = False`, disponible siempre) además de `telegram` y
`whatsapp_cloud`, y `POST /channels` con ese tipo DEBE responder `201` y listarlo
en `adapter_types`.

**R32.** `capacidades()` del canal genérico DEBE informar `free_text_allowed=true`,
`supports_buttons=false`, `supports_links=false`, `supports_images=false`,
`supports_files=false`, `supports_audio=false`, `requires_template=false`,
`max_options=0`, `min_list_options=0` y `max_list_options=0`, de modo que
`degrade_blocks` entregue solo texto.

**R33.** SI se construye el canal genérico sin secreto ENTONCES `build` DEBE
lanzar `ChannelNotConfigured`.

**R34.** SI `POST /channels` o `PATCH /channels/{id}` de un canal genérico trae un
`config.callback_url` que no es una URL `https` con host, sin credenciales
incrustadas y de hasta 2048 caracteres (fuera del modo de desarrollo, que admite
también `http`), ENTONCES el sistema DEBE responder `422 validation_error` sin
persistir; un canal sin `callback_url` es válido.

## telegram_gateway — callback saliente

**R35.** CUANDO se envía una respuesta por un canal genérico, el sistema DEBE
hacer `POST` a `config.callback_url` con `Content-Type: application/json` y un
`NormalizedMessage` `outbound` (`channel` = id del canal, `external_user_id` y
`external_chat_id` = destino, `kind` `text`, `external_message_id` único con
prefijo `out-`, `received_at` = reloj del gateway).

**R36.** El callback DEBE llevar `X-Lazaro-Timestamp` (segundos Unix del reloj del
gateway) y `X-Lazaro-Signature` = `sign_payload(secreto, timestamp, bytes
enviados)`, verificable por el receptor con el algoritmo de `CONTRATOS.md`.

**R37.** CUANDO el receptor responde 2xx, el canal DEBE devolver el estado `sent`.

**R38.** SI el receptor responde con un código no 2xx (incluidos 3xx, que no se
siguen) ENTONCES el canal DEBE devolver `failed` y `POST /send` DEBE responder
`502 upstream_error`.

**R39.** SI ocurre un error de red o de tiempo de espera ENTONCES el canal DEBE
devolver `failed`, registrar solo el tipo de la excepción y `POST /send` DEBE
responder `502 upstream_error`.

**R40.** CUANDO el texto saliente supera `MAX_TEXT_LENGTH`, el canal DEBE enviarlo
en varios callbacks consecutivos, en orden, cada uno dentro del límite, y
detenerse devolviendo `failed` en el primer fallo.

## telegram_gateway — anti-SSRF

**R41.** `validate_callback_url(url, resolver, allow_private)` DEBE aceptar solo
URLs `https` con host, sin credenciales incrustadas, y lanzar
`CallbackUrlRejected` en otro caso (`http`, `file`, `ftp`, sin host, con `user@`).

**R42.** SI alguna dirección a la que resuelve el host es una dirección bloqueada
ENTONCES `validate_callback_url` DEBE lanzar `CallbackUrlRejected`, probado con
ejemplos de cada clase de la definición (`10.0.0.5`, `127.0.0.1`, `169.254.169.254`,
`100.64.0.1`, `0.0.0.0`, `::1`, `fe80::1`, `fd00::1`, `::ffff:127.0.0.1`).

**R43.** SI un host resuelve a varias direcciones y alguna está bloqueada
ENTONCES `validate_callback_url` DEBE rechazarlo (todas deben ser públicas).

**R44.** SI el host es una IP literal ENTONCES `validate_callback_url` DEBE
validarla sin consultar al resolvedor; SI el host no resuelve ENTONCES DEBE
lanzar `CallbackUrlRejected`.

**R45.** CUANDO el cliente HTTP del callback envía la petición, DEBE conectarse a
la dirección ya validada (sin una segunda resolución) conservando el nombre
original en `Host` y en SNI, y NO DEBE seguir redirecciones.

**R46.** SI la URL es rechazada al enviar ENTONCES el canal DEBE devolver `failed`
sin hacer ninguna petición, registrar un WARNING `callback_blocked` con
`channel_id` (sin la URL) y `POST /send` DEBE responder `502 upstream_error`.

**R47.** SI el canal genérico no tiene `config.callback_url` ENTONCES `enviar_mensaje`
DEBE lanzar `ChannelNotConfigured` sin hacer ninguna petición.

## Configuración

**R48.** MIENTRAS `WEBHOOK_ALLOW_PRIVATE_CALLBACKS=true`, `validate_callback_url`
DEBE admitir `http` y direcciones bloqueadas (desarrollo); por defecto DEBE ser
`false`.

**R49.** SI `APP_ENV=production` y `WEBHOOK_ALLOW_PRIVATE_CALLBACKS=true` ENTONCES
`Settings` DEBE lanzar `ProductionConfigError` indicando esa variable.

**R50.** `Settings` DEBE leer `WEBHOOK_SIGNATURE_WINDOW_SECONDS` (entero, por
defecto `DEFAULT_SIGNATURE_WINDOW_SECONDS` = 300, entre 1 y 3600) y
`WEBHOOK_MAX_BODY_BYTES` (entero, por defecto 1048576, entre 1024 y 10485760), y
rechazar valores fuera de rango con `ValidationError`.

**R51.** `.env.example` DEBE declarar `WEBHOOK_SIGNATURE_WINDOW_SECONDS=300`,
`WEBHOOK_MAX_BODY_BYTES=1048576` y `WEBHOOK_ALLOW_PRIVATE_CALLBACKS=false` con un
comentario sobre el riesgo SSRF.

## Todos

**R52.** La batería existente de `services/telegram_gateway/tests` y
`contracts/tests` DEBE pasar sin modificaciones, salvo los tests que `design.md`
§6 sustituye por pruebas del comportamiento nuevo.
