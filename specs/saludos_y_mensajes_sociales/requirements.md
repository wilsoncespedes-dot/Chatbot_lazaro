# Requirements — #59 `saludos_y_mensajes_sociales`

Arregla el síntoma reportado: al escribir «hola», el bot responde que no
encontró información en los manuales. La causa no es la base de datos: con
`HARNESS_ROUTER_ENABLED=false`, todo mensaje en `ACTIVE` cae en
`default_tool = buscar_base_conocimiento` (`harness.py`) y `_tool_rag` envía
`no_answer_reply` cuando no hay fragmentos, contando además un fallo RAG que a
las tres repeticiones escala a asesor.

Esta feature añade **una guardia determinista y local** antes del router y de la
herramienta por defecto. No cambia los contratos, no añade herramientas a
`TOOL_MATRIX`, no llama al LLM para decidir y no ingiere documentos nuevos.

Definiciones usadas abajo:

- **Mensaje social**: texto cuya forma normalizada es exactamente igual a una de
  las frases configuradas en `SOCIAL_MESSAGES`. La forma normalizada se obtiene
  con `normalize_text` (minúsculas, sin tildes, espacios colapsados) y después
  sustituyendo cada carácter que no sea letra `a-z` ni dígito `0-9` por un
  espacio. Por ejemplo, «¡Hola!» → `hola` y «¿Cómo estás?» → `como estas`.
- **Texto completo**: el mensaje recibido, sin recortar ni reescribir. Un saludo
  seguido de una pregunta no es un mensaje social porque su forma normalizada
  no es igual a ninguna frase de la lista.

## Orquestador — guardia social

### R1
CUANDO un mensaje en estado `ACTIVE` es social, el orquestador DEBE enviar el
texto configurado en `SOCIAL_REPLY`.

### R2
CUANDO responde un mensaje social, el orquestador NO DEBE llamar a
`adapters.rag.search`.

### R3
CUANDO responde un mensaje social, el orquestador NO DEBE llamar a
`adapters.llm.complete`.

### R4
CUANDO responde un mensaje social, el orquestador NO DEBE registrar el evento
`no_results`.

### R5
CUANDO responde un mensaje social, el orquestador NO DEBE incrementar el
contador de fallos RAG mediante `record_rag_outcome`.

### R6
CUANDO responde un mensaje social, el orquestador NO DEBE crear un caso ni
enviar aviso a asesores.

### R7
SI un mensaje no es social ENTONCES el orquestador DEBE continuar con la
precedencia actual: guardrails → palabras clave (supresión, asesor,
frustración) → router si está activo → herramienta por defecto.

### R8
CUANDO un mensaje contiene un saludo y una pregunta, el orquestador DEBE enviar
el texto completo al flujo de RAG sin sustituirlo por la respuesta social.

### R9
SI un mensaje contiene una palabra clave de supresión, asesor o frustración
ENTONCES el orquestador DEBE ejecutar esa palabra clave antes que la regla
social.

## Configuración y pureza

### R10
El orquestador DEBE leer la lista de frases y la respuesta social de las
variables de entorno `SOCIAL_MESSAGES` y `SOCIAL_REPLY`, declaradas en
`.env.example`.

### R11
El detector de mensajes sociales DEBE ser una función pura sin acceso a red,
base de datos ni adaptadores.

## Cobertura del acceptance

| Criterio del acceptance | Cobertura |
|---|---|
| «hola» ya no dice que no encontró información | R1, R2, R3 |
| No cuenta como fallo ni molesta al asesor | R4, R5, R6 |
| Las preguntas reales siguen igual | R7, R8 |
| «quiero un asesor» sigue escalando | R9 |
| Configurable y sin coste | R10, R11 |

## Test que verifica cada requirement

| Requirement | Test (archivo → task) |
|---|---|
| R1 | `services/orchestrator/tests/test_social_messages.py::test_social_reply_is_sent` (T4) |
| R2, R3 | `test_social_messages.py::test_social_reply_does_not_call_rag_or_llm` (T4) |
| R4, R5, R6 | `test_social_messages.py::test_social_reply_does_not_record_failure_or_handover` (T4) |
| R7 | `test_social_messages.py::test_non_social_message_keeps_existing_flow` (T5) |
| R8 | `test_social_messages.py::test_greeting_with_question_goes_to_rag_with_full_text` (T5) |
| R9 | `test_social_messages.py::test_handover_keyword_wins_over_social` (T6) |
| R10 | `test_social_messages.py::test_social_settings_are_read_from_env` (T2) |
| R11 | `test_social_messages.py::test_is_social_message_is_pure_and_exact` (T3) |
| No regresión de la matriz de herramientas | `test_harness_matrix.py::test_r1_r3_matrix_decision` y `::test_r1_r2_matrix_is_complete_immutable_and_has_six_tools` (existentes, T8) |
