# Tasks — #60 `calidad_respuestas_y_evaluacion`

Reglas: no se ingiere corpus, no se activa el router, no se amplía
`eval/scoring.py` con `saluda`, no se añaden herramientas ni dependencias. Los
tests existentes que se ajustan se documentan en el informe de cierre.

## Prompts y coste

- [x] T1 — Añadir la regla de cortesía a `LLM_SYSTEM_PROMPT` en `services/orchestrator/orchestrator/domain.py` (L165-177) y a `HARNESS_ROUTER_PROMPT` en `services/orchestrator/orchestrator/harness.py` (L87-96), según `design.md`. Conservar el JSON de citas, la frase «únicamente los fragmentos» y la matriz de seis herramientas. Cubre: R1, R2.

- [x] T2 — Crear `services/orchestrator/tests/test_answer_quality.py` con `test_rag_prompt_is_courteous_and_grounded` y `test_router_prompt_is_courteous_without_new_tools`: comprobar que ambos prompts piden cortesía, que el prompt RAG sigue exigiendo citas literales y que el de router no autoriza herramientas nuevas. Cubre: R1, R2.

- [x] T3 — En el mismo archivo, añadir `test_greeting_question_uses_full_text_and_one_llm_call` con `env.post(text="hola, ¿cómo doy de alta un usuario nuevo?")` y fragmentos configurados: `env.rag.calls[0][0]` es el texto completo y `len(env.llm.calls) == 1`. Verificar además que `test_harness_matrix.py` sigue en verde sin editarse. Cubre: R3, R4, R13.

## Rechazo útil

- [x] T4 — Cambiar `no_answer_reply` en `services/orchestrator/orchestrator/config.py` y `NO_ANSWER_REPLY` en `.env.example` al texto de `design.md`. En `test_answer_quality.py` añadir `test_default_refusal_is_clear_and_offers_advisor` (contiene «No tengo ese dato» y «asesor», y no contiene «No encontré información») y `test_both_refusals_use_configured_text` (el rechazo por sin fragmentos y el de respuesta inválida envían `settings.no_answer_reply`). Actualizar las copias del texto antiguo en `test_decisions.py:10` y `test_no_inventar.py:24` para usar `Settings().no_answer_reply`. Cubre: R5, R6, R7.

- [x] T5 — Actualizar `DEFAULT_REFUSAL` en `eval/run_eval.py` al mismo texto. Añadir `test_default_refusal_matches_orchestrator` en `eval/tests/test_run_eval.py` comparando con `Settings().no_answer_reply` del orquestador. Cubre: R8.

## Evaluación

- [x] T6 — En `eval/tests/test_scoring.py`, añadir `test_report_exposes_quality_metrics`: a partir de un `Summary` con aciertos, rechazos e inventadas, comprobar que `render_report` incluye «Aciertos de recuperación», «Rechazos correctos» y «Respuestas inventadas detectadas». No modificar `eval/scoring.py`. Cubre: R9.

- [x] T7 — Añadir dos casos de saludo+pregunta a `eval/preguntas.json` (ids `s01`, `s02`, tipo `responde`, `fragmento_esperado` ya presente en el manual). Añadir `test_r7_saludo_pregunta_cases` en `eval/tests/test_preguntas.py`: al menos 2 preguntas empiezan por saludo y sus fragmentos están en el manual. Actualizar `eval/tests/test_run_eval_attacks.py:286` de 19 a 21 preguntas. Cubre: R10.

## Configuración y cierre

- [x] T8 — Añadir `test_threshold_is_read_from_env` en `services/rag/tests/test_search_config.py` (monkeypatch de `RAG_SIMILARITY_THRESHOLD` sobre `rag.config.Settings`) y `test_top_k_is_read_from_env` en `test_answer_quality.py` (monkeypatch de `RAG_TOP_K` sobre `orchestrator.config.Settings`). No cambiar los valores por defecto. Cubre: R11, R12.

- [x] T9 — Ejecutar `python -m pytest -q` y `./init.sh` en verde. **Ejecutar la medición real antes y después** (no solo documentar el comando): con el manual de ejemplo y `FakeEmbeddings`/`FakeChunkRepository`, correr `run_eval.main` en `--modo rag` a través de un `TestClient` de la app FastAPI de RAG, y registrar en `progress/impl_calidad_respuestas_y_evaluacion.md` los valores de `tasa_recuperacion`, `tasa_rechazo` e `inventadas` de ambas pasadas junto con la trazabilidad R1–R13 y los tests existentes ajustados. Declarar explícitamente que los valores absolutos no representan el corpus de producción y que no se usa la medición para recalibrar el umbral. Comprobación de cierre; no cubre ningún `R<n>`.

- [x] T10 — Revisión de código enfocada; si aprueba, marcar #60 como `done` en `feature_list.json`, mover el resumen a `progress/history.md` y dejar `progress/current.md` con la plantilla. Comprobación de cierre; no cubre ningún `R<n>`.
