# Review — feature #21 panel_administracion (segunda revisión)

**Veredicto:** APPROVED

`./init.sh` ejecutado por el reviewer: 1310 passed, exit 0.

## Fixes de la revisión anterior
- Hallazgo 1 (oráculo de tiempo, R2/T3): [x] `services/orchestrator/orchestrator/domain.py:670-682`
  `_fake_password_hash` cachea el hash ficticio por número de iteraciones en `_fake_password_hashes`.
  En `authenticate_admin` (`domain.py:704-708`) el usuario inexistente hace un único PBKDF2
  (`verify_password`) a partir del segundo login, igual que con una contraseña incorrecta o un rol
  no admin (`domain.py:710-714`). El límite (R11) se sigue comprobando antes (`domain.py:697-702`).
- Hallazgo 2 (test): [x] `services/orchestrator/tests/test_admin.py:167-195` espía
  `hashlib.pbkdf2_hmac` (`accounts.py` resuelve el atributo al llamarlo, así que el espía lo intercepta),
  calienta la caché y exige `unknown == wrong == not_admin == 1`. Con el código anterior,
  `unknown` sería 2 y el test fallaría, así que la regresión queda cubierta.

## Trazabilidad requirements ↔ tests
- R1: [x] `test_login_creates_session_and_sets_cookie_attributes`, `test_session_ttl_is_configurable`, `test_login_uses_secure_cookie_when_configured`
- R2: [x] `test_failed_login_returns_same_response_for_all_three_cases`, `test_login_unknown_user_still_runs_password_comparison`
- R3: [x] `test_admin_routes_redirect_without_session`, `test_expired_session_redirects_to_login`, `test_logout_closes_session`, `test_demoted_admin_session_is_rejected`, `test_login_and_static_css_are_public`
- R4: [x] `test_post_without_or_with_wrong_csrf_is_forbidden`, `test_post_without_session_redirects_before_csrf`
- R5: [x] `test_admin_html_has_csp_and_no_external_resources`
- R6: [x] `test_admin_responses_never_include_service_token_or_password`
- R7: [x] `test_create_profile_from_panel_and_list_it`, `test_invalid_profile_from_panel_returns_422`, `test_duplicate_profile_from_panel_returns_409`
- R8: [x] `test_change_role_and_protect_last_admin`, `test_change_role_rejects_invalid_role`
- R9: [x] `test_link_token_page_shows_link_and_expiry_once_with_no_store`, `test_link_token_for_unknown_profile_returns_404`
- R10: [x] `test_events_are_recent_first_short_and_redacted`, `test_events_respect_configured_limit`, `test_redact_reason_and_short_id_are_pure`
- R11: [x] `test_login_throttled_by_username_after_max_failures`, `test_login_throttled_by_ip_after_max_failures`, `test_throttled_login_does_not_call_verify_password`, `test_throttle_expires_when_failures_leave_the_window`, `test_successful_login_resets_username_failures`, `test_forwarded_for_is_ignored_without_trust`, `test_forwarded_for_is_used_with_trust`

## Tasks completas
- T1: [x]
- T2: [x]
- T3: [x] (el defecto del hash ficticio está corregido)
- T4: [x]
- T5: [x]
- T6: [x]

## Checkpoints
- C1: [x] (`./init.sh` exit 0)
- C2: [x] (solo #21 en `in_progress`)
- C3: [x] (sin dependencias nuevas, SQL parametrizado, sin `print`/`eval`/`exec`/TODO en `admin*.py` ni en `domain.py`, variables nuevas en `.env.example`)
- C4: [x] (1310 verdes; las pruebas de seguridad de R2, R5, R6 y R11 existen y pasan)
- C5: [x] (se valida al cierre de sesión)
- C6: [x]

## Observaciones no bloqueantes (siguen de la revisión anterior)
- `admin_routes.py` `_form`: un cuerpo que no es UTF-8 acaba en un 500 genérico; mejor usar `errors="replace"` o responder 422.
- Las rutas inexistentes bajo `/admin/*` devuelven el 404/405 JSON genérico y no un 303 a login. No ejecutan nada.
- `FakeRepository.list_profiles` devuelve el orden de inserción y Postgres ordena por `username`.
- El barrido de R5/R6 no incluye las páginas de error 401/403/404/409/422/429.
- Un perfil cuyo hash se creó con un número de iteraciones distinto del actual tarda distinto que el hash ficticio. Es un riesgo menor que solo aparece si se cambia `PASSWORD_HASH_ITERATIONS`.
