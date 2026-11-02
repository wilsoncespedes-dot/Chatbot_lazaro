# #22 panel_fragmentos — Design

## Decisión

El panel de #21 llama al RAG desde el servidor con `HttpRagClient` y
`SERVICE_TOKEN`, igual que hoy `search`. El navegador solo ve HTML de `/admin`.
Se reutilizan sin cambios `POST /manuals` y `PATCH /chunks/{id}`; el contrato
crece de forma aditiva con tres rutas. No se usa código externo (no hay carpeta
`referencias/`); todo se apoya en código del propio proyecto.

## Contrato (aditivo)

| Ruta | Request | Respuesta 200 | Errores |
|------|---------|---------------|---------|
| `GET /manuals` | — | `ManualListResponse` = `RootModel[list[ManualSummary]]` | 401, 500 |
| `GET /manuals/{id}/chunks` | — | `ChunkListResponse` = `RootModel[list[ChunkItem]]` | 401, 404 `not_found`, 500 |
| `PATCH /chunks/{id}/active` | `ChunkActiveRequest` | `ChunkItem` | 401, 404 `not_found`, 422 `validation_error`, 500 |

```python
# lazaro_contracts/manuals.py
class ManualSummary(ContractModel):
    manual_id: Identifier
    name: Annotated[str, StringConstraints(min_length=1, max_length=MAX_MANUAL_NAME_LENGTH)]
    chunks: Annotated[int, Field(ge=0)]

# lazaro_contracts/chunks.py
class ChunkItem(ContractModel):          # mismos campos que ChunkUpdateResponse
    chunk_id, manual_id, manual, order, text, active
class ChunkActiveRequest(ContractModel):
    active: StrictBool                   # "true" o 1 → 422 (R7)
```

`ChunkUpdateResponse` no se toca (fila publicada). Ejemplos nuevos en
`contracts/examples/`: `manual_list_response.json`, `chunk_list_response.json`,
`chunk_active_request.json`, `chunk_active_response.json`. Se exportan en
`__init__.py` y se añaden tres secciones nuevas en `CONTRATOS.md`; las secciones
publicadas (incluidas `POST /manuals` y `PATCH /chunks/{id}`) no se editan.

## RAG

| Archivo | Cambio |
|---------|--------|
| `rag/domain.py` | `ManualNotFound(DomainError)` → 404 `not_found`; `list_manuals(repo)`, `list_manual_chunks(manual_id, repo)`, `set_chunk_active(chunk_id, body, repo)`. |
| `rag/adapters/repository.py` | Protocol, Fake y Postgres: `list_manuals() -> list[ManualSummary]` (`ORDER BY created_at DESC, manual_id`; Fake: orden inverso de inserción), `list_chunks(manual_id) -> list[Chunk] \| None` (`None` si el manual no existe; `ORDER BY ord`), `update_active(chunk_id, active) -> Chunk` (`UPDATE … WHERE chunk_id=%s`, `rowcount == 0` → `ChunkNotFound`, luego `SELECT` con `JOIN manuals`, en una transacción, como `update_text`). `set_active` existente no cambia. |
| `rag/main.py` | Tres rutas; el middleware de token existente ya las cubre (R8). |

SQL siempre parametrizado. `update_active` no toca `text` ni `embedding` (R5).

## Orchestrator

| Archivo | Cambio |
|---------|--------|
| `adapters/rag.py` | `RagClient` + `HttpRagClient` + `FakeRagClient`: `list_manuals()`, `list_chunks(manual_id)`, `upload_manual(name, filename, content, content_type) -> ManualUploadResponse`, `update_chunk(chunk_id, text) -> ChunkUpdateResponse`, `set_chunk_active(chunk_id, active) -> ChunkItem`. Ids en la URL con `urllib.parse.quote(id, safe="")`. |
| `domain.py` | `RagRejected(DomainError)` con `status_code` ∈ {404, 415, 422} y `code` del `ErrorResponse` del RAG. Resto de fallos → `ServiceUnavailable` existente (502). |
| `admin.py` | Plantillas `manuals_page`, `manual_chunks_page`, `error_page(status, code)` con `html.escape`; enlace "Manuales" en el `nav` de `render_page`; mensajes fijos por código (R17). |
| `admin_routes.py` | `GET/POST /admin/manuals`, `GET /admin/manuals/{manual_id}`, `POST /admin/chunks/{chunk_id}`, `POST /admin/chunks/{chunk_id}/active`. |
| `config.py` + `.env.example` | `ADMIN_MANUAL_MAX_BYTES`. |
| `requirements.txt` | `python-multipart>=0.0.9,<1` (ver Dependencias). |
| `tests/test_admin_fragmentos.py` (nuevo) | R9–R22 con `FakeRagClient`. |
| `rag/tests/test_list_chunks.py` (nuevo) | R2–R8. |

Orden en cada ruta (igual que #21): sesión (R19) → leer formulario → CSRF (R20) →
validación local (R11, R14, R16) → llamada al RAG → `303` o página de error.
`POST /admin/manuals` lee el multipart con `await request.form()` de Starlette y
comprueba el tamaño del `UploadFile` antes de leerlo entero; si supera el límite
→ `413`. `name` se valida con `ManualUploadRequest`, `text` con
`ChunkUpdateRequest` y `active` acepta solo las cadenas `"true"`/`"false"`. La
redirección de R13/R15 usa el `manual_id` de la respuesta del RAG. Las páginas de
error nunca muestran `message` del RAG (R17), y en logs solo se registra el tipo
de excepción, como hace hoy `HttpRagClient.search`.

## Dependencias

`python-multipart>=0.0.9,<1` (Apache-2.0) en el orquestador, con la misma
versión acotada que ya usa `services/rag/requirements.txt`. Starlette la necesita
para leer el formulario multipart de la carga de archivos. El agente no la
instala; el humano la añade al entorno antes de implementar.

## Alternativas descartadas

- **Añadir `active` opcional a `PATCH /chunks/{id}`**: cambiaría un modelo ya
  publicado (`text` es obligatorio) y rompe el principio aditivo; una ruta
  propia es más pequeña y explícita.
- **Parsear el multipart a mano con la biblioteca estándar**: `cgi` ya no existe
  en Python 3.13+ y un parser propio es más superficie de error que la
  dependencia que el proyecto ya usa.
- **Que el navegador llame al RAG directamente**: obligaría a exponer
  `SERVICE_TOKEN` (contra R21).

## Supuestos a confirmar

| Supuesto | Default |
|----------|---------|
| Límite de tamaño de la carga desde el panel | `ADMIN_MANUAL_MAX_BYTES=20971520` (20 MiB, rango 1–104857600) |
| Las listas no se paginan: un manual tiene pocos cientos de fragmentos | — |
| `ManualSummary.chunks` admite 0 aunque hoy la ingesta siempre crea ≥ 1 | — |
| Desactivar un fragmento solo lo saca de `POST /search` (comportamiento existente); no se borra | — |
