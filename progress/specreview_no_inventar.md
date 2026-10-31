# Spec review — no_inventar (feature #6), segunda vuelta

**Veredicto:** SPEC_APPROVED

## Correcciones pedidas en la primera vuelta
- [x] R7 partido: R7 (`DEBE ignorar` mayúsculas y espacios repetidos) y R8 (`NO DEBE ignorar` tildes ni puntuación).
- [x] R10 partido: R11 (`DEBE enviar` solo `answer`) y R12 (`DEBE registrar` `rag_answer` con motivo `chunks_found`).
- [x] R11 partido: R13 (`DEBE enviar NO_ANSWER_REPLY`) y R14 (`NO DEBE enviar` texto del LLM).
- [x] Renumeración a 23 requirements. `tasks.md`, la tabla de cobertura y las referencias R<n> de `design.md` son coherentes con ella.

## Cobertura del acceptance
- [x] Todos los criterios de `acceptance` están cubiertos en la tabla de `requirements.md`: R1-R3, R4-R8, R9-R10, R13-R15 (R16-R18 como flujo asociado), R19-R20, R23. Los tests listados en el acceptance corresponden a R11, R12, R2, R4, R5, R6 y R9.

## EARS estricto
- [x] Cada R<n> usa uno de los 5 patrones, con un solo `DEBE` o `NO DEBE`.
- [x] Sin verbos blandos.

## Verificable
- [x] Cada R<n> tiene al menos una task de test (R21 y R23 con tests estáticos).

## Sin invenciones
- [x] El traspaso con `INVALID_ANSWER_HANDOVER` (R16, R17) es una suposición configurable, listada en «Supuestos a confirmar» y deducible del contrato, que ya reserva el motivo `invalid_answer`. El humano debe confirmar el valor por defecto `true`.

## Diseño
- [x] Respeta las 3 capas (validación pura en `domain.py`) y no toca `contracts/`.
- [x] Sin dependencias nuevas, y lo declara.
- [x] Tiene cuatro alternativas descartadas.
- [x] Tiene la sección «Supuestos a confirmar».

## Tasks
- [x] T1-T24 están todas en `[ ]`, en orden y con sus R<n>.
- [x] Entre todas cubren R1-R23 (T24 cubre R1-R23).

## Nada peligroso
- [x] No borra datos, no usa red y no toca archivos fuera del repo.
