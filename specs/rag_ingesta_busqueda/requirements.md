# Requirements — rag_ingesta_busqueda

> Servicio: `rag` (`services/rag/`), salvo R19-R21 que cubre `scripts/cargar_manual.py`
> (cliente de `rag`). Contratos: `POST /manuals` y `POST /search` de
> `contracts/CONTRATOS.md`. Los supuestos configurables están en `design.md`.

## Ingesta: POST /manuals

## R1
CUANDO `rag` recibe `POST /manuals` (multipart con `file` y `name`) con un archivo PDF válido que contiene texto, el sistema DEBE responder `201` con `{manual_id, chunks}`, donde `chunks` es el número de fragmentos guardados y `manual_id` es un identificador válido según el contrato.

## R2
CUANDO `rag` recibe `POST /manuals` con un archivo DOCX válido que contiene texto, el sistema DEBE responder `201` con `{manual_id, chunks}` con `chunks >= 1`.

## R3
CUANDO `rag` ingiere un manual, el sistema DEBE dividir el texto extraído en fragmentos de como máximo `CHUNK_SIZE` caracteres, de modo que cada fragmento consecutivo comparta `CHUNK_OVERLAP` caracteres con el anterior.

## R4
CUANDO `rag` ingiere un manual, el sistema DEBE guardar cada fragmento con `chunk_id` único, `manual_id`, número de orden (1, 2, ... según su posición en el texto), texto, vector de embedding y `active = true`.

## R5
CUANDO `rag` ingiere un manual, el sistema DEBE calcular el vector de cada fragmento a través del adaptador de embeddings y guardarlo con el nombre del manual (`name`) para devolverlo en `/search`.

## R6
SI el archivo de `POST /manuals` no es un PDF ni un DOCX (se decide por el contenido, no por la extensión) ENTONCES el sistema DEBE responder `415` con `{"error": "unsupported_format", "message": ...}` y no guardar nada.

## R7
SI el archivo de `POST /manuals` está vacío (0 bytes) ENTONCES el sistema DEBE responder `422` con `{"error": "empty_document", "message": ...}` y no guardar nada.

## R8
SI el archivo de `POST /manuals` es un PDF o DOCX sin texto extraíble (o ilegible) ENTONCES el sistema DEBE responder `422` con `{"error": "empty_document", "message": ...}` y no guardar nada.

## R9
SI falta la parte `file` o `name`, o `name` tiene más de 200 caracteres o está vacío, ENTONCES el sistema DEBE responder `422` con `{"error": "validation_error", "message": ...}`.

## R10
SI el adaptador de embeddings falla durante una ingesta ENTONCES el sistema DEBE responder `500` con `{"error": "internal_error", "message": ...}` y no dejar ningún fragmento del manual guardado.

## Búsqueda: POST /search

## R11
CUANDO `rag` recibe `POST /search` válido, el sistema DEBE devolver `200` con un arreglo JSON de elementos `{chunk_id, manual, text, score}` ordenados por `score` descendente.

## R12
CUANDO `rag` recibe `POST /search`, el sistema DEBE devolver como máximo `top_k` fragmentos.

## R13
CUANDO `rag` recibe `POST /search`, el sistema DEBE devolver solo fragmentos con `score >= RAG_SIMILARITY_THRESHOLD`, donde `score` es la similitud coseno entre el vector de la consulta y el del fragmento.

## R14
SI ningún fragmento activo alcanza `RAG_SIMILARITY_THRESHOLD` ENTONCES el sistema DEBE devolver `200` con el arreglo vacío `[]`.

## R15
SI ningún fragmento activo alcanza `RAG_SIMILARITY_THRESHOLD` ENTONCES el sistema NO DEBE devolver en `POST /search` los fragmentos más parecidos.

## R16
El sistema NO DEBE devolver en `POST /search` ningún fragmento con `active = false`, aunque su score supere el umbral.

## R17
CUANDO `rag` recibe `POST /search` con `category` distinto de `null`, el sistema DEBE ignorarla y devolver el mismo resultado que sin ella (supuesto S7 del contrato).

## Seguridad, errores y script

## R18
SI una petición a `POST /manuals` o `POST /search` llega sin `X-Service-Token` válido ENTONCES el sistema DEBE responder `401` con `{"error": "unauthorized", "message": ...}` y no ejecutar la ingesta ni la búsqueda.

## Script de carga

## R19
CUANDO se ejecuta `scripts/cargar_manual.py <ruta> --nombre <nombre>`, el script DEBE enviar `POST {RAG_URL}/manuals` como multipart con el archivo en `file` y el nombre en `name`, con el encabezado `X-Service-Token` igual a `SERVICE_TOKEN`, e imprimir `manual_id` y `chunks` de la respuesta `201` con código de salida 0.

## R20
SI `rag` responde con un código de error o no es alcanzable ENTONCES `scripts/cargar_manual.py` DEBE terminar con código de salida distinto de 0 e imprimir en `stderr` el `error` y el `message` recibidos (o la causa de red).

## R21
SI la ruta del archivo no existe, o `RAG_URL` o `SERVICE_TOKEN` no están definidos, ENTONCES `scripts/cargar_manual.py` DEBE terminar con código de salida distinto de 0 sin enviar ninguna petición.

## Adaptadores y pruebas

## R22
El sistema DEBE acceder a los embeddings y al almacenamiento de fragmentos únicamente a través de las interfaces `EmbeddingsClient` y `ChunkRepository`, cada una con una versión falsa (`FakeEmbeddings` determinista, `FakeChunkRepository` en memoria) y una real (`HttpEmbeddingsClient`, `PgVectorChunkRepository`).

## R23
El sistema DEBE producir con `FakeEmbeddings` el mismo vector para el mismo texto en cualquier ejecución.

## R24
El sistema DEBE producir con `FakeEmbeddings` vectores con similitud coseno 1.0 para textos iguales.

## R25
El sistema NO DEBE incluir en el texto de ninguna sentencia SQL de `PgVectorChunkRepository` el texto de la consulta ni el de los manuales (se pasan como parámetros).
