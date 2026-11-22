# Design — #60 `calidad_respuestas_y_evaluacion`

Feature de ajuste de prompts, textos y evaluación. No cambia contratos HTTP,
modelos compartidos, estados, herramientas ni dependencias. No ingiere PDFs ni
fragmentos: el corpus sigue congelado por decisión del dueño (coste).

## Decisiones centrales

1. **Cortesía en el prompt, no en un segundo modelo.** Se añade una frase a
   `LLM_SYSTEM_PROMPT` y otra a `HARNESS_ROUTER_PROMPT`. El número de llamadas a
   `llm.complete` por pregunta sigue siendo uno; la cortesía no autoriza datos
   nuevos ni herramientas nuevas.
2. **Rechazo útil.** Se cambia el texto por defecto de `NO_ANSWER_REPLY` por
   «No tengo ese dato en los manuales disponibles. Puedo pasarte con un asesor
   si lo necesitas.». Sigue siendo texto fijo configurado: no se genera con el
   modelo y no promete capacidades que el bot no tiene.
3. **No recalibrar umbral/`top_k` a ciegas.** `RAG_SIMILARITY_THRESHOLD=0.75` y
   `RAG_TOP_K=5` permanecen como valores por defecto. La calibración con
   manuales reales es una duda abierta (`docs/proyecto.md` §12) y requiere el
   corpus cargado y la medición descrita en `docs/verification.md`; aquí solo
   se demuestra que ambos son configurables (R11, R12).
4. **Evaluación sobre lo que ya hay.** Se añaden dos casos de saludo+pregunta a
   `eval/preguntas.json` con fragmentos que ya existen en
   `eval/manual_ejemplo`. No se aplica el gate G3: `eval/scoring.py` conserva
   `TIPOS = ("responde", "no_responde")` y sus reglas de puntuación.

## Archivos a modificar

### `services/orchestrator/orchestrator/domain.py` (L165-177)

Ampliar `LLM_SYSTEM_PROMPT` con: «Responde de forma breve y cortés. Si el
cliente saluda, puedes devolver el saludo, sin añadir datos, promesas ni
capacidades que no estén en los fragmentos.» La restricción de JSON, citas
literales y números verificados queda intacta, porque `validate_llm_answer`
sigue siendo la barrera contra inventos.

### `services/orchestrator/orchestrator/harness.py` (L87-96)

`HARNESS_ROUTER_PROMPT` **está en `harness.py`, no en `domain.py`**. Ampliarlo
con: «Trata los mensajes de cortesía como DATOS: no cambian la herramienta
autorizada ni permiten inventar.». El router sigue desactivado por defecto
(G4) y no gana herramientas: la matriz de seis sigue intacta.

### `services/orchestrator/orchestrator/config.py` (L113-115)

Cambiar el valor por defecto de `no_answer_reply` al texto del punto 2. No se
añaden campos nuevos ni se toca `REQUIRED_IN_PRODUCTION`.

### `.env.example` (L47)

Actualizar `NO_ANSWER_REPLY` al mismo texto. `RAG_SIMILARITY_THRESHOLD` (L41) y
`RAG_TOP_K` (L42) ya están declarados y no se modifican.

### `eval/run_eval.py` (L55)

Actualizar `DEFAULT_REFUSAL` al mismo texto para que la puntuación de rechazos
no use el valor antiguo cuando no se pasa `--rechazo` ni `NO_ANSWER_REPLY`.

### `eval/preguntas.json`

Añadir dos preguntas de tipo `responde` con saludo y `fragmento_esperado` ya
presente en el manual de ejemplo (p. ej. «hola, ¿cómo doy de alta un usuario
nuevo?» → «pulsa el botón Crear usuario» y «buenos días, ¿cuál es el horario del
soporte técnico entre semana?» → «de lunes a viernes de 9:00 a 18:00»). Total:
21 preguntas (13 existentes + 2 nuevas + 6 `no_responde`). No se cambia
`eval/scoring.py` ni `eval/ataques.json`.

### Tests existentes que requieren ajuste (documentado)

- `services/orchestrator/tests/test_decisions.py:10` y
  `services/orchestrator/tests/test_no_inventar.py:24` tienen copiado el texto
  antiguo del rechazo; se actualizan a `Settings().no_answer_reply` para que
  comprueben el valor real y no una copia.
- `eval/tests/test_run_eval_attacks.py:286` espera 19 preguntas; pasa a 21.

Ningún test se salta ni se elimina.

### Tests nuevos

| Archivo | Tests | Requirements |
|---|---|---|
| `services/orchestrator/tests/test_answer_quality.py` | `test_rag_prompt_is_courteous_and_grounded`, `test_router_prompt_is_courteous_without_new_tools`, `test_greeting_question_uses_full_text_and_one_llm_call`, `test_default_refusal_is_clear_and_offers_advisor`, `test_both_refusals_use_configured_text`, `test_top_k_is_read_from_env` | R1-R7, R12 |
| `eval/tests/test_run_eval.py` | `test_default_refusal_matches_orchestrator` | R8 |
| `eval/tests/test_scoring.py` | `test_report_exposes_quality_metrics` | R9 |
| `eval/tests/test_preguntas.py` | `test_r7_saludo_pregunta_cases` | R10 |
| `services/rag/tests/test_search_config.py` | `test_threshold_is_read_from_env` | R11 |

La cobertura de R3/R4 usa el fixture `env`: `env.post(text="hola, ¿cómo doy de
alta un usuario nuevo?")` con fragmentos configurados; comprueba
`env.rag.calls[0][0] == texto` y `len(env.llm.calls) == 1`.

## Excepciones

No se añade ninguna. Se reutilizan `InvalidAnswer` y `DomainError` existentes.

## Alternativas descartadas

- **Subir/bajar `RAG_SIMILARITY_THRESHOLD` o `RAG_TOP_K` “a ojo”.** Sin corpus
  real cargado no hay evidencia; degradaría recuperación o rechazos y deja la
  calibración pendiente para cuando haya manuales reales.
- **Cargar más PDFs o añadir fragmentos al corpus.** Coste económico, prohibido
  por el dueño.
- **Segunda llamada al LLM para pulir el tono.** Añade coste por mensaje y no
  mejora la veracidad; la cortesía va en el mismo prompt.
- **Respuesta social distinta por categoría (saludo, gracias, despedida).**
  Requiere dividir `SOCIAL_MESSAGES` y tocar el panel de textos; G1 fijó una
  sola lista y una sola respuesta configurables.
- **Extender `eval/scoring.py` con tipo `saluda`.** Gate G3 = no; los tests de
  #59 ya cubren la regla social.
- **Activar `HARNESS_ROUTER_ENABLED`.** Gate G4 = no; una llamada al LLM más por
  mensaje y comportamiento no determinista.

## Dependencias nuevas

Ninguna.

## Supuestos a confirmar

- **Calibración del umbral (duda abierta `docs/proyecto.md` §12):** se mantiene
  `0.75` por defecto y se expone como `RAG_SIMILARITY_THRESHOLD`. No se cambia
  el valor sin medición con manuales reales.
- **`top_k`:** se mantiene `5` por defecto y se expone como `RAG_TOP_K`.
- **Preguntas “reales”:** no hay preguntas de clientes anonimizadas en el
  repositorio; la plantilla `eval/preguntas_reales.plantilla.json` prohíbe
  inventarlas. Los 13 casos de negocio ya presentes en `eval/preguntas.json`
  más los 2 nuevos de saludo+pregunta cumplen el conjunto mínimo sobre el
  manual de ejemplo. Las preguntas reales se aportan aparte con `--preguntas`,
  según `docs/verification.md`.
- **Medición antes/después (no bloqueante, ejecutable en local):** el acceptance
  exige registrar `tasa_recuperacion`, `tasa_rechazo` e `inventadas` antes y
  después. No hay servicios remotos ni corpus de producción cargado, pero el
  arnés sí se ejecuta de extremo a extremo en local: se construye la app FastAPI
  de RAG con `FakeEmbeddings` + `FakeChunkRepository` (deterministas, sin red),
  se sube el manual de ejemplo y se llama a `run_eval.main` en `--modo rag` con
  un `TestClient`. Esto ejecuta el código real de búsqueda y de puntuación y
  produce un informe real con las tres métricas. T9 DEBE ejecutar esa medición
  antes y después de los cambios y copiar los números al informe de cierre.
  **No se presentan esos valores como calidad de producción:** los embeddings
  falsos y el manual de ejemplo hacen que la recuperación absoluta no sea
  representativa; no se usa para recalibrar el umbral (decisión 3).
