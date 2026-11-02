# Review — feature 22 (panel_fragmentos)

**Veredicto:** APPROVED

`./init.sh`: verde (1398 passed, 0 failed). Es la ejecución que pasó el leader
justo antes de esta revisión y coincide con el intento 2 de
`progress/impl_panel_fragmentos.md`. No la he repetido.

## Trazabilidad requirements ↔ tests
- R1: [x] `contracts/tests/test_panel_fragmentos.py::test_new_route_section_exists_and_names_rag`, `::test_new_route_documents_its_errors_only`, `::test_new_route_models_are_exported`, `::test_published_route_rows_are_unchanged`; ejemplos validados en `contracts/tests/test_examples.py` (4 JSON nuevos)
- R2: [x] `services/rag/tests/test_list_chunks.py::test_list_manuals_returns_newest_first_with_chunk_counts`, `::test_pgvector_list_manuals_counts_chunks_and_orders_newest_first`
- R3: [x] `::test_list_chunks_returns_all_active_and_inactive_in_order`, `::test_pgvector_list_chunks_is_parameterized_and_ordered`
- R4: [x] `::test_list_chunks_unknown_manual_returns_404`, `::test_pgvector_list_chunks_unknown_manual_returns_none`
- R5: [x] `::test_patch_active_false_and_true_keeps_text_embedding_manual_and_order`, `::test_pgvector_update_active_is_parameterized_and_only_updates_active`
- R6: [x] `::test_patch_active_unknown_chunk_returns_404_without_changes`, `::test_pgvector_update_active_missing_chunk_rolls_back`
- R7: [x] `::test_patch_active_rejects_invalid_bodies_without_changes` ({}, "true", "false", 1, 0, extra); `contracts/tests/test_panel_fragmentos.py::test_chunk_active_request_rejects_non_booleans`
- R8: [x] `::test_new_routes_require_service_token` (sin token y token incorrecto, en las 3 rutas)
- R9: [x] `services/orchestrator/tests/test_admin_fragmentos.py::test_manuals_page_lists_manuals_and_upload_form`
- R10: [x] `::test_upload_manual_redirects_to_created_manual`, `::test_http_rag_upload_manual_sends_multipart_and_token`
- R11: [x] `::test_upload_manual_rejects_oversize_missing_and_invalid_without_calling_rag`
- R12: [x] `::test_manual_chunks_page_lists_order_text_state_and_forms`
- R13: [x] `::test_edit_chunk_redirects_to_its_manual`, `::test_http_rag_update_chunk_sends_json_and_escapes_id`
- R14: [x] `::test_edit_chunk_rejects_blank_text_without_calling_rag` (ausente, espacios, blancos)
- R15: [x] `::test_toggle_chunk_active_redirects_to_manual[true|false]`, `::test_http_rag_set_chunk_active_sends_boolean`
- R16: [x] `::test_toggle_chunk_active_rejects_invalid_values_without_calling_rag` ("", "maybe", "1", "True", "false ")
- R17: [x] `::test_rag_rejections_render_fixed_pages_with_same_status`, `::test_http_rag_maps_404_415_and_422_to_rag_rejected`
- R18: [x] `::test_rag_unavailable_renders_502_without_details` (5 operaciones), `::test_http_rag_turns_other_failures_into_service_unavailable`
- R19: [x] `::test_new_admin_routes_redirect_without_session_before_calling_rag`
- R20: [x] `::test_new_admin_posts_require_csrf_before_calling_rag[None|token-equivocado]` (incluye multipart)
- R21: [x] `::test_service_token_never_reaches_the_browser` (OK, 413, 422, 404, 502; cuerpo + cabeceras + cookies)
- R22: [x] `::test_new_admin_html_has_security_headers_and_no_external_resources`

## Tasks completas
- T1–T10: [x] (todas en `[x]` en `specs/panel_fragmentos/tasks.md`)

## Arquitectura y convenciones
- Capas respetadas: SQL solo en `services/rag/rag/adapters/repository.py` (parametrizado con `%s`, commit/rollback); dominio sin IO (`rag/domain.py:180-217`); HTTP solo en `orchestrator/adapters/rag.py`.
- Nada compartido entre servicios fuera de `lazaro_contracts`. Contrato aditivo: `ChunkUpdateResponse` y las filas publicadas no cambian (lo cubre un test).
- Dependencia nueva `python-multipart>=0.0.9,<1` (Apache-2.0) en `services/orchestrator/requirements.txt:7` y en `design.md`.
- `ADMIN_MANUAL_MAX_BYTES` en `config.py:71` (1–104857600) y `.env.example:69`.
- Salida HTML escapada con `_esc`/`html.escape` (incluido el `manual_id` del título, `admin.py:277` → `render_page`). Ids en URL con `quote(..., safe="")`. Los logs solo registran el tipo de excepción o el código HTTP, nunca cuerpos ni el token.
- No hay `print()`, `eval`/`exec` ni TODOs en el código tocado.

## Checkpoints
- C1: [x] arnés completo; `./init.sh` verde
- C2: [x] solo #22 está `in_progress`; `progress/current.md` describe la sesión
- C3: [x] (ver Arquitectura; `.env` no está trackeado; no hay código copiado)
- C4: [x] tests con `FakeRagClient`, `FakeChunkRepository`, `httpx.MockTransport` y conexiones falsas; ningún servicio real
- C5: [x] aplica al cierre que hace el leader: falta la entrada en `progress/history.md` y el paso a `done`
- C6: [x] spec completo, EARS, dependencias y supuestos en `design.md`, tasks `[x]`, cada R cubierto

## Observaciones no bloqueantes (follow-up opcional)
1. `contracts/CONTRATOS.md:243` y `:278`: el campo «Llama» de `POST /manuals` y `PATCH /chunks/{id}` sigue diciendo «panel de administración (futuro)». Ya lo llama el orquestador. El design prohibía tocar las secciones publicadas, así que conviene actualizarlo en una feature de documentación.
2. `services/orchestrator/orchestrator/admin_routes.py:282`: `await request.form()` recibe y guarda en un archivo temporal todo el multipart antes de comprobar el tamaño (`:307-308`). El 413 impide reenviar el archivo al RAG, pero no limita lo que recibe el orquestador. Recomendable fijar un límite de cuerpo en el proxy o en Uvicorn.
3. `admin_routes.py:291`: un input de archivo vacío (`filename=""`, 0 bytes) llega como `UploadFile` y se reenvía al RAG, que contesta 422 `empty_document`. El navegador lo evita con `required` y el resultado final sigue siendo 422, pero no se rechaza en local como el resto de casos de R11.
4. `admin_routes.py:298-316`: el nombre se valida antes que el tamaño, así que un archivo demasiado grande con nombre inválido devuelve 422 y no 413. Es compatible con R11.
