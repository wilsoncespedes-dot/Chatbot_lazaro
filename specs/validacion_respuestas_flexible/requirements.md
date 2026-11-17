# Requirements — validacion_respuestas_flexible (#62)

Servicio: `orchestrator` (`domain.validate_llm_answer` y `LLM_SYSTEM_PROMPT`).
Problema: la validación anti-alucinación de `no_inventar` rechaza respuestas
correctas y el cliente recibe "No encontré información…" aunque el manual sí
tenga la respuesta. Se aflojan solo los falsos rechazos; las cifras y citas
inventadas siguen rechazándose.

## R1
CUANDO la salida del LLM es un JSON envuelto en un bloque de código Markdown
(```` ``` ```` o ```` ```json ````), el sistema DEBE validar el JSON interior.

## R2
SI tras quitar el bloque de código el texto no es JSON válido ENTONCES el
sistema DEBE rechazarlo con `invalid_json`.

## R3
El sistema NO DEBE contar como cifras los marcadores de pasos al inicio de
línea ("1.", "2)", "3-", "Paso 4:") al comprobar `number_not_in_citations`.

## R4
SI la respuesta contiene cualquier otra cifra que no aparece en los
fragmentos citados ENTONCES el sistema DEBE rechazarla con
`number_not_in_citations`.

## R5
El sistema DEBE aceptar una cita que coincide con su fragmento ignorando
mayúsculas, espacios repetidos, tildes y signos de puntuación.

## R6
SI la cita tiene palabras que no están en su fragmento, está vacía o solo
aparece en otro fragmento ENTONCES el sistema DEBE rechazarla con
`quote_not_literal`.

## R7
El prompt del sistema DEBE permitir pasos numerados y DEBE seguir exigiendo
que cualquier otra cifra aparezca en los fragmentos citados.
