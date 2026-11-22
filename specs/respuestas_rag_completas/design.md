# Design — respuestas_rag_completas

## Archivos

- `services/orchestrator/orchestrator/domain.py`: hacer explícita la síntesis
  breve en el prompt; dividir las entregas largas en `_send`.
- `services/rag/rag/domain.py`: reemplazar ventanas ciegas por empaquetado de
  frases y líneas, manteniendo el límite configurable y usando corte por
  palabra solo para unidades mayores que el límite.
- `services/telegram_gateway/telegram_gateway/adapters/telegram.py`: quitar el
  truncamiento silencioso y dividir por límites legibles como defensa final.
- `services/orchestrator/tests/` y `services/rag/tests/`: cubrir síntesis,
  límites semánticos, solapamiento y entrega larga.
- `specs/respuestas_rag_completas/`: registrar requisitos y trazabilidad.

## Decisiones

La respuesta se mantiene anclada a citas literales ya verificadas; la síntesis
no desactiva la barrera contra alucinaciones. El prompt propone 1200 caracteres
como objetivo, no como truncamiento. La salida se entrega en mensajes de hasta
3500 caracteres para dejar margen bajo el límite de 4096 caracteres del
contrato y Telegram. Se prefieren párrafos, después frases y finalmente
palabras para dividir. La cola transaccional registra una sola respuesta
completa y envía los bloques separados; el adaptador de Telegram conserva
todos los bloques aunque el texto combinado supere el máximo de una llamada a
`sendMessage`.

La fragmentación agrupa unidades cortas hasta `CHUNK_SIZE`. En cada frontera
se agrega contexto anterior formado por unidades completas mientras quepa en
`CHUNK_OVERLAP`; si una unidad individual es demasiado larga, se corta por
palabras y, como último recurso, por caracteres. No se agregan dependencias.

Se descarta aumentar indiscriminadamente `CHUNK_SIZE`: reduce algunos cortes,
pero mezcla temas y no resuelve respuestas copiadas extensas ni el límite de
entrega.

## Supuestos

- `CHUNK_SIZE=1000`, `CHUNK_OVERLAP=200`, `RAG_TOP_K=5` y el umbral de similitud
  permanecen configurables como hoy.
- Los extractores PDF y DOCX representan páginas o párrafos con saltos de línea
  cuando el formato de origen lo permite.
- La pregunta del usuario no implica que toda la respuesta deba caber en un
  único mensaje físico: si es extensa se divide, pero cada parte queda completa.
