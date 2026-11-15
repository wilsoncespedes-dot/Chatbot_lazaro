# #54 segundo_factor_panel — Design

Solo orchestrator. Se reutilizan: `authenticate_profile` y la tabla
`admin_login_attempts` (#21), `admin_sessions`, `record_panel_audit` (#41),
`hash_token`, `ProductionConfigError` y los patrones de rutas, CSRF y
`security_headers` de `admin_routes.py`/`advisor_routes.py`. Roles de personal de
#49: `admin`, `supervisor`, `asesor`, `responsable_datos`.

## Dependencias (revisadas en `services/orchestrator/requirements.txt`)

Existentes: fastapi, uvicorn, pydantic(-settings), httpx, pg8000, python-multipart,
websockets. Ninguna ofrece cifrado autenticado y `cryptography` NO está
instalada en el `.venv`.

| Paquete | Versión | Licencia | Uso |
|---|---|---|---|
| `cryptography` | `>=43,<48` | Apache-2.0 OR BSD-3-Clause (se usa bajo Apache-2.0/BSD, ambas permitidas) | Solo `cryptography.fernet.Fernet` para cifrar el secreto TOTP (AES-128-CBC + HMAC-SHA256, autenticado) |

- **T0 (humano, previa a todo):** añadir `cryptography>=43,<48` a
  `services/orchestrator/requirements.txt` e instalarla en el `.venv` y en la
  imagen. El agente no instala. TOTP, base32, HMAC, SHA-256 y comparación en
  tiempo constante usan solo la biblioteca estándar (`hmac`, `hashlib`,
  `base64`, `struct`, `secrets`): no hay dependencia de TOTP ni de QR (el secreto
  se muestra como texto y URI; QR queda fuera).
- No se copia código de terceros.

## Archivos

| Archivo | Cambio |
|---|---|
| `services/orchestrator/requirements.txt` | `cryptography>=43,<48` (T0). |
| `services/orchestrator/orchestrator/two_factor.py` (nuevo) | Lógica pura: `generate_secret`, `totp_at`, `verify_totp`, `provisioning_uri`, `encrypt_secret`/`decrypt_secret` (Fernet), `generate_recovery_codes`, `normalize_recovery_code`, `hash_recovery_code`. Sin IO. |
| `orchestrator/config.py` | Campos nuevos, propiedad `panel_2fa_required_effective`, validación de producción. |
| `orchestrator/adapters/repository.py` | Tablas, columna `enroll_only` y métodos en `Repository`, `FakeRepository`, `PostgresRepository`. |
| `orchestrator/domain.py` | Excepciones, `authenticate_profile(..., code="")` ampliado, `begin_two_factor_enrollment`, `confirm_two_factor_enrollment`, `reset_two_factor`. |
| `orchestrator/two_factor_routes.py` (nuevo) | `create_two_factor_router(settings, adapters, panel)` con `panel in {"admin","asesor"}`: `GET /<panel>/2fa`, `POST /<panel>/2fa/start`, `POST /<panel>/2fa/confirm`. |
| `orchestrator/two_factor_page.py` (nuevo) | HTML escapado con `html.escape` y `Cache-Control: no-store`. |
| `orchestrator/admin_routes.py` | Campo `code` en `login`, mapeo de nuevas excepciones, `POST /admin/profiles/{id}/2fa/reset`, `logout` usa la sesión sin restricción. |
| `orchestrator/advisor_routes.py` | Campo `code` en `login`, mapeo de excepciones, `logout` usa la sesión sin restricción. |
| `orchestrator/admin.py`, `advisor_panel.py` | Campo «Código de verificación» en los formularios de login; botón de restablecer en la tabla de perfiles. |
| `orchestrator/main.py` | Registrar los routers `/admin/2fa` y `/asesor/2fa`; las rutas ya caen bajo la exención de `/admin` y `/asesor`. |
| `.env.example`, `render.yaml`, `docs/despliegue.md` | Variables nuevas (R44) y procedimiento SQL de recuperación operativa (R46–R48). |
| `services/orchestrator/tests/test_two_factor_recovery_doc.py` (nuevo) | Test documental sobre `docs/despliegue.md` (R46–R48). |
| `services/orchestrator/tests/test_two_factor_*.py` (nuevos) | Ver tasks. |

Sin cambios en `contracts/`, gateways ni otros servicios.

## Configuración (`Settings` y `.env.example`)

| Variable | Tipo / default | Notas |
|---|---|---|
| `PANEL_2FA_REQUIRED` | `bool | None`, sin definir | Efectivo: `true` en producción, `false` en otro entorno; valor explícito se respeta (R21, R22). |
| `PANEL_2FA_ENCRYPTION_KEY` | str, vacío | Clave Fernet; obligatoria y válida en producción (R41). Vacía fuera de producción: el registro responde `503 two_factor_unavailable` (R16). Rotación fuera de alcance. |
| `PANEL_2FA_ISSUER` | str, `Lazaro Software` | 1–64 caracteres. |
| `PANEL_2FA_WINDOW_STEPS` | int, `1` | 0–2. |
| `PANEL_2FA_RECOVERY_CODES` | int, `8` | 4–20. |

Los límites de intentos reutilizan `ADMIN_LOGIN_MAX_ATTEMPTS` y `ADMIN_LOGIN_WINDOW_MINUTES`.
La validación de clave en `config.py` decodifica base64 urlsafe y exige 32 bytes sin
importar `cryptography`; el mensaje del error nombra la variable, nunca su valor.

## Esquema (añadir a `_SCHEMA`/`_MIGRATIONS`, aditivo e idempotente)

```sql
CREATE TABLE IF NOT EXISTS staff_two_factor (
  profile_id TEXT PRIMARY KEY REFERENCES profiles(id),
  secret_ciphertext TEXT NOT NULL,
  enabled_at TIMESTAMPTZ,                -- NULL = registro pendiente
  last_used_step BIGINT NOT NULL DEFAULT 0,
  created_at TIMESTAMPTZ NOT NULL)
CREATE TABLE IF NOT EXISTS staff_recovery_codes (
  code_hash TEXT PRIMARY KEY,
  profile_id TEXT NOT NULL REFERENCES profiles(id),
  created_at TIMESTAMPTZ NOT NULL, used_at TIMESTAMPTZ)
ALTER TABLE admin_sessions ADD COLUMN IF NOT EXISTS enroll_only BOOLEAN NOT NULL DEFAULT FALSE
CREATE INDEX IF NOT EXISTS staff_recovery_codes_profile ON staff_recovery_codes (profile_id)
```

## Firmas nuevas

```python
# two_factor.py
def generate_secret() -> bytes                      # 20 bytes aleatorios
def totp_at(secret: bytes, step: int, digits: int = 6) -> str
def verify_totp(secret: bytes, code: str, now: datetime, window: int) -> int | None  # paso coincidente o None
def provisioning_uri(secret: bytes, account: str, issuer: str) -> str
def encrypt_secret(secret: bytes, key: str) -> str
def decrypt_secret(ciphertext: str, key: str) -> bytes  # TwoFactorUnavailable si clave/ciphertext inválidos
def generate_recovery_codes(count: int) -> list[str]     # 'xxxx-xxxx-xxxx-xxxx' base32 minúsculas
def normalize_recovery_code(raw: str) -> str
def hash_recovery_code(raw: str) -> str                  # sha256 hex del normalizado

# Repository (Protocol + Fake + Postgres)
def get_two_factor(profile_id) -> TwoFactorRecord | None
def save_pending_two_factor(profile_id, ciphertext, now) -> bool          # False si ya activo
def activate_two_factor(profile_id, step, code_hashes, now) -> bool       # pendiente→activo + códigos, en una transacción
def advance_two_factor_step(profile_id, step) -> bool                     # UPDATE … WHERE enabled_at IS NOT NULL AND last_used_step < :step
def consume_recovery_code(profile_id, code_hash, now) -> bool             # UPDATE … WHERE used_at IS NULL (rowcount 1)
def delete_two_factor(profile_id) -> bool                                 # secreto + códigos
def create_session(..., enroll_only: bool = False)
def get_session_any(token_hash, now) -> AdminSession | None               # incluye restringidas
def promote_session(token_hash) -> None                                   # enroll_only=false
```

`get_session` y `get_session_for_roles` **excluyen** las sesiones `enroll_only`
(fail-closed): cualquier consumidor existente (rutas, websocket de #53) las trata
como no autenticadas sin cambios (R24). Solo `two_factor_routes` y `logout` usan
`get_session_any`.

## Flujo de login (`authenticate_profile`, orden fijo)

1. Límite de intentos por usuario/IP (sin cambios; R13).
2. Contraseña y rol (sin cambios, hash ficticio; fallos cuentan; R15).
3. Si `get_two_factor(profile.id)` está activo:
   - clave inválida o descifrado falla → `TwoFactorUnavailable` (R16);
   - `code` vacío → `TwoFactorCodeRequired` (`401 two_factor_required`, no cuenta; R11);
   - código con forma de recuperación (tras normalizar, 16 caracteres base32) → `consume_recovery_code`; fallo → `record_login_failure` y `TwoFactorCodeInvalid` (R32, R33);
   - si no, `verify_totp` → paso `s`; `None` o `advance_two_factor_step` falso → `record_login_failure` y `TwoFactorCodeInvalid` (R3, R12, R17–R19).
4. Si no está activo y `panel_2fa_required_effective` → sesión `enroll_only=True` (R23); si no, sesión normal (R26).
5. `clear_login_failures` y sesión nueva (R14).

Los routers capturan `TwoFactorCodeRequired`/`TwoFactorCodeInvalid` y devuelven
`401` con el formulario (mensaje fijo, mismo código HTTP que contraseña errónea;
`TwoFactorCodeRequired` muestra «Introduce tu código de verificación»);
`TwoFactorUnavailable` devuelve `503`. El uso de código de recuperación se audita
en la ruta con `record_panel_audit(profile, "two_factor_recovery_used", "ok")`
(`target=None`).

## Registro

`POST …/2fa/start`: sesión (`get_session_any`) + CSRF; genera secreto,
`encrypt_secret`, `save_pending_two_factor` (reemplaza un pendiente previo); la
respuesta muestra base32 y URI (única vez que el secreto sale del servidor).
`GET …/2fa` solo muestra estado (activo/no activo) y el botón de iniciar, nunca
el secreto. `POST …/2fa/confirm`: descifra el pendiente, `verify_totp`; si valida,
`activate_two_factor(step, hashes)` guarda códigos hash y último paso (R20), si la
sesión es restringida la promueve y, en todos los casos (restringida o normal), borra las demás sesiones del perfil conservando la actual con `delete_sessions_for_profile(profile_id, keep_token_hash=...)` (R25),
audita `two_factor_enrolled` y muestra los códigos en claro una sola vez (R6,
R31). Los códigos en claro no se persisten ni se loguean.

## Restablecimiento

`reset_two_factor(actor, target_id, adapters)`: rechaza `actor.id == target_id`
(`PanelValidationError`, 400), perfil inexistente (`ProfileNotFound` 404) y sin
segundo factor (`TwoFactorNotEnabled` 409); `delete_two_factor`,
`delete_sessions_for_profile`, audita `two_factor_reset` con `target=target_id`.
La ruta vive en `/admin` (solo rol `admin`, CSRF con `_require_csrf_audited`).

## Recuperación operativa (SQL documentado en `docs/despliegue.md`)

Vía declarada explícitamente como **SQL documentado** (no hay comando de app ni
endpoint: exige acceso operativo a la BD, que ya es el nivel de confianza máximo).
Sección «Recuperar el segundo factor del panel» con este contenido:

```sql
-- psql "$DATABASE_URL" -v operator='nombre.operador' -v profile_id='<profiles.id>'
BEGIN;
SELECT id, username, role FROM profiles WHERE id = :'profile_id';  -- confirmar el perfil
INSERT INTO panel_audit (actor_profile_id, actor_role, action, target, result, at)
  SELECT 'ops:' || :'operator', 'operator', 'two_factor_reset_ops', id, 'ok', now()
  FROM profiles WHERE id = :'profile_id';
DELETE FROM staff_recovery_codes WHERE profile_id = :'profile_id';
DELETE FROM staff_two_factor     WHERE profile_id = :'profile_id';
DELETE FROM admin_sessions       WHERE profile_id = :'profile_id';
COMMIT;
```

- Si el perfil no existe, el `INSERT … SELECT` no inserta y los `DELETE` no tocan filas;
  el procedimiento indica verificar que el `SELECT` devolvió una fila antes del `COMMIT`.
- **Variante pérdida/cambio de `PANEL_2FA_ENCRYPTION_KEY`:** mismo bloque sin filtro
  de perfil: el `INSERT … SELECT` recorre `staff_two_factor` (una fila de auditoría por
  perfil afectado) y los `DELETE` usan `profile_id IN (SELECT profile_id FROM staff_two_factor)`
  (los `DELETE` de sesiones y códigos van antes del de `staff_two_factor`).
- Nunca se hace `SELECT` de `secret_ciphertext`, hashes ni la clave; el actor
  `ops:<operador>` es no nulo y no es un perfil real (`panel_audit.actor_profile_id` no tiene FK).
- Tras ejecutarlo, el perfil entra solo con contraseña (R39) y, si el 2FA es obligatorio,
  queda en sesión restringida de registro. El bootstrap #23 **no** sirve (se niega si ya hay administrador).

## Excepciones (en `domain.py`, `DomainError`)

`TwoFactorCodeRequired` (401, `two_factor_required`), `TwoFactorCodeInvalid`
(401, `two_factor_invalid`), `TwoFactorUnavailable` (503, `two_factor_unavailable`),
`TwoFactorAlreadyEnabled` (409, `two_factor_already_enabled`), `TwoFactorNotEnabled`
(409, `two_factor_not_enabled`). Se reutilizan `LoginThrottled`, `ProfileNotFound`,
`PanelValidationError`, `CsrfInvalid`, `ProductionConfigError`.

## Alternativa descartada

**Cifrar el secreto con un esquema propio sobre `hashlib`/`hmac`** (stream cipher
de HMAC) para evitar una dependencia: descartado, implica inventar criptografía;
Fernet es un formato autenticado, auditado y mantenido. **Segunda
alternativa:** pantalla de código separada tras la contraseña con cookie de reto;
descartada por añadir estado y cookies, y porque el formulario de una sola pasada
con campo `code` reutiliza el límite de intentos sin tablas nuevas.

## Supuestos a confirmar (defaults configurables, sin requisitos legales inventados)

- **S1** TOTP sin proveedor externo; Google/Microsoft fuera de alcance (acceptance).
- **S2** Obligatorio por defecto solo en producción (`PANEL_2FA_REQUIRED`); el dueño puede fijarlo explícitamente, incluso a `false`.
- **S3** Ventana ±1 paso (`PANEL_2FA_WINDOW_STEPS`) y 8 códigos de recuperación (`PANEL_2FA_RECOVERY_CODES`).
- **S4** Sin autoservicio para desactivar ni regenerar códigos: solo restablece un administrador; un admin que pierde su factor y sus códigos necesita a otro admin o el procedimiento SQL operativo (R46–R48); el bootstrap #23 no sirve porque se niega si ya existe un administrador.
- **S5** Códigos de recuperación de 80 bits con SHA-256 sin sal: la entropía alta hace inviable la fuerza bruta; el hash ya cumple «guardados como hash».
- **S6** El administrador no puede restablecerse a sí mismo (R36).
- **S7** Sin QR: secreto en base32 y URI para copiar o pegar en la app autenticadora.
- **S8** Cambiar `PANEL_2FA_REQUIRED` a `true` no cierra sesiones existentes; vencen por TTL.
- **S9** Rotación de `PANEL_2FA_ENCRYPTION_KEY` no soportada: cambiarla exige ejecutar el procedimiento SQL de recuperación para los perfiles afectados (R47).
- **S10** `last_used_step` es estrictamente monótono; aceptar un código del paso siguiente (dentro de la ventana) invalida el paso actual.
