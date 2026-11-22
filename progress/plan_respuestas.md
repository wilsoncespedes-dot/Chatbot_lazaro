# Plan — que el bot responda bien, sin hacer más de lo asignado

> Prioridad actual (2026-11-21). Sustituye a `progress/plan_profe.md`.
> Síntoma reportado: al escribir «hola», el bot responde que no encontró
> información en la base de datos.
>
> **Restricción del dueño (2026-11-21):** el conocimiento está congelado. Hay
> unos PDFs y **no se pueden añadir más porque sale cobrado**. El bot debe
> arreglárselas por sí mismo con lo que ya tiene: ni ingesta nueva, ni más
> llamadas de pago por mensaje.

## 1. Diagnóstico: por qué pasa (verificado en código)

No es un fallo de la base de datos ni de «entrenamiento» del modelo. Es un
**enrutamiento por defecto demasiado amplio**:

1. `HARNESS_ROUTER_ENABLED=false` en `.env.example` L107. El router que podría
   distinguir intenciones está apagado por defecto.
2. `_resolve_and_run` (`domain.py` L2087-2199) solo desvía antes del final los
   guardrails, supresión, petición de asesor y frustración. Un saludo no encaja
   en ninguno.
3. `default_tool(ConversationState.ACTIVE)` devuelve siempre
   `buscar_base_conocimiento` (`harness.py` L104-108). Por tanto **todo** mensaje
   normal se manda a buscar en los manuales.
4. `_tool_rag` (`domain.py` L1797-1804) no encuentra fragmentos relevantes para
   «hola» y envía `settings.no_answer_reply`, que vale
   «No encontré información sobre eso en los manuales. Te paso con un asesor.»
   (`config.py` L108 y `.env.example` L47). Es el mensaje que el usuario parafrasea.
5. Efecto secundario: ese mismo camino llama a `record_rag_outcome`. Con
   `AUTO_HANDOVER_FAILURE_THRESHOLD=3`, tres saludos seguidos pueden abrir un
   caso y avisar a un asesor (`domain.py` L1701-1737).

Conclusión: el bot está haciendo **más** de lo que le corresponde (tratar un
saludo como una pregunta de manuales) y, además, contabilizándolo como fallo.

## 2. Qué significa «entrenar» en este proyecto

No hay fine-tuning: el modelo es externo y se llama por
`orchestrator/adapters/llm.py`. «Entrenar» aquí es, en orden de coste:

1. Añadir una **regla determinista** para los mensajes sociales (saludos,
   agradecimientos, confirmaciones cortas).
2. Ajustar los **prompts** (`LLM_SYSTEM_PROMPT`, `build_router_prompt`) para que
   no mezclen cortesía con respuestas de manuales.
3. Ajustar **textos y parámetros configurables** (respuestas fijas, umbral de
   similitud, `top_k`).
4. **Aprovechar el corpus existente**: revisar la segmentación y el umbral de
   los PDFs ya cargados. No se ingiere nada nuevo.
5. Ampliar el **set de evaluación** (`eval/preguntas.json`) y medir antes/después.

Con corpus cerrado hay un límite honesto: una pregunta cuyo dato no está en esos
PDFs **no puede responderse sin inventar**. La salida correcta en ese caso es un
rechazo claro y útil que ofrezca al asesor, no un «no encontré la base de datos»
ni una respuesta inventada con conocimiento general del modelo.

Límite no negociable (`docs/architecture.md` §4): **el bot no inventa**. Las
respuestas factuales solo salen de fragmentos con cita verificada. Los saludos
son texto fijo configurado, no generación libre: así no puede inventar datos ni
inventarse capacidades que no tiene.

## 3. Límites del plan (no hacer más de lo asignado)

- No nuevos canales, ni API de Lázaro, ni MCP, ni gráficos, ni nuevo servicio.
- No nueva herramienta del modelo que escriba en base de datos.
- **No cargar PDFs nuevos ni añadir fragmentos** (coste).
- **No añadir llamadas al LLM por mensaje**: saludos y rechazos se resuelven con
  lógica determinista ya existente (`normalize_text`, `matches_any`, clasificador
  de palabras clave), que no cuesta nada.
- No activar el router global: añade una llamada al LLM por mensaje y hace el
  comportamiento menos predecible.
- Solo `services/orchestrator/`, su configuración, `eval/` y los specs.
- Una feature a la vez, con `spec → review → implement → tests → init.sh`.

## 4. Features

### #59 `saludos_y_mensajes_sociales` (primera, imprescindible)

`title`: «Respuesta determinista a saludos y mensajes sociales».

**Acceptance**

- «hola», «buenos días», «gracias», «ok», «perfecto», «¿cómo estás?» reciben una
  respuesta corta y configurable.
- Esa respuesta **no** llama a `rag.search`, **no** llama a `llm.complete`,
  **no** registra evento `no_results`, **no** llama a `record_rag_outcome` y
  **no** crea caso ni avisa a asesores.
- Una pregunta real («¿cómo creo un usuario?») sigue exactamente por el flujo
  actual de RAG.
- Si el mensaje contiene un saludo **y** una pregunta, manda la pregunta a RAG;
  el saludo no la sustituye.

**Esqueleto EARS para `requirements.md`**

- R1 — CUANDO un mensaje en estado `ACTIVE` coincide con la lista de mensajes
  sociales configurada, el orquestador DEBE enviar el texto social configurado.
- R2 — CUANDO responde un mensaje social, el orquestador NO DEBE llamar a
  `adapters.rag.search` ni a `adapters.llm.complete`.
- R3 — CUANDO responde un mensaje social, el orquestador NO DEBE registrar
  `no_results` ni incrementar el contador de fallos RAG.
- R4 — SI el mensaje no coincide con la lista social ENTONCES el orquestador
  DEBE continuar con la precedencia actual: keywords → router (si activo) →
  herramienta por defecto.
- R5 — CUANDO un mensaje contiene un saludo y una pregunta, el orquestador DEBE
  enviar el texto completo al flujo de RAG.
- R6 — Los textos y la lista de mensajes sociales DEBEN leerse de configuración
  y declararse en `.env.example`.

**Diseño previsto**

- La detección es **determinista y local**, reutilizando lo que ya existe:
  `normalize_text` / `matches_any` de `harness.py` y, si conviene, el clasificador
  de palabras clave de `classifier.py` (#25), que es puramente local y no
  consume tokens. No se llama al LLM para decidir si un mensaje es un saludo.
- Función pura nueva en `domain.py` (o `small_talk.py` si conviene mantener
  `domain.py` manejable): `is_social_message(text, phrases) -> bool`. Sin IO.
- Precedencia: después de guardrails y keywords de supresión/asesor/frustración,
  antes del router y de `default_tool`. Así un «hola, quiero un asesor» sigue
  escalando.
- Configuración nueva en `config.py` + `.env.example`:
  `SOCIAL_MESSAGES` (lista cerrada) y `SOCIAL_REPLY` (texto fijo), con
  normalización igual a la de `HANDOVER_KEYWORDS`.
- Alternativas descartadas: activar el router para todo (no determinista y
  cuesta una llamada al LLM por mensaje); meter los saludos en los manuales
  (mezcla documentación con conversación); ajustar el umbral RAG para que
  «hola» coincida (rompería "no inventar" y degradaría las respuestas reales);
  fine-tuning (fuera de alcance y sin infraestructura).

**Tests** — `services/orchestrator/tests/test_social_messages.py`

- Parametrizado con los saludos: ResponseText = `SOCIAL_REPLY`; fakes de RAG,
  LLM y handover que lanzan excepción si se llaman; assert de cero eventos
  `no_results` y cero `record_rag_outcome`.
- Caso «hola, ¿cómo creo un usuario?»: `rag.search` recibe el texto completo.
- Caso «hola, quiero hablar con un asesor»: gana la keyword de escalado.
- Caso con pregunta real sin saludo: sigue pasando por RAG (no regresión).

### #60 `calidad_respuestas_y_evaluacion` (segunda)

`title`: «Mejorar la calidad de las respuestas de manuales con evaluación».

Objetivo: exprimir **los PDFs que ya existen** para que las preguntas reales
sí encuentren respuesta, y que las que no estén en ellos se rechacen con un
texto útil. Sin ingesta nueva y sin inventar.

**Acceptance**

- Los prompts de RAG y del router incluyen reglas explícitas de cortesía sin
  permitir contenido fuera de los fragmentos.
- El set `eval/preguntas.json` incluye al menos 10 preguntas reales del negocio
  y casos límite de saludo+pregunta, evaluados contra el corpus ya cargado.
- Se registra la medición antes y después: `tasa_recuperacion`,
  `tasa_rechazo` e `inventadas` (`eval/run_eval.py`).
- El mensaje de rechazo deja de decir «no encontré información en los manuales»
  y pasa a un texto claro: no tengo ese dato, puedo pasarte con un asesor.
- **No se ejecuta `scripts/cargar_manual.py`** ni se añaden fragmentos: el
  corpus es el que hay y el coste de ampliarlo está fuera de alcance.

**Esqueleto EARS**

- R1 — El prompt del asistente DEBE prohibir responder con datos ausentes de los
  fragmentos, incluso si el usuario saluda antes de preguntar.
- R2 — CUANDO el dataset de evaluación se ejecuta, el sistema DEBE conservar
  los tipos `responde` y `no_responde` y sus reglas de puntuación actuales.
- R3 — El sistema DEBE exponer como configuración el umbral de similitud y
  `top_k` usados por la búsqueda (supuesto de `docs/proyecto.md` §12).
- R4 — CUANDO ningún fragmento del corpus existente responde la pregunta, el
  orquestador DEBE enviar un rechazo fijo que ofrezca la intervención de un
  asesor, sin usar conocimiento general del modelo.

**Diseño previsto**

- Cambios acotados en `domain.py` (`LLM_SYSTEM_PROMPT`, `build_llm_prompt`,
  texto de `no_answer_reply`) y `harness.py` (`HARNESS_ROUTER_PROMPT`).
- Sin cambio de modelo, sin dependencias nuevas y sin nuevas llamadas al LLM.
- `eval/preguntas.json` se amplía; no se cambia `eval/scoring.py` salvo gate G3.
- Se puede reequilibrar el umbral/`top_k` **solo con los fragmentos actuales**;
  eso no cuesta nada y no añade conocimiento.

### Ampliación opcional del evaluador (dentro de #60 si se aprueba)

Añadir tipo `saluda` a `eval/scoring.py` con outcome `saludo_correcto`, para que
los saludos se midan con el mismo mecanismo que las preguntas. Por defecto
**no se hace**: los tests unitarios de #59 ya cubren la regla y ampliar el
evaluador toca `scoring.py`, `run_eval.py` y cuatro archivos de tests.

## 5. Gates a confirmar

| Gate | Default recomendado |
|---|---|
| G1 — ¿Dónde se configuran los saludos? | En `.env.example` como `SOCIAL_MESSAGES`/`SOCIAL_REPLY`. No tocar el panel de textos: es un cambio mayor y no aporta aquí |
| G2 — ¿Qué se considera «social»? | Lista cerrada: saludos, agradecimientos y confirmaciones de una o dos palabras. Nunca frases con `?` ni con verbo de consulta |
| G3 — ¿Extender `eval/scoring.py` con tipo `saluda`? | No. Solo tests unitarios en #59 |
| G4 — ¿Activar el router? | No. Se deja `HARNESS_ROUTER_ENABLED=false` |
| G5 — ¿Se toca el corpus? | No, bajo ninguna forma. Solo se ajustan prompts, umbral/`top_k`, textos y evaluación sobre los PDFs ya cargados |
| G6 — ¿Puede el bot responder con conocimiento general del modelo cuando el PDF no cubre la pregunta? | No. Eso sería inventar y está prohibido. Debe rechazar con un texto útil y ofrecer asesor. Si se quiere lo contrario, hace falta una decisión explícita del dueño que modifique la regla «el bot no inventa» |

**Decisiones confirmadas por el dueño (2026-11-21):** G1 = configuración local
sin LLM; G6 = rechazo útil + asesor. Quedan como defaults firmes para los specs:
toda la autonomía se resuelve con reglas deterministas y clasificador de
palabras clave; ninguna respuesta usa conocimiento general del modelo.

## 6. Verificación y cierre

- Por feature: spec en `specs/<name>/`, `./init.sh` en verde, trazabilidad
  `R<n>` → test en `progress/impl_<name>.md`, reviewer y `done`.
- Reproducción del síntoma original: test con «hola» que fallaba antes de #59 y
  pasa después.
- No regresión: tests existentes de `test_conversation_states.py`,
  `test_no_inventar.py`, `test_auto_handover.py` y `test_harness_flow.py`
  siguen verdes sin editarse.
- Medición #60: antes/después con `python eval/run_eval.py ...`, usando
  exclusivamente el corpus ya presente.
- Comprobación de coste: `#59` no añade ninguna llamada a `adapters.llm` ni a
  `adapters.rag` para mensajes sociales; `#60` no cambia el número de llamadas
  por pregunta.

## 7. Entregables

- `specs/saludos_y_mensajes_sociales/{requirements,design,tasks}.md`
- `specs/calidad_respuestas_y_evaluacion/{requirements,design,tasks}.md`
- `services/orchestrator/orchestrator/domain.py` (guardia social y prompts)
- `services/orchestrator/orchestrator/config.py` y `.env.example`
- `services/orchestrator/tests/test_social_messages.py`
- `eval/preguntas.json` (y solo si G3: `eval/scoring.py`)
- `feature_list.json`: IDs #59 y #60 en `pending` hasta abrir cada spec
