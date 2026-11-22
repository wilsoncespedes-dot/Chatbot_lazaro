# Spec review — #68 bandeja_unificada_tomar_control

**Veredicto:** SPEC_APPROVED

- Cobertura: los 7 criterios de `acceptance` están cubiertos (estados R1-R8, lectura y auditoría R9-R14, tomar atómico R15-R26, devolver R27-R29, visibilidad configurable y supresión R30-R35, consentimiento R36-R37, pruebas R42).
- EARS y verificabilidad: correctos, un solo DEBE por requisito.
- Diseño: respeta las 3 capas, sin dependencias nuevas, con alternativas descartadas y supuestos S1-S6. La atomicidad usa advisory lock y no necesita migración. No hay índice único en `cases`, así que el diseño es coherente.
- Tasks: todas en `[ ]`, ordenadas y con sus R.

Notas no bloqueantes para el implementador:
- R18 (el bot no responde con `with_advisor`) no figura en el "Cubre" de ninguna task. T14 ("bot calla tras tomar") debe cubrirlo con una prueba, y el informe de T16 debe mapearlo.
- R42 es meta, y T16 lo cubre.
