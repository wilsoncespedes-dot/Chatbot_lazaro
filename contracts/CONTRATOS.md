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
| 403  | `forbidden`          | `/cases/{id}/authorize`, `/cases/{id}/reply`, `/cases/{id}/close`, `/cases/{id}/assign` | el asesor no está autorizado para esa acción sobre el caso (S12) |
| 404  | `not_found`          | `/cases/{id}/reply`, `/cases/{id}/close` | el caso no existe |
| 409  | `case_closed`        | `/cases/{id}/assign`, `/cases/{id}/reply` | el caso está cerrado (S11) |
| 415  | `unsupported_format` | `/manuals` | el archivo no es PDF ni DOCX |
| 422  | `empty_document`     | `/manuals` | archivo vacío o sin texto extraíble |
| 502  | `telegram_error`     | `/send` | la API de Telegram falla |
| 502  | `upstream_error`     | `/cases/{id}/reply` | la llamada a `POST /send` del gateway falla |
| 503  | `privacy_not_configured` | `/privacy/purge` | falta `PRIVACY_RETENTION_DAYS` (o, en handover, `PRIVACY_ACTIVE_CASE_MAX_DAYS`); no se borra nada |
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
| 403 | forbidden | el asesor no está autorizado a responder el caso; no se envía nada al cliente (S12) |
| 404 | not_found | el caso no existe |
| 409 | case_closed | el caso está cerrado; no se envía nada al cliente (S12) |
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

### PATCH /chunks/{id}

- **Expone:** rag
- **Llama:** panel de administración (futuro)
- **Modelos:** `ChunkUpdateRequest` → `ChunkUpdateResponse`

`{id}` es el `chunk_id` (identificador, 1–64 caracteres). Reemplaza el texto
completo del fragmento y recalcula su embedding con el proveedor configurado
antes de persistir; conserva `chunk_id`, `manual_id`, manual, orden y estado
activo. El texto no vacío se guarda exactamente como se recibe (R3).

#### Request

| Campo | Tipo | Obligatorio | Descripción |
|-------|------|-------------|-------------|
| `text` | texto no vacío | sí | texto nuevo del fragmento; vacío o solo espacios se rechaza |

#### Respuesta

`200 OK`

| Campo | Tipo | Obligatorio | Descripción |
|-------|------|-------------|-------------|
| `chunk_id` | identificador | sí | id del fragmento editado |
| `manual_id` | identificador | sí | manual al que pertenece el fragmento |
| `manual` | texto (1–200) | sí | nombre del manual |
| `order` | entero ≥ 1 | sí | orden del fragmento dentro del manual |
| `text` | texto | sí | texto nuevo guardado |
| `active` | booleano | sí | estado activo del fragmento, sin cambios |

#### Errores

| HTTP | error | Cuándo |
|------|-------|--------|
| 401 | unauthorized | falta `X-Service-Token` o no es válido |
| 422 | validation_error | el cuerpo no valida contra `ChunkUpdateRequest` |
| 404 | not_found | el fragmento no existe |
| 500 | internal_error | error inesperado |

### GET /manuals

- **Expone:** rag
- **Llama:** orchestrator (panel de administración, #22)
- **Modelos:** `ManualListResponse` (lista de `ManualSummary`)

Devuelve todos los manuales, el más reciente primero, con el número de
fragmentos de cada uno. Sin cuerpo de petición.

#### Request

Sin cuerpo.

#### Respuesta

`200 OK`. El cuerpo es un **arreglo JSON** de nivel superior (S10) con un
elemento por manual (`ManualSummary`); puede ser el arreglo vacío `[]`.

| Campo | Tipo | Obligatorio | Descripción |
|-------|------|-------------|-------------|
| `manual_id` | identificador | sí | id del manual |
| `name` | texto (1–200) | sí | nombre legible del manual |
| `chunks` | entero ≥ 0 | sí | número de fragmentos del manual, activos e inactivos |

#### Errores

| HTTP | error | Cuándo |
|------|-------|--------|
| 401 | unauthorized | falta `X-Service-Token` o no es válido |
| 500 | internal_error | error inesperado |

### GET /manuals/{id}/chunks

- **Expone:** rag
- **Llama:** orchestrator (panel de administración, #22)
- **Modelos:** `ChunkListResponse` (lista de `ChunkItem`)

`{id}` es el `manual_id` (identificador, 1–64 caracteres). Devuelve todos los
fragmentos del manual, activos e inactivos, en orden ascendente de `order`.

#### Request

Sin cuerpo.

#### Respuesta

`200 OK`. El cuerpo es un **arreglo JSON** de nivel superior (S10) con un
elemento por fragmento (`ChunkItem`); puede ser el arreglo vacío `[]`.

| Campo | Tipo | Obligatorio | Descripción |
|-------|------|-------------|-------------|
| `chunk_id` | identificador | sí | id del fragmento |
| `manual_id` | identificador | sí | manual al que pertenece el fragmento |
| `manual` | texto (1–200) | sí | nombre del manual |
| `order` | entero ≥ 1 | sí | orden del fragmento dentro del manual |
| `text` | texto no vacío | sí | contenido del fragmento |
| `active` | booleano | sí | si el fragmento participa en `POST /search` |

#### Errores

| HTTP | error | Cuándo |
|------|-------|--------|
| 401 | unauthorized | falta `X-Service-Token` o no es válido |
| 404 | not_found | el manual no existe |
| 500 | internal_error | error inesperado |

### PATCH /chunks/{id}/active

- **Expone:** rag
- **Llama:** orchestrator (panel de administración, #22)
- **Modelos:** `ChunkActiveRequest` → `ChunkItem`

`{id}` es el `chunk_id` (identificador, 1–64 caracteres). Guarda el estado
activo del fragmento y devuelve el fragmento completo; no cambia su texto,
embedding, manual ni orden. Desactivar un fragmento solo lo saca de
`POST /search`; no lo borra.

#### Request

| Campo | Tipo | Obligatorio | Descripción |
|-------|------|-------------|-------------|
| `active` | booleano JSON | sí | nuevo estado del fragmento; solo se aceptan `true` y `false` |

#### Respuesta

`200 OK`

| Campo | Tipo | Obligatorio | Descripción |
|-------|------|-------------|-------------|
| `chunk_id` | identificador | sí | id del fragmento |
| `manual_id` | identificador | sí | manual al que pertenece el fragmento |
| `manual` | texto (1–200) | sí | nombre del manual |
| `order` | entero ≥ 1 | sí | orden del fragmento dentro del manual |
| `text` | texto no vacío | sí | contenido del fragmento, sin cambios |
| `active` | booleano | sí | estado activo guardado |

#### Errores

| HTTP | error | Cuándo |
|------|-------|--------|
| 401 | unauthorized | falta `X-Service-Token` o no es válido |
| 404 | not_found | el fragmento no existe |
| 422 | validation_error | el cuerpo no valida contra `ChunkActiveRequest` |
| 500 | internal_error | error inesperado |

### POST /cases/{id}/close

- **Expone:** handover
- **Llama:** asesor (herramienta interna con token; panel en el futuro), orchestrator (comando `/cerrar` de un asesor desde Telegram, #16)
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
| 403 | forbidden | el asesor no está autorizado a cerrar el caso; el caso no cambia (S12) |
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
| 403 | forbidden | el asesor no está autorizado sobre el caso; el caso no cambia (S12) |
| 404 | not_found | el caso no existe |
| 409 | case_closed | el caso está cerrado (S11) |
| 500 | internal_error | error inesperado |

### POST /cases/{id}/authorize

- **Expone:** handover
- **Llama:** orchestrator (antes de reenviar la respuesta de un asesor con `POST /cases/{id}/reply` y, con el comando `/cerrar` de un asesor, antes de `POST /cases/{id}/close`)
- **Modelos:** `CaseAuthorizeRequest` → `CaseAuthorizeResponse`

`{id}` es el `case_id` (identificador, 1–64 caracteres). Consulta si el asesor
`advisor_id` puede hacer `action` sobre el caso según las reglas de S12. Si puede,
responde `200` con `allowed` = `true`; si no, responde `403` con `error` =
`forbidden` (nunca `allowed` = `false`). Autorizar sobre un caso `closed` responde
`409` con `error` = `case_closed`.

#### Request

| Campo | Tipo | Obligatorio | Descripción |
|-------|------|-------------|-------------|
| `advisor_id` | identificador | sí | asesor que quiere actuar sobre el caso (S6) |
| `action` | `reply` \| `close` | sí | acción que se quiere autorizar: responder o cerrar |

#### Respuesta

`200 OK`

| Campo | Tipo | Obligatorio | Descripción |
|-------|------|-------------|-------------|
| `allowed` | `true` | sí | siempre `true`; si no está autorizado se responde `403` |
| `case_id` | identificador | sí | caso consultado |

#### Errores

| HTTP | error | Cuándo |
|------|-------|--------|
| 401 | unauthorized | falta `X-Service-Token` o no es válido |
| 422 | validation_error | el cuerpo no valida contra `CaseAuthorizeRequest` |
| 403 | forbidden | el asesor no está autorizado para `action` sobre el caso (S12) |
| 404 | not_found | el caso no existe |
| 409 | case_closed | el caso está cerrado |
| 500 | internal_error | error inesperado |

### POST /cases/{id}/client-message

- **Expone:** handover
- **Llama:** orchestrator (al recibir por `POST /messages` un mensaje de un cliente con caso; S13)
- **Modelos:** `CaseClientMessageRequest` → `CaseClientMessageResponse`

`{id}` es el `case_id` (identificador, 1–64 caracteres). Si el caso está `assigned`,
handover envía el texto al asesor asignado y responde `200` con `status` =
`forwarded`; si el caso existe y no está `assigned`, responde `200` con `status` =
`not_assigned` sin enviar nada (S13).

#### Request

| Campo | Tipo | Obligatorio | Descripción |
|-------|------|-------------|-------------|
| `text` | texto (1–4096) | sí | mensaje del cliente que se reenvía al asesor |
| `at` | fecha ISO 8601 con zona | sí | momento del mensaje del cliente |

#### Respuesta

`200 OK`

| Campo | Tipo | Obligatorio | Descripción |
|-------|------|-------------|-------------|
| `status` | `forwarded` \| `not_assigned` | sí | `forwarded` si se envió al asesor asignado; `not_assigned` si el caso no está `assigned` |
| `case_id` | identificador | sí | caso del mensaje |

#### Errores

| HTTP | error | Cuándo |
|------|-------|--------|
| 401 | unauthorized | falta `X-Service-Token` o no es válido |
| 422 | validation_error | el cuerpo no valida contra `CaseClientMessageRequest` |
| 404 | not_found | el caso no existe |
| 502 | upstream_error | falló el envío al asesor (la llamada a `POST /send` del gateway falla) |
| 500 | internal_error | error inesperado |

### POST /privacy/purge

- **Expone:** orchestrator y handover (cada servicio purga solo su propia base)
- **Llama:** `scripts/purgar_datos.py` (servicio `retention_worker`), en el orden
  fijo **handover → orchestrator**: si la purga de handover no responde `200`,
  no se llama al orchestrator en esa iteración.
- **Modelos:** `PrivacyPurgeRequest` → `PrivacyPurgeResponse`

Borra los datos personales más antiguos que el plazo aprobado
(`PRIVACY_RETENTION_DAYS`). Handover cierra y borra además los casos activos
(`open`, `assigned` o `timed_out`) que superan `PRIVACY_ACTIVE_CASE_MAX_DAYS`
(R35). Los registros operativos necesarios y `privacy_consents` se conservan
(R26, R39).

#### Request

El cuerpo es el objeto vacío `{}`.

| Campo | Tipo | Obligatorio | Descripción |
|-------|------|-------------|-------------|
| (sin campos) | — | — | — |

#### Respuesta

`200 OK`

| Campo | Tipo | Obligatorio | Descripción |
|-------|------|-------------|-------------|
| `cutoff` | fecha ISO 8601 con zona | sí | instante de corte usado en la purga |
| `deleted` | objeto `{tabla: entero}` | sí | filas borradas por tabla en esta llamada |
| `closed_active_cases` | entero ≥ 0 | sí | handover: casos activos cerrados y borrados; orchestrator: `0` |

#### Errores

| HTTP | error | Cuándo |
|------|-------|--------|
| 401 | `unauthorized` | falta `X-Service-Token` o no es válido (R20, R33) |
| 422 | `validation_error` | el cuerpo no es `{}` |
| 503 | `privacy_not_configured` | falta la configuración de retención; no se borra nada (R21, R32) |
| 500 | `internal_error` | error inesperado; la transacción hace rollback |

### GET /cases

- **Expone:** handover
- **Llama:** orchestrator (panel de asesores, #29)
- **Modelos:** `CaseListQuery` → `CaseListResponse` (elementos `CaseListItem`)

Lista de solo lectura de los casos que un asesor puede gestionar según S12 y la
regla de huérfanos (S14). Exige `X-Service-Token`. Un `advisor_id` que no está en
`ADVISOR_CHAT_IDS` recibe `200` con la lista vacía.

#### Request

Los parámetros viajan en la query; un parámetro no declarado se rechaza con
`422 validation_error`.

| Campo | Tipo | Obligatorio | Descripción |
|-------|------|-------------|-------------|
| `advisor_id` | identificador (1–64) | sí | chat_id del asesor que pide el listado (S6) |

#### Respuesta

`200 OK`. El cuerpo es un **arreglo JSON** de nivel superior (S10) con como
máximo `CASE_LIST_LIMIT` casos (por defecto 50, máximo 200), ordenados por
`created_at` ascendente y, a igual `created_at`, por `case_id` ascendente. Cada
elemento (`CaseListItem`):

| Campo | Tipo | Obligatorio | Descripción |
|-------|------|-------------|-------------|
| `case_id` | identificador | sí | caso listado |
| `status` | `open` \| `timed_out` \| `assigned` | sí | estado actual del caso |
| `created_at` | fecha ISO 8601 con zona | sí | fecha de creación del caso |
| `actions` | lista no vacía y sin repetidos de `reply` \| `assign` \| `close` | sí | acciones que el asesor puede hacer hoy (S14) |

#### Errores

| HTTP | error | Cuándo |
|------|-------|--------|
| 401 | unauthorized | falta `X-Service-Token` o no es válido |
| 422 | validation_error | los parámetros de query no validan contra `CaseListQuery` |
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
| S11 | Asignar con `POST /cases/{id}/assign` un caso ya `assigned` responde `200` con `status` = `assigned` sin cambiar el asesor asignado cuando quien asigna es el asesor asignado; si es otro asesor, responde `403` con `error` = `forbidden` sin cambiar el caso (S12, cambio de la #13); asignar un caso `closed` responde `409` con `error` = `case_closed` | — |
| S12 | Autorización de asesores (`POST /cases/{id}/authorize`). Solo son asesores los chat_id de `ADVISOR_CHAT_IDS` (hasta que existan el panel y la verificación de cuentas); un `advisor_id` que no está en `ADVISOR_CHAT_IDS` recibe `403` con `error` = `forbidden`. Responder (`reply`): un caso `open` o `timed_out` lo responde cualquier asesor registrado y la primera respuesta lo asigna; un caso `assigned` solo lo responde el asesor asignado. Cerrar (`close`): un caso `open` o `timed_out` lo cierra cualquier asesor registrado; un caso `assigned` solo lo cierra el asesor asignado, salvo un caso huérfano. Caso huérfano: un caso `assigned` cuyo `advisor_id` es nulo o ya no está en `ADVISOR_CHAT_IDS`. Un caso huérfano lo cierra cualquier asesor registrado: `POST /cases/{id}/close` lo pasa a `closed` y `authorize` con `action` = `close` responde `200` con `allowed` = `true`; cerrarlo no es reasignarlo. Un caso huérfano no lo responde ni lo asigna ningún otro asesor: `POST /cases/{id}/reply` y `authorize` con `action` = `reply` responden `403` con `error` = `forbidden`, y `POST /cases/{id}/assign` responde `403` con `error` = `forbidden` sin modificar el caso, como con cualquier caso asignado a otro asesor. Sin reasignación y sin rol supervisor. Las mismas reglas se aplican en `POST /cases/{id}/reply` (el orquestador responde `403` sin enviar nada al cliente), `POST /cases/{id}/close` y `POST /cases/{id}/assign` (handover responde `403` sin modificar el caso); asignar un caso ya `assigned` (S11) solo responde `200` al asesor asignado y otro asesor recibe `403`. Esto cambia el `200` sin cambios que S11 daba en la #9 a cualquier asesor: el asesor asignado sigue recibiendo `200` sin cambios. Precedencia de errores en `POST /cases/{id}/authorize`, `POST /cases/{id}/close` y `POST /cases/{id}/assign`: `403` (asesor no registrado) → `404` (caso inexistente) → `409` (caso `closed`; en `POST /cases/{id}/close`, `200` sin cambios por S8) → `403` (caso asignado a otro asesor), escalón que no se aplica a `POST /cases/{id}/close` ni a `authorize` con `action` = `close` sobre un caso huérfano (para ellos, superados los tres primeros escalones, el cierre está permitido). En `POST /cases/{id}/reply` el orquestador autoriza antes de comprobar si el caso existe: un `advisor_id` no registrado recibe `403` con `error` = `forbidden` aunque el caso no exista. `POST /cases/{id}/close` sobre un caso `closed` sigue S8: `200` sin cambios para cualquier asesor registrado, aunque no sea el asignado; `authorize` con `action` = `close` sobre un caso `closed` responde `409`. `POST /cases/{id}/reply` sobre un caso `closed` responde `409` con `error` = `case_closed`, sin enviar nada al cliente (el orquestador propaga el `409` de `authorize`). Si handover no está disponible para autorizar, el orquestador falla cerrado: no envía la respuesta y responde `502` con `upstream_error` (la fila `502 upstream_error` ya publicada de `POST /cases/{id}/reply`). La autorización por HTTP con `SERVICE_TOKEN` no impide que un proceso que ya tenga ese token suplante un `advisor_id` registrado; la identidad por persona llega con la #16 (remitente del webhook validado) o con el panel y la verificación de cuentas. Retirada de un asesor: antes de quitar su chat_id de `ADVISOR_CHAT_IDS`, el asesor cierra sus casos; al arrancar, handover registra cuántos casos huérfanos hay, sin sus ids. | — |
| S13 | Solo se reenvían al asesor, con `POST /cases/{id}/client-message`, los mensajes de un cliente cuyo caso está `assigned`; con un caso `open`, con `not_assigned` o con `404` sigue el flujo actual (RAG, rechazo o traspaso). Si el reenvío falla (`502`), el cliente recibe un texto fijo y no se vuelve al RAG. Los comandos de asesor `/responder <case_id> <texto>` y `/cerrar <case_id>` llegan por `POST /messages`, cuyo contrato no cambia; un mensaje de un asesor que no es `/responder` ni `/cerrar` sigue el flujo actual, como el de cualquier cliente. Los comandos se autorizan con las reglas de S12; en ellos el `advisor_id` es el `telegram_user_id` del update validado con `TELEGRAM_WEBHOOK_SECRET`, nunca un id escrito en el texto del mensaje, y la pertenencia a `ADVISOR_CHAT_IDS` se comprueba con ese `telegram_user_id`, no con el `chat_id`; por eso un id de grupo (negativo) de `ADVISOR_CHAT_IDS` no puede usar los comandos. | — |
| S14 | `GET /cases` lista solo los casos que el asesor puede gestionar según S12: `open` y `timed_out` con `actions` = `reply`, `assign`, `close`; `assigned` al solicitante con `actions` = `reply`, `close`; huérfanos (`assigned` con `advisor_id` nulo o fuera de `ADVISOR_CHAT_IDS`) con `actions` = `close`. Nunca incluye casos `closed` ni `assigned` a otro asesor registrado. Orden por `created_at` ascendente y, a igual `created_at`, por `case_id` ascendente. Límite `CASE_LIST_LIMIT` (default 50, máximo 200) aplicado después de filtrar; sin cursor en v1. Un `advisor_id` que no está en `ADVISOR_CHAT_IDS` recibe `200` con la lista vacía, sin registrar denegación. | `CASE_LIST_LIMIT = 50` |
