# Tasks — evaluacion

- [x] T1 — Crear `eval/manual_ejemplo/manual_ejemplo.md` con contenido inventado (sin datos reales). Cubre: R4.
- [x] T2 — Crear `eval/preguntas.json` con >= 10 `responde` (con `fragmento_esperado` literal) y >= 5 `no_responde`. Cubre: R1, R2, R3.
- [x] T3 — Implementar `normalize` y `load_questions` en `eval/scoring.py` con validación (`ValueError`). Cubre: R6.
- [x] T4 — Implementar `Question`, `Observation`, `Scored`, `score()` para ambos modos. Cubre: R8, R9, R10, R11, R12, R18, R19, R29.
- [x] T5 — Implementar `summarize()` y `render_report()` sin división por cero. Cubre: R13, R14, R15, R30, R31.
- [x] T6 — Test `test_preguntas.py`: conteos mínimos, ids únicos, fragmento esperado presente en el manual, archivo inválido lanza `ValueError`. Cubre: R1, R2, R3, R4, R5, R6.
- [x] T7 — Test `test_scoring.py` con resultados de ejemplo: acierto, fallo, rechazo correcto, inventada, rechazo indebido, sin respuesta, error, resumen y proporción `None`, informe con «Ninguno» y con fallos. Cubre: R8, R9, R10, R11, R12, R13, R14, R15, R18, R19, R29, R30, R31.
- [x] T8 — Test que verifica por análisis de `ast` que `scoring.py` no importa librerías de red ni usa `os.environ`. Cubre: R7.
- [x] T9 — Implementar `query_rag` y `query_orchestrator` con cliente `httpx` inyectable y `ReplySink`. Cubre: R16, R17, R18, R19, R25, R26, R28.
- [x] T10 — Implementar `main()` con argumentos `--url`, `--modo`, `--top-k`, `--espera`, `--rechazo`, `--preguntas`, `--umbral-minimo-aciertos`; escritura de `eval/resultados_<fecha>.md`; códigos de salida; comprobación de `SERVICE_TOKEN`; validación de `--top-k` (1-20) y del umbral (0-1). Cubre: R16, R20, R21, R22, R23, R27, R28, R32, R33.
- [x] T11 — Test `test_run_eval.py` con `httpx.MockTransport`: cuerpo y encabezado de `/search`, modo orquestador con receptor falso, timeout, error `401`/`5xx` con salida != 0, archivo de resultados escrito, `--preguntas` alterno, umbral mínimo, falta de token sin peticiones, `--top-k` y umbral fuera de rango sin peticiones, encabezado en `/messages`, continuar tras error. Cubre: R16, R17, R18, R19, R20, R21, R22, R23, R25, R26, R27, R28, R32, R33.
- [x] T12 — Test que el informe y la salida estándar no contienen el valor de `SERVICE_TOKEN`. Cubre: R24.
- [x] T13 — Añadir `EVAL_SINK_PORT` a `.env.example` y `eval/resultados_*.md` a `.gitignore`; documentar en el `--help` cómo cargar el manual con `scripts/cargar_manual.py`. Cubre: R17, R20.
- [x] T14 — Ejecutar `./init.sh` y `python -m pytest eval`; documentar el mapa R↔test en `progress/impl_evaluacion.md`. Cubre: R1-R33.
