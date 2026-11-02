# Implementación — búsqueda híbrida RAG (#31)

Estado: T1–T4 completas y con tests; T5 pendiente solo de la comparación real
contra dos despliegues y de que Claude ejecute `./init.sh`. El modo híbrido
queda **apagado por defecto** (`RAG_HYBRID_ENABLED=false`). No se modificó
`feature_list.json`, `progress/current.md` ni el harness.

## Resumen

- `services/rag/rag/config.py`: `rag_hybrid_enabled=False` y
  `rag_hybrid_candidate_limit=50`.
- `.env.example`: `RAG_HYBRID_ENABLED=false`, `RAG_HYBRID_CANDIDATE_LIMIT=50`.
- `services/rag/rag/domain.py`: `search_chunks` delega en `search_hybrid`
  cuando el flag está activo y mantiene intacto el camino semántico anterior.
  El umbral se vuelve a aplicar como defensa en profundidad.
- `services/rag/rag/adapters/repository.py`:
  - `RRF_K = 60` y `reciprocal_rank_fusion(...)`.
  - `FakeChunkRepository.search_hybrid(...)` con tokenización española
    aproximada, candidatos semánticos y textuales, unión por `chunk_id`,
    filtro activo, umbral semántico y `top_k`.
  - `PgVectorChunkRepository.search_hybrid(...)` con
    `websearch_to_tsquery('spanish', ...)`, `ts_rank_cd`, pgvector, RRF y SQL
    parametrizado. El score devuelto es siempre `1 - distancia coseno`.
  - Índice GIN `to_tsvector('spanish', text) WHERE active`.
- `eval/run_eval.py`: `--comparar-url` (alias `--url-b`) ejecuta dos endpoints
  RAG con las mismas preguntas, `top_k` y umbral (`RAG_SIMILARITY_THRESHOLD`),
  y escribe `eval/comparacion_<fecha>.md`.
- `eval/scoring.py`: `Summary.resultados_no_responde` y
  `render_comparison(...)` con aciertos de recuperación, rechazos correctos,
  resultados en `no_responde` y respuestas inventadas.
- Tests nuevos:
  `services/rag/tests/test_search_hybrid.py` y
  `eval/tests/test_run_eval_compare.py`.

Sin dependencias nuevas y sin copia de código externo.

## Trazabilidad

- R1 → `services/rag/tests/test_search_hybrid.py::test_hybrid_unions_semantic_and_lexical_candidates`
- R1 → `services/rag/tests/test_search_hybrid.py::test_hybrid_deduplicates_the_same_chunk_from_both_sources`
- R1 → `services/rag/tests/test_search_hybrid.py::test_hybrid_enabled_delegates_with_the_configured_parameters`
- R2 → `services/rag/tests/test_search_hybrid.py::test_hybrid_orders_by_rrf_and_returns_the_semantic_score`
- R2 → `services/rag/tests/test_search_hybrid.py::test_rrf_k_is_60_and_combines_one_based_ranks`
- R3 → `services/rag/tests/test_search_hybrid.py::test_hybrid_threshold_rejects_low_semantic_score_even_with_lexical_match`
- R3 → `services/rag/tests/test_search_hybrid.py::test_hybrid_threshold_keeps_only_semantic_candidates`
- R4 → `services/rag/tests/test_search_hybrid.py::test_hybrid_respects_top_k_and_active_filter`
- R4 → `services/rag/tests/test_search_hybrid.py::test_hybrid_returns_empty_when_both_sources_have_no_candidates`
- R1 → `services/rag/tests/test_search_hybrid.py::test_hybrid_keeps_semantic_candidates_when_only_the_lexical_side_is_empty`
- R3 → `services/rag/tests/test_search_hybrid.py::test_hybrid_keeps_semantic_candidates_when_only_the_lexical_side_is_empty`
- R4 → `services/rag/tests/test_search_hybrid.py::test_hybrid_ignores_category_like_the_legacy_search`
- R4 → `services/rag/tests/test_search_hybrid.py::test_hybrid_enabled_delegates_with_the_configured_parameters`
- R5 → `services/rag/tests/test_search_hybrid.py::test_default_flag_is_off_and_candidate_limit_is_50`
- R5 → `services/rag/tests/test_search_hybrid.py::test_hybrid_mode_keeps_http_contract`
- R5 → `services/rag/tests/test_search_hybrid.py::test_disabled_flag_uses_the_existing_semantic_search`
- R1–R4 (SQL real) → `services/rag/tests/test_search_hybrid.py::test_pgvector_hybrid_uses_spanish_full_text_and_parameterized_sql`
- R1 (índice) → `services/rag/tests/test_search_hybrid.py::test_pgvector_schema_adds_the_active_spanish_gin_index`
- R6 → `eval/tests/test_run_eval_compare.py::test_r6_comparison_uses_same_questions_and_parameters`
- R6 → `eval/tests/test_run_eval_compare.py::test_r6_report_contains_comparable_metrics`
- R6 → `eval/tests/test_run_eval_compare.py::test_r6_report_records_the_shared_semantic_threshold`
- R6 → `eval/tests/test_run_eval_compare.py::test_r6_comparison_is_only_for_rag`
- R6 → `eval/tests/test_run_eval_compare.py::test_r6_comparison_returns_error_if_an_endpoint_fails`
- R6 → `eval/tests/test_run_eval_compare.py::test_r6_token_never_appears_in_the_comparison_report`

## Evaluación comparativa y decisión del default

Comando reproducible (requiere el mismo manual cargado en ambos despliegues):

```bash
SERVICE_TOKEN=... RAG_SIMILARITY_THRESHOLD=0.75 \
python eval/run_eval.py \
  --url http://rag-semantico:8000 \
  --comparar-url http://rag-hibrido:8000 \
  --top-k 5
```

El informe se guarda en `eval/comparacion_<fecha>.md` con las métricas de R6.

En esta sesión el implementer no ejecuta shell ni usa red, así que no se pudo
lanzar la comparación contra dos despliegues reales; el comparador sí está
probado de extremo a extremo con `httpx.MockTransport`. **Decisión:** el flag
permanece `false` hasta que el dueño ejecute el comando anterior y guarde una
comparación que mejore o conserve recuperación y rechazos sin aumentar
resultados en `no_responde`.

T5 queda pendiente solo de la ejecución real de esa comparación y de
`./init.sh` por Claude.

## Correcciones tras ./init.sh

- `test_hybrid_returns_empty_when_only_the_lexical_side_is_empty` usaba
  `threshold=0.1`, pero `FakeEmbeddings` da una similitud semántica de 0.707
  para `alfa` frente a `beta gamma` (colisión de hash). La prueba se corrigió
  con evidencia: ahora se llama
  `test_hybrid_keeps_semantic_candidates_when_only_the_lexical_side_is_empty`,
  calcula el score real con `cosine_similarity` y comprueba que, sin
  coincidencia textual, el candidato semántico se devuelve si alcanza el
  umbral (R1, R3).
- `eval/tests/test_run_eval_compare.py::test_r6_report_contains_comparable_metrics`
  necesitaba que un endpoint devolviera un resultado para la pregunta
  `no_responde`. El fixture `comparison_handler` ahora lo hace en el endpoint
  izquierdo; las métricas del informe (recuperación 1/1 vs 0/1, rechazos 0/1
  vs 1/1 y resultados en `no_responde` 1 vs 0) coinciden con el escenario
  comparado, sin tocar la métrica.

Pendiente: Claude ejecuta `./init.sh` y añade aquí el resultado. T5 sigue
pendiente de la comparación real entre dos despliegues.

## Verificación local
./init.sh: 2063 passed, 1 skipped; entorno listo. Los dos fallos anteriores se corrigieron en el fixture de test y en el umbral derivado del FakeEmbeddings. T5 mantiene pendiente la comparación contra dos endpoints reales; no se activa el modo híbrido por defecto.

## Ajuste preventivo señalado por reviewer
Antes de cerrar, ordenar explícitamente las filas de los CTE semantic y lexical por rank antes de aplicar candidate_limit. El reviewer encontró que lexical LIMIT sin ORDER BY puede seleccionar candidatos arbitrarios y sesgar RRF. Aunque la feature se mantiene apagada, corregir ahora para que su habilitación posterior no dependa de ese arreglo.

Resuelto: ambos CTE calculan `ROW_NUMBER()` y después aplican `ORDER BY rank LIMIT %s`; la semántica ya no ordena por `score` (que no desempataba igual que el rango) y la textual deja de recortar sin orden. Queda cubierto por
`services/rag/tests/test_search_hybrid.py::test_pgvector_hybrid_uses_spanish_full_text_and_parameterized_sql`
(R1–R4), que exige dos apariciones de `ORDER BY rank LIMIT %s`. Sin cambios de
parámetros, contrato ni comportamiento con el flag apagado.

Ajuste ORDER BY rank verificado con ./init.sh: 2063 passed, 1 skipped.

## Cierre
- Claude code reviewer: APPROVED; los dos CTE ordenan por rank antes de candidate_limit.
- `./init.sh`: 2063 passed, 1 skipped.
- Feature #31 cerrada como done. T5 (evaluación comparativa real) queda como operación previa a cambiar `RAG_HYBRID_ENABLED` a true, no como requisito para mantener el modo semántico actual.
