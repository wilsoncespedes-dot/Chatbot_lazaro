# Review — feature 31 (busqueda_hibrida_rag)

**Veredicto:** APPROVED (con `RAG_HYBRID_ENABLED=false`; ver condición de activación)

`./init.sh`: 2063 passed, 1 skipped (ejecutado por el leader justo antes de esta revisión; no se repitió). No se ejecutó la evaluación externa porque requiere dos despliegues y credenciales.

## Trazabilidad requirements ↔ tests
Todos en `services/rag/tests/test_search_hybrid.py` salvo R6.
- R1: [x] `test_hybrid_unions_semantic_and_lexical_candidates`, `test_hybrid_deduplicates_the_same_chunk_from_both_sources`, `test_hybrid_keeps_semantic_candidates_when_only_the_lexical_side_is_empty`, `test_hybrid_enabled_delegates_with_the_configured_parameters`, `test_pgvector_hybrid_uses_spanish_full_text_and_parameterized_sql`, `test_pgvector_schema_adds_the_active_spanish_gin_index`
- R2: [x] `test_hybrid_orders_by_rrf_and_returns_the_semantic_score` (orden RRF ≠ orden semántico; score > 0.9, no RRF), `test_rrf_k_is_60_and_combines_one_based_ranks`
- R3: [x] `test_hybrid_threshold_rejects_low_semantic_score_even_with_lexical_match`, `test_hybrid_threshold_keeps_only_semantic_candidates`
- R4: [x] `test_hybrid_respects_top_k_and_active_filter`, `test_hybrid_returns_empty_when_both_sources_have_no_candidates`, `test_hybrid_ignores_category_like_the_legacy_search`
- R5: [x] `test_hybrid_mode_keeps_http_contract` (200/401/422 y forma `SearchResponse`), `test_disabled_flag_uses_the_existing_semantic_search`, `test_default_flag_is_off_and_candidate_limit_is_50`
- R6: [x] `eval/tests/test_run_eval_compare.py::test_r6_comparison_uses_same_questions_and_parameters`, `test_r6_report_contains_comparable_metrics`, `test_r6_report_records_the_shared_semantic_threshold`, `test_r6_comparison_is_only_for_rag`, `test_r6_comparison_returns_error_if_an_endpoint_fails`, `test_r6_token_never_appears_in_the_comparison_report`

## Tasks
- T1: [x] `config.py:33-34`, `.env.example` (`RAG_HYBRID_ENABLED=false`, `RAG_HYBRID_CANDIDATE_LIMIT=50`).
- T2: [x] `repository.py` `search_hybrid` fake y PostgreSQL.
- T3: [x] `domain.py:174-183`.
- T4: [x] `eval/run_eval.py` `--comparar-url`, `eval/scoring.py` `render_comparison`.
- T5: [ ] **Pendiente con justificación**: la comparación real necesita dos despliegues RAG con el mismo corpus y `SERVICE_TOKEN`, que no están disponibles en esta sesión. Está documentado en `progress/impl_busqueda_hibrida_rag.md` («Evaluación comparativa y decisión del default»), junto con el comando reproducible y la decisión del default (`false`). `./init.sh` ya se ejecutó en verde. Esto es compatible con el «Criterio para activar el modo» de `requirements.md` y con el criterio de acceptance 4: el comportamiento **no** se activa por defecto antes de la comparación.

## Revisión del código
- **SQL parametrizado:** [x] `repository.py:313-344`. `query_text`, el vector, los límites, el umbral y `top_k` van por `%s`. El test inyecta `'); DROP TABLE chunks;--` y comprueba que no aparece en el SQL.
- **Filtro activo:** [x] ambos CTE filtran `WHERE c.active`; el índice GIN parcial (`WHERE active`) coincide con la expresión `to_tsvector('spanish', text)` de la consulta.
- **Score semántico original:** [x] los dos CTE calculan `1 - (embedding <=> vector)`. El umbral se aplica a `f.score`, no a `rrf`, y el dominio lo vuelve a aplicar (`domain.py:183`). En el fake el score es `cosine_similarity` y el umbral se aplica a `semantic_scores`.
- **RRF:** [x] k=60, rangos 1-based y `FULL OUTER JOIN` por `chunk_id`, así que no hay duplicados. RRF solo se usa en el `ORDER BY` y el dominio no reordena por score.
- **Flag por defecto en false:** [x] el camino legado no cambia (`domain.py:184+`).
- **Arquitectura/convenciones:** [x] sin dependencias nuevas, sin rutas nuevas y sin cambios en `contracts/`. La lógica de selección está en el dominio y el SQL en el adaptador.

## Checkpoints
- C1: [x] arnés completo; `./init.sh` exit 0.
- C2: [x] solo #31 está `in_progress`; `progress/current.md` describe la sesión activa.
- C3: [x] estructura respetada; ningún import entre servicios; sin dependencias nuevas; variables nuevas en `.env.example`; sin `print` de debug (los `print` de `run_eval.py` son la salida de la CLI), sin `eval`/`exec` y sin SQL concatenado con texto del usuario.
- C4: [x] tests con fakes (`FakeChunkRepository`, conexión stub, `httpx.MockTransport`); ninguno usa red ni BD real.
- C5: [x] sin archivos sospechosos sin trackear. La entrada de `history.md` de #31 la añade el leader al cerrar.
- C6: [x] spec completo y aprobado, EARS, cada R<n> con test. T5 en `[ ]` con justificación (ver arriba).

## Condición antes de activar `RAG_HYBRID_ENABLED=true` (no bloqueante con el flag apagado)
1. ~~Ordenamiento de los CTE~~ **RESUELTO (2026-11-02, re-verificación posterior al APPROVED):** `repository.py:321` (`semantic`) y `repository.py:330` (`lexical`) terminan ahora en `ORDER BY rank LIMIT %s`, así que cada lado conserva los `candidate_limit` rangos más altos. Los parámetros siguen alineados con los 9 `%s` (`repository.py:343-353`). `test_search_hybrid.py:279` comprueba `sql.count("ORDER BY rank LIMIT %s") == 2`. `tests/test_search_hybrid.py`: 16 passed (lo ejecutó el reviewer). `./init.sh` tras el ajuste: 2063 passed, 1 skipped (lo informa el leader).
2. **PENDIENTE: T5, evaluación real.** Todavía no se ejecutó porque faltan dos despliegues RAG (legado e híbrido) con el mismo corpus y `SERVICE_TOKEN`. Hay que ejecutar el comando de `progress/impl_busqueda_hibrida_rag.md` y guardar `eval/comparacion_<fecha>.md`. Solo se cambia el default si recuperación y rechazos mejoran o se mantienen sin aumentar los resultados en `no_responde`. Hasta entonces `RAG_HYBRID_ENABLED` sigue en `false`.

## Cambios requeridos
Ninguno para cerrar la feature con el flag desactivado.
