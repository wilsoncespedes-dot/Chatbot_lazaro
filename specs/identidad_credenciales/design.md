# #38 identidad_credenciales — Design

Solo orchestrator. Identidad = módulo propio dentro del orquestador con
interfaz explícita (decisión registrada), no un microservicio nuevo. Se
reutilizan: perfiles/usernames de #20, patrón de throttling y hash ficticio de
#21 (`authenticate_profile`), reductor/`apply_conversation_event` de #37,
`ConversationTexts` (textos fijos editables en el panel) y `LinkBlock` de #36.
La UI de administración de clientes/credenciales (tabla, días, botones) es
#42; aquí solo endpoints internos con `X-Service-Token` y funciones de dominio.

## Archivos

| Archivo | Cambio |
|---|---|
| `services/orchestrator/orchestrator/identity.py` (nuevo) | Lógica pura: firma/verificación de token, `credential_status`, `days_remaining`, `IdentityPolicy` + `resolve_identity_policy`, `is_logout_command`. Sin IO. |
| `services/orchestrator/orchestrator/accounts.py` | `hash_password_scrypt`; `verify_password` despacha por prefijo (`scrypt$` / `pbkdf2_sha256$`). `hash_password` (PBKDF2) se conserva para #20/#21. |
| `services/orchestrator/orchestrator/domain.py` | Excepciones nuevas; funciones `issue_login_link`, `login_client`, `end_client_session`, `create_client`, `renew_credential`, `revoke_credential`, `close_client_session`, `get_client_status`, `active_client_id`; hook en `_handle_consent_button` (R1) y en `_route_consented_text` (R2, R28–R35, R41, R47). Transiciones nuevas en `_TRANSITIONS` (R43). |
| `services/orchestrator/orchestrator/identity_routes.py` (nuevo) | Router `GET/POST /acceso` (HTML propio, sin CDN). |
| `services/orchestrator/orchestrator/identity_page.py` (nuevo) | Render HTML del formulario/éxito/errores (escape con `html.escape`), reutiliza `admin.ADMIN_CSS` en línea o `/admin/static/admin.css`. |
| `services/orchestrator/orchestrator/main.py` | Registrar rutas `/acceso`; exención del middleware solo para `path == "/acceso"`; rutas internas `/clients…`; modelos Pydantic locales. Instalar al arrancar (idempotente) un `logging.Filter` en el logger `uvicorn.access` que sustituya el valor de `t=` en la query por `***` (en `record.args` y en el mensaje formateado) (R25). Se elige filtro en vez de `--no-access-log` para conservar el log de acceso; el `Dockerfile` no cambia. |
| `services/orchestrator/orchestrator/privacy.py` | `ConversationTexts` + campos `login_link_label`, `session_closed_reply` (aditivo; el panel #37 los muestra automáticamente vía `CONVERSATION_TEXT_FIELDS`). No entran en `consent_configured`. |
| `services/orchestrator/orchestrator/adapters/repository.py` | Tablas, índices y métodos nuevos en `Repository`, `FakeRepository`, `PostgresRepository`. |
| `services/orchestrator/orchestrator/config.py` + `.env.example` | Variables nuevas; validación de producción (R8, R50). |
| `services/orchestrator/tests/conftest.py` | Fixture: suites heredadas usan `IDENTITY_LOGIN_REQUIRED=false` donde verifican RAG sin login (R44). |
| `services/orchestrator/tests/test_identity_*.py` (nuevos) | Ver tasks. |

Sin cambios en `contracts/` (no hay rutas nuevas entre servicios; `/acceso` es
para el navegador y `/clients` lo usa una herramienta del admin, como
`/profiles` en #20). Sin cambios en gateways.

## Esquema (añadir a `_SCHEMA` / `_INDEXES`, aditivo e idempotente)

```sql
CREATE TABLE IF NOT EXISTS client_credentials (
  profile_id TEXT PRIMARY KEY REFERENCES profiles(id),
  valid_from TIMESTAMPTZ NOT NULL, valid_until TIMESTAMPTZ NOT NULL,
  revoked_at TIMESTAMPTZ, created_at TIMESTAMPTZ NOT NULL, updated_at TIMESTAMPTZ NOT NULL)
CREATE TABLE IF NOT EXISTS login_links (
  token_hash TEXT PRIMARY KEY, contact_id TEXT NOT NULL, channel TEXT NOT NULL,
  external_chat_id TEXT NOT NULL, created_at TIMESTAMPTZ NOT NULL,
  expires_at TIMESTAMPTZ NOT NULL, used_at TIMESTAMPTZ)
CREATE TABLE IF NOT EXISTS client_sessions (
  id TEXT PRIMARY KEY, profile_id TEXT NOT NULL REFERENCES profiles(id),
  contact_id TEXT NOT NULL, started_at TIMESTAMPTZ NOT NULL,
  last_activity_at TIMESTAMPTZ NOT NULL, ended_at TIMESTAMPTZ, end_reason TEXT)
CREATE TABLE IF NOT EXISTS identity_login_attempts (
  id BIGSERIAL PRIMARY KEY, username TEXT NOT NULL, ip TEXT NOT NULL, at TIMESTAMPTZ NOT NULL)
CREATE TABLE IF NOT EXISTS identity_audit (
  id BIGSERIAL PRIMARY KEY, profile_id TEXT, contact_id TEXT, action TEXT NOT NULL,
  reason TEXT NOT NULL, at TIMESTAMPTZ NOT NULL)
-- índices
CREATE UNIQUE INDEX IF NOT EXISTS client_sessions_one_active_profile
  ON client_sessions (profile_id) WHERE ended_at IS NULL      -- R27
CREATE UNIQUE INDEX IF NOT EXISTS client_sessions_one_active_contact
  ON client_sessions (contact_id) WHERE ended_at IS NULL      -- R27
CREATE INDEX IF NOT EXISTS login_links_contact ON login_links (contact_id)
CREATE INDEX IF NOT EXISTS identity_login_attempts_user_at ON identity_login_attempts (username, at)
CREATE INDEX IF NOT EXISTS identity_login_attempts_ip_at ON identity_login_attempts (ip, at)
```

`cliente_id` = `profiles.id` del perfil `cliente`. La asociación chat↔cliente
vive en `client_sessions` (historial incluido); no se añade columna a
`contacts`. `identity_audit` se separa de `events` porque una revocación puede
no tener `contact_id` (`events.contact_id` es `NOT NULL`).

## Firmas

```python
# identity.py (puro)
LINK_PREFIX = "login-link:v1:"
def sign_login_token(key: str) -> str                         # "<nonce>.<hmac_hex>" (R3)
def verify_login_token_signature(token: str, key: str) -> bool  # hmac.compare_digest (R13)
CredentialStatus = Literal["vigente", "por_vencer", "vencida", "revocada", "no_iniciada"]
def credential_status(valid_from, valid_until, revoked_at, now, notice_days) -> CredentialStatus
def credential_allows_access(status) -> bool                  # vigente | por_vencer
def days_remaining(valid_until, now) -> int                   # R45, ≥ 0
def is_logout_command(text: str, commands: tuple[str, ...]) -> bool  # normalize_text, igualdad exacta
@dataclass(frozen=True)
class IdentityPolicy:
    link_ttl_minutes: int; session_idle_minutes: int; login_max_attempts: int
    lockout_minutes: int; validity_days: int; expiry_notice_days: int
def resolve_identity_policy(settings, overrides: dict[str, str]) -> IdentityPolicy  # R49

# accounts.py
def hash_password_scrypt(password: str, n: int, r: int = 8, p: int = 1, salt: bytes | None = None) -> str
def verify_password(password: str, stored: str) -> bool       # ambos esquemas (R20)

# domain.py
@dataclass(frozen=True)
class LoginOutcome: status: Literal["ok", "ok_no_access"]       # éxito; errores = excepciones
def issue_login_link(contact: Contact, settings, adapters) -> str | None   # URL o None (R7, R9)
def login_client(token: str, username: str, password: str, client_ip: str,
                 settings, adapters) -> LoginOutcome
def end_client_session(session: ClientSession, reason: str, settings, adapters,
                       notify: bool) -> None
def create_client(username, password, valid_from, valid_until, settings, adapters) -> ClientStatus
def renew_credential(profile_id, settings, adapters) -> ClientStatus
def revoke_credential(profile_id, settings, adapters) -> ClientStatus
def close_client_session(profile_id, settings, adapters) -> ClientStatus
def get_client_status(profile_id, settings, adapters) -> ClientStatus
def active_client_id(contact_id: str, adapters) -> str | None   # punto estable para #39/#40

# Repository (Protocol + Fake + Postgres)
def create_client_credential(username, password_hash, valid_from, valid_until, now) -> Profile  # UsernameTaken
def get_client_credential(profile_id) -> ClientCredential | None
def get_client_credentials_by_username(username) -> tuple[Profile, str, ClientCredential | None] | None
def renew_client_credential(profile_id, valid_until, now) -> bool         # False si revocada
def revoke_client_credential(profile_id, now) -> bool
def add_login_link(token_hash, contact_id, channel, external_chat_id, now, expires_at) -> None  # invalida previos (R5)
def get_login_link(token_hash, now) -> LoginLink | None                    # solo vigente y sin usar
def start_client_session(token_hash, profile_id, session_id, now) -> Literal["ok", "invalid_link", "conflict"]
def get_active_session_by_contact(contact_id) -> ClientSession | None
def get_active_session_by_profile(profile_id) -> ClientSession | None
def touch_client_session(session_id, now) -> None
def end_client_session(session_id, reason, now) -> bool                   # solo si ended_at IS NULL
def count_identity_login_failures(username, ip, since) -> tuple[int, int]
def record_identity_login_failure(username, ip, now, prune_before) -> None
def clear_identity_login_failures(username) -> None
def add_identity_audit(profile_id, contact_id, action, reason, at) -> None
def get_identity_overrides() -> dict[str, str]                            # app_settings LIKE 'identity.%'
```

`ClientCredential(profile_id, valid_from, valid_until, revoked_at)`,
`LoginLink(token_hash, contact_id, channel, external_chat_id, expires_at)`,
`ClientSession(id, profile_id, contact_id, started_at, last_activity_at)`,
`ClientStatus(profile_id, username, status, valid_from, valid_until, days_remaining, has_active_session)`.
Ninguno expone hash ni token.

**Atomicidad (R15, R27).** `start_client_session` en una transacción bajo el
lock existente:

```sql
WITH l AS (UPDATE login_links SET used_at=%(now)s
           WHERE token_hash=%(h)s AND used_at IS NULL AND expires_at > %(now)s
           RETURNING contact_id)
INSERT INTO client_sessions (id, profile_id, contact_id, started_at, last_activity_at)
SELECT %(id)s, %(pid)s, l.contact_id, %(now)s, %(now)s FROM l
RETURNING contact_id
```

Sin fila → `invalid_link`. `UniqueViolation` de un índice parcial → rollback
(el token queda sin usar) → `conflict`. `FakeRepository` reproduce lo mismo
con un `threading.Lock` y comprobaciones explícitas.

## Flujo `login_client` (orden fijo)

1. `verify_login_token_signature` → si falla `LoginLinkInvalid` (sin repo, R13).
2. `get_login_link(hash, now)` → `None` → `LoginLinkInvalid` (R12).
3. Política (`resolve_identity_policy`); throttling por usuario normalizado e
   IP en `lockout_minutes` → `LoginThrottled` (R23) sin verificar contraseña.
4. Buscar credenciales; usuario inexistente → verificar contra hash ficticio
   (R22); contraseña mala o rol ≠ `cliente` → `record_identity_login_failure`
   + `ClientLoginFailed` (R21, R48).
5. Sin fila de credencial / `revocada` / `no_iniciada` → audit
   `login_denied` + `CredentialNotEnabled` (R36, R37).
6. Sesión activa del perfil: si está inactiva (R30) se finaliza con `idle`
   (aplica `SESSION_IDLE_TIMEOUT` a su contacto salvo `with_advisor`); si
   sigue activa → audit `login_conflict` + `SessionConflict` (R26).
7. `start_client_session` → `invalid_link` → `LoginLinkInvalid`; `conflict` →
   `SessionConflict`.
8. `clear_identity_login_failures`; audit `login`; evento `LOGIN_VALID` o
   `LOGIN_EXPIRED` (según `credential_status`) vía `apply_conversation_event`;
   enviar `active_welcome` o `suspended_reply` al canal del contacto (R16, R34).

`/acceso` mapea: `LoginLinkInvalid` 400, `ClientLoginFailed` 401,
`CredentialNotEnabled` 403, `SessionConflict` 409, `LoginThrottled` 429; todas
con HTML genérico (nunca JSON, nunca eco del usuario/contraseña). El token
viaja como campo oculto `t` y en `GET` como query `?t=`; con
`Referrer-Policy: no-referrer` y `no-store`. No se usa CSRF adicional: el
token de un solo uso secreto cumple esa función. Campos extra del formulario
se ignoran (R17).

## Flujo de mensajes (`_route_consented_text`)

Se ejecuta tanto para el camino legacy Telegram (`process_message`) como para
`process_channel_message`, así ambos canales comparten la lógica. Con
`IDENTITY_LOGIN_REQUIRED=true` y antes del `switch` de estados de #37:

1. Estado `None` → `awaiting_login` (R47; antes era `active`).
2. Si hay sesión activa: comprobar inactividad (R30/R31) salvo `with_advisor`;
   si no expiró, `touch_client_session` (R28).
3. Comando de cierre (R29) con sesión → `end_client_session("logout")`,
   respuesta `session_closed_reply` + enlace nuevo; return.
4. `active`/`no_access` sin sesión → `SESSION_CLOSED`, recordatorio + enlace (R33).
5. `active` con credencial `vencida` → `CREDENTIAL_EXPIRED` + `suspended_reply` (R35);
   `revocada` → finalizar sesión `revoked` + R33.
6. `no_access` con credencial vigente → `CREDENTIAL_RENEWED` y seguir (R41).
7. `awaiting_login` → `login_reminder` + `LinkBlock` nuevo (R2).
8. Resto: flujo existente de #37 sin cambios.

El envío de texto+enlace usa `adapters.gateway.send_channel_blocks(contact.channel,
destino, [TextBlock, LinkBlock])`; destino = `external_chat_id` o, para
contactos legacy Telegram, `str(chat_id)`. En `_handle_consent_button`, tras
aceptar, se añade el `LinkBlock` a la respuesta `accepted_reply` (R1).

`IDENTITY_LOGIN_REQUIRED=false` salta los pasos 1–7 (R44): permite que las
suites históricas de RAG/traspaso sigan probando ese flujo sin sesión. En
producción `false` está prohibido (R50).

## Excepciones

Nuevas en `domain.py`, subclases de `DomainError` (handler existente):
`LoginLinkInvalid` (400 `invalid_link`), `ClientLoginFailed` (401
`invalid_credentials`), `CredentialNotEnabled` (403 `access_not_enabled`),
`SessionConflict` (409 `session_active`), `CredentialRevoked` (409
`credential_revoked`, R46), `ClientNotFound` (404 `client_not_found`).
Se reutilizan `LoginThrottled` (429) y `UsernameTaken` (409).

## Rutas internas (`X-Service-Token`, modelos locales en `main.py`)

| Ruta | Cuerpo | Respuesta |
|---|---|---|
| `POST /clients` | `username`, `password` (≥ `PROFILE_PASSWORD_MIN_LENGTH`), `valid_from?`, `valid_until?` | `201 ClientStatusResponse` |
| `GET /clients/{profile_id}` | — | `200 ClientStatusResponse` |
| `POST /clients/{profile_id}/renew` | — | `200` / `409 credential_revoked` |
| `POST /clients/{profile_id}/revoke` | — | `200` |
| `POST /clients/{profile_id}/close-session` | — | `200` |

`ClientStatusResponse`: `profile_id`, `username`, `status`, `valid_from`,
`valid_until`, `days_remaining`, `has_active_session`. `#42` reutilizará estas
funciones de dominio desde el panel.

## Config (`.env.example`, sección "identidad y credenciales (#38)")

| Variable | Default | Notas |
|---|---|---|
| `IDENTITY_PUBLIC_BASE_URL` | vacío | URL pública del orchestrator (Render: `https://<orchestrator>.onrender.com`). Requerida https en producción. |
| `IDENTITY_LINK_SIGNING_KEY` | vacío | Secreto ≥ 32 caracteres en producción. Distinto de `SERVICE_TOKEN`. |
| `IDENTITY_LOGIN_REQUIRED` | `true` | `false` solo en desarrollo/tests. |
| `IDENTITY_LINK_TTL_MINUTES` | `15` | 1–1440 |
| `IDENTITY_SESSION_IDLE_MINUTES` | `60` | 5–1440 |
| `IDENTITY_LOGIN_MAX_ATTEMPTS` | `5` | 1–100 |
| `IDENTITY_LOCKOUT_MINUTES` | `15` | 1–1440 |
| `CREDENTIAL_VALIDITY_DAYS` | `30` | 1–366 |
| `CREDENTIAL_EXPIRY_NOTICE_DAYS` | `5` | 0–60 |
| `IDENTITY_LOGOUT_COMMANDS` | `/salir,cerrar sesion,cerrar sesión` | Se evita `/cerrar…` porque choca con el prefijo de comandos de asesor. |
| `PASSWORD_SCRYPT_N` | `32768` | potencia de 2, ≥ 16384; r=8, p=1, `maxmem` 64 MiB. Tests llaman a `hash_password_scrypt` con n pequeño. |

Los seis tiempos/límites de producto se pueden sobrescribir en caliente con
claves `identity.link_ttl_minutes`, `identity.session_idle_minutes`,
`identity.login_max_attempts`, `identity.lockout_minutes`,
`identity.validity_days`, `identity.expiry_notice_days` en `app_settings`
(R49), cumpliendo la regla de `docs/architecture.md` §3.5 (tiempos de producto
administrables). La UI para editarlas llega con #42.

`render.yaml`: añadir `IDENTITY_PUBLIC_BASE_URL` y `IDENTITY_LINK_SIGNING_KEY`
con `sync: false` al servicio orchestrator.

## Dependencias

Ninguna nueva: `hashlib.scrypt`, `hmac`, `secrets`, `html` (stdlib).

## Alternativas descartadas

- **argon2-cffi / bcrypt** (lo que sugiere `docs/especificacion.md`): mejores
  en teoría, pero añaden dependencia nativa que el humano debe instalar y
  compilar en la imagen. `hashlib.scrypt` es memory-hard, está en stdlib y
  OWASP lo acepta cuando Argon2id no está disponible. El formato con prefijo
  permite migrar a Argon2id después sin romper hashes.
- **Reutilizar PBKDF2 de #20 para clientes**: no es memory-hard; los clientes
  son el universo más grande de credenciales.
- **Token JWT autocontenido sin fila en BD**: no permite un solo uso ni
  invalidar enlaces previos sin una lista de revocación; la firma HMAC se
  conserva solo como filtro barato previo a la BD.
- **Reutilizar `admin_login_attempts`**: acoplaría bloqueos del panel admin y
  del login de clientes detrás de la misma IP de proxy.
- **Barrido periódico de sesiones inactivas**: requeriría un worker nuevo. La
  expiración perezosa (al siguiente mensaje o intento de login) cumple "tras 1
  hora sin mensajes" porque nada se procesa con una sesión expirada. `#42`
  puede añadir el barrido si el panel necesita reflejarlo en tiempo real.
- **Columna `client_id` en `contacts`**: duplicaría la verdad de
  `client_sessions` y complicaría el cierre.

## Decisiones de producto y supuestos (defaults seguros, no bloquean)

1. **Deshacer una revocación.** El documento no define cómo se reactiva una
   credencial revocada. Default: la renovación de una revocada responde
   `409 credential_revoked`; el admin crea una credencial nueva. **Recomendación:**
   que #42 añada una acción explícita "reactivar" auditada si el negocio lo
   necesita.
2. **"1 mes" = 30 días** configurables (`CREDENTIAL_VALIDITY_DAYS`) en vez de
   mes calendario, para que el cálculo sea predecible.
3. **Credencial no iniciada** (`now < valid_from`): se trata como acceso no
   habilitado (403), igual que revocada.
4. **Inactividad con asesor:** la sesión no expira mientras el contacto está en
   `with_advisor`, para no interrumpir la atención humana.
5. **Revocación/cierre admin** envían `session_closed_reply`; no envían enlace
   (el siguiente mensaje del cliente lo recibe por R2/R33).
6. **Textos de la página `/acceso`** (etiquetas y errores genéricos) son UI
   fija en `identity_page.py`, como el login del panel; los textos del chat
   (`login_link_label`, `session_closed_reply`) son administrables en el panel
   (#37). Si faltan, falla cerrado sin enlace (R9).
7. **Retención:** las filas de `login_links` usadas/vencidas se borran al
   emitir un enlace nuevo para ese contacto; `identity_login_attempts` se poda
   al registrar (como #21). La purga de #35/#37 no borra `client_sessions`
   activas; el plazo de `identity_audit` queda sujeto a la validación legal ya
   abierta.
8. **Perfiles `cliente` de #20 sin fila de credencial** no pueden iniciar
   sesión (403). `POST /clients` crea perfil y credencial juntos; asociar
   credencial a un perfil `cliente` previo queda para #42 si hace falta.
9. **Logs de proxy externos** (Render u otro balanceador) pueden registrar la
   URL con `t=`; quedan fuera de R25. Mitigación: token de un solo uso con
   caducidad corta (R4–R6).
