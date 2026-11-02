# Tasks — búsqueda híbrida RAG (#31)

- [x] T1 — Añadir `RAG_HYBRID_ENABLED=false` y límite de candidatos en config y `.env.example`. Cubre: R5.
- [x] T2 — Implementar `search_hybrid` en repositorio fake y PostgreSQL: full-text español, candidatos pgvector, fusión RRF por id, filtro activo y score semántico original. Cubre: R1–R4.
- [x] T3 — Integrar selección por flag en `search_chunks` y probar modo legado/híbrido, umbral, duplicados, fuentes vacías, score, `top_k` y filtros. Cubre: R1–R5.
- [x] T4 — Extender evaluación para comparar dos endpoints con el mismo corpus, preguntas, `top_k` y umbral; probar igualdad de parámetros y métricas del informe. Cubre: R6.
- [x] T5 — El comparador y la verificación local están implementados; `./init.sh`: 2063 passed, 1 skipped. La comparación de dos despliegues queda pendiente para habilitar el flag; la decisión actual y comando reproducible están en `progress/impl_busqueda_hibrida_rag.md`. Cubre: R6.
