# Implementación — edicion_fragmentos

## Resumen

- Contrato: nuevos modelos `ChunkUpdateRequest` y `ChunkUpdateResponse` en
  `contracts/lazaro_contracts/chunks.py`, exportados en `__init__.py`, con
  ejemplos y sección `PATCH /chunks/{id}` en `CONTRATOS.md`.
- Servicio RAG: `update_chunk_text` en `domain.py` comprueba existencia,
  recalcula el embedding y persiste; `NotFound` se mapea a `404 not_found`.
- Repositorios: `exists` y `update_text` en la interfaz, la versión fake y
  pgvector. En Postgres el texto y el vector se escriben en una sola sentencia
  `UPDATE` parametrizada; el resto de columnas no se tocan.
- El texto no vacío no se normaliza; vacío o solo espacios se rechaza en el
  modelo con `422 validation_error`.

## Trazabilidad

- R1 → `contracts/tests/test_contratos_doc.py::test_chunk_update_errors_table_has_all_documented_codes`
- R1 → `contracts/tests/test_examples.py::test_every_example_validates_against_its_model[chunk_update_request.json]`
- R1 → `contracts/tests/test_examples.py::test_every_example_validates_against_its_model[chunk_update_response.json]`
- R2 → `services/rag/tests/test_edit_chunk.py::test_patch_chunk_rejects_blank_text`
- R2 → `contracts/tests/test_models.py::test_chunk_update_request_rejects_blank_text`
- R3 → `services/rag/tests/test_edit_chunk.py::test_patch_chunk_preserves_text_exactly`
- R3 → `contracts/tests/test_models.py::test_chunk_update_request_preserves_text_exactly`
- R4 → `services/rag/tests/test_edit_chunk.py::test_patch_chunk_without_token_returns_401`
- R4 → `services/rag/tests/test_edit_chunk.py::test_patch_chunk_with_wrong_token_returns_401`
- R5 → `services/rag/tests/test_edit_chunk.py::test_patch_chunk_recalculates_embedding`
- R6 → `services/rag/tests/test_edit_chunk.py::test_patch_chunk_updates_text_and_returns_200`
- R6 → `services/rag/tests/test_adapters.py::test_pgvector_update_text_is_parameterized_and_keeps_metadata`
- R7 → `services/rag/tests/test_edit_chunk.py::test_patch_chunk_preserves_metadata`
- R8 → `services/rag/tests/test_edit_chunk.py::test_patch_chunk_updates_text_and_returns_200`
- R8 → `contracts/tests/test_models.py::test_chunk_update_response_has_fragment_metadata_fields`
- R9 → `services/rag/tests/test_edit_chunk.py::test_patch_chunk_not_found`
- R9 → `services/rag/tests/test_adapters.py::test_pgvector_update_text_missing_chunk_raises_not_found_and_rolls_back`
- R10 → `services/rag/tests/test_edit_chunk.py::test_patch_chunk_embeddings_failure_keeps_previous_values`
- R10 → `services/rag/tests/test_adapters.py::test_pgvector_update_text_missing_chunk_raises_not_found_and_rolls_back`

## Pendiente para Claude

Ejecutar `./init.sh` y adjuntar el resultado al informe.

## Fallo de init.sh (corrección 1)

`init.sh`: 1 failed, 1231 passed.

- `contracts/tests/test_contratos_doc.py::test_chunk_update_request_table_lists_text` (línea 907):
  `assert "`text`" in _first_column_cells(...)` falla porque `_first_column_cells` devuelve
  `{'text'}` (sin backticks). El test está mal escrito, no el documento: la segunda aserción
  debe comparar contra `"text"` (igual que los demás tests que usan `_first_column_cells`).
  Corrige solo el test; no cambies CONTRATOS.md.

## Corrección 2 (informe de init.sh)

- Corregido `contracts/tests/test_contratos_doc.py::test_chunk_update_request_table_lists_text`:
  la segunda aserción compara contra `"text"`, que es lo que devuelve
  `_first_column_cells` (sin backticks). `CONTRATOS.md` no cambia.
- Ningún otro archivo tocado.
