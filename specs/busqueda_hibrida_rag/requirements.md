# Requirements — búsqueda híbrida RAG (#31)

## Contexto

`POST /search` conserva su contrato. La búsqueda actual usa similitud coseno
de pgvector y `RAG_SIMILARITY_THRESHOLD` (default `0.75`). El modo híbrido queda
desactivado por defecto hasta comparar ambos modos con la evaluación existente.

## Requisitos

### R1 — Candidatos híbridos

CUANDO `RAG_HYBRID_ENABLED` está activo y RAG recibe `POST /search`, el sistema
DEBE obtener candidatos activos mediante búsqueda semántica pgvector y búsqueda
textual PostgreSQL en español, y unirlos por `chunk_id` sin duplicados.

### R2 — Fusión de rangos

CUANDO RAG ordena candidatos híbridos, el sistema DEBE usar Reciprocal Rank
Fusion para combinar sus rangos semántico y textual, sin usar el score RRF como
score de respuesta.

### R3 — Umbral semántico

CUANDO RAG filtra candidatos híbridos, el sistema DEBE aceptar únicamente los
cuyo score de similitud semántica original sea mayor o igual a
`RAG_SIMILARITY_THRESHOLD` y devolver ese score original.

### R4 — Límite y filtros

CUANDO RAG devuelve una búsqueda híbrida, el sistema DEBE respetar `top_k`, el
filtro de fragmentos activos y el comportamiento existente de `category`.

### R5 — Compatibilidad HTTP

CUANDO RAG recibe `POST /search` en modo semántico o híbrido, el sistema DEBE
conservar autenticación, validación, códigos HTTP y forma de respuesta
documentados para la ruta.

### R6 — Comparación previa a habilitar por defecto

CUANDO se evalúan los modos semántico e híbrido, el sistema DEBE ejecutar ambos
con el mismo corpus, archivo de preguntas, `top_k` y umbral, y generar métricas
comparables de aciertos de recuperación, rechazos correctos y resultados en
preguntas `no_responde`.

## Criterio para activar el modo

El modo permanece apagado por defecto. Solo se cambia el default después de
guardar una comparación reproducible que mejore o conserve aciertos de
recuperación y rechazos correctos, sin aumentar resultados en preguntas
`no_responde`.
