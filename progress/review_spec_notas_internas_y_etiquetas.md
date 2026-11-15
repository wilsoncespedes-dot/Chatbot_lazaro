# Revisión de spec — #50 notas_internas_y_etiquetas

**Veredicto:** APROBADO

- Cobertura del acceptance: los 6 criterios están cubiertos.
  - Notas visibles diferenciadas con autor y fecha, solo con permiso: R1-R4.
  - Seguridad de aislamiento (canal, IA, resumen, memoria): R10-R13.
  - Etiquetas y filtro: R14-R28.
  - Escape, sesión, CSRF y auditoría sin texto: R29-R34.
  - Supresión y retención: R35-R38.
  - Longitudes configurables y esquema: R39-R40.
- EARS: cada R tiene un solo DEBE y verbos concretos, y cada uno es verificable con un test.
- Diseño: solo cambia el orchestrator, sin dependencias nuevas y con tablas propias (no `messages`). Incluye alternativas descartadas y «Supuestos a confirmar» (N1-N5, con defaults seguros).
- Tasks: T1-T18 están todas en `[ ]`, en orden, y cubren R1-R40. Los tests (T12-T16) y `./init.sh` (T18) están incluidos.
- No hay nada peligroso: no usa la red ni borra datos sin que lo ejecute una persona.

Observaciones no bloqueantes:
- R4 mezcla "no mostrar" y "no permitir modificar" en una sola frase. Es aceptable porque ambas se prueban a la vez.
- N1 (solo el autor borra sus notas) es una decisión de producto con un default seguro y es fácil de ampliar.
