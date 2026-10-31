# Spec review — orquestador_basico (2ª vuelta)

**Veredicto:** SPEC_APPROVED

## Checklist
- [x] Cobertura: cada criterio de `acceptance` está cubierto por algún R<n> (tabla final de requirements.md).
- [x] EARS estricto: R17, R23, R24, R27, R28, R29, R33 y R41/R42 quedaron con un solo `DEBE`/`NO DEBE`; las particiones R36-R42 mantienen la numeración estable. Sin verbos blandos.
- [x] Verificable: cada R<n> tiene un test concreto en tasks.md.
- [x] Sin invenciones: R30 declara en requirements.md y en design.md (línea 76) que deriva de `docs/architecture.md` §4, no de `acceptance`.
- [x] Diseño: respeta 3 capas, contratos, dependencias con versión y licencia, alternativas descartadas, «Supuestos a confirmar».
- [x] Tasks: todas en `[ ]`, ordenadas, con R<n>; R1-R42 cubiertos (R36-R40 en T3/T4/T18/T21, R41 en T5/T24, R42 en T2/T27).
- [x] Nada peligroso: no borra datos, tests sin red ni BD real, nada fuera del repo.

## Notas menores (no bloqueantes)
- R25 y R26 combinan varias acciones tras un único `DEBE`; aceptable, cada una se verifica en el mismo test.
