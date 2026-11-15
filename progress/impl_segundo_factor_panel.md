# Implementación — segundo_factor_panel (#54)

## Resumen

Segundo factor TOTP (RFC 6238) para los paneles `/admin` y `/asesor`:

- `orchestrator/two_factor.py`: TOTP con HMAC-SHA1, ventana configurable,
  secreto de 160 bits, URI `otpauth://`, cifrado Fernet y códigos de
  recuperación de 80 bits con hash SHA-256. Solo biblioteca estándar y
  `cryptography.fernet`.
- `config.py`: `PANEL_2FA_*`, propiedad `panel_2fa_required_effective` y
  validación de la clave Fernet en producción.
- Repositorio: tablas `staff_two_factor` y `staff_recovery_codes`, columna
  `admin_sessions.enroll_only`, paso monótono, consumo atómico de códigos y
  sesiones restringidas ocultas a `get_session*`.
- Dominio: login con código o recuperación, registro pendiente/confirmación,
  borrado de las demás sesiones al confirmar y restablecimiento por admin.
- Rutas/páginas: `GET/POST /{admin,asesor}/2fa[/start|/confirm]`, botón y ruta
  `POST /admin/profiles/{id}/2fa/reset`, campo `code` en ambos logins y cierre
  de sesión que acepta sesiones restringidas.
- Configuración y documentación: variables en `.env.example`, `render.yaml` y
  `docs/despliegue.md`, con el SQL operativo de recuperación.

No se toca `contracts/`, gateways, handover ni rag. T0 (instalación de
`cryptography`) ya estaba completada por el humano. T16 queda pendiente de que
Claude ejecute `./init.sh` y añada el resultado; el mapa R→test está abajo.

## Trazabilidad

- R1 → `tests/test_two_factor_pure.py::test_rfc6238_appendix_b_vectors`
- R2 → `tests/test_two_factor_pure.py::test_window_accepts_previous_and_next_step`, `tests/test_two_factor_login.py::test_window_allows_only_configured_offset`
- R3 → `tests/test_two_factor_pure.py::test_outside_window_is_rejected`, `tests/test_two_factor_login.py::test_window_allows_only_configured_offset`
- R4 → `tests/test_two_factor_pure.py::test_non_six_ascii_digits_are_rejected_without_exception`
- R5 → `tests/test_two_factor_pure.py::test_provisioning_uri_contains_issuer_and_secret`, `tests/test_two_factor_routes.py::test_enrollment_in_both_panels_shows_secret_only_once`
- R6 → `tests/test_two_factor_routes.py::test_enrollment_in_both_panels_shows_secret_only_once`
- R7 → `tests/test_two_factor_routes.py::test_invalid_confirmation_keeps_pending_and_csrf_is_required`
- R8 → `tests/test_two_factor_repository.py::test_save_pending_never_replaces_an_active_secret`, `tests/test_two_factor_routes.py::test_enrollment_in_both_panels_shows_secret_only_once`
- R9 → `tests/test_two_factor_routes.py::test_client_role_and_missing_session_cannot_enroll`
- R10 → `tests/test_two_factor_login.py::test_login_with_active_factor_requires_valid_code`
- R11 → `tests/test_two_factor_login.py::test_missing_code_does_not_count_as_failure`
- R12 → `tests/test_two_factor_login.py::test_wrong_code_counts_as_failure_and_creates_no_session`
- R13 → `tests/test_two_factor_login.py::test_throttle_wins_even_with_correct_code`
- R14 → `tests/test_two_factor_login.py::test_login_with_active_factor_requires_valid_code`
- R15 → `tests/test_two_factor_login.py::test_unknown_user_and_wrong_password_share_result`
- R16 → `tests/test_two_factor_login.py::test_invalid_key_fails_closed`, `tests/test_two_factor_config.py::test_production_requires_a_valid_encryption_key`
- R17 → `tests/test_two_factor_login.py::test_repeated_and_previous_steps_are_rejected`, `tests/test_two_factor_repository.py::test_activation_and_step_advance_are_monotonic`
- R18 → `tests/test_two_factor_login.py::test_repeated_and_previous_steps_are_rejected`, `tests/test_two_factor_repository.py::test_activation_and_step_advance_are_monotonic`
- R19 → `tests/test_two_factor_repository.py::test_concurrent_same_step_advance_accepts_only_one`
- R20 → `tests/test_two_factor_login.py::test_confirmation_step_cannot_be_reused_at_login`, `tests/test_two_factor_repository.py::test_activation_and_step_advance_are_monotonic`
- R21 → `tests/test_two_factor_config.py::test_required_defaults_by_environment`, `::test_empty_required_variable_means_unset`
- R22 → `tests/test_two_factor_config.py::test_explicit_required_is_respected_in_any_environment`
- R23 → `tests/test_two_factor_login.py::test_required_without_factor_creates_restricted_session`, `tests/test_two_factor_routes.py::test_restricted_session_only_reaches_enrollment_and_logout`
- R24 → `tests/test_two_factor_routes.py::test_restricted_session_only_reaches_enrollment_and_logout`, `tests/test_two_factor_repository.py::test_restricted_sessions_are_hidden_from_normal_reads`
- R25 → `tests/test_two_factor_routes.py::test_confirmation_promotes_restricted_session_and_removes_other_sessions`, `::test_normal_session_confirmation_also_removes_other_sessions`
- R26 → `tests/test_two_factor_login.py::test_login_without_factor_only_needs_password`
- R27 → `tests/test_two_factor_pure.py::test_encrypt_round_trip_and_ciphertext_hides_secret`, `tests/test_two_factor_secrets.py::test_enrollment_login_and_reset_never_leak_secrets`
- R28 → `tests/test_two_factor_routes.py::test_enrollment_in_both_panels_shows_secret_only_once`, `tests/test_two_factor_secrets.py::test_enrollment_login_and_reset_never_leak_secrets`
- R29 → `tests/test_two_factor_secrets.py::test_enrollment_login_and_reset_never_leak_secrets`, `::test_recovery_login_does_not_log_the_code`
- R30 → `tests/test_two_factor_routes.py::test_enrollment_in_both_panels_shows_secret_only_once`
- R31 → `tests/test_two_factor_pure.py::test_recovery_codes_format_uniqueness_and_normalization`
- R32 → `tests/test_two_factor_login.py::test_recovery_code_is_single_use_and_audited`, `tests/test_two_factor_repository.py::test_recovery_codes_are_single_use`
- R33 → `tests/test_two_factor_login.py::test_recovery_code_is_single_use_and_audited`, `tests/test_two_factor_repository.py::test_recovery_codes_are_single_use`
- R34 → `tests/test_two_factor_pure.py::test_recovery_codes_format_uniqueness_and_normalization`
- R35 → `tests/test_two_factor_reset.py::test_reset_removes_factor_sessions_and_audits`
- R36 → `tests/test_two_factor_reset.py::test_self_reset_is_rejected_without_changes`
- R37 → `tests/test_two_factor_reset.py::test_missing_profile_and_factor_return_404_and_409`
- R38 → `tests/test_two_factor_reset.py::test_non_admin_and_bad_csrf_are_forbidden_and_audited`
- R39 → `tests/test_two_factor_reset.py::test_reset_profile_logs_in_without_factor_and_gets_restricted_session`
- R40 → `tests/test_two_factor_routes.py::test_invalid_confirmation_keeps_pending_and_csrf_is_required`, `::test_page_values_are_escaped`
- R41 → `tests/test_two_factor_config.py::test_production_requires_a_valid_encryption_key`, `::test_production_rejects_invalid_key`
- R42 → `tests/test_two_factor_config.py::test_production_with_valid_key_keeps_required_true`
- R43 → `tests/test_two_factor_config.py::test_invalid_ranges_are_rejected`
- R44 → `tests/test_two_factor_config.py::test_documented_variables_exist_in_env_example_render_and_docs`
- R45 → `tests/test_two_factor_acceso_regression.py::test_client_login_form_has_no_verification_code`, `::test_acceso_without_valid_link_keeps_its_400`, `tests/test_two_factor_login.py::test_client_role_cannot_use_staff_login`
- R46 → `tests/test_two_factor_recovery_doc.py::test_recovery_sql_is_transactional_and_targets_one_profile`
- R47 → `tests/test_two_factor_recovery_doc.py::test_recovery_doc_covers_key_loss_and_bootstrap`
- R48 → `tests/test_two_factor_recovery_doc.py::test_recovery_doc_never_selects_secret_material_or_key_values`

## Notas

- `test_config.py::test_only_health_and_messages_routes_exposed` se actualizó
  con las seis rutas nuevas; su intención (conjunto exacto de rutas) no cambia.
- `test_production_config.py` añade una clave Fernet válida a su configuración
  base porque R41 la exige en producción.
- T16 no se marca: ejecutar `./init.sh` corresponde a Claude tras esta sesión.

## `init.sh` intento 1 — fallos

- Resultado: 13 failed, 3476 passed, 1 skipped. Hallazgos: `test_requirements_txt_matches_design` debe reconocer `cryptography`; 11 pruebas de `test_two_factor_login.py` usan la fixture `env` sin pedirla como parámetro; `test_non_admin_and_bad_csrf_are_forbidden_and_audited` no observa la auditoría del CSRF inválido; `test_recovery_login_does_not_log_the_code` intenta abrir `/admin/2fa` con factor activo y sin autenticación de segundo factor, por lo que solo obtiene el redirect de login. Corregir tests/setup dirigidamente, preservando el comportamiento de seguridad y probando un código de recuperación válido por el flujo de login.

## Correcciones tras el intento 1 (dirigidas)

- `tests/test_orchestrator_app.py::test_requirements_txt_matches_design`: se
  añade `cryptography` a la lista esperada (T0 ya la declaró en
  `requirements.txt`). La comprobación de cota doble se mantiene.
- `tests/test_two_factor_login.py`: las diez pruebas que usan el fixture local
  `env` ahora lo reciben como parámetro; no cambia ninguna aserción ni el flujo
  de seguridad.
- `tests/test_two_factor_reset.py::test_non_admin_and_bad_csrf_are_forbidden_and_audited`:
  la cookie manual del supervisor se crea con `path="/admin"` y se limpia antes
  del login del administrador, de modo que la petición sin CSRF se evalúa con
  el actor correcto y la auditoría `forbidden` es observable.
- `tests/test_two_factor_secrets.py::test_recovery_login_does_not_log_the_code`:
  usa un código de recuperación real generado y activado, inicia sesión por
  `/admin/login` (303) y comprueba que ni el código ni sus datos aparecen en
  logs/auditoría, con la fila `two_factor_recovery_used` presente.

Sin cambios en código de aplicación, contratos, harness ni otros servicios. El
mapa R→test sigue vigente. T16 sigue pendiente de la ejecución de `./init.sh`
por Claude.

## Verificación final

`bash ./init.sh`: exit 0, 3489 passed, 1 skipped y 2 avisos de deprecación.
T0–T18 completas; queda pendiente la revisión de código Claude.
