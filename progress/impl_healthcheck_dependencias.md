# Implementación — healthcheck_dependencias (#47)

## Resumen

`GET /health` de los cuatro servicios sigue siendo público y conserva el cuerpo
saludable `{"status":"ok","service":"<nombre>"}`. Ahora comprueba una
dependencia crítica con una operación de solo lectura y un timeout finito
(`HEALTHCHECK_TIMEOUT_SECONDS`, por defecto 2 s, máximo 10):

- `telegram_gateway`: Redis (`PING`).
- `orchestrator`, `rag` y `handover`: PostgreSQL (`SELECT 1` en una conexión
  independiente y acotada, sin inicializar esquema).

Si la dependencia falla o expira, responden `503` con `status = unhealthy` y
`dependencies = {"<dependencia>": "unavailable"}`, sin URL, credenciales, DSN ni
mensajes de excepción. Docker Compose marca `healthy`/`unhealthy` con
healthchecks HTTP y `redis-cli ping`, y espera a las dependencias saludables.

## Trazabilidad

- R1 → `services/telegram_gateway/tests/test_health_dependencies.py::test_health_ok_when_redis_responds`
- R1 → `services/orchestrator/tests/test_health_dependencies.py::test_health_ok_when_postgres_responds`
- R1 → `services/rag/tests/test_health_dependencies.py::test_health_ok_when_postgres_responds`
- R1 → `services/handover/tests/test_health_dependencies.py::test_health_ok_when_postgres_responds`
- R1 → `contracts/tests/test_contratos_doc.py::test_health_documents_healthy_response`
- R2 → `services/telegram_gateway/tests/test_health_dependencies.py::test_health_returns_503_when_redis_is_unavailable`
- R2 → `services/telegram_gateway/tests/test_health_dependencies.py::test_health_failure_body_does_not_expose_redis_url`
- R2 → `services/orchestrator/tests/test_health_dependencies.py::test_health_returns_503_when_postgres_fails`
- R2 → `services/rag/tests/test_health_dependencies.py::test_health_returns_503_when_postgres_fails`
- R2 → `services/handover/tests/test_health_dependencies.py::test_health_returns_503_when_postgres_fails`
- R2 → `contracts/tests/test_contratos_doc.py::test_health_documents_unhealthy_response_and_dependencies`
- R2 → `contracts/tests/test_contratos_doc.py::test_health_documents_that_no_sensitive_details_are_exposed`
- R2 → `contracts/tests/test_models.py::test_health_response_rejects_inconsistent_dependencies`
- R3 → `services/telegram_gateway/tests/test_health_dependencies.py::test_health_ok_when_redis_responds`
- R3 → `services/telegram_gateway/tests/test_health_dependencies.py::test_health_returns_503_when_redis_times_out`
- R3 → `services/telegram_gateway/tests/test_health_dependencies.py::test_redis_dedup_ping_uses_a_bounded_probe`
- R4 → `services/orchestrator/tests/test_health_dependencies.py::test_postgres_health_check_uses_select_one_without_schema`
- R4 → `services/rag/tests/test_health_dependencies.py::test_postgres_health_check_uses_select_one_without_schema`
- R4 → `services/handover/tests/test_health_dependencies.py::test_postgres_health_check_uses_select_one_without_schema`
- R5 → `services/telegram_gateway/tests/test_health_dependencies.py::test_healthcheck_timeout_must_be_positive_and_bounded`
- R5 → `services/orchestrator/tests/test_health_dependencies.py::test_healthcheck_timeout_must_be_positive_and_bounded`
- R5 → `services/rag/tests/test_health_dependencies.py::test_healthcheck_timeout_must_be_positive_and_bounded`
- R5 → `services/handover/tests/test_health_dependencies.py::test_healthcheck_timeout_must_be_positive_and_bounded`
- R5 → `services/orchestrator/tests/test_health_dependencies.py::test_postgres_health_check_uses_select_one_without_schema`
- R5 → `services/rag/tests/test_health_dependencies.py::test_postgres_health_check_uses_select_one_without_schema`
- R5 → `services/handover/tests/test_health_dependencies.py::test_postgres_health_check_uses_select_one_without_schema`
- R5 → `services/handover/tests/test_healthcheck_compose.py::test_env_example_declares_healthcheck_timeout`
- R6 → `services/handover/tests/test_healthcheck_compose.py::test_every_application_service_has_http_healthcheck`
- R6 → `services/handover/tests/test_healthcheck_compose.py::test_startup_dependencies_wait_for_healthy_dependencies`
- R7 → `services/handover/tests/test_healthcheck_compose.py::test_redis_healthcheck_uses_ping`
- R7 → `services/handover/tests/test_healthcheck_compose.py::test_every_application_service_has_http_healthcheck`
- R8 → `services/telegram_gateway/tests/test_health_dependencies.py::test_health_returns_503_when_redis_times_out`
- R8 → `services/telegram_gateway/tests/test_health_dependencies.py::test_health_returns_503_when_redis_is_unavailable`
- R8 → `services/orchestrator/tests/test_health_dependencies.py::test_health_returns_503_on_timeout`
- R8 → `services/rag/tests/test_health_dependencies.py::test_health_returns_503_on_timeout`
- R8 → `services/handover/tests/test_health_dependencies.py::test_health_returns_503_on_timeout`
- R8 → `services/orchestrator/tests/test_health_dependencies.py::test_postgres_health_check_propagates_failures_and_closes`
- R8 → `services/rag/tests/test_health_dependencies.py::test_postgres_health_check_propagates_failures_and_closes`
- R8 → `services/handover/tests/test_health_dependencies.py::test_postgres_health_check_propagates_failures_and_closes`
- R9 → `./init.sh` (pendiente de la verificación final de Claude)

## Contrato

- `HealthResponse` acepta `status` = `ok | unhealthy` y un mapa opcional
  `dependencies` de nombre → `unavailable`.
- Validación cruzada (review_healthcheck_dependencias, cambio 1): `unhealthy`
  exige un mapa `dependencies` no vacío y `ok` no admite `dependencies`. Los
  dos cuerpos válidos siguen aceptándose y los cuatro contradictorios se
  rechazan.
- `contracts/examples/health_unavailable_response.json` cubre el cuerpo no
  saludable; el ejemplo saludable no cambia.
- `contracts/CONTRATOS.md` §Salud documenta ambos resultados, el límite del
  probe y la ausencia de datos sensibles.

## Nota de verificación

No se ejecutaron comandos de shell en esta sesión (límite del implementer).
Claude ejecutará `./init.sh` al cerrar y añadirá el resultado.

## Verificación del leader

- `./init.sh`: **verde**, 3150 passed, 1 skipped, 2 warnings de deprecación, 0 fallos (188 s).
- T1–T6 completadas; lista para revisión de código.
