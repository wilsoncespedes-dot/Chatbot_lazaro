# Requirements — respuestas_rag_completas

Servicios: `rag` (`services/rag/`) para fragmentación; `orchestrator`
(`services/orchestrator/`) para la síntesis y el envío; `telegram_gateway`
(`services/telegram_gateway/`) conserva la entrega según el canal.

## R1
CUANDO el orquestador genera una respuesta RAG, el sistema DEBE pedir al LLM
que sintetice en español claro la información pertinente de los fragmentos,
que no copie bloques extensos y que mantenga la respuesta dentro de 1200
caracteres cuando la evidencia lo permita.

## R2
CUANDO el LLM genera una respuesta RAG, el sistema DEBE conservar la
validación existente de citas, identificadores y números antes de enviarla.

## R3
CUANDO `rag` fragmenta texto con límites de frase o salto de línea, el sistema
DEBE preferir esos límites al crear fragmentos sin superar `CHUNK_SIZE`, salvo
cuando una frase por sí sola exceda ese tamaño.

## R4
CUANDO una frase excede `CHUNK_SIZE`, el sistema DEBE dividirla en límites de
palabra cuando sea posible y garantizar que los fragmentos no superen el
tamaño configurado.

## R5
CUANDO el orquestador envía una respuesta mayor que 3500 caracteres, el
sistema DEBE dividirla en mensajes consecutivos en límites de párrafo, frase o
palabra, y DEBE entregar todo el texto sin truncarlo.

## R6
SI la respuesta RAG no cuenta con citas válidas ENTONCES el sistema DEBE
conservar el rechazo fijo y NO DEBE enviar texto sin validar.
