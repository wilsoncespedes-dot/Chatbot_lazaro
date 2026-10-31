# Review — feature 5 rag_ingesta_busqueda

**Veredicto:** APPROVED

`./init.sh` termina verde: 498 tests pasan. `feature_list.json` deja la feature en `in_progress` con `auto_approved: true`. El implementer no la marcó `done`.

## Trazabilidad requirements ↔ tests
La tabla de `progress/impl_rag_ingesta_busqueda.md` asigna al menos un test a cada R. Los nombres coinciden con los de `tasks.md` T10-T16.
- R1: [x] `test_upload_pdf_returns_201_with_chunks`
- R2: [x] `test_upload_docx_returns_201_with_chunks`
- R3: [x] `test_chunks_respect_size_and_overlap`
- R4: [x] `test_upload_stores_chunk_fields_and_active_true`, `test_chunk_order_starts_at_one`
- R5: [x] `test_upload_uses_name_in_search_manual`
- R6: [x] `test_upload_text_file_returns_415`, `test_upload_fake_pdf_extension_returns_415`
- R7: [x] `test_upload_empty_file_returns_422_empty_document`
- R8: [x] `test_upload_pdf_without_text_returns_422`
- R9: [x] `test_upload_missing_name_returns_422_validation_error`, `test_upload_name_too_long_returns_422`
- R10: [x] `test_upload_embeddings_failure_returns_500_and_stores_nothing`
- R11: [x] `test_search_orders_by_score_desc`, `test_search_result_shape`
- R12: [x] `test_search_returns_at_most_top_k`
- R13: [x] `test_search_filters_below_threshold`
- R14: [x] `test_search_returns_empty_when_no_chunk_passes_threshold`
- R15: [x] `test_search_does_not_return_closest_below_threshold`
- R16: [x] `test_search_excludes_inactive_chunks`
- R17: [x] `test_search_ignores_category`
- R18: [x] `test_manuals_without_token_returns_401`, `test_search_without_token_returns_401`, `test_search_with_wrong_token_returns_401_and_no_embedding_call`
- R19: [x] `test_script_posts_multipart_with_token`, `test_script_prints_manual_id_and_chunks`
- R20: [x] `test_script_exits_nonzero_on_error_response`, `test_script_exits_nonzero_when_rag_unreachable`
- R21: [x] `test_script_fails_when_file_missing`, `test_script_fails_when_env_missing`
- R22: [x] `test_requirements_txt_matches_design`. Los Fake* se inyectan en `create_app` desde `conftest.py`.
- R23: [x] `test_fake_embeddings_is_deterministic`
- R24: [x] `test_fake_embeddings_same_text_cosine_one`
- R25: [x] `test_pgvector_repository_uses_parameters_only`

## Tasks completas
- T1-T17: [x] Todas están `[x]` en `specs/rag_ingesta_busqueda/tasks.md`.

## Revisión de código
- `services/rag/rag/adapters/repository.py`: todo el SQL es parametrizado con `%s`. Solo el `vector({dim})` del DDL usa un entero interpretado con `int()`, que no es texto de usuario. El umbral y `active` van en la consulta. Hace rollback si falla.
- `services/rag/requirements.txt`: tiene versiones acotadas. Las dependencias coinciden con la tabla de `design.md`: pypdf BSD-3, python-docx MIT y pg8000. No hay GPL ni AGPL.
- `.env.example` incluye las variables nuevas: `EMBEDDINGS_BASE_URL`, `EMBEDDINGS_API_KEY`, `EMBEDDINGS_DIM`, `CHUNK_SIZE` y `CHUNK_OVERLAP`.
- No hay `print`, `eval`, `exec` ni TODO en `services/rag/rag`.
- No hay `.env` trackeado: `init.sh` lo confirma.
- Los tests usan adaptadores falsos, `httpx.MockTransport` y una conexión DB-API falsa. No usan red ni base de datos real.

## Checkpoints
- C1: [x]
- C2: [x] Solo una feature en `in_progress`. Los tests pasan.
- C3: [x]
- C4: [x] Las pruebas de seguridad de 401 existen y pasan.
- C5: [ ] No aplica todavía: la feature sigue en `in_progress`. El cierre de sesión y `history.md` los hace el leader.
- C6: [x]

## Cambios requeridos
Ninguno.
