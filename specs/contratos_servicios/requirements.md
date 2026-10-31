# Requirements — contratos_servicios (feature #1)

> Feature: «Contratos entre servicios». Fija las rutas HTTP/JSON entre servicios
> de la versión mínima antes de programarlos (`docs/proyecto.md` §7, decisión D5).
> Todo lo de esta feature vive en `contracts/` (más una línea en
> `requirements-dev.txt`). Ningún servicio de `services/` se toca.
>
> Notación EARS estricta (`docs/specs.md`). Los supuestos `S<n>` citados están
> en `design.md` §«Supuestos a confirmar». Ids estables: no renumerar.

Las 8 rutas de esta feature («las rutas del contrato») son:

| Ruta                          | Servicio que la expone |
|-------------------------------|------------------------|
| `POST /messages`              | `orchestrator`         |
| `POST /send`                  | `telegram_gateway`     |
| `POST /search`                | `rag`                  |
| `POST /handover`              | `handover`             |
| `POST /cases/{id}/reply`      | `orchestrator`         |
| `POST /manuals`               | `rag`                  |
| `POST /cases/{id}/close`      | `handover`             |
| `POST /cases/check-timeouts`  | `handover`             |

---

## A. Documento `contracts/CONTRATOS.md`

## R1
El sistema DEBE incluir el archivo `contracts/CONTRATOS.md` con un encabezado
de nivel 3 con el texto exacto `### <MÉTODO> <ruta>` (p. ej. `### POST /messages`)
por cada una de las 8 rutas del contrato.

## R2
En la sección de cada ruta, `CONTRATOS.md` DEBE indicar el servicio que la
expone en una línea `- **Expone:** <servicio>`, con el servicio de la tabla de
arriba.

## R3
En la sección de cada ruta, `CONTRATOS.md` DEBE indicar quién la llama en una
línea `- **Llama:** <quién>` no vacía.

## R4
En la sección de cada ruta, `CONTRATOS.md` DEBE nombrar en una línea
`- **Modelos:**` los modelos de request y de response de la ruta, citados entre
comillas invertidas con nombres que existen en `lazaro_contracts.__all__`.

## R5
En la sección de cada ruta, `CONTRATOS.md` DEBE incluir una subsección
`#### Request` con una tabla de columnas `Campo | Tipo | Obligatorio | Descripción`
que contenga todos los campos del modelo de request de esa ruta.

## R6
En la sección de cada ruta, `CONTRATOS.md` DEBE incluir una subsección
`#### Respuesta` que indique el código HTTP de éxito y una tabla de columnas
`Campo | Tipo | Obligatorio | Descripción` que contenga todos los campos del
modelo de response de esa ruta (para `POST /search`, los de `SearchResult`).

## R7
En la sección de cada ruta, `CONTRATOS.md` DEBE incluir una subsección
`#### Errores` con una tabla de columnas `HTTP | error | Cuándo` que contenga al
menos las filas `401 | unauthorized` y `422 | validation_error`.

## R8
`CONTRATOS.md` DEBE documentar en la tabla `#### Errores` de cada ruta los
errores propios de esa ruta: `POST /send` → `502 | telegram_error`;
`POST /manuals` → `415 | unsupported_format` y `422 | empty_document`;
`POST /cases/{id}/reply` → `404 | not_found` y `502 | upstream_error`;
`POST /cases/{id}/close` → `404 | not_found`.

## R9
`CONTRATOS.md` DEBE incluir una sección `## Reglas comunes` que documente que
toda ruta del contrato exige el encabezado `X-Service-Token` igual a
`SERVICE_TOKEN` y que sin él la respuesta es `401` con `error` = `unauthorized`,
con las excepciones `GET /health` y el webhook de Telegram.

## R10
La sección `## Reglas comunes` de `CONTRATOS.md` DEBE documentar que todo error
tiene la forma `{"error": "<codigo>", "message": "<texto>"}` (modelo
`ErrorResponse`) e incluir la tabla de códigos de error de `design.md` §4.

## R11
La sección `## Reglas comunes` de `CONTRATOS.md` DEBE documentar que `update_id`
es el identificador único por mensaje y que el orquestador, ante un `update_id`
ya visto, responde `202` con `status` = `duplicate` sin reprocesar.

## R12
La sección `## Reglas comunes` de `CONTRATOS.md` DEBE documentar que los 4
servicios (`telegram_gateway`, `orchestrator`, `rag`, `handover`) exponen
`GET /health` sin token, con respuesta `{"status": "ok", "service": "<nombre>"}`
(modelo `HealthResponse`).

## R13
`CONTRATOS.md` DEBE incluir una sección `## Supuestos a confirmar` que recoja el
supuesto `S1`: `POST /manuals` es `multipart/form-data` con las partes `file`
(archivo) y `name` (texto).

## R14
La sección `## Supuestos a confirmar` de `CONTRATOS.md` DEBE recoger el supuesto
`S2`: `last_messages` de `POST /handover` son como máximo los últimos 10
mensajes, en orden cronológico, como lista de `{role, text, at}`.

## R15
La sección `## Supuestos a confirmar` de `CONTRATOS.md` DEBE mencionar cada uno
de los identificadores de supuesto `S1` a `S10` definidos en `design.md`.

---

## B. Paquete `contracts/lazaro_contracts/`

## R16
El paquete `lazaro_contracts` DEBE exportar en `__all__` (e importar desde
`lazaro_contracts`) estos modelos: `MessageRequest`, `MessageResponse`,
`SendRequest`, `SendResponse`, `SearchRequest`, `SearchResult`,
`SearchResponse`, `HandoverRequest`, `LastMessage`, `HandoverResponse`,
`CaseReplyRequest`, `CaseReplyResponse`, `ManualUploadRequest`,
`ManualUploadResponse`, `CaseCloseRequest`, `CaseCloseResponse`,
`CheckTimeoutsRequest`, `CheckTimeoutsResponse`, `ErrorResponse`,
`HealthResponse`.

## R17
Cada modelo de R16 DEBE ser una subclase de `pydantic.BaseModel` de pydantic
versión mayor 2.

## R18
SI un objeto validado con cualquier modelo de R16 distinto de `SearchResponse`
contiene un campo no declarado ENTONCES el modelo DEBE lanzar
`pydantic.ValidationError`.

## R19
SI a un ejemplo válido de cualquier modelo de R16 se le quita un campo
obligatorio ENTONCES el modelo DEBE lanzar `pydantic.ValidationError` (se
comprueba para cada campo obligatorio de cada modelo; en `SearchResponse`,
quitando un campo de un elemento).

## R20
SI un campo de fecha (`MessageRequest.received_at`, `LastMessage.at`) llega sin
zona horaria ENTONCES el modelo DEBE lanzar `pydantic.ValidationError`.

## R21
SI un campo `text` de `MessageRequest`, `SendRequest`, `CaseReplyRequest` o
`LastMessage` está vacío o supera `MAX_TEXT_LENGTH` (4096) caracteres ENTONCES
el modelo DEBE lanzar `pydantic.ValidationError`.

## R22
SI un identificador (`case_id`, `contact_id`, `advisor_id`, `chunk_id`,
`manual_id` o un elemento de `timed_out_cases`) está vacío o supera
`MAX_IDENTIFIER_LENGTH` (64) caracteres ENTONCES el modelo DEBE lanzar
`pydantic.ValidationError`.

## R23
`MessageRequest` DEBE exigir `update_id` (entero ≥ 0), `telegram_user_id`
(entero), `chat_id` (entero), `text` (texto) y `received_at` (fecha ISO 8601
con zona horaria).

## R24
SI `MessageResponse.status` no es `accepted` ni `duplicate` ENTONCES el modelo
DEBE lanzar `pydantic.ValidationError`.

## R25
`SendRequest` DEBE exigir `chat_id` (entero) y `text` (texto).

## R26
SI el campo `sent` de `SendResponse` o de `CaseReplyResponse` no es `true`
ENTONCES el modelo DEBE lanzar `pydantic.ValidationError`.

## R27
`SearchRequest` DEBE exigir `query` (texto no vacío) y `top_k` (entero).

## R28
SI `SearchRequest.top_k` es menor que 1 o mayor que `MAX_TOP_K` (20) ENTONCES
el modelo DEBE lanzar `pydantic.ValidationError`.

## R29
`SearchResponse` DEBE validar un arreglo JSON de nivel superior cuyos elementos
son `SearchResult` (`chunk_id`, `manual`, `text`, `score`), incluido el arreglo
vacío `[]`.

## R30
SI `SearchResult.score` es menor que -1 o mayor que 1 ENTONCES el modelo DEBE
lanzar `pydantic.ValidationError`.

## R31
`HandoverRequest` DEBE exigir `case_id`, `contact_id`, `chat_id` (entero),
`reason` y `last_messages` (lista de `LastMessage`).

## R32
SI `HandoverRequest.reason` no es `no_relevant_chunks`, `user_request` ni
`invalid_answer` ENTONCES el modelo DEBE lanzar `pydantic.ValidationError`.

## R33
SI `HandoverRequest.last_messages` tiene más de `MAX_LAST_MESSAGES` (10)
elementos ENTONCES el modelo DEBE lanzar `pydantic.ValidationError`.

## R34
SI `LastMessage.role` no es `user`, `bot` ni `advisor` ENTONCES el modelo DEBE
lanzar `pydantic.ValidationError`.

## R35
`HandoverResponse` DEBE exigir `status` (`notified` o `no_advisors`) y
`case_id`.

## R36
`CaseReplyRequest` DEBE exigir `advisor_id` y `text`.

## R37
SI `ManualUploadRequest.name` está vacío o supera `MAX_MANUAL_NAME_LENGTH` (200)
caracteres ENTONCES el modelo DEBE lanzar `pydantic.ValidationError`.

## R38
SI `ManualUploadResponse.chunks` es menor que 1 ENTONCES el modelo DEBE lanzar
`pydantic.ValidationError`.

## R39
`CaseCloseRequest` DEBE exigir `advisor_id`.

## R40
SI `CaseCloseResponse.status` no es `closed` ENTONCES el modelo DEBE lanzar
`pydantic.ValidationError`.

## R41
`CheckTimeoutsRequest` DEBE validar el objeto vacío `{}`.

## R42
`CheckTimeoutsResponse` DEBE exigir `timed_out_cases` como lista de
identificadores, incluida la lista vacía `[]`.

## R43
SI `ErrorResponse.error` no cumple la expresión `^[a-z][a-z0-9_]*$` o
`ErrorResponse.message` está vacío ENTONCES el modelo DEBE lanzar
`pydantic.ValidationError`.

## R44
SI `HealthResponse.status` no es `ok` o `HealthResponse.service` está vacío
ENTONCES el modelo DEBE lanzar `pydantic.ValidationError`.

## R45
El paquete `lazaro_contracts` DEBE exportar las constantes
`SERVICE_TOKEN_HEADER = "X-Service-Token"`, `MAX_TEXT_LENGTH = 4096`,
`MAX_LAST_MESSAGES = 10`, `MAX_TOP_K = 20`, `MAX_IDENTIFIER_LENGTH = 64` y
`MAX_MANUAL_NAME_LENGTH = 200`.

## R46
Los módulos de `contracts/lazaro_contracts/` NO DEBEN importar módulos que no
sean de la biblioteca estándar, `pydantic` o el propio `lazaro_contracts`.

---

## C. Ejemplos `contracts/examples/`

## R47
`contracts/examples/` DEBE contener al menos un archivo `.json` por cada modelo
de R16 excepto `SearchResult` y `LastMessage` (que se cubren anidados en
`search_response.json` y `handover_request.json`).

## R48
Cada archivo `.json` de `contracts/examples/` DEBE validar sin errores con
`model_validate_json` del modelo que le asigna el mapa `EXAMPLES` de
`contracts/tests/test_examples.py`.

## R49
SI existe en `contracts/examples/` un archivo `.json` que no figura en el mapa
`EXAMPLES` ENTONCES la suite de tests de contratos DEBE fallar.

---

## D. Dependencias

## R50
`contracts/requirements.txt` DEBE contener exactamente una dependencia, en la
línea `pydantic>=2.12,<3`.

## R51
`requirements-dev.txt` DEBE incluir la línea `-r contracts/requirements.txt`.

---

## E. Añadidos (ids estables, no renumerar)

## R52
CUANDO un objeto validado con `SearchRequest` no incluye `category`, el modelo
DEBE dejar `category` con el valor `None`.

---

## Cobertura del `acceptance` de `feature_list.json`

| # | Criterio de aceptación (resumen) | Requirements |
|---|----------------------------------|--------------|
| 1 | `CONTRATOS.md` con las 8 rutas; para cada una: servicio, llamante, campos con tipo y obligatoriedad, respuestas y errores | R1, R2, R3, R4, R5, R6, R7, R8 |
| 2 | Reglas comunes: `X-Service-Token`, `{error, message}`, id único por mensaje, `GET /health` | R9, R10, R11, R12 |
| 3 | Paquete `lazaro_contracts` con un modelo Pydantic v2 por request y response + `ErrorResponse` | R16, R17, R18, R20–R46, R52 |
| 4 | `contracts/examples/` con al menos un JSON válido por request y response | R47, R48, R49 |
| 5 | `contracts/tests/` valida cada ejemplo y rechaza un ejemplo sin campo obligatorio | R48, R19 |
| 6 | `contracts/requirements.txt` con pydantic acotado a v2 | R50, R51 |
| 7 | Supuesto (confirmar): `/manuals` multipart; `last_messages` = últimos 10 `{role, text, at}` | R13, R14, R15, R33, R34, R37 |
