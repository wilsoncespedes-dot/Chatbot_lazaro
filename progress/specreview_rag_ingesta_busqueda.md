# Spec review — feature 5 rag_ingesta_busqueda (segunda revisión)

**Veredicto:** SPEC_APPROVED

## Cobertura de acceptance
- [x] Ingesta PDF/DOCX con campos y `{manual_id, chunks}`: R1-R5
- [x] 415 / 422: R6, R7, R8 (R9 validación del contrato)
- [x] `/search` con top_k, umbral y orden: R11-R13
- [x] Lista vacía bajo el umbral, no los más parecidos: R14, R15
- [x] `active=false` nunca aparece: R16
- [x] Adaptadores con versión falsa y real: R22, R23, R24
- [x] Script `cargar_manual.py`: R19-R21
- [x] Supuestos de umbral y modelo: design.md, «Supuestos a confirmar»
- [x] Tests con PDF/DOCX generados, sin red ni DB: cubierto por proceso en T8/T9 y design.md (anotado en Supuestos)

## EARS estricto
- [x] R14 y R15 separados, un modal cada uno.
- [x] R23 (determinismo) y R24 (coseno 1.0) separados.
- [x] R25 reescrito con un solo `NO DEBE`.
- [x] Meta-requirement eliminado; validador de `Settings` eliminado y anotado en Supuestos.
- [x] Resto de R con patrón EARS válido, sin verbos blandos.

## Verificable
- [x] Cada R tiene un test nombrado en T10-T16 (R16: `test_search_excludes_inactive_chunks`; R25: `test_pgvector_repository_uses_parameters_only`; R18: T13).

## Sin invenciones
- [x] Ningún R añade comportamiento fuera de acceptance o del contrato. R9, R17, R18 se deducen del contrato.

## Diseño
- [x] Respeta 3 capas y `contracts/`; sin GPL/AGPL (`psycopg` LGPL descartado explícitamente).
- [x] Dependencias nuevas con versión y licencia.
- [x] Alternativas descartadas y sección «Supuestos a confirmar» presentes.
- [x] SQL parametrizado, umbral y `active` en la consulta.

## Tasks
- [x] Todas en `[ ]`, en orden, con sus `R<n>`.
- [x] Entre todas cubren R1-R25.
- [x] Referencias renumeradas correctamente.

## Nada peligroso
- [x] Sin borrados de datos, sin red real en tests, sin archivos fuera del repo.

## Observación menor (no bloqueante)
- design.md, lista de tests nuevos, no menciona `test_security.py` (sí está en T13). El implementador debe seguir tasks.md.
