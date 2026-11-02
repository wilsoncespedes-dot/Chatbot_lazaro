# Implementación — #20 verificacion_cuentas

Estado: implementado (T1–T6), pendiente de `./init.sh` y revisión de código.

## Resumen

Solo `services/orchestrator`. Se añaden perfiles con rol y contraseña en
PBKDF2-SHA256 (`accounts.py`), tablas `profiles`/`link_tokens` en el
repositorio (falso y Postgres), emisión de tokens de un solo uso y el vínculo
por `/start <token>` con consumo atómico (`UPDATE ... WHERE used_at IS NULL`).
Las rutas internas `POST /profiles` y `POST /profiles/{id}/link-token` quedan
protegidas por el middleware `X-Service-Token`. No hay dependencias nuevas.
Se actualizó `test_only_health_and_messages_routes_exposed` para incluir las
dos rutas nuevas.

## Trazabilidad

- R1 → `services/orchestrator/tests/test_accounts.py::test_create_profile_returns_201_without_password`
- R1 → `services/orchestrator/tests/test_accounts.py::test_create_profile_normalizes_username_to_lowercase`
- R1 → `services/orchestrator/tests/test_accounts.py::test_invalid_role_returns_422`
- R1 → `services/orchestrator/tests/test_accounts.py::test_invalid_username_returns_422`
- R1 → `services/orchestrator/tests/test_accounts.py::test_short_password_returns_422`
- R1 → `services/orchestrator/tests/test_accounts.py::test_password_min_length_is_configurable`
- R2 → `services/orchestrator/tests/test_accounts.py::test_duplicate_username_is_case_insensitive_and_returns_409`
- R3 → `services/orchestrator/tests/test_accounts.py::test_hash_password_format_salt_and_verify`
- R3 → `services/orchestrator/tests/test_accounts.py::test_create_profile_returns_201_without_password`
- R3 → `services/orchestrator/tests/test_accounts.py::test_profile_password_never_appears_in_logs`
- R4 → `services/orchestrator/tests/test_accounts.py::test_issue_link_token_stores_only_hash_and_uses_fixed_ttl`
- R4 → `services/orchestrator/tests/test_accounts.py::test_issue_link_token_link_is_null_without_bot_username`
- R5 → `services/orchestrator/tests/test_accounts.py::test_issue_link_token_for_unknown_profile_returns_404`
- R6 → `services/orchestrator/tests/test_accounts.py::test_parse_start_token`
- R6 → `services/orchestrator/tests/test_accounts.py::test_start_token_links_sender_and_consumes_token`
- R7 → `services/orchestrator/tests/test_accounts.py::test_unknown_token_sends_failed_reply_without_consuming`
- R7 → `services/orchestrator/tests/test_accounts.py::test_expired_token_sends_failed_reply_and_stays_unused`
- R7 → `services/orchestrator/tests/test_accounts.py::test_reused_token_sends_failed_reply`
- R7 → `services/orchestrator/tests/test_accounts.py::test_account_already_linked_to_another_profile_sends_failed_reply`
- R8 → `services/orchestrator/tests/test_accounts.py::test_two_concurrent_consumptions_only_one_wins`
- R8 → `services/orchestrator/tests/test_accounts.py::test_postgres_consume_link_token_is_atomic_single_statement`
- R9 → `services/orchestrator/tests/test_accounts.py::test_start_token_links_sender_and_consumes_token`
- R9 → `services/orchestrator/tests/test_accounts.py::test_unknown_token_sends_failed_reply_without_consuming`
- R10 → `services/orchestrator/tests/test_accounts.py::test_profile_routes_require_service_token`

## Corrección del fallo de init.sh (resuelto)

`init.sh` había dado 1 failed, 1267 passed en
`services/orchestrator/tests/test_adapters.py::test_postgres_repository_uses_parameters_only`
(`assert "'" not in sql`) por el DDL de `profiles`:
`CHECK (role IN ('admin','asesor','cliente'))` introducía literales entre comillas.

Corrección: se eliminó esa cláusula `CHECK` de `_SCHEMA` y el rol se sigue validando en
el modelo Pydantic `ProfileCreateRequest` (R1), sin tocar el test existente ni debilitarlo.
El DDL nuevo queda sin comillas y el test vuelve a pasar. Pendiente de ejecutar
`./init.sh` de nuevo para confirmar todo en verde.
