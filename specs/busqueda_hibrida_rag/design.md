# Design — búsqueda híbrida RAG (#31)

## Alcance

Mantener `POST /search` y su modelo `SearchResult`. El modo existente sigue
siendo el predeterminado (`RAG_HYBRID_ENABLED=false`); la búsqueda híbrida se
activa por configuración después de la comparación de evaluación definida en
R6.

## Cambios previstos

- `services/rag/rag/config.py`: flag `rag_hybrid_enabled` y límite configurable
  de candidatos híbridos (default 50); agregar defaults a `.env.example`.
- `services/rag/rag/domain.py`: elegir búsqueda semántica existente o método
  híbrido del repositorio; en híbrido filtrar por score semántico original,
  ordenar por RRF y devolver como máximo `top_k`.
- `services/rag/rag/adapters/repository.py`: extender el protocolo y los
  repositorios fake/PostgreSQL con búsqueda híbrida. PostgreSQL usa
  `websearch_to_tsquery('spanish', ...)`, `ts_rank_cd` y una expresión GIN sobre
  fragmentos activos. SQL parametrizado. Unir candidatos por `chunk_id`; el
  score devuelto es `1 - cosine distance`, no RRF. Constante RRF `k=60`.
- `services/rag/tests/`: casos de fusión, duplicados, fuentes vacías,
  umbral semántico, filtro activo, `top_k`, score de salida y contrato.
- `eval/run_eval.py` y `eval/tests/`: permitir comparar dos endpoints con el
  mismo corpus/preguntas/parámetros y guardar un informe con las métricas de R6.
- `progress/impl_busqueda_hibrida_rag.md`: trazabilidad R1–R6 y resultado de
  evaluación usado para decidir el default.

No se agregan dependencias. La búsqueda vectorial y el evaluador actual se
reutilizan; no se copia código externo.

## Firmas previstas

- `ChunkRepository.search_hybrid(query_vector, query_text, top_k, threshold,
  candidate_limit) -> list[SearchResult]`.
- `search_chunks(...)` conserva su firma y delega según configuración.
- El comparador de evaluación reutiliza carga, puntuación e informe existentes;
  no agrega rutas ni cambia `/search`.

## Alternativa descartada

Cambiar `SearchResult.score` por score RRF: rompe el significado actual del
score y permitiría que un resultado léxicamente fuerte eluda el umbral de
similitud. RRF solo ordena; el umbral y el score siguen siendo semánticos.

## Supuestos resueltos

- El corpus de evaluación es el mismo para ambas ejecuciones; no se reingestan
  manuales ni se cambia el umbral entre modos.
- Si la evaluación no mejora/conserva las métricas requeridas, el flag queda
  apagado por defecto; no se fuerza un cambio de producto.
