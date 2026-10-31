# Review — feature 2 (esqueleto_servicios)

**Veredicto:** APPROVED

`./init.sh` terminó verde: 386 passed, `[OK] Todos los tests pasan`, `.env` no está en git.

## Trazabilidad requirements ↔ tests
Todos los tests del mapa de `progress/impl_esqueleto_servicios.md` existen
en `services/*/tests/`. Hay 25 tests por servicio (`test_<svc>_app.py`) y 13 en
`services/orchestrator/tests/test_orchestrator_infra.py`.
- R1: [x] `test_service_layout_exists`
- R2: [x] `test_create_app_returns_fastapi`
- R3: [x] `test_module_exposes_fastapi_app`
- R4: [x] `test_settings_reads_service_token_from_env`
- R5: [x] `test_requirements_txt_matches_design`
- R6: [x] `test_dockerfile_base_image_and_cmd`
- R7: retirado en la revisión 2 del spec
- R8: [x] `test_health_returns_ok_without_token`
- R9: [x] `test_health_body_matches_contract`
- R10: [x] `test_health_ignores_wrong_token`
- R11: [x] `test_missing_token_returns_401`
- R12: [x] `test_wrong_token_returns_401`
- R13: [x] `test_unknown_route_without_token_returns_401_not_404`
- R14: [x] `test_post_without_token_returns_401`
- R15: [x] `test_empty_configured_token_rejects_everything`
- R16: [x] `test_valid_token_passes_auth`
- R17: [x] `test_unknown_route_with_token_returns_not_found_error`
- R18: [x] `test_invalid_body_returns_validation_error`
- R19: [x] `test_unhandled_exception_returns_internal_error`
- R20: [x] `test_domain_error_maps_to_its_code_and_status`
- R21: [x] `test_compose_defines_all_services`
- R22: [x] `test_postgres_uses_pgvector_image`
- R23: [x] `test_redis_uses_bsd_licensed_image`
- R24: [x] `test_compose_service_reads_env_file`
- R25: [x] `test_postgres_reads_env_file`
- R26: [x] `test_compose_service_publishes_expected_port`
- R27: [x] `test_compose_service_builds_from_root_with_own_dockerfile`
- R28: [x] `test_init_sql_enables_vector`
- R29: [x] `test_postgres_mounts_init_scripts`
- R30: [x] `test_settings_fields_are_in_env_example`
- R31: [x] `test_compose_interpolated_vars_are_in_env_example`
- R32: [x] `test_env_example_has_postgres_vars`
- R33: [x] `test_ci_triggers_on_push_and_pull_request`
- R34: [x] `test_ci_installs_dev_requirements`
- R35: [x] `test_ci_runs_pytest`
- R36: [x] `test_ci_uses_python_312`
- R37: [x] `test_dev_requirements_include_every_service`
- R38: [x] test de health y test de token ausente en los 4 servicios
- R39: [x] colección de pytest desde la raíz sin errores (386 tests)
- R40: [x] `./init.sh` con exit 0 y bloque de tests en `[OK]`
- R41: [x] `test_module_app_imports_without_service_token`
- R42: [x] `test_unhandled_exception_message_hides_details`
- R43: [x] `python -m pytest` en verde (386 passed)

## Tasks completas
- T1–T19: [x] todas en `[x]` en `specs/esqueleto_servicios/tasks.md`.

## Revisión de código
- Arquitectura: [x] cada servicio tiene `main.py`, `config.py`, `domain.py` y `adapters/`. Ningún servicio importa código de otro. Lo compartido sale de `lazaro_contracts`.
- Seguridad: [x] la comparación del token usa `hmac.compare_digest` y falla cerrado con token vacío. Las rutas desconocidas sin token dan 401. El 500 devuelve un mensaje genérico y el detalle va solo al log.
- Convenciones: [x] sin `print`, `eval` ni TODO. Dependencias con versión acotada y licencia MIT. El `Dockerfile` usa un usuario no root. `.env` está ignorado y las variables nuevas están en `.env.example`.
- Los 4 `main.py` son idénticos salvo el nombre del servicio (comprobado con diff entre rag y handover).

## Checkpoints
- C1: [x]
- C2: [x] solo la feature 2 está en `in_progress`.
- C3: [x]
- C4: [x] los tests no usan red ni base de datos reales.
- C5: [ ] no aplica a esta revisión. `progress/history.md` lo actualiza el cierre de sesión del leader. Los `__pycache__` están en `.gitignore`.
- C6: [x]

## Cambios requeridos
Ninguno.
