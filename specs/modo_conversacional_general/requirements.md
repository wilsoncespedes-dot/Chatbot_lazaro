# Requirements — modo_conversacional_general

Servicio: `orchestrator` (`services/orchestrator/`). El modo vive en el mismo
bot y canal, y reutiliza la memoria e historial existentes.

## R1
CUANDO una conversación está en estado `ACTIVE`,
`CONVERSATIONAL_MODE_ENABLED=true` y una búsqueda RAG exitosa no devuelve
fragmentos, el orquestador DEBE solicitar al LLM una clasificación explícita
`general` o `manual_required` junto con la respuesta.

## R2
CUANDO el LLM devuelve `general` con una respuesta válida, el orquestador DEBE
enviarla al cliente por el flujo de salida existente.

## R3
CUANDO el LLM devuelve `manual_required`, el orquestador DEBE enviar el rechazo
configurado en `no_answer_reply`.

## R4
CUANDO el LLM devuelve `manual_required`, el orquestador DEBE conservar el
registro de ausencia de resultados RAG y el umbral de traspaso a asesor
existentes.

## R5
SI la salida conversacional no es JSON válido, no cumple el esquema o contiene
una respuesta vacía ENTONCES el orquestador DEBE rechazarla y ejecutar el flujo
de rechazo y traspaso existente.

## R6
SI no hay fragmentos RAG y el mensaje coincide con un término de
`CONVERSATIONAL_BUSINESS_TERMS` ENTONCES el orquestador NO DEBE aceptar ni enviar
una respuesta de modo `general`.

## R7
CUANDO el orquestador prepara el prompt conversacional, DEBE incluir memoria e
historial existentes solo cuando `MEMORY_ENABLED=true` y exista una sesión
activa para el contacto.

## R8
SI `MEMORY_ENABLED=false` o no existe una sesión activa ENTONCES el orquestador
NO DEBE incluir memoria ni historial de sesión en el prompt conversacional.

## R9
CUANDO una búsqueda RAG devuelve fragmentos, el sistema DEBE conservar el flujo
RAG actual, incluida la validación de citas antes de enviar la respuesta.

## R10
SI el servicio RAG no está disponible ENTONCES el orquestador DEBE conservar el
flujo actual de error y NO DEBE recurrir al modo conversacional.

## R11
CUANDO el orquestador emite una respuesta conversacional, DEBE guardarla y
encolar su entrega mediante el repositorio y outbox existentes.

## R12
CUANDO el orquestador guarda una respuesta conversacional, DEBE persistir el
texto completo en el historial del contacto, aunque el outbox lo divida en
bloques de entrega.

## R13
El sistema NO DEBE añadir una base de datos ni tablas para el modo
conversacional.

## R14
El sistema NO DEBE añadir un servicio para el modo conversacional.

## R15
SI el filtro existente `HARNESS_INJECTION_PATTERNS` detecta una instrucción de
inyección ENTONCES el orquestador NO DEBE invocar el LLM conversacional y DEBE
conservar el rechazo y el traspaso por fallo existentes.

La lista configurable de términos es una salvaguarda determinista para los
temas de negocio conocidos. Para mensajes no cubiertos por esa lista, la
clasificación `general`/`manual_required` del LLM sigue siendo una decisión
probabilística; el prompt debe abstenerse de afirmar información de Lázaro sin
fuente y cualquier salida inválida debe fallar cerrada.
