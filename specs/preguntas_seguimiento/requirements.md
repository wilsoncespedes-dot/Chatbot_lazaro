# Requirements — preguntas_seguimiento (#64)

Servicio: `orchestrator` (`domain._tool_rag`, `build_llm_prompt`). Problema:
la búsqueda en el manual usaba solo el último mensaje, así que "¿y cómo la
anulo?" tras preguntar por facturas no encontraba nada útil.

## R1
CUANDO un mensaje que va al manual tiene como máximo
`RAG_FOLLOWUP_MAX_WORDS` palabras y el mismo contacto envió otra pregunta en
los últimos `RAG_FOLLOWUP_WINDOW_MINUTES` minutos, el sistema DEBE buscar
también con "pregunta anterior + mensaje".

## R2
SI el mensaje es más largo, no hay pregunta anterior dentro de la ventana o
`RAG_FOLLOWUP_ENABLED` es falso ENTONCES el sistema DEBE buscar solo con el
mensaje.

## R3
El sistema DEBE combinar ambas búsquedas sin repetir fragmentos, conservando
la mejor puntuación de cada uno y como máximo `RAG_TOP_K` fragmentos; la
consulta combinada NO DEBE superar 1000 caracteres.

## R4
CUANDO se usa la pregunta anterior, el prompt DEBE incluirla en
`<pregunta_anterior>` antes de `<pregunta>`, tratada como DATOS y sin que su
contenido pueda cerrar esa ni otras etiquetas del prompt.
