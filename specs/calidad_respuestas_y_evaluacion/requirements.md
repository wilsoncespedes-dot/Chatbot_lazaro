# Requirements — #60 `calidad_respuestas_y_evaluacion`

Objetivo: exprimir **los PDFs que ya existen** para que las preguntas reales
sí encuentren respuesta y las que no estén en ellos se rechacen con un texto
útil, sin inventar y sin añadir coste. El síntoma de «hola» ya quedó resuelto en
#59; esta feature cubre la calidad del resto de respuestas.

Restricciones heredadas del dueño y del plan (`progress/plan_respuestas.md`):
no ingerir documentos nuevos, no añadir llamadas al LLM por mensaje, no tocar
la matriz de herramientas (6 fijas), no activar el router, no extender
`eval/scoring.py` con un tipo `saluda` (G3 = no), no nuevos servicios, canales,
MCP ni API de Lázaro. Fuera del corpus: rechazo útil + asesor, nunca
conocimiento general del modelo.

## Orquestador

### R1
El prompt `LLM_SYSTEM_PROMPT` del orquestador DEBE exigir respuestas breves y
corteses sin introducir datos, promesas ni capacidades ausentes de los
fragmentos.

### R2
El prompt `HARNESS_ROUTER_PROMPT` del orquestador DEBE exigir cortesía sin
ampliar la matriz de herramientas ni autorizar contenido inventado.

### R3
CUANDO un mensaje contiene un saludo y una pregunta y existen fragmentos
relevantes, el orquestador DEBE enviar el texto completo a
`adapters.rag.search`.

### R4
CUANDO un mensaje contiene un saludo y una pregunta y existen fragmentos
relevantes, el orquestador DEBE realizar exactamente una llamada a
`adapters.llm.complete`.

### R5
El texto por defecto de `no_answer_reply` DEBE indicar que no se tiene el dato
y ofrecer la intervención de un asesor.

### R6
El texto por defecto de `no_answer_reply` NO DEBE contener la frase «No
encontré información».

### R7
El orquestador DEBE seguir usando `settings.no_answer_reply` tanto en el
rechazo por falta de fragmentos como en el de respuesta inválida.

## Evaluación

### R8
`eval/run_eval.py` DEBE usar como rechazo por defecto el mismo texto que el
orquestador.

### R9
El informe de `eval/scoring.py` DEBE incluir `tasa_recuperacion`,
`tasa_rechazo` e `inventadas`.

### R10
`eval/preguntas.json` DEBE conservar solo los tipos `responde` y
`no_responde` e incluir al menos dos casos de saludo seguido de pregunta cuyo
`fragmento_esperado` figure en el manual de ejemplo.

## Configuración y no regresión

### R11
La configuración del servicio RAG DEBE leer `RAG_SIMILARITY_THRESHOLD` de las
variables de entorno.

### R12
La configuración del orquestador DEBE leer `RAG_TOP_K` de las variables de
entorno.

### R13
El harness DEBE seguir teniendo exactamente seis herramientas autorizadas.

## Cobertura del acceptance

| Criterio del acceptance | Cobertura |
|---|---|
| Prompts con cortesía sin contenido fuera de fragmentos | R1, R2 |
| Dataset con preguntas de negocio y saludo+pregunta | R10 |
| Medición antes/después de las tres métricas | R8, R9 y task T9 |
| Rechazo claro que ofrezca asesor | R5, R6, R7 |
| Sin ingesta nueva ni fragmentos | Restricción de diseño; ver `design.md` |
| Sin llamadas extra al LLM | R3, R4, R13 |

## Test que verifica cada requirement

| Requirement | Test (archivo → task) |
|---|---|
| R1 | `services/orchestrator/tests/test_answer_quality.py::test_rag_prompt_is_courteous_and_grounded` (T2) |
| R2 | `::test_router_prompt_is_courteous_without_new_tools` (T2) |
| R3, R4 | `::test_greeting_question_uses_full_text_and_one_llm_call` (T3) |
| R5, R6 | `::test_default_refusal_is_clear_and_offers_advisor` (T4) |
| R7 | `::test_both_refusals_use_configured_text` (T4) |
| R8 | `eval/tests/test_run_eval.py::test_default_refusal_matches_orchestrator` (T5) |
| R9 | `eval/tests/test_scoring.py::test_report_exposes_quality_metrics` (T6) |
| R10 | `eval/tests/test_preguntas.py::test_r7_saludo_pregunta_cases` (T7) |
| R11 | `services/rag/tests/test_search_config.py::test_threshold_is_read_from_env` (T8) |
| R12 | `services/orchestrator/tests/test_answer_quality.py::test_top_k_is_read_from_env` (T8) |
| R13 | `test_harness_matrix.py::test_r1_r2_matrix_is_complete_immutable_and_has_six_tools` (existente, T3) |
