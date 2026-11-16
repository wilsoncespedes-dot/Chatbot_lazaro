# Spec review — feature 58 `correcciones_sonar`

**Veredicto:** APPROVED

Segunda pasada, acotada al único bloqueo de la primera (R13/R14). Resuelto.

## Comprobado en esta pasada

- **R13 y R14 retirados**: no queda ninguna mención a `R13` ni `R14` en
  `specs/correcciones_sonar/`. Los requirements son R1–R12, cada uno con un
  solo `DEBE`.
- **Ningún `R<n>` sin test concreto**: la tabla «Test que verifica cada
  requirement» de `requirements.md` asigna a cada R1–R12 un test con nombre y
  archivo, y cada uno está creado por una task (T2, T3, T5, T6, T8, T9, T11,
  T13).
- **Ninguna task referencia un `R<n>` eliminado**: los `Cubre:` de T1–T13 solo
  citan R1–R12 y entre todas los cubren todos. T14 y T15 quedan como
  comprobaciones de cierre, declaradas sin `R<n>`.
- **Los 7 criterios del acceptance siguen cubiertos**:
  - S8786 → R1, R2, R3, R4.
  - secrets:S6698 → R5, R6, R7.
  - S3516 → R8, R9, R10 (código `0` por los tests existentes, citados en T15).
  - S5863 `test_adapters.py` → R11.
  - Falsos positivos S2068 / S5332 → R12.
  - S5863 obsoleto en `test_advisor_commands.py` → tabla de triaje de
    `design.md` (fila «Obsoleto»); T14 comprueba que el archivo no se toca.
  - Sin cambios de contrato, tests intactos, `./init.sh` verde → T14 y T15.

## Validado en la primera pasada (no reabierto)

Equivalencia de `_contains_email` y `_redact_emails` con las regex actuales,
ausencia de cambios de contrato y de dependencias, conexión perezosa de
`PgVectorChunkRepository` (R6), alternativas descartadas, «Supuestos a
confirmar», tasks en `[ ]` y en orden, nada peligroso.

## Nota no bloqueante

- `eval/scoring.py` L30 conserva la misma regex de correo cuadrática. Está
  fuera del reporte y del acceptance; queda anotado en `design.md` para el
  leader como posible feature posterior.
