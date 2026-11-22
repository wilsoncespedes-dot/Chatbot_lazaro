# Implementación — #76 `fuente_clientes_y_futuro_lazaro`

## Resumen

- Nuevo `services/orchestrator/orchestrator/client_source.py` con el Protocol
  `FuenteDeClientes` y `FuenteClientesLocal` sobre el repositorio actual.
- `domain.py`: `Adapters.client_source` (default `None`) y helper
  `client_source_of`; `create_client`, `list_clients_admin`,
  `renew_credential`, `revoke_credential` y `search_client_by_public_id` pasan
  por el puerto. No cambian esquema, rutas ni contratos HTTP.
- `admin.py`: tarjeta `#futuro-lazaro` en `/admin/clientes` con el texto exacto,
  sin formularios/botones/enlaces, también en respuestas de error.
- `docs/architecture.md`: sección «Posibilidad a futuro, no implementada» sobre
  `LazaroClientSource` (buscar, listar, sincronizar, duplicados, borrados).
- No se añadió adaptador, configuración ni variable de entorno de Lázaro.

## Trazabilidad

- R1 → `services/orchestrator/tests/test_client_source.py::test_default_source_is_local_and_injectable`
- R2 → `services/orchestrator/tests/test_client_source.py::test_local_create_returns_profile_with_public_id`
- R3 → `services/orchestrator/tests/test_client_source.py::test_local_find_by_id_and_missing`
- R4 → `services/orchestrator/tests/test_client_source.py::test_local_find_by_id_and_missing`
- R5 → `services/orchestrator/tests/test_client_source.py::test_local_list_matches_repository`
- R6 → `services/orchestrator/tests/test_client_source.py::test_local_create_returns_profile_with_public_id`
- R7 → `services/orchestrator/tests/test_client_source.py::test_local_create_duplicate_public_id_raises`
- R8 → `services/orchestrator/tests/test_client_source.py::test_local_create_duplicate_username_raises`
- R9 → `services/orchestrator/tests/test_client_source.py::test_local_update_renews_revokes_and_rejects`
- R10 → `services/orchestrator/tests/test_client_source.py::test_local_update_renews_revokes_and_rejects`
- R11 → `services/orchestrator/tests/test_client_source.py::test_local_update_renews_revokes_and_rejects`
- R12 → `services/orchestrator/tests/test_client_source.py::test_default_source_is_local_and_injectable`
- R13 → `services/orchestrator/tests/test_client_source.py::test_admin_create_client_goes_through_port`
- R14 → `services/orchestrator/tests/test_client_source.py::test_list_renew_revoke_and_search_use_port`
- R15 → `services/orchestrator/tests/test_client_source.py::test_list_renew_revoke_and_search_use_port`
- R16 → `services/orchestrator/tests/test_client_source.py::test_list_renew_revoke_and_search_use_port`
- R17 → `services/orchestrator/tests/test_client_source.py::test_post_clients_api_goes_through_port`
- R18 → `services/orchestrator/tests/test_client_source.py::test_clients_page_shows_future_card_exact_text`
- R19 → `services/orchestrator/tests/test_client_source.py::test_clients_page_shows_future_card_exact_text`
- R20 → `services/orchestrator/tests/test_client_source.py::test_clients_page_shows_future_card_exact_text`
- R21 → `services/orchestrator/tests/test_client_source.py::test_no_lazaro_source_in_code_or_config`
- R22 → `services/orchestrator/tests/test_client_source.py::test_clients_page_lazaro_only_in_future_card`
- R23 → `services/orchestrator/tests/test_client_source.py::test_docs_describe_lazaro_adapter_as_future_only`
- R24 → `services/orchestrator/tests/test_client_source.py::test_docs_describe_lazaro_adapter_as_future_only`
- R25 → `services/orchestrator/tests/test_client_source.py::test_docs_describe_lazaro_adapter_as_future_only`
- R26 → suite existente; pendiente de `./init.sh` (lo ejecuta Claude al cerrar la sesión).

## Notas

- `obtener_credencial` es la quinta lectura justificada en `design.md` §3.
- T20 queda sin marcar: no ejecuté `./init.sh` por los límites de herramientas.

## Verificación (init.sh)
init.sh: 4724 passed, 1 skipped, exit 0. Trazabilidad R<n> -> test en services/orchestrator/tests/test_client_source.py.
