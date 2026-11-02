# Implementación — #22 panel_fragmentos

Estado: implementado según `specs/panel_fragmentos/{requirements,design,tasks}.md`.
Corregido el fallo del intento 1 de `./init.sh` (ver «Verificación»). La verificación final pasó: 1398 tests, 0 fallidos.

## Resumen

- Contrato aditivo: `ManualSummary`, `ManualListResponse`, `ChunkItem`,
  `ChunkListResponse` y `ChunkActiveRequest` en `lazaro_contracts`, exportados
  en `__all__`; cuatro ejemplos nuevos y tres secciones nuevas en
  `CONTRATOS.md`. No se editó ninguna sección publicada.
- RAG: `ManualNotFound` y las funciones `list_manuals`, `list_manual_chunks` y
  `set_chunk_active`; `list_manuals`, `list_chunks` y `update_active` en el
  Protocol, `FakeChunkRepository` y `PgVectorChunkRepository` (SQL parametrizado
  y transacción). `update_active` solo escribe `active`.
- Orquestador: métodos nuevos de `RagClient`/`HttpRagClient`/`FakeRagClient`
  con `X-Service-Token`, ids escapados, `RagRejected` para 404/415/422 y
  `ServiceUnavailable` para el resto. `ADMIN_MANUAL_MAX_BYTES` en `config.py` y
  `.env.example`; `python-multipart` en `requirements.txt`.
- Panel: plantillas de manuales, fragmentos y error fijo; enlace «Manuales» en
  la navegación común; rutas `GET/POST /admin/manuals`,
  `GET /admin/manuals/{manual_id}`, `POST /admin/chunks/{chunk_id}` y
  `POST /admin/chunks/{chunk_id}/active` con orden sesión → formulario → CSRF →
  validación local → RAG. El navegador nunca recibe `SERVICE_TOKEN`.
- Ajustes necesarios en tests existentes: la lista exacta de dependencias del
  orquestador incluye `python-multipart` y la lista exacta de rutas incluye las
  cuatro rutas nuevas del panel. No se elimina ni debilita ninguna aserción.

## Trazabilidad

- R1 → `contracts/tests/test_panel_fragmentos.py::test_new_route_section_exists_and_names_rag`
- R1 → `contracts/tests/test_panel_fragmentos.py::test_new_route_models_are_exported`
- R1 → `contracts/tests/test_panel_fragmentos.py::test_new_route_documents_its_errors_only`
- R1 → `contracts/tests/test_panel_fragmentos.py::test_new_route_success_and_fields_are_documented`
- R1 → `contracts/tests/test_examples.py::test_every_example_validates_against_its_model[manual_list_response.json]`
- R1 → `contracts/tests/test_examples.py::test_every_example_validates_against_its_model[chunk_list_response.json]`
- R1 → `contracts/tests/test_examples.py::test_every_example_validates_against_its_model[chunk_active_request.json]`
- R1 → `contracts/tests/test_examples.py::test_every_example_validates_against_its_model[chunk_active_response.json]`
- R2 → `services/rag/tests/test_list_chunks.py::test_list_manuals_returns_newest_first_with_chunk_counts`
- R2 → `services/rag/tests/test_list_chunks.py::test_pgvector_list_manuals_counts_chunks_and_orders_newest_first`
- R3 → `services/rag/tests/test_list_chunks.py::test_list_chunks_returns_all_active_and_inactive_in_order`
- R3 → `services/rag/tests/test_list_chunks.py::test_pgvector_list_chunks_is_parameterized_and_ordered`
- R4 → `services/rag/tests/test_list_chunks.py::test_list_chunks_unknown_manual_returns_404`
- R4 → `services/rag/tests/test_list_chunks.py::test_pgvector_list_chunks_unknown_manual_returns_none`
- R5 → `services/rag/tests/test_list_chunks.py::test_patch_active_false_and_true_keeps_text_embedding_manual_and_order`
- R5 → `services/rag/tests/test_list_chunks.py::test_pgvector_update_active_is_parameterized_and_only_updates_active`
- R6 → `services/rag/tests/test_list_chunks.py::test_patch_active_unknown_chunk_returns_404_without_changes`
- R6 → `services/rag/tests/test_list_chunks.py::test_pgvector_update_active_missing_chunk_rolls_back`
- R7 → `services/rag/tests/test_list_chunks.py::test_patch_active_rejects_invalid_bodies_without_changes`
- R7 → `contracts/tests/test_panel_fragmentos.py::test_chunk_active_request_rejects_non_booleans`
- R8 → `services/rag/tests/test_list_chunks.py::test_new_routes_require_service_token`
- R9 → `services/orchestrator/tests/test_admin_fragmentos.py::test_manuals_page_lists_manuals_and_upload_form`
- R10 → `services/orchestrator/tests/test_admin_fragmentos.py::test_upload_manual_redirects_to_created_manual`
- R10 → `services/orchestrator/tests/test_admin_fragmentos.py::test_http_rag_upload_manual_sends_multipart_and_token`
- R11 → `services/orchestrator/tests/test_admin_fragmentos.py::test_upload_manual_rejects_oversize_missing_and_invalid_without_calling_rag`
- R12 → `services/orchestrator/tests/test_admin_fragmentos.py::test_manual_chunks_page_lists_order_text_state_and_forms`
- R13 → `services/orchestrator/tests/test_admin_fragmentos.py::test_edit_chunk_redirects_to_its_manual`
- R13 → `services/orchestrator/tests/test_admin_fragmentos.py::test_http_rag_update_chunk_sends_json_and_escapes_id`
- R14 → `services/orchestrator/tests/test_admin_fragmentos.py::test_edit_chunk_rejects_blank_text_without_calling_rag`
- R15 → `services/orchestrator/tests/test_admin_fragmentos.py::test_toggle_chunk_active_redirects_to_manual`
- R15 → `services/orchestrator/tests/test_admin_fragmentos.py::test_http_rag_set_chunk_active_sends_boolean`
- R16 → `services/orchestrator/tests/test_admin_fragmentos.py::test_toggle_chunk_active_rejects_invalid_values_without_calling_rag`
- R17 → `services/orchestrator/tests/test_admin_fragmentos.py::test_rag_rejections_render_fixed_pages_with_same_status`
- R17 → `services/orchestrator/tests/test_admin_fragmentos.py::test_http_rag_maps_404_415_and_422_to_rag_rejected`
- R18 → `services/orchestrator/tests/test_admin_fragmentos.py::test_rag_unavailable_renders_502_without_details`
- R18 → `services/orchestrator/tests/test_admin_fragmentos.py::test_http_rag_turns_other_failures_into_service_unavailable`
- R19 → `services/orchestrator/tests/test_admin_fragmentos.py::test_new_admin_routes_redirect_without_session_before_calling_rag`
- R20 → `services/orchestrator/tests/test_admin_fragmentos.py::test_new_admin_posts_require_csrf_before_calling_rag`
- R21 → `services/orchestrator/tests/test_admin_fragmentos.py::test_service_token_never_reaches_the_browser`
- R22 → `services/orchestrator/tests/test_admin_fragmentos.py::test_new_admin_html_has_security_headers_and_no_external_resources`

## Pendiente para Claude

Ejecutar `./init.sh` y adjuntar el resultado al informe.

## Verificación `./init.sh` — intento 1 (FAIL)

- Resultado: 1397 passed, 1 failed.
- `services/rag/tests/test_list_chunks.py::test_list_chunks_returns_all_active_and_inactive_in_order`: `GET /manuals/{id}/chunks` pasa objetos internos `Chunk` a `ChunkListResponse`, que requiere `ChunkItem`; falla la validación Pydantic.
- Corrección: mapear los campos públicos de cada `Chunk` a `ChunkItem`, sin exponer el embedding.

## Corrección aplicada

- `services/rag/rag/domain.py::list_manual_chunks` devuelve ahora `list[ChunkItem]`
  construido a partir de los campos públicos de cada `Chunk` (`chunk_id`,
  `manual_id`, `manual`, `order`, `text`, `active`), con la misma comprobación
  `ManualNotFound` → 404. El `embedding` sigue siendo interno y no se serializa.
- `GET /manuals/{id}/chunks` en `main.py` no cambia: sigue envolviendo el
  resultado del dominio en `ChunkListResponse`, que ahora recibe `ChunkItem`
  válidos. R3, R4 y R8 no cambian de comportamiento.

## Verificación `./init.sh` — intento 2 (OK)

- Resultado: 1398 passed, 0 failed; entorno listo.
- Se completó T10.
