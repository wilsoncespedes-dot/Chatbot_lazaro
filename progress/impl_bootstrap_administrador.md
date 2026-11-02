# Implementación — #23 bootstrap_administrador

## Resumen

Comando local `python -m orchestrator.bootstrap_admin --username <nombre>` en
`services/orchestrator/orchestrator/bootstrap_admin.py`. Lee `DATABASE_URL` de
`Settings`, se niega si ya hay un administrador, valida el username con
`USERNAME_PATTERN`, pide la contraseña dos veces con `getpass.getpass` y guarda
solo `hash_password(...)` mediante `Repository.create_profile`. Códigos de
salida: `0` éxito, `1` admin existente, `2` entrada inválida, `UsernameTaken`,
`DATABASE_URL` vacía o error del repositorio. No añade rutas HTTP ni variables.

Se añadió la sección «Primer administrador» en `README.md`.

## Trazabilidad

- R1 → `services/orchestrator/tests/test_bootstrap_admin.py::test_bootstrap_creates_single_admin_with_hashed_password`
- R2 → `services/orchestrator/tests/test_bootstrap_admin.py::test_bootstrap_creates_single_admin_with_hashed_password`
- R3 → `services/orchestrator/tests/test_bootstrap_admin.py::test_password_is_read_twice_with_getpass_by_default`
- R4 → `services/orchestrator/tests/test_bootstrap_admin.py::test_password_option_is_rejected_without_creating_or_leaking`
- R4 → `services/orchestrator/tests/test_bootstrap_admin.py::test_environment_variable_is_never_used_as_password`
- R5 → `services/orchestrator/tests/test_bootstrap_admin.py::test_success_does_not_expose_password_in_out_err_or_logs`
- R5 → `services/orchestrator/tests/test_bootstrap_admin.py::test_mismatch_and_short_password_do_not_expose_password`
- R5 → `services/orchestrator/tests/test_bootstrap_admin.py::test_repository_error_does_not_expose_password`
- R6 → `services/orchestrator/tests/test_bootstrap_admin.py::test_existing_admin_exits_without_prompting_or_changing_data`
- R7 → `services/orchestrator/tests/test_bootstrap_admin.py::test_invalid_username_exits_without_profiles`
- R7 → `services/orchestrator/tests/test_bootstrap_admin.py::test_short_password_exits_without_profiles`
- R7 → `services/orchestrator/tests/test_bootstrap_admin.py::test_mismatched_passwords_exit_without_profiles`
- R8 → `services/orchestrator/tests/test_bootstrap_admin.py::test_username_taken_leaves_existing_profile_intact`
- R9 → `services/orchestrator/tests/test_bootstrap_admin.py::test_missing_database_url_exits_without_connecting`
- R10 → `services/orchestrator/tests/test_bootstrap_admin.py::test_app_exposes_no_bootstrap_route`

## Notas

- `_BootstrapParser.error` no imprime el mensaje de argparse porque puede
  contener el valor de `--password`; imprime una línea de uso fija.
- Las excepciones del repositorio solo exponen `type(exc).__name__`, nunca su
  mensaje ni la URL.
- La comprobación «ya hay admin» sigue el design (antes de pedir la contraseña);
  no se añadió la doble comprobación sugerida en la revisión, por mantenerse
  dentro del diseño aprobado.
