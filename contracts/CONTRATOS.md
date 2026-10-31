# Contratos entre servicios

> Versión 1 (versión mínima del chatbot). Fuente de verdad: los modelos Pydantic
> del paquete `lazaro_contracts`; este documento es su versión legible y los tests
> de `contracts/tests/` comprueban que ambos coinciden.

- Todas las rutas son HTTP + JSON en UTF-8 (salvo `POST /manuals`, que es
  `multipart/form-data`, ver supuesto S1).
- Las fechas van en ISO 8601 **con zona horaria** (p. ej. `2026-10-30T19:05:00Z`);
  una fecha sin zona se rechaza con `422 validation_error`.
- Los identificadores (`case_id`, `contact_id`, `advisor_id`, `chunk_id`,
  `manual_id`) son texto de 1 a 64 caracteres. Los ids de Telegram
  (`update_id`, `telegram_user_id`, `chat_id`) son enteros.
- Los textos de mensajes (`text`) tienen de 1 a 4096 caracteres.
- Un campo no declarado en el modelo se rechaza con `422 validation_error`.

## Reglas comunes

### Autenticación

Toda ruta del contrato exige el encabezado `X-Service-Token` (constante
`SERVICE_TOKEN_HEADER`) con un valor igual a la variable de entorno
`SERVICE_TOKEN`. Si falta o no coincide, la respuesta es `401` con
`error` = `unauthorized`.

Excepciones (no piden token):

- `GET /health` de cada servicio.
- El webhook de Telegram del `telegram_gateway` (lo llama Telegram, que no conoce
  el token; su protección la fija la feature del gateway).

### Errores

Todo error tiene la forma `{"error": "<codigo>", "message": "<texto>"}` (modelo
`ErrorResponse`). `error` es un código en `snake_case` (`^[a-z][a-z0-9_]*$`) y
`message` un texto no vacío para personas. Nunca se devuelve el stack trace.

| HTTP | `error`              | Dónde | Cuándo |
|------|----------------------|-------|--------|
| 401  | `unauthorized`       | todas las rutas del contrato | falta `X-Service-Token` o no coincide con `SERVICE_TOKEN` |
| 422  | `validation_error`   | todas | el cuerpo no valida contra el modelo (el servicio sustituye la respuesta 422 por defecto de FastAPI por `{error, message}`) |
| 404  | `not_found`          | `/cases/{id}/reply`, `/cases/{id}/close` | el caso no existe |
| 409  | `case_closed`        | `/cases/{id}/assign` | el caso está cerrado (S11) |
| 415  | `unsupported_format` | `/manuals` | el archivo no es PDF ni DOCX |
| 422  | `empty_document`     | `/manuals` | archivo vacío o sin texto extraíble |
| 502  | `telegram_error`     | `/send` | la API de Telegram falla |
| 502  | `upstream_error`     | `/cases/{id}/reply` | la llamada a `POST /send` del gateway falla |
| 500  | `internal_error`     | todas | error inesperado; nunca se devuelve el stack trace |

### Mensajes repetidos

`update_id` (el id que Telegram asigna a cada actualización) es el
identificador único por mensaje. El orquestador guarda los `update_id` ya
vistos; ante un `update_id` ya visto responde `202` con `status` = `duplicate`
sin reprocesar el mensaje (no busca, no responde, no crea casos).

### Salud

Los 4 servicios (`telegram_gateway`, `orchestrator`, `rag`, `handover`) exponen
`GET /health` sin token. Respuesta `200` con
`{"status": "ok", "service": "<nombre>"}` (modelo `HealthResponse`), donde
`<nombre>` es el nombre del servicio.

## Rutas

### POST /messages

- **Expone:** orchestrator
- **Llama:** telegram_gateway (por cada mensaje de texto recibido en el webhook)
- **Modelos:** `MessageRequest` → `MessageResponse`

#### Request

| Campo | Tipo | Obligatorio | Descripción |
|-------|------|-------------|-------------|
| `update_id` | entero ≥ 0 | sí | id único de la actualización de Telegram; sirve para descartar repetidos |
| `telegram_user_id` | entero | sí | id de Telegram del cliente |
| `chat_id` | entero | sí | chat al que se responde |
| `text` | texto (1–4096) | sí | texto del mensaje del cliente |
| `received_at` | fecha ISO 8601 con zona | sí | momento en que el gateway recibió el mensaje |

#### Respuesta

`202 Accepted`

| Campo | Tipo | Obligatorio | Descripción |
|-------|------|-------------|-------------|
| `status` | `accepted` \| `duplicate` | sí | `accepted` si se procesa; `duplicate` si el `update_id` ya se vio |

#### Errores

| HTTP | error | Cuándo |
|------|-------|--------|
| 401 | unauthorized | falta `X-Service-Token` o no es válido |
| 422 | validation_error | el cuerpo no valida contra `MessageRequest` |
| 500 | internal_error | error inesperado |

### POST /send

- **Expone:** telegram_gateway
- **Llama:** orchestrator, handover (avisos a asesores y aviso de vencimiento al cliente)
- **Modelos:** `SendRequest` → `SendResponse`

#### Request

| Campo | Tipo | Obligatorio | Descripción |
|-------|------|-------------|-------------|
| `chat_id` | entero | sí | chat de Telegram de destino |
| `text` | texto (1–4096) | sí | texto a enviar |

#### Respuesta

`200 OK`

| Campo | Tipo | Obligatorio | Descripción |
|-------|------|-------------|-------------|
| `sent` | `true` | sí | siempre `true`; si el envío falla se responde con error |

#### Errores

| HTTP | error | Cuándo |
|------|-------|--------|
| 401 | unauthorized | falta `X-Service-Token` o no es válido |
| 422 | validation_error | el cuerpo no valida contra `SendRequest` |
| 502 | telegram_error | la API de Telegram falla |
| 500 | internal_error | error inesperado |

### POST /search

- **Expone:** rag
- **Llama:** orchestrator (y la evaluación, feature 8)
- **Modelos:** `SearchRequest` → `SearchResponse` (elementos `SearchResult`)

#### Request

| Campo | Tipo | Obligatorio | Descripción |
|-------|------|-------------|-------------|
| `query` | texto (1–4096) | sí | pregunta del cliente |
| `top_k` | entero (1–20) | sí | máximo de fragmentos a devolver |
| `category` | identificador o `null` | no | categoría del manual; por defecto `null`, RAG la ignora por ahora (S7) |

#### Respuesta

`200 OK`. El cuerpo es un **arreglo JSON** de nivel superior (S10) con los
fragmentos que superan el umbral de similitud, ordenados de mayor a menor
`score`; puede ser el arreglo vacío `[]`. Cada elemento (`SearchResult`):

| Campo | Tipo | Obligatorio | Descripción |
|-------|------|-------------|-------------|
| `chunk_id` | identificador | sí | id del fragmento |
| `manual` | texto (1–200) | sí | nombre del manual de origen |
| `text` | texto | sí | contenido del fragmento |
| `score` | número (-1 a 1) | sí | similitud con la consulta |

#### Errores

| HTTP | error | Cuándo |
|------|-------|--------|
| 401 | unauthorized | falta `X-Service-Token` o no es válido |
| 422 | validation_error | el cuerpo no valida contra `SearchRequest` |
| 500 | internal_error | error inesperado |

### POST /handover

- **Expone:** handover
- **Llama:** orchestrator
- **Modelos:** `HandoverRequest` → `HandoverResponse`

#### Request

| Campo | Tipo | Obligatorio | Descripción |
|-------|------|-------------|-------------|
| `case_id` | identificador | sí | caso propuesto por el orquestador (S3) |
| `contact_id` | identificador | sí | contacto del cliente |
| `chat_id` | entero | sí | chat del cliente, para avisarle si vence la espera (S4) |
| `reason` | `no_relevant_chunks` \| `user_request` \| `invalid_answer` | sí | motivo del traspaso (S5) |
| `last_messages` | lista de `LastMessage` (máx. 10) | sí | últimos mensajes en orden cronológico (S2) |

Cada elemento de `last_messages` (`LastMessage`):

| Campo | Tipo | Obligatorio | Descripción |
|-------|------|-------------|-------------|
| `role` | `user` \| `bot` \| `advisor` | sí | quién escribió el mensaje |
| `text` | texto (1–4096) | sí | texto del mensaje |
| `at` | fecha ISO 8601 con zona | sí | momento del mensaje |

#### Respuesta

`200 OK`

| Campo | Tipo | Obligatorio | Descripción |
|-------|------|-------------|-------------|
| `status` | `notified` \| `no_advisors` | sí | `notified` si se avisó a algún asesor; `no_advisors` si no hay asesores |
| `case_id` | identificador | sí | caso efectivo: el nuevo o el abierto que se reutilizó (S3) |

#### Errores

| HTTP | error | Cuándo |
|------|-------|--------|
| 401 | unauthorized | falta `X-Service-Token` o no es válido |
| 422 | validation_error | el cuerpo no valida contra `HandoverRequest` |
| 500 | internal_error | error inesperado |

### POST /cases/{id}/reply

- **Expone:** orchestrator
- **Llama:** asesor (herramienta interna con token; panel de asesores en el futuro)
- **Modelos:** `CaseReplyRequest` → `CaseReplyResponse`

`{id}` es el `case_id` (identificador, 1–64 caracteres).

#### Request

| Campo | Tipo | Obligatorio | Descripción |
|-------|------|-------------|-------------|
| `advisor_id` | identificador | sí | asesor que responde (S6) |
| `text` | texto (1–4096) | sí | respuesta que se reenvía al cliente |

#### Respuesta

`200 OK`

| Campo | Tipo | Obligatorio | Descripción |
|-------|------|-------------|-------------|
| `sent` | `true` | sí | siempre `true`; si el reenvío falla se responde con error |

#### Errores

| HTTP | error | Cuándo |
|------|-------|--------|
| 401 | unauthorized | falta `X-Service-Token` o no es válido |
| 422 | validation_error | el cuerpo no valida contra `CaseReplyRequest` |
| 404 | not_found | el caso no existe |
| 502 | upstream_error | la llamada a `POST /send` del gateway falla |
| 500 | internal_error | error inesperado |

### POST /manuals

- **Expone:** rag
- **Llama:** `scripts/cargar_manual.py` (panel de administración en el futuro)
- **Modelos:** `ManualUploadRequest` → `ManualUploadResponse`

#### Request

`multipart/form-data` (S1). El modelo `ManualUploadRequest` solo valida la parte
`name`, porque un archivo binario no se representa en JSON.

| Campo | Tipo | Obligatorio | Descripción |
|-------|------|-------------|-------------|
| `file` | archivo (PDF o DOCX) | sí | manual a cargar |
| `name` | texto (1–200) | sí | nombre legible del manual |

#### Respuesta

`201 Created`

| Campo | Tipo | Obligatorio | Descripción |
|-------|------|-------------|-------------|
| `manual_id` | identificador | sí | id del manual cargado |
| `chunks` | entero ≥ 1 | sí | número de fragmentos indexados |

#### Errores

| HTTP | error | Cuándo |
|------|-------|--------|
| 401 | unauthorized | falta `X-Service-Token` o no es válido |
| 422 | validation_error | falta una parte o `name` no es válido |
| 415 | unsupported_format | el archivo no es PDF ni DOCX |
| 422 | empty_document | archivo vacío o sin texto extraíble |
| 500 | internal_error | error inesperado |

### POST /cases/{id}/close

- **Expone:** handover
- **Llama:** asesor (herramienta interna con token; panel en el futuro)
- **Modelos:** `CaseCloseRequest` → `CaseCloseResponse`

`{id}` es el `case_id` (identificador, 1–64 caracteres). Cerrar un caso ya
cerrado responde igual, `200` con `status` = `closed` (S8).

#### Request

| Campo | Tipo | Obligatorio | Descripción |
|-------|------|-------------|-------------|
| `advisor_id` | identificador | sí | asesor que cierra el caso |

#### Respuesta

`200 OK`

| Campo | Tipo | Obligatorio | Descripción |
|-------|------|-------------|-------------|
| `status` | `closed` | sí | siempre `closed` |
| `case_id` | identificador | sí | caso cerrado |

#### Errores

| HTTP | error | Cuándo |
|------|-------|--------|
| 401 | unauthorized | falta `X-Service-Token` o no es válido |
| 422 | validation_error | el cuerpo no valida contra `CaseCloseRequest` |
| 404 | not_found | el caso no existe |
| 500 | internal_error | error inesperado |

### POST /cases/check-timeouts

- **Expone:** handover
- **Llama:** worker o cron
- **Modelos:** `CheckTimeoutsRequest` → `CheckTimeoutsResponse`

Marca como vencidos los casos cuya espera supera `HANDOVER_TIMEOUT_SECONDS` y
avisa a sus clientes.

#### Request

El cuerpo es el objeto vacío `{}`.

| Campo | Tipo | Obligatorio | Descripción |
|-------|------|-------------|-------------|
| (sin campos) | — | — | — |

#### Respuesta

`200 OK`

| Campo | Tipo | Obligatorio | Descripción |
|-------|------|-------------|-------------|
| `timed_out_cases` | lista de identificadores | sí | casos marcados como vencidos en esta llamada; puede ser `[]` |

#### Errores

| HTTP | error | Cuándo |
|------|-------|--------|
| 401 | unauthorized | falta `X-Service-Token` o no es válido |
| 422 | validation_error | el cuerpo no es `{}` |
| 500 | internal_error | error inesperado |

### POST /cases/{id}/assign

- **Expone:** handover
- **Llama:** orchestrator (al reenviar la respuesta de un asesor con `POST /cases/{id}/reply`)
- **Modelos:** `CaseAssignRequest` → `CaseAssignResponse`

`{id}` es el `case_id` (identificador, 1–64 caracteres). Asignar un caso ya
`assigned` responde igual, `200` con `status` = `assigned`, sin cambiar el asesor
asignado; asignar un caso `closed` responde `409` con `error` = `case_closed`
(S11).

#### Request

| Campo | Tipo | Obligatorio | Descripción |
|-------|------|-------------|-------------|
| `advisor_id` | identificador | sí | asesor al que se asigna el caso (S6) |

#### Respuesta

`200 OK`

| Campo | Tipo | Obligatorio | Descripción |
|-------|------|-------------|-------------|
| `status` | `assigned` | sí | siempre `assigned` |
| `case_id` | identificador | sí | caso asignado |

#### Errores

| HTTP | error | Cuándo |
|------|-------|--------|
| 401 | unauthorized | falta `X-Service-Token` o no es válido |
| 422 | validation_error | el cuerpo no valida contra `CaseAssignRequest` |
| 404 | not_found | el caso no existe |
| 409 | case_closed | el caso está cerrado (S11) |
| 500 | internal_error | error inesperado |

## Supuestos a confirmar

Decisiones tomadas sin confirmación humana. Cambiar cualquiera es un cambio de
contrato.

| Id | Supuesto | Valor por defecto |
|----|----------|-------------------|
| S1 | `POST /manuals` es `multipart/form-data` con las partes `file` (archivo) y `name` (texto) | — |
| S2 | `last_messages` de `POST /handover` son como máximo los últimos 10 mensajes, en orden cronológico (más antiguo primero), como lista de `{role, text, at}` con `role` ∈ `user`, `bot`, `advisor` | `MAX_LAST_MESSAGES = 10` |
| S3 | `case_id` lo genera el orquestador (texto, p. ej. UUID). Si el contacto ya tiene un caso abierto, handover lo reutiliza y devuelve en `HandoverResponse.case_id` el caso efectivo | — |
| S4 | `HandoverRequest` añade `chat_id` para que handover pueda avisar al cliente al vencer la espera | — |
| S5 | `reason` ∈ `no_relevant_chunks`, `user_request`, `invalid_answer` (este último reservado para la feature 6) | — |
| S6 | `advisor_id` es texto; en la versión mínima contiene el chat_id del asesor (de `ADVISOR_CHAT_IDS`) en decimal | — |
| S7 | `category` de `POST /search` es opcional y RAG la ignora hasta que exista el clasificador | `null` |
| S8 | Cerrar un caso ya cerrado es idempotente: `200` con `status` = `closed` | — |
| S9 | Límites: texto ≤ 4096 (límite de `sendMessage` de Telegram), `top_k` ≤ 20, identificadores ≤ 64, nombre de manual ≤ 200 | `MAX_TEXT_LENGTH`, `MAX_TOP_K`, `MAX_IDENTIFIER_LENGTH`, `MAX_MANUAL_NAME_LENGTH` |
| S10 | La respuesta de `POST /search` es un arreglo JSON de nivel superior | — |
| S11 | Asignar con `POST /cases/{id}/assign` un caso ya `assigned` responde `200` con `status` = `assigned` sin cambiar el asesor asignado; asignar un caso `closed` responde `409` con `error` = `case_closed` | — |
