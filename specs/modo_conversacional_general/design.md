# Design — modo_conversacional_general

## Alcance

El modo se ejecuta como fallback conversacional **solo después** de una búsqueda
RAG exitosa sin fragmentos. Los mensajes sociales que #86 ya atiende de forma
determinista conservan su respuesta actual. Si RAG encuentra fragmentos, no se
cambia el flujo de respuesta con citas. Si RAG está caído, se conserva el error
actual sin invocar este fallback.

La misma llamada al LLM que genera la respuesta general clasifica el mensaje en
JSON como `general` o `manual_required`. Antes de aceptar una respuesta
`general`, una regla determinista compara el mensaje normalizado con la lista
configurable `CONVERSATIONAL_BUSINESS_TERMS`; una coincidencia fuerza la rama
`manual_required` aunque el LLM diga `general`. La categoría `general` puede
contestar conocimiento general y retomar el contexto incluido en el prompt. La
categoría `manual_required` impide enviar la respuesta generada y conserva el
rechazo fijo, el registro de fallo RAG y el traspaso actual. El prompt también
indica que preguntas de productos, políticas, procesos, operaciones, precios o
datos personales de Lázaro requieren manuales o herramientas autorizadas.

La lista local es una barrera determinista para los términos configurados, no
una garantía de detección exhaustiva de cualquier forma de preguntar por la
empresa. Para mensajes fuera de la lista el clasificador del LLM sigue siendo
probabilístico; el prompt reduce ese riesgo, y la respuesta general no se
presenta como información oficial de Lázaro. La lista debe poder ampliarse desde
el entorno cuando se conozcan los términos del negocio.

## Archivos y firmas

- `services/orchestrator/orchestrator/config.py`: añadir
  `conversational_mode_enabled: bool = True`,
  `conversational_business_terms` con el default no vacío
  `Lázaro, producto(s), servicio(s), precio(s), plan(es), tarifa(s), factura(s),
  pago(s), cuenta(s), cliente(s), usuario(s), política(s), proceso(s),
  operación(es), licencia(s), contrato(s), pedido(s), reserva(s), soporte,
  horario(s), garantía(s), manual(es), instalar, instalo, instala, instale,
  instalación, configurar, configuro, configura, configuración`
  y sus properties normalizadas. Pydantic lee `CONVERSATIONAL_MODE_ENABLED` y
  `CONVERSATIONAL_BUSINESS_TERMS` del entorno.
- `.env.example`: documentar `CONVERSATIONAL_MODE_ENABLED=true`, editable por
  despliegue sin requerir una base de datos o migración, y los términos de
  negocio configurables.
- `services/orchestrator/orchestrator/domain.py`:
  - añadir `CONVERSATIONAL_SYSTEM_PROMPT` y un esquema local
    `ConversationalAnswer` con `mode: Literal["general", "manual_required"]`
    y `answer: str`;
  - añadir `build_conversational_prompt(question, context) -> tuple[str, str]`;
  - añadir `parse_conversational_answer(raw) -> ConversationalAnswer`, que
    rechace JSON malformado, forma desconocida o respuesta vacía para `general`;
  - añadir una guarda determinista con `matches_any` antes de aceptar la
    respuesta `general`;
  - extender `_tool_rag` para invocar el fallback solo ante búsqueda exitosa sin
    fragmentos, con la opción habilitada y si el guardia existente no detectó
    prompt injection. `manual_required` e inválidos
    conservan el rechazo y los efectos de ausencia RAG; una respuesta `general`
    se envía con `_send` y registra un evento `conversation_reply`, sin contarla
    como fallo RAG. El texto completo se guarda en un solo registro de historial
    y el outbox conserva la división actual por bloques.
- `services/orchestrator/tests/test_conversational_mode.py`: cubrir prompt,
  parsing, routing fallback, rechazo para negocio, contexto de memoria y
  aislamiento ante errores.
- `progress/impl_modo_conversacional_general.md`: mapa de trazabilidad de R a
  pruebas.

No cambian `TOOL_NAMES`/`TOOL_MATRIX`: los mensajes siguen primero por el RAG
existente; el modo conversacional no puede ejecutar herramientas. La respuesta
general se almacena y envía por `_send`, por lo que se mantienen historial,
outbox, reintentos y división por límites actuales.

## Decisiones

- El modo queda habilitado por defecto porque es la capacidad solicitada; el
  switch configurable permite apagarlo en despliegues. Cuando está apagado se
  conserva exactamente el rechazo actual al no haber fragmentos.
- La clasificación se solicita junto con la respuesta, en una sola llamada
  existente al LLM tras el no-hit de RAG. No se añade una llamada de router por
  cada mensaje ni una nueva herramienta.
- El rechazo usa el `no_answer_reply` y `_record_rag_outcome` actuales. Solo una
  respuesta de modo `general` evita aumentar la cuenta de fallos RAG.
- Se reutiliza `_memory_context`; no se altera la política global de memoria.
  Por tanto el contexto se incluye solo con `MEMORY_ENABLED=true` y sesión
  activa, y sigue sujeto a límites, filtros y retención existentes.
- Se descarta responder con LLM libre ante cualquier mensaje sin buscar RAG:
  podría convertir consultas sobre datos del negocio en respuestas no
  verificadas. También se descarta crear otra base o almacenar una transcripción
  paralela, porque el repositorio ya tiene historial y memoria con controles.

## Supuestos configurables

- `CONVERSATIONAL_MODE_ENABLED=true` es el valor por defecto inicial; el
  operador lo puede apagar con la variable del mismo nombre.
- Con `MEMORY_ENABLED=false`, el modo responde al mensaje actual sin recuperar
  conversación previa. No se cambia el default de memoria existente ni se
  presupone el valor efectivo de AWS.
- La distinción `general` frente a `manual_required` se expresa en el contrato
  JSON del LLM y se prueba con fakes. El sistema falla cerrado si la forma no se
  puede validar; la lista determinista bloquea los términos de negocio
  configurados aunque el LLM clasifique mal.

- La garantía determinista de bloqueo solo cubre términos incluidos en
  `CONVERSATIONAL_BUSINESS_TERMS`; no se afirma que el LLM clasifique
  perfectamente toda pregunta sobre la empresa.

## Dependencias y errores

No se añaden dependencias, servicios, excepciones públicas, rutas HTTP ni
migraciones. Se reutiliza `ServiceUnavailable` y el error/flujo de rechazo
existente ante fallo de LLM o una salida no válida.
