# Tasks — evaluacion_ataques_y_preguntas_reales (#55)

- [x] T1 — Añadir `Attack`, `AttackResult`, `AttackSummary`, constantes y `load_attacks` en `eval/scoring.py` con validación de campos, duplicados, categorías y datos personales. Cubre: R2, R3, R4, R5, R6.
- [x] T2 — Añadir `score_attack`, `summarize_attacks` y `render_attacks` (sin mensaje ni respuesta en la salida). Cubre: R7, R8, R9, R10, R11, R12.
- [x] T3 — Añadir `check_real_set` en `eval/scoring.py`. Cubre: R24, R25, R26.
- [x] T4 — Crear `eval/ataques.json` con ≥3 ataques por categoría, sin datos reales. Cubre: R1.
- [x] T5 — Crear `eval/preguntas_reales.plantilla.json` con lista vacía e instrucciones. Cubre: R23.
- [x] T6 — Añadir flags `--ataques`, `--sin-ataques`, `--minimo-preguntas`, `--exigir-minimo` al parser de `eval/run_eval.py`. Cubre: R14, R15, R26, R29.
- [x] T7 — Implementar `_collect_attacks` y la integración en `main` (solo modo orquestador, chat ids propios, error de carga → 2 sin red). Cubre: R13, R16, R20.
- [x] T8 — Calcular código de salida (≠0 si un ataque no es resistido) y añadir sección «Ataques» al informe sin alterar `--comparar-url` ni `--umbral-minimo-aciertos`; conservar `--url` obligatorio (base de preguntas y ataques) y `--preguntas` repetible, contando el mínimo sobre el total de todos los archivos. Cubre: R17, R18, R19, R21, R22, R33.
- [x] T9 — Emitir el aviso de mínimo de preguntas (stderr e informe) solo con `--preguntas`; mantener código 2 si el archivo falta o es inválido. Cubre: R25, R27, R28, R29.
- [x] T10 — Ajustar los tests existentes de modo orquestador en `eval/tests/test_run_eval.py` con `--sin-ataques`. Cubre: R21.
- [x] T11 — Crear `eval/tests/test_attacks_scoring.py`: carga válida/ inválida/duplicados/PII, archivo real `ataques.json` (≥3 por categoría), puntuación, resumen, render sin datos, plantilla y `check_real_set`. Cubre: R1, R2, R3, R4, R5, R6, R7, R8, R9, R10, R11, R12, R23, R24.
- [x] T12 — Crear `eval/tests/test_run_eval_attacks.py` con `httpx.MockTransport` y sink falso: ataques ejecutados en orquestador, no en rag, `--sin-ataques`, `--ataques`, código ≠0 con ataque no resistido y 0 si todos resistidos, sección separada, archivo inválido → 2 sin peticiones, aviso <50, `--minimo-preguntas`, `--exigir-minimo`, sin aviso sin `--preguntas`, ausencia de mensaje/respuesta/token en informe y salida, compatibilidad `--comparar-url` y `--umbral-minimo-aciertos`, varios `--preguntas` que suman para el mínimo, `--url` obligatorio (su ausencia falla en el parser) y usado como base de las peticiones de ataques. Cubre: R13, R14, R15, R16, R17, R18, R19, R20, R21, R22, R25, R26, R27, R28, R29, R33.
- [x] T13 — Documentar en `docs/verification.md` cuándo correr la evaluación, plantilla, comandos y recalibración de `RAG_SIMILARITY_THRESHOLD`, incluyendo un comando de ejemplo con `--url`, `--modo orquestador`, `--preguntas` (repetible), `--ataques` y `--minimo-preguntas`. Cubre: R30, R31, R33.
- [x] T14 — Ejecutar `./init.sh` en verde y escribir `progress/impl_evaluacion_ataques_y_preguntas_reales.md` con la trazabilidad R→test. Cubre: R32.
