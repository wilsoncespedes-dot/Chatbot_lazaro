# Design — contratos_servicios (feature #1)

> Cómo se construye lo pedido en `requirements.md`. Apoyado en
> `docs/architecture.md` (§1 mapa, §3 principios 1, 2, 6, 7, 8) y
> `docs/conventions.md`. Redactado en modo nocturno: cada decisión no cubierta
> por los documentos está listada como supuesto `S<n>` en §9.

## 1. Alcance

- Solo se crean archivos bajo `contracts/` y se añade una línea a
  `requirements-dev.txt`.
- No se toca `services/`, `eval/`, `scripts/`, `docker-compose.yml` ni `.github/`.
- No se añaden variables de entorno (ver §9, «Por qué no hay variables de entorno nuevas»).
- El paquete no se empaqueta (sin `pyproject.toml`): en los tests se importa
  gracias al `conftest.py` raíz, que ya añade `contracts/` a `sys.path`. Cómo
  llega `lazaro_contracts` a las imágenes Docker lo decide la feature 2
  (esqueleto_servicios).
- Compatibilidad: el código DEBE funcionar en Python 3.12 (`docs/architecture.md`
  §2) aunque el `.venv` local sea 3.14. Nada de sintaxis exclusiva de 3.13+.

## 2. Archivos

| Acción  | Ruta | Contenido |
|---------|------|-----------|
| crear   | `contracts/requirements.txt` | una línea: `pydantic>=2.12,<3` |
| crear   | `contracts/CONTRATOS.md` | documento legible (estructura en §5) |
| crear   | `contracts/lazaro_contracts/__init__.py` | reexporta modelos y constantes; define `__all__` |
| crear   | `contracts/lazaro_contracts/common.py` | `ContractModel`, tipos `Identifier`, `MessageText`, `AwareDatetime`, constantes, `ErrorResponse`, `HealthResponse` |
| crear   | `contracts/lazaro_contracts/messages.py` | `/messages` y `/send` |
| crear   | `contracts/lazaro_contracts/search.py` | `/search` |
| crear   | `contracts/lazaro_contracts/manuals.py` | `/manuals` |
| crear   | `contracts/lazaro_contracts/cases.py` | `/handover`, `/cases/{id}/reply`, `/cases/{id}/close`, `/cases/check-timeouts` |
| crear   | `contracts/examples/*.json` | 21 ejemplos (lista en §6) |
| crear   | `contracts/tests/test_examples.py` | mapa `EXAMPLES`, validación de ejemplos, cobertura |
| crear   | `contracts/tests/test_models.py` | campos obligatorios, extra, límites, enums |
| crear   | `contracts/tests/test_contratos_doc.py` | estructura de `CONTRATOS.md` |
| crear   | `contracts/tests/test_packaging.py` | requirements, constantes, imports permitidos |
| modificar | `requirements-dev.txt` | añadir `-r contracts/requirements.txt` (R51) |

Los módulos se nombran por tema y no por servicio (`cases.py`, no `handover.py`)
para no confundirlos con los paquetes `orchestrator`, `handover`, etc. que el
`conftest.py` raíz pone en `sys.path`.

## 3. Firmas nuevas

Estilo de `docs/conventions.md` (docstring de una línea, `from __future__ import
annotations`, comillas dobles). Esbozo **normativo** de tipos y límites; el
implementer puede añadir docstrings y `Field(description=...)`.

```python
# contracts/lazaro_contracts/common.py
from typing import Annotated, Literal
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StringConstraints

SERVICE_TOKEN_HEADER = "X-Service-Token"
MAX_TEXT_LENGTH = 4096          # S9: límite de sendMessage de Telegram
MAX_LAST_MESSAGES = 10          # S2
MAX_TOP_K = 20                  # S9
MAX_IDENTIFIER_LENGTH = 64      # S9
MAX_MANUAL_NAME_LENGTH = 200    # S9

Identifier = Annotated[str, StringConstraints(min_length=1, max_length=MAX_IDENTIFIER_LENGTH)]
MessageText = Annotated[str, StringConstraints(min_length=1, max_length=MAX_TEXT_LENGTH)]

class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid")          # R18

class ErrorResponse(ContractModel):
    error: Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9_]*$")]
    message: Annotated[str, StringConstraints(min_length=1)]

class HealthResponse(ContractModel):
    status: Literal["ok"]
    service: Annotated[str, StringConstraints(min_length=1)]
```

```python
# contracts/lazaro_contracts/messages.py
class MessageRequest(ContractModel):       # POST /messages (orchestrator)
    update_id: Annotated[int, Field(ge=0)]
    telegram_user_id: int
    chat_id: int
    text: MessageText
    received_at: AwareDatetime

class MessageResponse(ContractModel):      # 202
    status: Literal["accepted", "duplicate"]

class SendRequest(ContractModel):          # POST /send (telegram_gateway)
    chat_id: int
    text: MessageText

class SendResponse(ContractModel):         # 200
    sent: Literal[True]
```

```python
# contracts/lazaro_contracts/search.py
class SearchRequest(ContractModel):        # POST /search (rag)
    query: Annotated[str, StringConstraints(min_length=1, max_length=MAX_TEXT_LENGTH)]
    top_k: Annotated[int, Field(ge=1, le=MAX_TOP_K)]
    category: Identifier | None = None     # S7

class SearchResult(ContractModel):
    chunk_id: Identifier
    manual: Annotated[str, StringConstraints(min_length=1, max_length=MAX_MANUAL_NAME_LENGTH)]
    text: Annotated[str, StringConstraints(min_length=1)]
    score: Annotated[float, Field(ge=-1.0, le=1.0)]

class SearchResponse(RootModel[list[SearchResult]]):   # 200, arreglo de nivel superior (S10)
    pass
```

```python
# contracts/lazaro_contracts/manuals.py
class ManualUploadRequest(ContractModel):  # POST /manuals (rag), partes de texto del multipart (S1)
    name: Annotated[str, StringConstraints(min_length=1, max_length=MAX_MANUAL_NAME_LENGTH)]

class ManualUploadResponse(ContractModel): # 201
    manual_id: Identifier
    chunks: Annotated[int, Field(ge=1)]
```

```python
# contracts/lazaro_contracts/cases.py
HandoverReason = Literal["no_relevant_chunks", "user_request", "invalid_answer"]   # S5

class LastMessage(ContractModel):
    role: Literal["user", "bot", "advisor"]
    text: MessageText
    at: AwareDatetime

class HandoverRequest(ContractModel):      # POST /handover (handover)
    case_id: Identifier                    # S3
    contact_id: Identifier
    chat_id: int                           # S4
    reason: HandoverReason
    last_messages: Annotated[list[LastMessage], Field(max_length=MAX_LAST_MESSAGES)]

class HandoverResponse(ContractModel):     # 200
    status: Literal["notified", "no_advisors"]
    case_id: Identifier                    # S3: caso efectivo (nuevo o reutilizado)

class CaseReplyRequest(ContractModel):     # POST /cases/{id}/reply (orchestrator)
    advisor_id: Identifier                 # S6
    text: MessageText

class CaseReplyResponse(ContractModel):    # 200
    sent: Literal[True]

class CaseCloseRequest(ContractModel):     # POST /cases/{id}/close (handover)
    advisor_id: Identifier

class CaseCloseResponse(ContractModel):    # 200
    status: Literal["closed"]
    case_id: Identifier

class CheckTimeoutsRequest(ContractModel): # POST /cases/check-timeouts (handover), cuerpo {}
    pass

class CheckTimeoutsResponse(ContractModel):  # 200
    timed_out_cases: list[Identifier]
```

`__init__.py` reexporta los 20 modelos de R16 y las 6 constantes de R45 en
`__all__` (más `ContractModel`, `Identifier`, `MessageText`, `HandoverReason`,
que también pueden usarse en los servicios).

`SearchResponse` es un `RootModel`: R18 (campos extra) se comprueba en sus
elementos `SearchResult`, y R17 se cumple porque `RootModel` hereda de
`BaseModel`.

Validación en tests: siempre con `Model.model_validate_json(texto)` (modo JSON:
convierte cadenas ISO 8601 en `datetime`). No se usa `strict=True` (ver §7).

## 4. Errores y excepciones

No se añaden excepciones Python: la validación lanza `pydantic.ValidationError`.
Los servicios convierten errores a `ErrorResponse` (feature 2 y siguientes).
Tabla de códigos que `CONTRATOS.md` debe incluir (R10):

| HTTP | `error`              | Dónde | Cuándo |
|------|----------------------|-------|--------|
| 401  | `unauthorized`       | todas las rutas del contrato | falta `X-Service-Token` o no coincide con `SERVICE_TOKEN` |
| 422  | `validation_error`   | todas | el cuerpo no valida contra el modelo (el servicio sustituye la respuesta 422 por defecto de FastAPI por `{error, message}`) |
| 404  | `not_found`          | `/cases/{id}/reply`, `/cases/{id}/close` | el caso no existe |
| 415  | `unsupported_format` | `/manuals` | el archivo no es PDF ni DOCX |
| 422  | `empty_document`     | `/manuals` | archivo vacío o sin texto extraíble |
| 502  | `telegram_error`     | `/send` | la API de Telegram falla |
| 502  | `upstream_error`     | `/cases/{id}/reply` | la llamada a `POST /send` del gateway falla |
| 500  | `internal_error`     | todas | error inesperado; nunca se devuelve el stack trace |

## 5. Estructura de `CONTRATOS.md`

Fija, para que `test_contratos_doc.py` pueda comprobarla (R1–R15):

```markdown
# Contratos entre servicios
(intro: versión, HTTP + JSON, UTF-8, fechas ISO 8601 con zona, ids como texto)

## Reglas comunes
### Autenticación          → X-Service-Token = SERVICE_TOKEN, 401 unauthorized, excepciones (R9)
### Errores                → forma {"error", "message"}, ErrorResponse, tabla §4 (R10)
### Mensajes repetidos     → update_id, 202 + status "duplicate" (R11)
### Salud                  → GET /health en los 4 servicios, HealthResponse (R12)

## Rutas
### POST /messages
- **Expone:** orchestrator
- **Llama:** telegram_gateway
- **Modelos:** `MessageRequest` → `MessageResponse`
#### Request
| Campo | Tipo | Obligatorio | Descripción |
#### Respuesta
`202 Accepted` + tabla Campo | Tipo | Obligatorio | Descripción
#### Errores
| HTTP | error | Cuándo |
(… una sección igual por ruta …)

## Supuestos a confirmar
S1 … S10 (copiados de design.md §9)
```

Contenido por ruta:

| Ruta | Expone | Llama | Modelos | Éxito | Errores propios |
|------|--------|-------|---------|-------|-----------------|
| `POST /messages` | orchestrator | telegram_gateway | `MessageRequest` → `MessageResponse` | 202 | — |
| `POST /send` | telegram_gateway | orchestrator, handover (avisos a asesores y aviso de vencimiento al cliente) | `SendRequest` → `SendResponse` | 200 | 502 `telegram_error` |
| `POST /search` | rag | orchestrator (y la evaluación, feature 8) | `SearchRequest` → `SearchResponse` (elementos `SearchResult`) | 200 | — |
| `POST /handover` | handover | orchestrator | `HandoverRequest` → `HandoverResponse` | 200 | — |
| `POST /cases/{id}/reply` | orchestrator | asesor (herramienta interna con token; panel de asesores en el futuro) | `CaseReplyRequest` → `CaseReplyResponse` | 200 | 404 `not_found`, 502 `upstream_error` |
| `POST /manuals` | rag | `scripts/cargar_manual.py` (panel de administración en el futuro) | `ManualUploadRequest` → `ManualUploadResponse` | 201 | 415 `unsupported_format`, 422 `empty_document` |
| `POST /cases/{id}/close` | handover | asesor (herramienta interna con token; panel en el futuro) | `CaseCloseRequest` → `CaseCloseResponse` | 200 | 404 `not_found` |
| `POST /cases/check-timeouts` | handover | worker o cron | `CheckTimeoutsRequest` → `CheckTimeoutsResponse` | 200 | — |

`{id}` en las rutas de casos es un `Identifier` (texto de 1 a 64 caracteres).
En `POST /manuals` la tabla `#### Request` lista dos partes multipart: `file`
(archivo, obligatorio, PDF o DOCX) y `name` (texto, obligatorio); el modelo
`ManualUploadRequest` solo valida `name`, porque un archivo binario no se
representa en JSON. En `POST /cases/check-timeouts` la tabla de request tiene
una fila `(sin campos)` y el cuerpo es `{}`. En `POST /search` la tabla de
respuesta describe un elemento del arreglo (`SearchResult`).

`test_contratos_doc.py` localiza cada sección por su encabezado `### POST …`
hasta el siguiente `###` de igual nivel o `##`, y comprueba: línea `Expone`,
línea `Llama` no vacía, nombres de `Modelos` en `lazaro_contracts.__all__`,
presencia de cada nombre de campo del modelo como celda `` `campo` `` en la
tabla correspondiente, filas de error obligatorias (R7, R8). Las tablas usan el
nombre de campo entre comillas invertidas en la primera columna.

## 6. Ejemplos (`contracts/examples/`)

Un archivo por caso, nombre en `snake_case`:

| Archivo | Modelo |
|---------|--------|
| `message_request.json` | `MessageRequest` |
| `message_response.json` | `MessageResponse` (`accepted`) |
| `message_response_duplicate.json` | `MessageResponse` (`duplicate`) |
| `send_request.json` | `SendRequest` |
| `send_response.json` | `SendResponse` |
| `search_request.json` | `SearchRequest` (con `category` omitido) |
| `search_response.json` | `SearchResponse` (2 resultados) |
| `search_response_empty.json` | `SearchResponse` (`[]`) |
| `handover_request.json` | `HandoverRequest` (con 2–3 `last_messages`) |
| `handover_response.json` | `HandoverResponse` (`notified`) |
| `handover_response_no_advisors.json` | `HandoverResponse` (`no_advisors`) |
| `case_reply_request.json` | `CaseReplyRequest` |
| `case_reply_response.json` | `CaseReplyResponse` |
| `manual_upload_request.json` | `ManualUploadRequest` (solo la parte `name`) |
| `manual_upload_response.json` | `ManualUploadResponse` |
| `case_close_request.json` | `CaseCloseRequest` |
| `case_close_response.json` | `CaseCloseResponse` |
| `check_timeouts_request.json` | `CheckTimeoutsRequest` (`{}`) |
| `check_timeouts_response.json` | `CheckTimeoutsResponse` |
| `error_response.json` | `ErrorResponse` (`unauthorized`) |
| `health_response.json` | `HealthResponse` |

Datos inventados y sin datos personales reales (ids de Telegram ficticios,
fechas `2026-10-30T19:05:00Z`). JSON en UTF-8, indentado con 2 espacios.

`test_examples.py` define `EXAMPLES: dict[str, type[BaseModel]]` (archivo →
modelo) y tres tests: cada ejemplo valida (R48), todo `.json` del directorio
está en `EXAMPLES` (R49), y cada modelo de R16 salvo `SearchResult` y
`LastMessage` aparece como valor de `EXAMPLES` (R47).

`test_models.py` deriva los casos de rechazo de los ejemplos: para cada modelo
con campos obligatorios (`field.is_required()`), quita cada campo del ejemplo y
espera `ValidationError` (R19); añade un campo `"unexpected"` y espera
`ValidationError` (R18); y tests parametrizados de límites y enumerados
(R20–R44, R52). Cada test lleva en su docstring el `R<n>` que cubre.

`test_packaging.py`: lee `contracts/requirements.txt` (R50) y
`requirements-dev.txt` (R51), comprueba las constantes (R45),
`pydantic.VERSION` empieza por `"2."` y cada modelo es subclase de `BaseModel`
(R17), y recorre con `ast` los `.py` de `lazaro_contracts/` comprobando que los
`import` solo son de stdlib (`sys.stdlib_module_names`), `pydantic` (y sus
submódulos) o el propio paquete, con imports relativos o `lazaro_contracts.*`
(R46). `typing_extensions` no se usa: con Python ≥ 3.12 basta `typing`.

## 7. Alternativas descartadas

1. **Respuesta de `/search` envuelta en objeto (`{"results": [...]}`).** Más
   extensible, pero `docs/proyecto.md` §7 y la feature 5 hablan de «una lista»
   y «lista vacía». Se sigue el borrador literal (S10); cambiarlo después es
   una feature de contrato propia.
2. **`extra="ignore"` (lector tolerante).** Facilita evolucionar, pero esconde
   erratas (`chatid` en vez de `chat_id`) que en un equipo principiante son
   probables. Se elige `extra="forbid"`; añadir un campo es un cambio de
   contrato explícito (`docs/architecture.md` §3.2).
3. **`strict=True` en los modelos.** Evitaría que `"123"` se convierta en `123`,
   pero en modo Python rechaza fechas como texto y obliga a cada servicio a
   validar siempre con `model_validate_json`. Se mantiene el modo por defecto
   de Pydantic.
4. **Generar los modelos desde un OpenAPI escrito a mano.** Añade una
   herramienta y un paso de build; el equipo es pequeño. Pydantic es la fuente
   de verdad y `CONTRATOS.md` la versión legible.
5. **Un `pyproject.toml` para instalar `lazaro_contracts` con pip.** No hace
   falta para los tests (lo resuelve `conftest.py`); se decide en la feature 2
   junto con los Dockerfile.

## 8. Dependencias

Línea exacta de `contracts/requirements.txt`:

```
pydantic>=2.12,<3
```

- `pydantic` — licencia MIT. Acotada a v2 (`<3`). Mínimo 2.12 porque es la
  primera serie con soporte oficial de Python 3.14 (el `.venv` local) y
  también soporta 3.12 (Docker/CI).
- `pytest` ya está en `requirements-dev.txt` (`pytest>=8,<9`, MIT). No hace
  falta nada más (no se usa FastAPI ni httpx en esta feature).
- `requirements-dev.txt` gana la línea `-r contracts/requirements.txt` para que
  `pip install -r requirements-dev.txt` deje los tests de contratos listos. Se
  conservan sin cambios las líneas existentes (`pytest>=8,<9` y
  `httpx>=0.27,<1`); solo se añade la nueva.
- `contracts/.gitkeep` no se toca: es inofensivo y ningún criterio de
  aceptación pide borrarlo.

**Estado del entorno:** a 2026-10-30 `pydantic` **no** está instalado en el
`.venv` (solo pytest). Antes de implementar hay que ejecutar, dentro del
proyecto:

```
.venv/Scripts/python.exe -m pip install -r contracts/requirements.txt
```

Es el único paquete que este spec autoriza instalar. Si la instalación se
deniega por permisos o falla, la feature queda `blocked` con el error
(`.claude/nocturno.md` §Dependencias); no se buscan vías alternativas de
instalación.

## 9. Supuestos a confirmar

Ninguno se decide en silencio; todos se copian a `CONTRATOS.md`
§«Supuestos a confirmar» (R13–R15).

| Id | Supuesto | Valor por defecto | Por qué |
|----|----------|-------------------|---------|
| S1 | `POST /manuals` es `multipart/form-data` con partes `file` (archivo) y `name` (texto) | — | Criterio de aceptación «confirmar». Nombres en inglés por `docs/conventions.md` (§7 dice «archivo, nombre») |
| S2 | `last_messages` = como máximo los últimos 10 mensajes, orden cronológico (más antiguo primero), cada uno `{role, text, at}` con `role` ∈ `user`, `bot`, `advisor` | `MAX_LAST_MESSAGES = 10` | Criterio de aceptación «confirmar». Los valores de `role` cubren cliente, bot y asesor |
| S3 | `case_id` lo genera el orquestador (texto, p. ej. UUID). Si el contacto ya tiene un caso abierto, handover lo reutiliza y devuelve en `HandoverResponse.case_id` el caso efectivo | — | §7 pone `case_id` en el request; la feature 7 dice «crea o reutiliza». Devolver el caso efectivo evita que el orquestador se quede con un id que handover no usó |
| S4 | `HandoverRequest` añade `chat_id` (no está en §7) | — | Handover debe avisar al cliente al vencer la espera (feature 7) y no puede leer la base del orquestador (`docs/architecture.md` §3.1) |
| S5 | `reason` ∈ `no_relevant_chunks`, `user_request`, `invalid_answer` | — | Los dos primeros vienen de la feature 4; `invalid_answer` queda reservado para la feature 6 (rechazo con oferta de asesor) |
| S6 | `advisor_id` es texto; en la versión mínima contiene el chat_id del asesor (de `ADVISOR_CHAT_IDS`) en decimal | — | Feature 7 «confirmar»; texto para que el panel de asesores pueda usar otro id sin cambiar el contrato |
| S7 | `category` de `/search` es opcional y RAG la ignora hasta que exista el clasificador | `None` | El clasificador está en `later` (§12: «qué son los servicios técnicos») |
| S8 | Cerrar un caso ya cerrado es idempotente: `200` con `status = "closed"` | — | Principio de idempotencia (`docs/architecture.md` §3.6); la feature 7 no lo fija |
| S9 | Límites: texto ≤ 4096 (límite de `sendMessage` de Telegram), `top_k` ≤ 20, identificadores ≤ 64, nombre de manual ≤ 200 | constantes de R45 | Acotar entradas; ninguna feature fija otros valores |
| S10 | La respuesta de `/search` es un arreglo JSON de nivel superior | — | Literal de §7 (ver alternativa 1) |

Dudas de `docs/proyecto.md` §12 que esta feature roza, sin resolverlas:

- **Audio e imágenes:** el contrato `/messages` solo transporta texto (`text`
  obligatorio). Qué hace el gateway con lo que no es texto lo fija la feature 3.
- **Formatos de manuales:** `/manuals` documenta PDF y DOCX (415 para otros);
  la validación real es de la feature 5.
- **Tiempo de espera del asesor:** `/cases/check-timeouts` no transporta el
  valor; vive en `HANDOVER_TIMEOUT_SECONDS` (ya en `.env.example`, feature 7).
- **Umbral y modelo de embeddings:** `score` solo se acota a [-1, 1]; el umbral
  vive en `RAG_SIMILARITY_THRESHOLD` (feature 5).

**Por qué no hay variables de entorno nuevas:** los límites de S2 y S9 son
parte del contrato y deben ser idénticos en quien envía y quien recibe; si
fueran variables de entorno, dos servicios podrían tener valores distintos y
romperse entre sí. Cambiarlos es un cambio de contrato. Cuántos mensajes manda
de verdad el orquestador (≤ 10) puede ser configurable en la feature 4.

## 10. Observaciones para features posteriores (no se resuelven aquí)

- El estado del caso queda repartido: `assigned` lo marca el orquestador
  (`/cases/{id}/reply`) y `timed_out`/`closed` handover. La feature 7 debe
  decidir quién es el dueño del caso; el contrato no lo impide (S3).
- Qué responde `/cases/{id}/reply` para un caso cerrado o vencido no está en
  ningún criterio; lo fija la feature 7 (posible 409, contrato propio).
- No se fija tamaño máximo de archivo en `/manuals` (ningún criterio lo pide).
