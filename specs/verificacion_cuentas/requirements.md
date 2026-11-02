# #20 verificacion_cuentas — Requirements

Servicio: **orchestrator** (único). Autenticación `X-Service-Token`, forma de
errores y `422 validation_error` siguen `contracts/CONTRATOS.md` §Reglas comunes;
no se repiten aquí.

## R1
CUANDO el orquestador recibe `POST /profiles` con `username` (3–64, `^[a-z0-9_.-]+$`
tras pasar a minúsculas), `role` ∈ {`admin`, `asesor`, `cliente`} y `password`
(longitud ≥ `PROFILE_PASSWORD_MIN_LENGTH`), el sistema DEBE crear el perfil y
responder `201` con `{id, username, role, linked: false}`, sin `password` ni hash.

## R2
SI `POST /profiles` llega con un `username` que ya existe sin distinguir
mayúsculas ENTONCES el sistema DEBE responder `409` con `error` = `username_taken`
sin crear ni modificar perfiles.

## R3
El sistema DEBE guardar la contraseña solo como `pbkdf2_sha256$<iteraciones>$<sal>$<hash>`
(sal aleatoria de 16 bytes por perfil), de modo que `verify_password(clave, hash)`
devuelva `True` solo para la clave original y ninguna fila, respuesta ni log
contenga la contraseña en claro.

## R4
CUANDO el orquestador recibe `POST /profiles/{id}/link-token` para un perfil
existente, el sistema DEBE emitir un token aleatorio (`secrets.token_urlsafe(32)`),
guardar solo su SHA-256 con `expires_at = ahora + LINK_TOKEN_TTL_MINUTES` y
responder `201` con `{token, link, expires_at}`.

## R5
SI `POST /profiles/{id}/link-token` se pide para un perfil inexistente ENTONCES
el sistema DEBE responder `404` con `error` = `profile_not_found` sin emitir token.

## R6
CUANDO `POST /messages` trae un texto `/start <token>` cuyo token existe, no está
usado y no ha expirado, el sistema DEBE, en una sola operación atómica, marcar el
token como usado y fijar el `telegram_user_id` del remitente en el perfil, y
enviar al remitente `link_success_reply`.

## R7
SI el token de `/start <token>` no existe, ya fue usado, expiró, o el
`telegram_user_id` ya está vinculado a otro perfil ENTONCES el sistema DEBE
enviar el mismo texto `link_failed_reply` en todos los casos, sin vincular y sin
consumir el token.

## R8
SI dos mensajes `/start <token>` con el mismo token se procesan a la vez
ENTONCES el sistema DEBE vincular como máximo uno; el otro recibe `link_failed_reply`.

## R9
CUANDO el orquestador procesa un `/start <token>`, el sistema NO DEBE guardar el
token (ni su texto) en `messages`, `events` ni logs, ni pasarlo al RAG, al LLM o
al traspaso.

## R10
SI `POST /profiles` o `POST /profiles/{id}/link-token` llegan sin un
`X-Service-Token` válido ENTONCES el sistema DEBE responder `401` con
`error` = `unauthorized` sin crear perfil ni token.

## Cobertura del acceptance
- Perfiles, rol, unicidad, hash → R1, R2, R3.
- Endpoint interno autenticado, token de un solo uso, TTL 15 min → R4, R5, R10.
- Vínculo por Telegram y consumo atómico → R6, R8.
- Sin credenciales/tokens en Telegram, errores no revelan perfil → R4 (el token
  vuelve solo al llamador HTTP), R7, R9.
- Pruebas de roles, inválido/expirado/reutilizado, vínculo, unicidad, hash → R1–R8.
