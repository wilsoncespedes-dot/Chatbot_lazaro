# Review — feature 19 (edicion_fragmentos)

**Veredicto:** APPROVED

Alcance revisado: solo los cambios de la #19 en `contracts/` (`chunks.py`,
exports, ejemplos `chunk_update_*.json`, sección `PATCH /chunks/{id}` de
`CONTRATOS.md` y sus tests) y `services/rag/` (`domain.py`, `main.py`,
`adapters/repository.py`, `tests/test_edit_chunk.py`, `tests/test_adapters.py`).
`./init.sh` en verde (1232 tests, según el leader); además relancé
`services/rag/tests/test_edit_chunk.py`, `test_adapters.py` y
`contracts -k chunk`: todos verdes.

## Trazabilidad requirements ↔ tests
- R1: [x] `contracts/tests/test_contratos_doc.py::test_chunk_update_route_is_exposed_by_rag`, `::test_chunk_update_errors_table_has_all_documented_codes` (401/404/422/500), `::test_chunk_update_request_table_lists_text`; `test_examples.py` (`chunk_update_request.json`, `chunk_update_response.json`); `test_packaging.py` (exports)
- R2: [x] `services/rag/tests/test_edit_chunk.py::test_patch_chunk_rejects_blank_text` (`""`, `"   "`, `"\n\t "`, sin llamar a embeddings); `contracts/tests/test_models.py::test_chunk_update_request_rejects_blank_text`
- R3: [x] `test_edit_chunk.py::test_patch_chunk_preserves_text_exactly`; `test_models.py::test_chunk_update_request_preserves_text_exactly`
- R4: [x] `test_edit_chunk.py::test_patch_chunk_without_token_returns_401`, `::test_patch_chunk_with_wrong_token_returns_401`
- R5: [x] `test_edit_chunk.py::test_patch_chunk_recalculates_embedding`
- R6: [x] `test_edit_chunk.py::test_patch_chunk_updates_text_and_returns_200`; `test_adapters.py::test_pgvector_update_text_is_parameterized_and_keeps_metadata`
- R7: [x] `test_edit_chunk.py::test_patch_chunk_preserves_metadata`; `test_adapters.py::test_pgvector_update_text_is_parameterized_and_keeps_metadata`
- R8: [x] `test_edit_chunk.py::test_patch_chunk_updates_text_and_returns_200`; `test_models.py::test_chunk_update_response_has_fragment_metadata_fields`
- R9: [x] `test_edit_chunk.py::test_patch_chunk_not_found`; `test_adapters.py::test_pgvector_update_text_missing_chunk_raises_not_found_and_rolls_back`
- R10: [x] `test_edit_chunk.py::test_patch_chunk_embeddings_failure_keeps_previous_values`

## Tasks completas
- T1: [x]
- T2: [x]
- T3: [x]
- T4: [x]

## Checkpoints (aplicables a la feature)
- C1: [x] `./init.sh` en verde.
- C2: [x] Una sola feature `in_progress`.
- C3: [x] Sin imports entre servicios; modelos en `lazaro_contracts`; ruta documentada en `CONTRATOS.md`; sin dependencias nuevas; SQL parametrizado (`repository.py` `update_text`/`exists`); sin `print`/TODO.
- C4: [x] Tests con `FakeEmbeddings`, `FakeChunkRepository` y conexión falsa (`UpdateConn`); prueba de no inyección SQL (`SECRET` no aparece en el SQL).
- C5: n/a hasta el cierre por el leader.
- C6: [x] Spec completo, tasks en `[x]`, cada R<n> con test.

## Observaciones no bloqueantes
1. `services/rag/rag/main.py` (`edit_chunk(id: str, ...)`): el `{id}` de la ruta no se valida como `Identifier` (1–64), aunque `CONTRATOS.md:281` lo describe así. Un id de más de 64 caracteres devuelve `404 not_found` en vez de `422`. No contradice ningún R<n>; conviene alinearlo en una feature futura.
2. `domain.update_chunk_text` hace `exists()` y `update_text()` en transacciones separadas; no es un riesgo porque `update_text` vuelve a comprobar `rowcount` y lanza `ChunkNotFound` con rollback.

## Cambios requeridos
Ninguno.
