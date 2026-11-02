# #21 panel_administracion — Design

## Decisión: panel dentro del orchestrator

El panel vive en el orchestrator, en rutas `/admin/*` con HTML renderizado en el
servidor. El orchestrator ya guarda los perfiles, los hashes (`verify_password`),
los tokens de vinculación (#20) y la tabla `events`, así que el panel usa esa
lógica directamente, sin servicio nuevo y sin rutas de contrato nuevas. Cuando
llegue #22, el orchestrator llamará al RAG con su `HttpRagClient` y su
`SERVICE_TOKEN` desde el servidor; esa credencial nunca llega al navegador (R6).

Referencia arquitectónica (no se copia código): tgoai/tgo @995da45 separa la UI
(tgo-web, React 19) de las APIs del backend. Su LICENSE es Apache 2.0 modificada,
con restricciones para frontend y multi-tenant, así que no cumple la regla de
"MIT/Apache 2.0 puro": **solo se toma como referencia, no se copia nada**.
Helpdock (AGPL) tampoco se usa. Aquí se sigue la misma idea (la UI solo usa la
API interna) pero sin SPA ni build de frontend.

## Archivos

| Archivo | Cambio |
|---------|--------|
| `orchestrator/admin.py` (nuevo) | Lógica pura: `redact_reason`, `short_id`, `new_session_token`, `render_page(title, body_html, csrf)`, plantillas como funciones que escapan todo con `html.escape`. Sin IO. |
| `orchestrator/admin_routes.py` (nuevo) | `APIRouter(prefix="/admin")`: login/logout, perfiles, rol, link-token, eventos. Lee formularios con `urllib.parse.parse_qs(await request.body())`. |
| `orchestrator/domain.py` | `authenticate_admin`, `change_role`, `list_profiles`, `recent_events`; excepciones `LastAdmin` (409 `last_admin`) y `LoginThrottled` (429, R11). |
| `orchestrator/adapters/repository.py` | Tablas `admin_sessions` y `admin_login_attempts`; métodos nuevos en Protocol, Fake y Postgres (abajo). |
| `orchestrator/main.py` | `include_router`; el middleware `X-Service-Token` deja pasar `/admin` (ahí autentica la sesión). |
| `orchestrator/config.py` + `.env.example` | Variables nuevas. |
| `tests/test_admin.py` (nuevo) | Tests R1–R11. |

## Esquema

```sql
CREATE TABLE IF NOT EXISTS admin_sessions (
  token_hash TEXT PRIMARY KEY, profile_id TEXT NOT NULL REFERENCES profiles(id),
  csrf_token TEXT NOT NULL, expires_at TIMESTAMPTZ NOT NULL)

CREATE TABLE IF NOT EXISTS admin_login_attempts (
  id BIGSERIAL PRIMARY KEY, username TEXT NOT NULL, ip TEXT NOT NULL,
  at TIMESTAMPTZ NOT NULL)
CREATE INDEX IF NOT EXISTS admin_login_attempts_user_at ON admin_login_attempts (username, at)
CREATE INDEX IF NOT EXISTS admin_login_attempts_ip_at ON admin_login_attempts (ip, at)
```

## Firmas nuevas

```python
# Repository (Protocol + Fake + Postgres)
def get_profile_credentials(self, username) -> tuple[Profile, str] | None  # (perfil, password_hash)
def list_profiles(self) -> list[Profile]
def set_role(self, profile_id, role) -> bool        # False si dejaría 0 admins; un solo UPDATE condicionado
def create_session(self, token_hash, profile_id, csrf_token, expires_at) -> None
def get_session(self, token_hash, now) -> AdminSession | None   # solo si no expiró y el perfil sigue siendo admin
def delete_session(self, token_hash) -> None
def recent_events(self, limit) -> list[StoredEvent]  # ORDER BY at DESC, id DESC
def count_login_failures(self, username, ip, since) -> tuple[int, int]  # (por username, por ip), at > since
def record_login_failure(self, username, ip, at, purge_before) -> None  # inserta y borra filas con at < purge_before
def clear_login_failures(self, username) -> None

# domain.py
def authenticate_admin(username, password, client_ip, settings, adapters) -> str | None
    # token de sesión o None; LoginThrottled (429) si R11 aplica
def change_role(profile_id, role, adapters) -> Profile   # ProfileNotFound | LastAdmin

# admin_routes.py
def client_ip(request, settings) -> str
```

- `set_role` en Postgres: `UPDATE profiles SET role=%s WHERE id=%s AND (%s='admin'
  OR role<>'admin' OR (SELECT count(*) FROM profiles WHERE role='admin')>1)
  RETURNING id`, bajo el lock existente.
- `authenticate_admin` siempre llama a `verify_password` (con un hash ficticio si
  el usuario no existe) para que el tiempo de respuesta no revele si existe (R2),
  salvo cuando R11 ya bloqueó el intento.
- Límite de intentos (R11), persistente en Postgres (tabla `admin_login_attempts`,
  SQL parametrizado; el Fake guarda una lista en memoria). Sin Redis: no hay
  dependencia ni servicio nuevo. Orden en `authenticate_admin`:
  1. `username` normalizado con `strip().lower()` (igual que #20);
     `since = clock() - ADMIN_LOGIN_WINDOW_MINUTES`.
  2. Si `count_login_failures(username, ip, since)` tiene algún valor
     `>= ADMIN_LOGIN_MAX_ATTEMPTS` → `LoginThrottled`, **sin** llamar a
     `verify_password` y sin registrar el intento (así el bloqueo termina cuando
     los fallos salen de la ventana deslizante).
  3. `verify_password` (con hash ficticio si hace falta). Si falla →
     `record_login_failure(username, ip, now, purge_before=since)` y `None`.
  4. Si va bien → `clear_login_failures(username)` y se crea la sesión.
  La ruta responde `429` con la misma plantilla y el mismo mensaje que el `401`.
- IP del cliente (`client_ip`): `request.client.host`. Solo si
  `ADMIN_TRUST_PROXY_HEADERS=true` se usa el último valor de `X-Forwarded-For`
  (el que añade el proxy de confianza); si falta, se vuelve a `request.client.host`.
- Cookie: `secrets.token_urlsafe(32)`; en la base solo se guarda su SHA-256
  (reutiliza `hash_token` de #20). Atributos: `HttpOnly; SameSite=Strict;
  Path=/admin; Max-Age=TTL`, y `Secure` si `ADMIN_COOKIE_SECURE`.
- CSRF: token de sincronización por sesión, en un campo oculto de cada
  formulario; se compara con `hmac.compare_digest` (R4). `SameSite=Strict` es
  una defensa más, no la única.
- Si el rol del admin cambia, `get_session` deja de devolver la sesión (R3).
- R5: todas las respuestas HTML pasan por un helper que añade CSP,
  `X-Content-Type-Options: nosniff` y `Cache-Control: no-store`. Sin JavaScript.
  Los estilos salen de una constante en `admin.py`, servida en
  `GET /admin/static/admin.css` (mismo origen, sin sesión, igual que el login;
  es una excepción explícita de R3).
  Así la CSP no necesita `'unsafe-inline'`.

Orden de comprobación en cada ruta protegida: sesión (R3) → CSRF en POST (R4) →
validación → dominio. Los errores se muestran en HTML con el código HTTP del
contrato (`422`, `404 profile_not_found`, `409 username_taken`/`last_admin`).

## Redacción (R10)

`redact_reason` aplica en este orden: correo `[^\s@]+@[^\s@]+` → `\d{6,}` →
`[A-Za-z0-9_-]{20,}` → `[redactado]`. Así quedan visibles `case:` y los códigos
cortos, pero se ocultan ids de Telegram, teléfonos, case_ids hex y tokens.

## Config (`.env.example`)

| Variable | Default |
|----------|---------|
| `ADMIN_SESSION_TTL_MINUTES` | `60` (5–1440) |
| `ADMIN_COOKIE_SECURE` | `true` (en local, por HTTP, `false`) |
| `ADMIN_EVENTS_LIMIT` | `100` (1–500) |
| `ADMIN_LOGIN_MAX_ATTEMPTS` | `5` (1–100) |
| `ADMIN_LOGIN_WINDOW_MINUTES` | `15` (1–1440) |
| `ADMIN_TRUST_PROXY_HEADERS` | `false` (en Render, detrás de su proxy, `true`) |

## Dependencias

Ninguna nueva. No hace falta `jinja2` (se usa `html.escape`) ni
`python-multipart` (los formularios urlencoded se leen con `urllib.parse`).
Ningún JS ni CSS externo.

## Alternativas descartadas

- **Servicio `admin_panel` nuevo (BFF)**: tendría que guardar el `SERVICE_TOKEN`
  y necesitaría una ruta nueva de verificación de credenciales en el contrato
  del orchestrator. Es más superficie para un panel mínimo, y
  `docs/architecture.md` §1 pide evitar servicios nuevos.
- **SPA React (como tgo-web)**: necesita una cadena de build con node y
  dependencias npm, y el navegador llamaría APIs con algún token. Va contra la
  regla de "sin dependencias innecesarias" y complica R6.
- **Sesión firmada sin estado (itsdangerous)**: es una dependencia nueva y no
  permite cerrar la sesión ni invalidarla al cambiar el rol.

## Supuestos

- El primer `admin` se crea con `POST /profiles` (#20, con `SERVICE_TOKEN`); el
  panel no tiene un bootstrap propio.
- El bloqueo por `username` permite que un tercero bloquee temporalmente a un
  admin; se acepta porque dura como mucho `ADMIN_LOGIN_WINDOW_MINUTES` y evita
  la fuerza bruta y el gasto de CPU de PBKDF2 sin límite.
- Las sesiones expiradas no se borran en segundo plano: se ignoran al leerlas y
  se borran al hacer logout.
