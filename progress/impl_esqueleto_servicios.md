# Implementación — esqueleto_servicios

Estado: T1..T19 completas. `python -m pytest`: 386 passed (exit 0). `./init.sh`: `[OK] Todos los tests pasan`, entorno listo.
`pytest --co -q` recoge los 5 archivos nuevos y `contracts/tests/` sin errores (R39).
Dependencias instaladas en .venv solo con `pip install -r services/<svc>/requirements.txt` (x4).
Las rutas `/_test/*` de los tests se registran dentro de los tests, no en la app.
Ficheros por servicio: `services/<svc>/tests/test_<svc>_app.py` (T = test). Infra: `services/orchestrator/tests/test_orchestrator_infra.py` (I).

## Trazabilidad R -> test

| R | Test |
|---|---|
| R1 | T::test_service_layout_exists |
| R2 | T::test_create_app_returns_fastapi |
| R3 | T::test_module_exposes_fastapi_app |
| R4 | T::test_settings_reads_service_token_from_env |
| R5 | T::test_requirements_txt_matches_design |
| R6 | T::test_dockerfile_base_image_and_cmd |
| R8 | T::test_health_returns_ok_without_token |
| R9 | T::test_health_body_matches_contract |
| R10 | T::test_health_ignores_wrong_token |
| R11 | T::test_missing_token_returns_401 |
| R12 | T::test_wrong_token_returns_401 |
| R13 | T::test_unknown_route_without_token_returns_401_not_404 |
| R14 | T::test_post_without_token_returns_401 |
| R15 | T::test_empty_configured_token_rejects_everything |
| R16 | T::test_valid_token_passes_auth |
| R17 | T::test_unknown_route_with_token_returns_not_found_error |
| R18 | T::test_invalid_body_returns_validation_error |
| R19 | T::test_unhandled_exception_returns_internal_error |
| R20 | T::test_domain_error_maps_to_its_code_and_status |
| R21 | I::test_compose_defines_all_services |
| R22 | I::test_postgres_uses_pgvector_image |
| R23 | I::test_redis_uses_bsd_licensed_image |
| R24 | T::test_compose_service_reads_env_file |
| R25 | I::test_postgres_reads_env_file |
| R26 | T::test_compose_service_publishes_expected_port |
| R27 | T::test_compose_service_builds_from_root_with_own_dockerfile |
| R28 | I::test_init_sql_enables_vector |
| R29 | I::test_postgres_mounts_init_scripts |
| R30 | T::test_settings_fields_are_in_env_example |
| R31 | I::test_compose_interpolated_vars_are_in_env_example |
| R32 | I::test_env_example_has_postgres_vars |
| R33 | I::test_ci_triggers_on_push_and_pull_request |
| R34 | I::test_ci_installs_dev_requirements |
| R35 | I::test_ci_runs_pytest |
| R36 | I::test_ci_uses_python_312 |
| R37 | I::test_dev_requirements_include_every_service |
| R38 | T::test_health_returns_ok_without_token, T::test_missing_token_returns_401 |
| R39 | `pytest --co -q`: 5 archivos nuevos + contracts/tests, sin errores |
| R40 | `./init.sh`: exit 0, `[OK] Todos los tests pasan` |
| R41 | T::test_module_app_imports_without_service_token |
| R42 | T::test_unhandled_exception_message_hides_details |
| R43 | `python -m pytest`: 386 passed, exit 0 |
