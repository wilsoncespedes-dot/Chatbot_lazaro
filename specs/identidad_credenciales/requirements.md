# #38 identidad_credenciales — Requirements

Servicio afectado: **orchestrator** (módulo de identidad propio dentro del
orquestador, según la decisión registrada). Ningún otro servicio cambia su
código; el gateway Telegram ya dibuja `LinkBlock` como botón URL (#36).

Vocabulario:

- **Credencial**: perfil `cliente` (#20) + fila en `client_credentials`
  (`valid_from`, `valid_until`, `revoked_at`).
- **Estado de credencial** (calculado, nunca almacenado como contador):
  `revocada` si `revoked_at` no es nulo; `no_iniciada` si `now < valid_from`;
  `vencida` si `now >= valid_until`; `por_vencer` si
  `valid_until - now <= CREDENTIAL_EXPIRY_NOTICE_DAYS`; si no, `vigente`.
  `por_vencer` cuenta como vigente para el acceso.
- **Enlace de login**: token firmado de un solo uso que referencia el
  contacto `(canal, external_user_id, external_chat_id)` que lo recibió.
- **Sesión**: fila en `client_sessions` que une un `contact_id` con un
  `profile_id` (= `cliente_id`). Activa mientras `ended_at` es nulo.
- **Política de identidad**: valores de tiempo/límite leídos de variables de
  entorno y sobrescribibles por claves `identity.*` de `app_settings`.

Trazabilidad con el acceptance de `feature_list.json` (#38):

| Acceptance | Requirements |
|---|---|
| A1 enlace firmado, un uso, caducidad; login asocia el chat | R1–R10, R12–R17, R49 |
| A2 sin vinculación manual ni comparación de número/ID | R17, R18 |
| A3 hash seguro, vigencia, revocación, bloqueo, sin filtrar contraseñas | R11, R19–R25, R36, R37, R48, R50 |
| A4 una sesión activa; cierre manual o inactividad; nuevo enlace | R26–R33 |
| A5 vencida → Sin acceso; renovación reactiva; revocación deniega | R34, R35, R38–R42, R45, R46 |
| A6 pruebas y `./init.sh` verde | R43, R44, R47 (y el test de cada R) |

## Emisión del enlace

## R1
CUANDO un contacto con consentimiento vigente pasa a `awaiting_login` por el
botón Acepto (#37), el orchestrator DEBE enviar al mismo canal y chat un
`LinkBlock` cuyo `url` es `IDENTITY_PUBLIC_BASE_URL` + `/acceso?t=<token>`.

## R2
MIENTRAS un contacto está en `awaiting_login`, CUANDO llega un mensaje de
texto suyo, el orchestrator DEBE responder con el texto `login_reminder` y un
`LinkBlock` con un enlace recién emitido.

## R3
El orchestrator DEBE emitir tokens con la forma `<nonce>.<firma>`, donde
`nonce` proviene de `secrets.token_urlsafe(32)` y `firma` es
HMAC-SHA256(`IDENTITY_LINK_SIGNING_KEY`, `"login-link:v1:" + nonce`) en hex.

## R4
El orchestrator DEBE guardar solo el SHA-256 del token junto con `contact_id`,
`channel`, `external_chat_id`, `expires_at` y `used_at`; el token en claro NO
DEBE persistirse.

## R5
CUANDO se emite un enlace nuevo para un contacto, el orchestrator DEBE
invalidar (marcar `used_at`) todos los enlaces sin usar previos de ese
contacto.

## R6
El orchestrator DEBE fijar `expires_at = now + IDENTITY_LINK_TTL_MINUTES`
(default 15, rango 1–1440).

## R7
SI `IDENTITY_PUBLIC_BASE_URL` o `IDENTITY_LINK_SIGNING_KEY` están vacíos ENTONCES
el orchestrator DEBE omitir el `LinkBlock`, enviar solo `login_reminder` y
registrar el log `identity_link_unavailable` sin crear filas de enlace.

## R8
SI `APP_ENV=production` y `IDENTITY_PUBLIC_BASE_URL` no empieza por `https://`
o `IDENTITY_LINK_SIGNING_KEY` tiene menos de 32 caracteres ENTONCES `Settings`
DEBE lanzar `ProductionConfigError` nombrando la variable.

## R9
SI el texto configurable `login_link_label` está vacío ENTONCES el
orchestrator DEBE comportarse como en R7 (sin enlace, log
`identity_texts_not_configured`).

## Página de login (`/acceso`)

## R10
CUANDO llega `GET /acceso?t=<token>`, el orchestrator DEBE responder `200`
con un formulario HTML (usuario, contraseña, token oculto) sin consumir el
token y sin cargar recursos de dominios externos.

## R11
El orchestrator DEBE servir `GET/POST /acceso` sin exigir `X-Service-Token`
y con los encabezados `Cache-Control: no-store`, `Referrer-Policy: no-referrer`
y la CSP de `admin.security_headers()`.

## R12
SI el token de `GET` o `POST /acceso` tiene firma inválida, no existe, ya se
usó o venció ENTONCES el orchestrator DEBE responder `400` con el mismo
mensaje genérico de enlace inválido, sin validar credenciales.

## R13
SI la firma del token es inválida ENTONCES el orchestrator NO DEBE consultar
el repositorio de enlaces.

## R14
CUANDO `POST /acceso` trae token válido y usuario/contraseña correctos de un
perfil `cliente` con credencial `vigente` o `por_vencer` y sin sesión activa,
el orchestrator DEBE crear una sesión que une el `contact_id` del enlace con
el `profile_id` y responder `200` con la página de éxito.

## R15
CUANDO se crea una sesión, el orchestrator DEBE marcar el enlace como usado en
la misma transacción, de modo que un segundo `POST /acceso` con el mismo token
cae en R12.

## R16
CUANDO se crea una sesión con credencial vigente, el orchestrator DEBE aplicar
`ConversationEvent.LOGIN_VALID` al contacto (→ `active`) y enviar
`active_welcome` a su canal y chat.

## R17
El orchestrator DEBE tomar el contacto a asociar exclusivamente del registro
del enlace; cualquier campo del formulario distinto de `t`, `username` y
`password` DEBE ignorarse.

## R18
El login NO DEBE leer ni comparar `profiles.telegram_user_id`, el número de
WhatsApp ni ningún ID de canal con datos del perfil, y NO DEBE modificar
`profiles.telegram_user_id`.

## Credenciales y seguridad

## R19
CUANDO se crea una credencial de cliente, el orchestrator DEBE guardar la
contraseña con `hashlib.scrypt` en formato
`scrypt$<n>$<r>$<p>$<sal_hex>$<hash_hex>` (sal aleatoria de 16 bytes).

## R20
`verify_password` DEBE validar tanto hashes `scrypt$…` como los
`pbkdf2_sha256$…` existentes de #20, con comparación en tiempo constante.

## R21
SI el usuario no existe, la contraseña es incorrecta o el perfil no tiene rol
`cliente` ENTONCES `POST /acceso` DEBE responder `401` con el mismo mensaje
genérico (idéntico en los tres casos), dejando el token sin consumir.

## R22
SI el usuario no existe ENTONCES el orchestrator DEBE ejecutar igualmente una
verificación contra un hash ficticio antes de responder.

## R23
SI el número de intentos fallidos del usuario o de la IP dentro de
`IDENTITY_LOCKOUT_MINUTES` (default 15) alcanza `IDENTITY_LOGIN_MAX_ATTEMPTS`
(default 5) ENTONCES `POST /acceso` DEBE responder `429` sin verificar la
contraseña, incluso si es correcta.

## R24
CUANDO un login de cliente tiene éxito, el orchestrator DEBE borrar los
intentos fallidos de ese usuario.

## R25
Ni la contraseña ni el token en claro DEBEN aparecer en mensajes enviados al
gateway, en filas de eventos/auditoría ni en registros de log del proceso
del orquestador, incluido el log de acceso de uvicorn (`uvicorn.access`), donde
el valor de `t=` de `/acceso?t=<token>` DEBE aparecer redactado. Supuesto: los
logs del proxy de Render quedan fuera del alcance de este requisito.

## Sesiones

## R26
SI la credencial ya tiene una sesión activa (tras aplicar R30) ENTONCES `POST
/acceso` DEBE responder `409` con el mensaje "cierra la otra sesión o espera",
sin crear sesión ni consumir el token.

## R27
El repositorio DEBE garantizar con un índice único parcial
(`WHERE ended_at IS NULL`) que una credencial y un contacto tengan como máximo
una sesión activa; ante dos logins concurrentes solo uno DEBE crear sesión.

## R28
MIENTRAS un contacto tiene sesión activa, CUANDO llega un mensaje suyo, el
orchestrator DEBE actualizar `last_activity_at` de la sesión.

## R29
CUANDO llega un mensaje cuyo texto normalizado coincide exactamente con un
valor de `IDENTITY_LOGOUT_COMMANDS` (default `/salir,cerrar sesion,cerrar
sesión`) y el contacto tiene sesión activa, el orchestrator DEBE finalizar la
sesión con motivo `logout`, aplicar `SESSION_CLOSED` y enviar
`session_closed_reply` junto con un `LinkBlock` nuevo.

## R30
CUANDO llega un mensaje o un intento de login y la sesión activa implicada
tiene `now - last_activity_at >= IDENTITY_SESSION_IDLE_MINUTES` (default 60),
el orchestrator DEBE finalizarla con motivo `idle` y aplicar
`SESSION_IDLE_TIMEOUT` a su contacto, salvo si el contacto está en
`with_advisor`.

## R31
CUANDO R30 finaliza la sesión del contacto que escribe, el orchestrator DEBE
responder `login_reminder` con un `LinkBlock` nuevo y NO DEBE enviar el
mensaje al flujo RAG/LLM.

## R32
CUANDO una sesión finaliza por cualquier motivo, el orchestrator NO DEBE
modificar ni borrar filas de `privacy_consents` del contacto.

## R33
MIENTRAS el estado del contacto es `active` o `no_access` y no tiene sesión
activa, CUANDO llega un mensaje suyo, el orchestrator DEBE aplicar
`SESSION_CLOSED` (→ `awaiting_login`) y responder como en R2.

## Vigencia, renovación y revocación

## R34
CUANDO se crea una sesión con credencial `vencida`, el orchestrator DEBE
aplicar `LOGIN_EXPIRED` (→ `no_access`) y enviar `suspended_reply` al chat.

## R35
MIENTRAS el contacto está en `active`, CUANDO llega un mensaje y su
credencial está `vencida`, el orchestrator DEBE aplicar `CREDENTIAL_EXPIRED`
(→ `no_access`), enviar `suspended_reply` y NO DEBE llamar a RAG/LLM.

## R36
SI la credencial está `revocada` o `no_iniciada`, o el perfil `cliente` no
tiene fila de credencial, ENTONCES `POST /acceso` DEBE responder `403` con un
mensaje genérico de acceso no habilitado y NO DEBE crear sesión.

## R37
El orchestrator DEBE registrar en `identity_audit` cada login exitoso, login
rechazado por credencial (R26, R36), cierre de sesión (con motivo),
renovación y revocación, con `profile_id`, `contact_id` (si aplica), acción,
motivo y fecha.

## R38
CUANDO `POST /clients` (interno, `X-Service-Token`) recibe `username` y
`password` válidos, el orchestrator DEBE crear en una transacción un perfil
`cliente` y su credencial con `valid_from = now` (o el valor dado) y
`valid_until = valid_from + CREDENTIAL_VALIDITY_DAYS` (default 30) si no se
indica, y responder `201` sin hash ni contraseña.

## R39
CUANDO `POST /clients/{profile_id}/renew` se aplica a una credencial no
revocada, el orchestrator DEBE fijar
`valid_until = max(valid_until, now) + CREDENTIAL_VALIDITY_DAYS`.

## R40
CUANDO una renovación deja vigente una credencial cuyo contacto con sesión
activa está en `no_access`, el orchestrator DEBE aplicar
`CREDENTIAL_RENEWED` (→ `active`) y enviar `active_welcome` a ese chat.

## R41
MIENTRAS el contacto está en `no_access` con sesión activa, CUANDO llega un
mensaje y la credencial está vigente, el orchestrator DEBE aplicar
`CREDENTIAL_RENEWED` antes de enrutar el mensaje.

## R42
CUANDO `POST /clients/{profile_id}/revoke` o
`POST /clients/{profile_id}/close-session` se ejecuta, el orchestrator DEBE
finalizar la sesión activa (motivo `revoked` o `admin_closed`), aplicar
`SESSION_CLOSED` a su contacto y enviar `session_closed_reply` a ese chat.

## Integración y regresión

## R43
El reductor de #37 DEBE incluir las transiciones
`(no_access, session_closed) → awaiting_login` y
`(no_access, session_idle_timeout) → awaiting_login` sin alterar las existentes.

## R44
DONDE `IDENTITY_LOGIN_REQUIRED=false` (default `true`), el orchestrator DEBE
conservar el enrutamiento previo a #38 (sin exigir sesión) para contactos
consentidos.

## R45
`GET /clients/{profile_id}` (interno) DEBE devolver `status` calculado según el
vocabulario, `days_remaining = (valid_until.date() - now.date()).days`
(mínimo 0) y `has_active_session`, sin hash.

## R46
SI `POST /clients/{profile_id}/renew` se aplica a una credencial revocada
ENTONCES el orchestrator DEBE responder `409` con
`{"error": "credential_revoked"}` sin cambiar `valid_until`.

## R47
MIENTRAS `IDENTITY_LOGIN_REQUIRED=true`, CUANDO llega un mensaje de un
contacto consentido sin fila en `conversation_states`, el orchestrator DEBE
tratarlo como `awaiting_login` (R2).

## R48
SI un intento de `POST /acceso` cae en R21 ENTONCES el orchestrator DEBE
registrar un intento fallido en `identity_login_attempts` con el usuario
normalizado y la IP del cliente.

## R49
CUANDO la política de identidad tiene una clave `identity.<nombre>` válida en
`app_settings`, el orchestrator DEBE usar ese valor en lugar del de la
variable de entorno (un valor no numérico o fuera de rango se descarta con log
`identity_setting_invalid` y rige la variable de entorno).

## R50
SI `APP_ENV=production` y `IDENTITY_LOGIN_REQUIRED=false` ENTONCES
`Settings` DEBE lanzar `ProductionConfigError` nombrando
`IDENTITY_LOGIN_REQUIRED`.
