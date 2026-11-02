# Spec review — feature 19 edicion_fragmentos

**Veredicto:** APPROVED

## Cobertura de acceptance
- A1 (editar texto sin cambiar identidad/manual/orden/activo) → R3, R6, R7.
- A2 (recalcular embedding antes de persistir) → R5, R6.
- A3 (X-Service-Token, 404, 422) → R4, R9, R2.
- A4 (CONTRATOS.md + lazaro_contracts con ejemplos) → R1 + T1.
- A5 (tests: éxito, inexistente, inválido, fallo embeddings sin cambio parcial, token) → R2, R4, R8, R9, R10 + T4.

## Diseño y tasks
- Respeta las 3 capas (dominio/repositorio/endpoint), reutiliza `EmbeddingsClient`, `ChunkRepository`, `Chunk` y el middleware; sin dependencias nuevas. `/chunks` no choca con rutas existentes.
- Alternativa descartada y «Supuestos a confirmar» presentes; los supuestos son defaults seguros.
- T1–T4 en `[ ]`, en orden y entre todas cubren R1–R10.
- Nada peligroso: no borra datos, no usa red nueva, no sale del repo.

## Observaciones no bloqueantes
- R9 mezcla `CUANDO … ENTONCES`; R10 lleva dos acciones bajo un solo `DEBE` («responder 500 y conservar»). No es ambiguo; el implementador puede probar ambas partes en el mismo test.
- R1 debería mencionar explícitamente los ejemplos JSON válidos de A4; T1 ya los incluye.
