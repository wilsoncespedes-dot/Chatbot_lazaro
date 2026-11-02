# #29 panel_asesores — Requirements

Servicio: **orchestrator** (único en esta feature). Rutas bajo `/asesor`, HTML
renderizado en el servidor con el mismo patrón de sesión, CSRF, cabeceras y
redacción del panel admin (#21). El panel complementa los comandos de Telegram
de #16: responder, asignar y cerrar casos con las rutas ya publicadas
(`POST /cases/{id}/reply` del orquestador; `authorize`, `assign` y `close` de
handover) y las reglas S12 que decide handover. No añade acciones
administrativas ni reglas de negocio nuevas.

**Identidad.** El `advisor_id` de cada acción es siempre el `telegram_user_id`
vinculado (#20) al perfil de la sesión. Nunca sale de un campo del formulario,
de la URL ni de una cabecera.

**Bloqueo parcial (R13).** Handover no publica una ruta para listar casos. El
estado y el asesor de cada caso solo viven en handover (`handover_cases`); el
orquestador solo guarda `case_links`. R13 depende de una feature de contrato
previa (ver `design.md` y `progress/spec_panel_asesores.md`). R1–R12 y R14–R15 no
dependen de ella.

## Sesión y acceso

## R1
CUANDO el orquestador recibe `POST /asesor/login` con `username` y `password` de
un perfil con rol `asesor` que pasan `verify_password`, el sistema DEBE crear una
sesión con expiración `ADMIN_SESSION_TTL_MINUTES` y responder `303` hacia
`/asesor` con una cookie `advisor_session` `HttpOnly`, `SameSite=Strict` y
`Path=/asesor` (más `Secure` si `ADMIN_COOKIE_SECURE`).

## R2
SI `POST /asesor/login` trae un usuario inexistente, una contraseña incorrecta o
un perfil con rol distinto de `asesor` (incluidos `admin` y `cliente`) ENTONCES
el sistema DEBE responder `401` con la misma página y el mismo mensaje en todos
los casos, sin crear sesión.

## R3
SI un mismo `username` normalizado, o una misma IP, acumula
`ADMIN_LOGIN_MAX_ATTEMPTS` fallos de login (sumando `/admin/login` y
`/asesor/login`) dentro de `ADMIN_LOGIN_WINDOW_MINUTES` ENTONCES el sistema DEBE
responder `429` a `POST /asesor/login` con el mensaje genérico de R2, antes de
llamar a `verify_password` y sin crear sesión.

## R4
MIENTRAS una petición a `/asesor` o `/asesor/*` (salvo `GET`/`POST
/asesor/login`) no traiga una cookie `advisor_session` válida (ausente,
desconocida, expirada, cerrada con `POST /asesor/logout`, o cuyo perfil ya no
tiene rol `asesor`), el sistema DEBE responder `303` hacia `/asesor/login` sin
ejecutar la operación pedida.

## R5
El sistema NO DEBE aceptar una sesión de rol `admin` en `/asesor/*` ni una
sesión de rol `asesor` en `/admin/*`; en ambos casos la petición recibe el
`303` al login de su panel y las rutas `/admin/*` existentes conservan su
comportamiento actual.

## R6
SI un `POST` a `/asesor/*` con sesión válida (salvo `/asesor/login`) llega sin
`csrf_token` o con uno distinto al de su sesión ENTONCES el sistema DEBE
responder `403` sin llamar a handover ni al gateway.

## R7
El sistema DEBE servir toda respuesta HTML de `/asesor` con las mismas
cabeceras que `/admin` (CSP `default-src 'self'; form-action 'self';
frame-ancestors 'none'`, `X-Content-Type-Options: nosniff`, `Cache-Control:
no-store`) y sin `<script>`, `<link>` ni `<img>` hacia un origen externo.

## R8
El sistema NO DEBE incluir el valor de `SERVICE_TOKEN`, la cabecera
`X-Service-Token`, ninguna contraseña ni ningún `password_hash` en el cuerpo,
las cabeceras ni las cookies de las respuestas de `/asesor`.

## Acciones sobre casos

## R9
SI el perfil de la sesión no tiene `telegram_user_id` vinculado ENTONCES el
sistema DEBE responder `403` con el código `telegram_not_linked` a
`POST /asesor/reply`, `/asesor/assign` y `/asesor/close`, sin llamar a handover
ni al gateway.

## R10
CUANDO un asesor con sesión envía `POST /asesor/reply` con `case_id` y `text`
válidos (`Identifier` y `CaseReplyRequest`), el sistema DEBE ejecutar
`reply_to_case` con `advisor_id` = `telegram_user_id` del perfil de la sesión y,
si tiene éxito, responder `303` hacia `/asesor?ok=reply`.

## R11
CUANDO un asesor con sesión envía `POST /asesor/assign` con un `case_id`
válido, el sistema DEBE llamar a `POST /cases/{id}/assign` de handover con
`advisor_id` = `telegram_user_id` del perfil de la sesión y, con `200`, responder
`303` hacia `/asesor?ok=assign`.

## R12
CUANDO un asesor con sesión envía `POST /asesor/close` con un `case_id` válido,
el sistema DEBE pedir `authorize` con `action` = `close` y después `close` a
handover con `advisor_id` = `telegram_user_id` del perfil de la sesión, enviar al
cliente vinculado el aviso `CASE_CLOSED_REPLY` (como `/cerrar` de #16) y
responder `303` hacia `/asesor?ok=close`.

## R13 (bloqueado por contrato previo)
CUANDO un asesor con sesión pide `GET /asesor/cases`, el sistema DEBE mostrar
exclusivamente los casos que la ruta de listado de handover devuelva para el
`advisor_id` = `telegram_user_id` del perfil de la sesión, con solo `case_id`,
`status`, `created_at` y las acciones que handover indique, sin reenviar ningún
parámetro de asesor recibido del navegador.

## Errores

## R14
SI handover o `reply_to_case` rechazan una acción de R10–R12 ENTONCES el sistema
DEBE responder con la página de error del panel y el código del contrato
(`403 forbidden`, `404 not_found`, `409 case_closed`, `422 validation_error`,
`502 upstream_error` si handover o el gateway no responden), con un mensaje fijo
por código, sin mostrar el `message` de handover y sin escribir nada más en el
caso.

## R15
CUANDO handover responde `403 forbidden` a una acción de R10–R12, el sistema
DEBE registrar el evento `advisor_forbidden` en el contacto vinculado al caso
(o solo un `WARNING` en el log si no hay contacto vinculado), igual que
`_record_forbidden` de #14.

## Cobertura del acceptance

| Criterio | Requirements |
|----------|--------------|
| 1. Login/logout de asesor; cliente no accede; admin conserva sus permisos | R1, R2, R3, R4, R5 |
| 2. Solo los casos que las reglas actuales permiten, incluidos huérfanos | R13 (bloqueado), R9–R12 + R14 (handover decide por caso) |
| 3. Responder, asignar y cerrar con rutas y reglas existentes, sin reglas en el navegador | R10, R11, R12, R14, R15 |
| 4. Sesión, CSRF, datos personales; `X-Service-Token` no llega al navegador | R4, R6, R7, R8, R13, R14 |
| 5. Tests: roles, aislamiento entre asesores, CSRF, errores del servicio, acciones | R1–R15 (ver tasks) |

Aislamiento entre asesores: el `advisor_id` sale siempre de la sesión
(R10–R12); un asesor que actúa sobre el caso `assigned` de otro recibe el `403`
de handover (R14) y queda `advisor_forbidden` (R15). Los casos huérfanos los
resuelve handover con la regla publicada por #17 (cerrar sí, responder/asignar
no); el panel no la replica.
