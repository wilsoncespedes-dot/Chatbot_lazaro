# impl_rag_ingesta_busqueda

Estado: implementado, `./init.sh` verde (498 tests). T1..T17 marcadas `[x]`. Pendiente de reviewer.

Dependencias añadidas a `services/rag/requirements.txt` (las del design) e instaladas en `.venv`.
Variables nuevas en `.env.example`: EMBEDDINGS_BASE_URL, EMBEDDINGS_API_KEY, EMBEDDINGS_DIM, CHUNK_SIZE, CHUNK_OVERLAP.

Notas: los tests importan los fakes como `rag_tests_fakes` (cargado en `conftest.py`) porque
`fakes.py` existe también en el orquestador y chocaría en `sys.modules`. `PgVectorChunkRepository`
ejecuta además `CREATE EXTENSION IF NOT EXISTS vector` en el primer uso (necesario para `vector(N)`).

## Trazabilidad R -> test (en `services/rag/tests/`)

| R | Test |
|---|---|
| R1 | test_ingest::test_upload_pdf_returns_201_with_chunks |
| R2 | test_ingest::test_upload_docx_returns_201_with_chunks |
| R3 | test_chunking::test_chunks_respect_size_and_overlap, test_short_text_gives_single_chunk |
| R4 | test_ingest::test_upload_stores_chunk_fields_and_active_true; test_chunking::test_chunk_order_starts_at_one |
| R5 | test_ingest::test_upload_uses_name_in_search_manual |
| R6 | test_ingest::test_upload_text_file_returns_415, test_upload_fake_pdf_extension_returns_415 |
| R7 | test_ingest::test_upload_empty_file_returns_422_empty_document |
| R8 | test_ingest::test_upload_pdf_without_text_returns_422 |
| R9 | test_ingest::test_upload_missing_name_returns_422_validation_error, test_upload_name_too_long_returns_422 |
| R10 | test_ingest::test_upload_embeddings_failure_returns_500_and_stores_nothing; test_adapters::test_http_embeddings_error_raises_embeddings_unavailable, test_pgvector_add_manual_rolls_back_on_error |
| R11 | test_search::test_search_orders_by_score_desc, test_search_result_shape |
| R12 | test_search::test_search_returns_at_most_top_k |
| R13 | test_search::test_search_filters_below_threshold; test_adapters::test_pgvector_search_sql_filters_active_and_threshold |
| R14 | test_search::test_search_returns_empty_when_no_chunk_passes_threshold |
| R15 | test_search::test_search_does_not_return_closest_below_threshold |
| R16 | test_search::test_search_excludes_inactive_chunks; test_adapters::test_pgvector_search_sql_filters_active_and_threshold |
| R17 | test_search::test_search_ignores_category |
| R18 | test_security::test_manuals_without_token_returns_401, test_search_without_token_returns_401, test_search_with_wrong_token_returns_401_and_no_embedding_call |
| R19 | test_cargar_manual::test_script_posts_multipart_with_token, test_script_prints_manual_id_and_chunks |
| R20 | test_cargar_manual::test_script_exits_nonzero_on_error_response, test_script_exits_nonzero_when_rag_unreachable |
| R21 | test_cargar_manual::test_script_fails_when_file_missing, test_script_fails_when_env_missing |
| R22 | test_adapters::test_http_embeddings_ok_parses_openai_format; conftest (Fake* inyectados en create_app); test_rag_app::test_requirements_txt_matches_design |
| R23 | test_adapters::test_fake_embeddings_is_deterministic |
| R24 | test_adapters::test_fake_embeddings_same_text_cosine_one |
| R25 | test_adapters::test_pgvector_repository_uses_parameters_only |
