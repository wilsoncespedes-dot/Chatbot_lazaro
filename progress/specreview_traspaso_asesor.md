# Spec review — traspaso_asesor (feature #7), segunda vuelta

**Veredicto:** SPEC_APPROVED

## Cobertura del acceptance
- [x] Los 8 criterios de `acceptance` estan cubiertos (tabla de trazabilidad).

## EARS estricto
- [x] R4 y R41 separados: un solo DEBE / NO DEBE cada uno.
- [x] R39 y R40 retirados (numeros no reutilizados), sin requisitos de contrato en esta feature.
- [x] Resto de R con uno de los 5 patrones y sin verbos blandos.

## Verificable
- [x] Cada R tiene un test nombrado en tasks.md (T7, T10, T16-T24, T25, T28, T31); R22 y R26 con fake de reloj y conexion falsa.

## Sin invenciones
- [x] R10 y el paso `timed_out` -> `assigned` (R11) estan justificados y marcados como "CONFIRMABLE" en design.md, con alternativa.
- [x] La ruta `assign` pasa a una feature previa de contrato; esta feature solo la consume.

## Diseno
- [x] No toca `contracts/` (principio 2). Precondicion explicita de feature previa.
- [x] 3 capas, `domain.py` sin IO, adaptadores con Fake, SQL parametrizado.
- [x] Dependencias nuevas (httpx, pg8000) con version y licencia BSD-3.
- [x] Alternativas descartadas (4) y seccion "Supuestos a confirmar".

## Tasks
- [x] Todas en `[ ]`, en orden, con `R<n>`; cubren R1-R38 y R41 (T33 cierra el mapa).

## Nada peligroso
- [x] No borra datos, no usa red real en tests, no toca fuera del repo.

## Nota para el leader (bloqueante para pasar a in_progress)
`CaseAssignRequest` y `CaseAssignResponse` NO existen aun en `contracts/lazaro_contracts/cases.py`, y `feature_list.json` no tiene todavia la feature previa de contrato. El leader debe crearla y completarla (`done`) antes de poner la feature #7 en `in_progress`; si no, la #7 queda `blocked`.
