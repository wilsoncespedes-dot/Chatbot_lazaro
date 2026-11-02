# #20 verificacion_cuentas — Design

Solo orchestrator. Sin panel, sin uso del rol para autorizar (eso llega con
features posteriores); aquí solo se guarda y se vincula.

## Archivos

| Archivo | Cambio |
|---------|--------|
| `services/orchestrator/orchestrator/accounts.py` (nuevo) | Lógica pura: `hash_password`, `verify_password`, `new_link_token`, `hash_token`, `parse_start_token`. Sin IO. |
| `services/orchestrator/orchestrator/domain.py` | `create_profile`, `issue_link_token`, `_handle_start_token` y desvío en `process_message`; excepciones nuevas. |
| `services/orchestrator/orchestrator/adapters/repository.py` | Tablas `profiles`, `link_tokens`; métodos en `Repository`, `FakeRepository` y `PostgresRepository`. |
| `services/orchestrator/orchestrator/main.py` | Rutas `POST /profiles`, `POST /profiles/{id}/link-token`; modelos Pydantic locales. |
| `services/orchestrator/orchestrator/config.py` + `.env.example` | Variables nuevas (abajo). |
| `services/orchestrator/tests/test_accounts.py` (nuevo) | Tests R1–R10. |

## Esquema (añadir a `_SCHEMA`)

```sql
CREATE TABLE IF NOT EXISTS profiles (
  id TEXT PRIMARY KEY, username TEXT UNIQUE NOT NULL, role TEXT NOT NULL
  CHECK (role IN ('admin','asesor','cliente')), password_hash TEXT NOT NULL,
  telegram_user_id BIGINT UNIQUE, created_at TIMESTAMPTZ NOT NULL)
CREATE TABLE IF NOT EXISTS link_tokens (
  token_hash TEXT PRIMARY KEY, profile_id TEXT NOT NULL REFERENCES profiles(id),
  expires_at TIMESTAMPTZ NOT NULL, used_at TIMESTAMPTZ)
```

`username` se guarda ya en minúsculas → `UNIQUE` basta para R2.

## Firmas

```python
# accounts.py
def hash_password(password: str, iterations: int, salt: bytes | None = None) -> str
def verify_password(password: str, stored: str) -> bool        # hmac.compare_digest
def new_link_token() -> str                                    # secrets.token_urlsafe(32)
def hash_token(token: str) -> str                              # sha256 hex
def parse_start_token(text: str) -> str | None                 # "/start <tok>" → tok; "/start" solo → None

# Repository (Protocol + Fake + Postgres)
def create_profile(self, username, role, password_hash, now) -> Profile   # UsernameTaken
def get_profile(self, profile_id) -> Profile | None
def add_link_token(self, token_hash, profile_id, expires_at) -> None
def consume_link_token(self, token_hash, telegram_user_id, now) -> bool
```

`Profile(id, username, role, telegram_user_id | None)`; nunca expone el hash.

**Atomicidad (R6–R8).** `consume_link_token` es una sola sentencia bajo el
`threading.Lock` existente:

```sql
WITH t AS (UPDATE link_tokens SET used_at=%s
           WHERE token_hash=%s AND used_at IS NULL AND expires_at > %s
           RETURNING profile_id)
UPDATE profiles SET telegram_user_id=%s FROM t WHERE profiles.id=t.profile_id
RETURNING profiles.id
```

Si `telegram_user_id` choca con `UNIQUE` (otra cuenta ya vinculada), la
sentencia falla, `_run` hace `rollback` y el token queda sin consumir → `False`.
Fila devuelta → `True`. La condición `used_at IS NULL` garantiza un solo
ganador aunque se pierda el lock (dos procesos).

**Flujo `/messages`.** En `process_message`, tras `get_or_create_contact` y
**antes** de `parse_advisor_command` y de `add_message`: si
`parse_start_token(text)` devuelve token → `_handle_start_token` envía
`link_success_reply`/`link_failed_reply`, registra
`logger.info("account_link result=%s contact_id=%s")` y retorna. `/start` sin
argumento sigue el flujo actual. Revincular un perfil ya vinculado con un token
nuevo reemplaza su `telegram_user_id` (el admin emitió el token a propósito).

**Rutas.** Solo para herramientas internas con `SERVICE_TOKEN` (el middleware
actual ya las protege, R10). `link` = `https://t.me/<TELEGRAM_BOT_USERNAME>?start=<token>`;
`null` si la variable está vacía. Respuesta de `/profiles/{id}/link-token`
incluye el token porque el llamador es el admin, no Telegram.

## Excepciones

Nuevas en `domain.py`, subclases de `DomainError` (reutiliza su handler):
`UsernameTaken` (409 `username_taken`), `ProfileNotFound` (404 `profile_not_found`).

## Config (`.env.example`, con default)

| Variable | Default |
|----------|---------|
| `LINK_TOKEN_TTL_MINUTES` | `15` (1–1440) |
| `PASSWORD_HASH_ITERATIONS` | `600000` (≥ 100000; tests usan 1000 vía `hash_password` directo) |
| `PROFILE_PASSWORD_MIN_LENGTH` | `12` |
| `TELEGRAM_BOT_USERNAME` | vacío |
| `LINK_SUCCESS_REPLY` | "Tu cuenta de Telegram quedó vinculada a tu perfil." |
| `LINK_FAILED_REPLY` | "No se pudo vincular la cuenta. Pide un enlace nuevo a tu administrador." |

## Dependencias

Ninguna: `hashlib.pbkdf2_hmac`, `secrets`, `hmac` (stdlib).

## Alternativas descartadas

- **argon2/bcrypt**: mejor resistencia, pero dependencia nativa nueva; PBKDF2-SHA256
  con 600k iteraciones es aceptable (OWASP) y el formato con prefijo permite migrar.
- **Modelos en `lazaro_contracts` + sección en `CONTRATOS.md`**: estas rutas no
  son entre servicios (las llama una herramienta del admin); `docs/conventions.md`
  permite modelos locales. Se documentarán en el contrato cuando exista el panel.
- **Guardar el token en claro**: una fuga de la base permitiría vincular cuentas.

## Supuestos

- Duda §12 "quién crea usuarios y contraseñas": un admin vía `POST /profiles`
  con `SERVICE_TOKEN` (sin panel). Sin endpoint de login ni cambio de contraseña.
- El perfil vinculado aún no cambia permisos (los asesores siguen saliendo de
  `ADVISOR_CHAT_IDS`, S12).
