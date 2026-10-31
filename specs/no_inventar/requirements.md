# Requirements — no_inventar

Servicio que cumple todo: **orchestrator** (`services/orchestrator`). No se toca ningún contrato: `HandoverReason` ya reserva `invalid_answer` para esta feature (`contracts/CONTRATOS.md` S5).

Definiciones: «fragmentos de RAG» = la lista `SearchResult` que devolvió `POST /search` para el mensaje en curso. «Salida del LLM» = el texto devuelto por `LLMClient.complete`. «Cita» = objeto `{chunk_id, quote}`. «Respuesta inválida» = cualquier salida del LLM que incumple R2-R10; se identifica con un motivo concreto (ver R15).

## Formato de la salida del LLM

## R1
CUANDO el orquestador pide una respuesta al LLM, el sistema DEBE indicar en el texto de sistema que la salida ha de ser un JSON `{"answer": <texto>, "citations": [{"chunk_id": <texto>, "quote": <texto>}]}`.

## R2
SI la salida del LLM no es JSON válido ENTONCES el sistema DEBE tratarla como respuesta inválida con motivo `invalid_json`.

## R3
SI la salida del LLM es JSON válido pero no tiene la forma `{answer: str no vacío, citations: lista de {chunk_id: str, quote: str}}` ENTONCES el sistema DEBE tratarla como respuesta inválida con motivo `invalid_shape`.

## Validación de citas

## R4
SI la lista `citations` está vacía ENTONCES el sistema DEBE tratar la respuesta como inválida con motivo `no_citations`.

## R5
SI algún `chunk_id` citado no está entre los fragmentos de RAG ENTONCES el sistema DEBE tratar la respuesta como inválida con motivo `foreign_chunk_id`.

## R6
SI el `quote` de una cita (vacío o no) no aparece literalmente en el texto del fragmento con ese `chunk_id` ENTONCES el sistema DEBE tratar la respuesta como inválida con motivo `quote_not_literal`.

## R7
CUANDO el sistema compara un `quote` con el texto de su fragmento, el sistema DEBE ignorar las diferencias de mayúsculas/minúsculas y de espacios repetidos (cualquier secuencia de espacios en blanco equivale a un espacio).

## R8
CUANDO el sistema compara un `quote` con el texto de su fragmento, el sistema NO DEBE ignorar las diferencias de tildes ni de signos de puntuación.

## Validación de números

## R9
SI algún número escrito en `answer` no aparece en el texto de ninguno de los fragmentos citados ENTONCES el sistema DEBE tratar la respuesta como inválida con motivo `number_not_in_citations`.

## R10
CUANDO el sistema extrae números de un texto, el sistema DEBE tomar como número cada secuencia de dígitos que admita separadores `.` o `,` entre dígitos (p. ej. `1500`, `3.5`, `1.500,75`) y comparar el texto del número tal cual, sin interpretar su valor.

## Resultado

## R11
CUANDO la salida del LLM es una respuesta válida, el sistema DEBE enviar al cliente únicamente el campo `answer` (no el JSON ni las citas) con `POST /send`.

## R12
CUANDO la salida del LLM es una respuesta válida, el sistema DEBE registrar el evento `rag_answer` con motivo `chunks_found`.

## R13
CUANDO la respuesta es inválida, el sistema DEBE enviar al cliente el texto fijo `NO_ANSWER_REPLY` (que incluye la oferta de hablar con un asesor).

## R14
CUANDO la respuesta es inválida, el sistema NO DEBE enviar al cliente ningún texto generado por el LLM.

## R15
CUANDO la respuesta es inválida, el sistema DEBE registrar el evento `invalid_answer` con contacto, fecha y como motivo uno de: `invalid_json`, `invalid_shape`, `no_citations`, `foreign_chunk_id`, `quote_not_literal`, `number_not_in_citations`.

## R16
CUANDO la respuesta es inválida y `INVALID_ANSWER_HANDOVER` es `true`, el sistema DEBE llamar a `POST /handover` con motivo `invalid_answer` después de enviar `NO_ANSWER_REPLY`.

## R17
DONDE `INVALID_ANSWER_HANDOVER` es `false`, el sistema NO DEBE llamar a `POST /handover` ante una respuesta inválida.

## R18
CUANDO la respuesta es inválida, el sistema NO DEBE registrar el evento `rag_answer`.

## Seguridad y restricciones

## R19
SI un LLM falso devuelve una respuesta bien formada que cita un `quote` inexistente en el fragmento ENTONCES el sistema DEBE entregar al cliente solo `NO_ANSWER_REPLY` (prueba de seguridad obligatoria).

## R20
SI un LLM falso devuelve una respuesta bien formada con citas literales válidas pero con un número en `answer` ausente de los fragmentos citados ENTONCES el sistema DEBE entregar al cliente solo `NO_ANSWER_REPLY` (prueba de seguridad obligatoria).

## R21
El sistema DEBE implementar la validación como función pura en `domain.py`, sin IO.

## R22
El sistema NO DEBE escribir en los registros (logs) el texto de `answer`, de `quote` ni de la salida del LLM; solo ids y el motivo.

## R23
SI se copia código de rag-support-bot (MIT) a algún archivo del repositorio ENTONCES ese archivo DEBE conservar el aviso de copyright original en su cabecera y figurar en `THIRD_PARTY_NOTICES.md`.

## Cobertura del `acceptance` original

| Criterio | R |
|---|---|
| JSON `{answer, citations}`; si no, inválida | R1, R2, R3 |
| Al menos una cita, chunk_id de RAG, quote literal (ignorando mayúsculas y espacios) | R4, R5, R6, R7, R8 |
| Números de `answer` en fragmentos citados | R9, R10 |
| Rechazo fijo con oferta de asesor y evento `invalid_answer` con motivo | R13, R14, R15 (R16-R18 concretan el traspaso y el resto del flujo) |
| Prueba de seguridad con LLM falso | R19, R20 |
| Aviso MIT en `THIRD_PARTY_NOTICES.md` | R23 |
| Tests: válida, JSON inválido, sin citas, chunk ajeno, cita no literal, número inventado | R11, R12, R2, R4, R5, R6, R9 |
