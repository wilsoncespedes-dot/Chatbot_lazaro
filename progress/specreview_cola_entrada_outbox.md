# Spec review — #64 cola_entrada_outbox

**Veredicto:** SPEC_APPROVED

- Cobertura: los 8 criterios de `acceptance` tienen R asociados (1: R1-R8; 2: R9-R16; 3: R17-R22; 4: R25; 5: R26-R28; 6: R29-R34; 7: R35-R40; 8: R41-R42).
- EARS: los R usan los patrones permitidos con un solo DEBE. Todos son verificables con un test concreto (`tasks.md` T16-T23 los nombra).
- Diseño: no añade infraestructura ni dependencias. Incluye alternativas descartadas y la sección de supuestos. Conserva la excepción de consentimiento de #35.
- Tasks: todas en `[ ]`, en orden, y su unión cubre R1-R42.
- Nada peligroso. Los datos se vacían al llegar a estado terminal y se purgan por retención.

Observaciones no bloqueantes, para el implementador:
1. `design.md` §2 dice que `config.py` lleva «9 variables», pero R36 y §5 listan 8. Vale 8.
2. R15 y R28 reclaman filas con concesión vencida sin tope explícito de intentos. Conviene que el implementador cierre el caso en que `attempts` ya supera el máximo (pasar a `failed`), sin cambiar los R.
