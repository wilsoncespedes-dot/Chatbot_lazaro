# Implementación #21 panel_administracion

Estado: implementado y corregido tras el fallo del intento 1 y tras el informe
de revisión `progress/review_panel_administracion.md`; pendiente de `./init.sh`
y revisión de Claude.

## Resumen

- `orchestrator/admin.py`: utilidades puras y plantillas HTML (CSP, redacción,
  short_id, CSS propio, escape con `html.escape`). Sin JS ni recursos externos.
- `orchestrator/admin_routes.py`: router `/admin` con login/logout, perfiles,
  cambio de rol, enlace de vinculación y eventos; sesión y CSRF obligatorios.
- `orchestrator/domain.py`: `authenticate_admin`, `change_role`,
  `list_profiles`, `recent_events`, `LastAdmin` y `LoginThrottled`.
- `orchestrator/adapters/repository.py`: tablas `admin_sessions` y
  `admin_login_attempts`, métodos nuevos en Protocol, Fake y Postgres con SQL
  parametrizado.
- `orchestrator/main.py`: `/admin` fuera del middleware `X-Service-Token`,
  rutas del panel registradas directamente en `app.router.routes` (la versión
  de FastAPI instalada envuelve `include_router` en un objeto sin `path`) y
  respuestas 303/403 HTML para sesión y CSRF.
- `config.py` y `.env.example`: seis variables nuevas con sus rangos.
- `tests/test_admin.py`: tests que cubren R1–R11 (incluidas las pruebas de
  seguridad de R5, R6 y R11).
- `tests/test_config.py`: se amplía la lista exacta de rutas con las de `/admin`
  (no se elimina ninguna aserción existente).

## Trazabilidad

- R1 → `services/orchestrator/tests/test_admin.py::test_login_creates_session_and_sets_cookie_attributes`
- R1 → `services/orchestrator/tests/test_admin.py::test_session_ttl_is_configurable`
- R1 → `services/orchestrator/tests/test_admin.py::test_login_uses_secure_cookie_when_configured`
- R2 → `services/orchestrator/tests/test_admin.py::test_failed_login_returns_same_response_for_all_three_cases`
- R2 → `services/orchestrator/tests/test_admin.py::test_login_unknown_user_still_runs_password_comparison`
- R3 → `services/orchestrator/tests/test_admin.py::test_admin_routes_redirect_without_session`
- R3 → `services/orchestrator/tests/test_admin.py::test_expired_session_redirects_to_login`
- R3 → `services/orchestrator/tests/test_admin.py::test_logout_closes_session`
- R3 → `services/orchestrator/tests/test_admin.py::test_demoted_admin_session_is_rejected`
- R3 → `services/orchestrator/tests/test_admin.py::test_login_and_static_css_are_public`
- R4 → `services/orchestrator/tests/test_admin.py::test_post_without_or_with_wrong_csrf_is_forbidden`
- R4 → `services/orchestrator/tests/test_admin.py::test_post_without_session_redirects_before_csrf`
- R5 → `services/orchestrator/tests/test_admin.py::test_admin_html_has_csp_and_no_external_resources`
- R6 → `services/orchestrator/tests/test_admin.py::test_admin_responses_never_include_service_token_or_password`
- R7 → `services/orchestrator/tests/test_admin.py::test_create_profile_from_panel_and_list_it`
- R7 → `services/orchestrator/tests/test_admin.py::test_invalid_profile_from_panel_returns_422`
- R7 → `services/orchestrator/tests/test_admin.py::test_duplicate_profile_from_panel_returns_409`
- R8 → `services/orchestrator/tests/test_admin.py::test_change_role_and_protect_last_admin`
- R8 → `services/orchestrator/tests/test_admin.py::test_change_role_rejects_invalid_role`
- R9 → `services/orchestrator/tests/test_admin.py::test_link_token_page_shows_link_and_expiry_once_with_no_store`
- R9 → `services/orchestrator/tests/test_admin.py::test_link_token_for_unknown_profile_returns_404`
- R10 → `services/orchestrator/tests/test_admin.py::test_events_are_recent_first_short_and_redacted`
- R10 → `services/orchestrator/tests/test_admin.py::test_events_respect_configured_limit`
- R11 → `services/orchestrator/tests/test_admin.py::test_login_throttled_by_username_after_max_failures`
- R11 → `services/orchestrator/tests/test_admin.py::test_login_throttled_by_ip_after_max_failures`
- R11 → `services/orchestrator/tests/test_admin.py::test_throttled_login_does_not_call_verify_password`
- R11 → `services/orchestrator/tests/test_admin.py::test_throttle_expires_when_failures_leave_the_window`
- R11 → `services/orchestrator/tests/test_admin.py::test_successful_login_resets_username_failures`
- R11 → `services/orchestrator/tests/test_admin.py::test_forwarded_for_is_ignored_without_trust`
- R11 → `services/orchestrator/tests/test_admin.py::test_forwarded_for_is_used_with_trust`

## Notas para la revisión

- El login devuelve 401 con la misma plantilla y mensaje que los tres fallos de
  R2; el 429 de R11 usa exactamente la misma respuesta.
- La comprobación del límite ocurre antes de `verify_password`; un usuario
  inexistente sí ejecuta `verify_password` contra un hash ficticio (R2).
- `set_role` en Postgres es un único `UPDATE ... RETURNING` condicionado a que
  quede al menos un admin (R8).
- Las sesiones se rechazan si el perfil deja de ser admin (R3).
- La tabla de intentos se purga con la misma ventana deslizante (R11) y los
  índices se crean aparte de `_SCHEMA` para no romper el test existente de
  creación de esquema.

## Verificación `./init.sh` — intento 1 (FAIL)

- Resultado: 1 failed, 1309 passed.
- Fallo: `services/orchestrator/tests/test_config.py::test_only_health_and_messages_routes_exposed`.
  Las rutas `/admin`, `/admin/login`, `/admin/logout`, `/admin/static/admin.css`,
  `/admin/profiles`, `/admin/profiles/{profile_id}/role`,
  `/admin/profiles/{profile_id}/link-token` y `/admin/events` NO aparecen en
  `app.routes`: el router de `admin_routes.py` no está registrado en la app
  (falta o no se ejecuta `include_router` en `orchestrator/main.py`).
- Corrección pedida: registrar el router `/admin` en `main.py` (T4) sin tocar
  el test; asegurar que `test_admin.py` ejercita la app real.
- Diagnóstico (Claude): `include_router` sí se ejecuta, pero la versión de
  FastAPI instalada en `.venv` registra el router como un único objeto
  `_IncludedRouter` en `app.routes` (sin `path`), no como `APIRoute` aplanadas.
  Por eso el test (que filtra `isinstance(r, APIRoute)`) no ve las rutas `/admin`.
  Resolver de forma que `{r.path for r in app.routes if isinstance(r, APIRoute)}`
  incluya las ocho rutas `/admin`   (p. ej. registrar las rutas del panel
  directamente en la app en lugar de con `include_router`), sin debilitar el test
  ni romper `test_admin.py`.

## Corrección aplicada tras el intento 1

- `orchestrator/admin_routes.py`: el `APIRouter` se crea sin `prefix` y cada
  ruta declara su ruta completa (`/admin/...`), para que `route.path` sea
  siempre la ruta final.
- `orchestrator/main.py`: en lugar de `include_router`, se hace
  `app.router.routes.extend(create_admin_router(...).routes)`. Así
  `{r.path for r in app.routes if isinstance(r, APIRoute)}` contiene las ocho
  rutas `/admin` y el comportamiento HTTP no cambia.
- No se modificó `tests/test_config.py` ni se debilitó ninguna aserción.
- `./init.sh` queda pendiente de ejecutarlo Claude al cerrar la sesión.

## Corrección tras la revisión de código (CHANGES_REQUESTED)

- Hallazgo 1 (oráculo de tiempo en el login, R2): `domain.py` cacheadiza el hash
  ficticio por número de iteraciones (`_fake_password_hashes` +
  `_fake_password_hash`). Un `username` inexistente ejecuta ahora exactamente
  una llamada a PBKDF2 (la de `verify_password`), igual que una contraseña
  incorrecta o un rol no admin; antes hacía dos (calcular el hash ficticio y
  verificarlo).
- Hallazgo 2 (test que lo demuestra): `test_login_unknown_user_still_runs_password_comparison`
  cuenta las llamadas a `hashlib.pbkdf2_hmac`, calienta la caché con un primer
  login y exige `1` llamada para usuario inexistente, contraseña incorrecta y
  rol no admin.
- No se eliminan aserciones existentes ni se cambia el estado de la feature.

## Verificación `./init.sh` — tras corrección 1 (OK)

- Resultado: 1310 passed, 0 failed. Entorno listo.
- Corrección: `main.py` añade las rutas del router del panel con
  `app.router.routes.extend(create_admin_router(...).routes)`; el test de rutas
  conserva la igualdad exacta con las ocho rutas `/admin`.
- Nota: un primer reintento de OpenCode salió con código 255 sin cambios; el
  segundo completó la corrección.
- Trazabilidad R1–R11 → test: presente (sección «Trazabilidad»).

## Corrección tras la revisión de código (CHANGES_REQUESTED)

- Hallazgo 1 (oráculo de tiempo, R2): `orchestrator/domain.py` ya no calcula el
  hash ficticio en cada login de usuario inexistente. `_fake_password_hash`
  cachea a nivel de módulo el hash ficticio por número de iteraciones, de modo
  que el camino de usuario inexistente hace exactamente una llamada a PBKDF2
  (`verify_password`), igual que contraseña incorrecta y rol no admin. Antes
  eran dos PBKDF2 (hash ficticio + verificación) y el tiempo revelaba si el
  usuario existía.
- Hallazgo 2 (test): `test_login_unknown_user_still_runs_password_comparison`
  ahora espía `hashlib.pbkdf2_hmac` y exige exactamente 1 ejecución para
  usuario inexistente, contraseña incorrecta y rol no admin, tras calentar la
  caché con un primer login.
- `./init.sh` pendiente de ejecutarlo Claude al cerrar la sesión.


## Corrección de revisión 1 (CHANGES_REQUESTED) — `./init.sh` OK

- Hallazgos 1 y 2 de `progress/review_panel_administracion.md` delegados a
  OpenCode: hash ficticio cacheado por número de iteraciones (una sola PBKDF2
  para usuario inexistente) y test con espía sobre `hashlib.pbkdf2_hmac`.
- `./init.sh`: 1310 passed, 0 failed. Entorno listo.
