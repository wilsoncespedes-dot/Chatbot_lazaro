# Review — feature #54 segundo_factor_panel

**Veredicto:** APPROVED

`./init.sh` (ejecutado tras las correcciones): exit 0, 3489 passed, 1 skipped, 2 avisos de deprecación ajenos a la feature.

## Trazabilidad requirements ↔ tests
La tabla R→test de `progress/impl_segundo_factor_panel.md` cubre R1–R48 y cada test existe en `services/orchestrator/tests/`. Cobertura destacada:
- R1: [x] `test_rfc6238_appendix_b_vectors`
- R2, R3, R4: [x] `test_two_factor_pure.py` (ventana, fuera de ventana, formato) y `test_window_allows_only_configured_offset`
- R5–R9: [x] `test_two_factor_routes.py`
- R10–R16: [x] `test_two_factor_login.py`
- R17–R20: [x] `test_two_factor_login.py` y `test_two_factor_repository.py`. R19 se prueba con `test_concurrent_same_step_advance_accepts_only_one`. El SQL de `advance_two_factor_step` es un `UPDATE … WHERE last_used_step < %s RETURNING`, atómico.
- R21–R22, R41–R43: [x] `test_two_factor_config.py`
- R23–R26: [x] `test_two_factor_login.py` y `test_two_factor_routes.py`
- R27–R30: [x] `test_two_factor_pure.py` y `test_two_factor_secrets.py`
- R31–R34: [x] `test_two_factor_pure.py`, `test_two_factor_login.py` y `test_two_factor_repository.py`. `consume_recovery_code` hace un `UPDATE … WHERE used_at IS NULL RETURNING`, de un solo uso.
- R35–R39: [x] `test_two_factor_reset.py`
- R40: [x] `test_invalid_confirmation_keeps_pending_and_csrf_is_required`, `test_page_values_are_escaped`
- R44: [x] `test_documented_variables_exist_in_env_example_render_and_docs`
- R45: [x] `test_two_factor_acceso_regression.py`
- R46–R48: [x] `test_two_factor_recovery_doc.py`

## Tasks completas
- T0–T18: [x] Todas en `[x]` en `specs/segundo_factor_panel/tasks.md`.

## Puntos revisados especialmente
- **Procedimiento SQL de recuperación (`docs/despliegue.md` §6 y §6.1):** es correcto y seguro.
  - Corre en una sola transacción `BEGIN … COMMIT`.
  - El perfil se declara explícitamente con `:'profile_id'` y el operador con `:'operator'`, ambos como literales psql citados. No hay concatenación insegura.
  - El `INSERT INTO panel_audit` va antes de los tres `DELETE`. Usa `actor_profile_id='ops:'||operador` (no nulo, y la tabla no tiene FK) y `action='two_factor_reset_ops'`.
  - Los tres `DELETE` coinciden con las tablas y columnas del esquema (`staff_recovery_codes`, `staff_two_factor`, `admin_sessions`, todas con `profile_id`).
  - Si el perfil no existe, no inserta ni borra nada.
  - Si un paso falla, el `COMMIT` queda en `ROLLBACK`.
  - No selecciona `secret_ciphertext`, hashes ni la clave. Avisa de que el bootstrap #23 no sirve. La variante §6.1 cubre la pérdida o cambio de `PANEL_2FA_ENCRYPTION_KEY` e indica que no se rota sin ejecutarla. El perfil queda sin factor (R39).
  - El procedimiento borra todas las sesiones del perfil, como corresponde a una recuperación operativa.
- **Preservar solo la sesión que confirmó (R25):** `confirm_two_factor_enrollment` llama a `promote_session(token)` y luego a `delete_sessions_for_profile(profile.id, keep_token_hash=token)`. Las sesiones de otros perfiles no se tocan. Los tests cubren sesión restringida y sesión normal.
- **Activación y anti-replay:**
  - La activación es atómica (CTE `UPDATE … WHERE enabled_at IS NULL` más inserción de códigos condicionada).
  - El paso de confirmación se guarda como último paso (R20).
- **Secretos:** solo se guarda el texto cifrado con Fernet. `test_two_factor_secrets.py` comprueba logs, auditoría, eventos y respuestas. No se encontraron secretos en el repo.

## Checkpoints
- C1–C6: [x] Todos cumplidos. Tests verdes, trazabilidad completa, tasks completas, sin cambios en contratos ni otros servicios, y sin secretos.

## Cambios requeridos
Ninguno.
