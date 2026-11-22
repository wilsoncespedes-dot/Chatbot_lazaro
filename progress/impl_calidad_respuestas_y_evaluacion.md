# Implementación — #60 `calidad_respuestas_y_evaluacion`

Feature #60 implementada en una sola sesión; cierre formal pendiente de T10.
Spec revisado en dos pasadas (`CAMBIOS REQUERIDOS` → `APROBADO`) antes de tocar
código.

## Qué cambió

1. **Cortesía sin coste**: una frase en `LLM_SYSTEM_PROMPT`
   (`orchestrator/domain.py`) y otra en `HARNESS_ROUTER_PROMPT`
   (`orchestrator/harness.py`). El prompt RAG sigue exigiendo JSON con citas
   literales y números verificados; el router sigue apagado y con seis
   herramientas.
2. **Rechazo útil**: `no_answer_reply`, `NO_ANSWER_REPLY` y `DEFAULT_REFUSAL`
   usan ahora el mismo texto: «No tengo ese dato en los manuales disponibles.
   Puedo pasarte con un asesor si lo necesitas.». Ya no aparece «No encontré
   información».
3. **Evaluación**: dos casos de saludo+pregunta (`s01`, `s02`) en
   `eval/preguntas.json`, usando fragmentos que ya están en el manual de
   ejemplo. `eval/scoring.py` no se tocó (gate G3).
4. **Configuración**: se demuestra que `RAG_SIMILARITY_THRESHOLD` y `RAG_TOP_K`
   se leen del entorno, sin cambiar sus valores por defecto (0.75 y 5).

## Trazabilidad R<n> → test

| Req | Test | Estado |
|---|---|---|
| R1 | `services/orchestrator/tests/test_answer_quality.py::test_rag_prompt_is_courteous_and_grounded` | verde |
| R2 | `services/orchestrator/tests/test_answer_quality.py::test_router_prompt_is_courteous_without_new_tools` | verde |
| R3, R4 | `services/orchestrator/tests/test_answer_quality.py::test_greeting_question_uses_full_text_and_one_llm_call` | verde |
| R5, R6 | `services/orchestrator/tests/test_answer_quality.py::test_default_refusal_is_clear_and_offers_advisor` | verde |
| R7 | `services/orchestrator/tests/test_answer_quality.py::test_both_refusals_use_configured_text` | verde |
| R8 | `eval/tests/test_run_eval.py::test_default_refusal_matches_orchestrator` | verde |
| R9 | `eval/tests/test_scoring.py::test_report_exposes_quality_metrics` | verde |
| R10 | `eval/tests/test_preguntas.py::test_r7_saludo_pregunta_cases` | verde |
| R11 | `services/rag/tests/test_search_config.py::test_threshold_is_read_from_env` | verde |
| R12 | `services/orchestrator/tests/test_answer_quality.py::test_top_k_is_read_from_env` | verde |
| R13 | `services/orchestrator/tests/test_harness_matrix.py::test_r1_r2_matrix_is_complete_immutable_and_has_six_tools` | verde, sin editar |

Tareas T1–T9 marcadas en `specs/calidad_respuestas_y_evaluacion/tasks.md`;
T10 (revisión y cierre) se completa al final de la sesión.

## Tests existentes ajustados (documentación obligatoria)

- `services/orchestrator/tests/test_decisions.py` y
  `services/orchestrator/tests/test_no_inventar.py`: la constante `NO_ANSWER`
  dejó de copiar el texto antiguo y ahora es `Settings().no_answer_reply`, para
  que comprueben el valor real y no una copia que pueda quedar desincronizada.
- `eval/tests/test_run_eval_attacks.py`: esperado de preguntas 19 → 21.
- No se ha saltado ni eliminado ningún test.

## Verificación

- `python -m pytest` → **3647 passed, 2 skipped** (eran 3631 antes de la
  ampliación de saludos; +5 tests parametrizados de #59 y +11 de #60).
- `python -m pytest -q` → salida 0.
- Validación de `feature_list.json` y presencia de los tres specs → correcta.
- `./init.sh` ejecutado con Git Bash
  (`& 'C:\Program Files\Git\bin\bash.exe' ./init.sh`) → `[OK] Entorno listo`,
  salida 0. `bash` invocado directamente desde PowerShell engancha el
  subsistema WSL, que no está instalado; por eso se usa la ruta absoluta de
  Git Bash.

## Medición antes/después (acceptance)

Arnés reproducible, sin red y sin corpus nuevo: se construye la app FastAPI de
RAG con `FakeEmbeddings` + `FakeChunkRepository`, se sube el manual de ejemplo
como PDF y se llama a `run_eval.main(..., --modo rag)` mediante `TestClient`.
Se ejecuta el código real de búsqueda y de puntuación.

| Pasada | Preguntas | `tasa_recuperacion` | `tasa_rechazo` | `inventadas` |
|---|---|---|---|---|
| Antes (código previo a #60) | 19 | 2/13 (15%) | 2/6 (33%) | 4 |
| Después (#60 implementado) | 21 | 2/15 (13%) | 2/6 (33%) | 4 |

Los dos casos nuevos de saludo+pregunta entran en el denominador de
recuperación y no aciertan con este embedder falso (bolsa de palabras por hash:
añadir «hola,» o «buenos días,» reduce la similitud). **Estos valores absolutos
no representan la calidad con el corpus de producción**: ni los embeddings ni
el manual son los reales. Por eso **no se ha recalibrado** `RAG_SIMILARITY_THRESHOLD`
ni `RAG_TOP_K` a partir de esta medición; siguen siendo 0.75 y 5. El objetivo
verificable de #60 —que el texto completo llega al RAG y cuesta una sola
llamada al LLM— lo demuestra el test determinista T3, no esta medición.

Comando de referencia con servicios y corpus reales (no ejecutado aquí):

```bash
python scripts/cargar_manual.py <manual_real.pdf> --nombre <nombre>
python eval/run_eval.py --url http://localhost:8001 --modo rag
```

## Gates y coste

- Sin ingesta en producción, sin fragmentos nuevos y sin PDFs añadidos.
- Router apagado; matriz de 6 herramientas intacta; sin tipo `saluda` en
  `eval/scoring.py`; sin servicios, canales, MCP ni API de Lázaro nuevos.
- Ninguna llamada extra a `adapters.llm`: la cortesía vive en el mismo prompt
  (R3/R4 comprueban exactamente una llamada).
- Sin dependencias nuevas.

## Revisión

Revisión de código enfocada: `CAMBIOS REQUERIDOS` por tres puntos (ejecutar
`./init.sh` con Git Bash, corregir afirmaciones prematuras del informe y
reforzar R8 con el camino real de `run_eval.main`). Corregidos y re-revisados:
`APROBADO`. #60 marcado `done`, resumen movido a `progress/history.md` y
`progress/current.md` dejado con la plantilla.
