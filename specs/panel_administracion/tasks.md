# #21 panel_administracion — Tasks

Todo en `services/orchestrator/`. Tests en `tests/test_admin.py`, con
`FakeRepository` y `TestClient`, y `password_hash_iterations` bajo en los tests.

- [x] **T1. Config y esquema.** Añadir `ADMIN_SESSION_TTL_MINUTES`,
  `ADMIN_COOKIE_SECURE`, `ADMIN_EVENTS_LIMIT`, `ADMIN_LOGIN_MAX_ATTEMPTS` (5),
  `ADMIN_LOGIN_WINDOW_MINUTES` (15) y `ADMIN_TRUST_PROXY_HEADERS` (false) a
  `config.py` y `.env.example`, con los rangos del design.
  Crear las tablas `admin_sessions` y `admin_login_attempts` y los métodos de
  repositorio del design (`get_profile_credentials`, `list_profiles`, `set_role`,
  `create_session`, `get_session`, `delete_session`, `recent_events`,
  `count_login_failures`, `record_login_failure`, `clear_login_failures`) en
  Protocol, Fake y Postgres, con SQL parametrizado. — R1, R3, R8, R10, R11
- [x] **T2. Lógica pura `admin.py`.** `redact_reason`, `short_id`, plantillas con
  `html.escape`, constante CSS, helper de cabeceras (CSP, nosniff, no-store).
  Tests unitarios de redacción y de que no haya orígenes externos. — R5, R10
- [x] **T3. Dominio.** `authenticate_admin` (hash ficticio si el usuario no
  existe; comprobación del límite de intentos **antes** de `verify_password`,
  registro de fallos y reinicio al acertar, `LoginThrottled`), `change_role` con
  `LastAdmin`, y `list_profiles`/`recent_events`. — R1, R2, R8, R11
- [x] **T4. Sesión y CSRF.** Router `/admin`: `GET/POST /admin/login`,
  `POST /admin/logout`, `GET /admin/static/admin.css` (sin sesión); `client_ip`;
  una dependencia que exige sesión (si no, `303` a login) y que en cada POST
  exige el `csrf_token` (si no, `403`). En `main.py`: `include_router` y dejar
  `/admin` fuera del middleware `X-Service-Token`. Tests: login ok y cookie con
  sus atributos; tres fallos de login con la misma respuesta; sin cookie, cookie
  expirada, tras logout y con el rol degradado → `303`; `GET
  /admin/static/admin.css` sin cookie → `200`; CSRF ausente o erróneo → `403`
  sin efecto. Límite: N fallos por username y N fallos por IP → `429` con el
  mismo mensaje y sin cookie; el `429` no ejecuta `verify_password` (espía);
  tras avanzar el reloj más allá de la ventana se puede entrar otra vez; un
  login correcto reinicia el contador del username; `X-Forwarded-For` se ignora
  salvo con `ADMIN_TRUST_PROXY_HEADERS=true`. — R1, R2, R3, R4, R11
- [x] **T5. Vistas.** `GET /admin` (inicio), `GET/POST /admin/profiles`,
  `POST /admin/profiles/{id}/role`, `POST /admin/profiles/{id}/link-token`,
  `GET /admin/events`. Tests: crear perfil (ok / 422 / 409); cambio de rol y
  `last_admin`; página del enlace con `no-store`; los eventos en orden y
  redactados. — R7, R8, R9, R10
- [x] **T6. Barrido de seguridad.** Test que recorre todas las respuestas de
  `/admin` (con un `SERVICE_TOKEN` centinela y una contraseña centinela) y
  comprueba que ni el token, ni la contraseña, ni `pbkdf2_sha256$` aparezcan en
  el cuerpo, las cabeceras o las cookies, y que cada HTML lleve la CSP y no
  tenga `src=`/`href=` externos. Ejecutar `./init.sh`. — R5, R6
