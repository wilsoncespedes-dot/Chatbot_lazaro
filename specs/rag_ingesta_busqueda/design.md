# Design — rag_ingesta_busqueda

## Archivos

Crear en `services/rag/rag/`:

- `domain.py` (modificar) — mantiene `DomainError`; añade `UnsupportedFormat` (415, `unsupported_format`), `EmptyDocument` (422, `empty_document`), `EmbeddingsUnavailable` (500, `internal_error`, interna) y las funciones puras `detect_format`, `chunk_text`, `cosine_similarity`, `select_results`, `ingest_manual` y `search_chunks`. Sin IO: la extracción de texto entra como función inyectada.
- `extraction.py` — IO de ficheros: `extract_text(data: bytes, fmt: str) -> str` con `pypdf` y `python-docx`. Un archivo ilegible lanza `EmptyDocument`.
- `adapters/embeddings.py` — `EmbeddingsClient` (Protocol), `HttpEmbeddingsClient` (httpx, `POST {EMBEDDINGS_BASE_URL}/embeddings`, formato compatible con OpenAI, sin SDK), `FakeEmbeddings` (determinista: hash por palabra a un vector de `dim` componentes, normalizado; sin red).
- `adapters/repository.py` — `ChunkRepository` (Protocol), `PgVectorChunkRepository` (pg8000, SQL parametrizado, `CREATE TABLE IF NOT EXISTS` en el primer uso, conexión perezosa), `FakeChunkRepository` (listas en memoria; calcula coseno con `cosine_similarity`).
- `config.py` (modificar) — añade `database_url`, `embeddings_base_url`, `embeddings_api_key`, `embeddings_model`, `embeddings_dim=1536`, `chunk_size=1000`, `chunk_overlap=200`, `rag_similarity_threshold=0.75`, `http_timeout_seconds=10`. Sin validador adicional: valores inválidos de estas variables quedan fuera de alcance.
- `main.py` (modificar) — `create_app(settings=None, embeddings=None, repository=None)`; rutas `POST /manuals` y `POST /search` declaradas con `def` (httpx y pg8000 son síncronos). Con `None` construye los adaptadores reales de forma perezosa (sin conectar al importar). Subida: `file: UploadFile = File(...)`, `name: str = Form(...)`, validado con `ManualUploadRequest`.
- `requirements.txt` (modificar) — dependencias nuevas.

Crear fuera del servicio:

- `scripts/cargar_manual.py` — `main(argv: list[str] | None = None, client: httpx.Client | None = None) -> int`.

Modificar:

- `/.env.example` — añadir `EMBEDDINGS_BASE_URL`, `EMBEDDINGS_API_KEY`, `EMBEDDINGS_DIM`, `CHUNK_SIZE`, `CHUNK_OVERLAP` (`EMBEDDINGS_MODEL`, `RAG_SIMILARITY_THRESHOLD`, `DATABASE_URL`, `RAG_URL`, `SERVICE_TOKEN` ya existen).
- `services/rag/tests/test_rag_app.py` — actualizar `test_requirements_txt_matches_design` (R5 del esqueleto) para aceptar las dependencias nuevas.

Tests nuevos en `services/rag/tests/`: `conftest.py`, `fakes.py` (reexporta fakes), `fixtures/` (opcional; los ficheros se generan en el test), `test_ingest.py`, `test_search.py`, `test_chunking.py`, `test_extraction.py`, `test_adapters.py`, `test_cargar_manual.py`.

## Firmas

```python
# domain.py
class UnsupportedFormat(DomainError): code = "unsupported_format"; status_code = 415
class EmptyDocument(DomainError): code = "empty_document"; status_code = 422
class EmbeddingsUnavailable(DomainError): code = "internal_error"; status_code = 500

@dataclass(frozen=True)
class Chunk: chunk_id: str; manual_id: str; manual: str; order: int; text: str; embedding: list[float]; active: bool = True

def detect_format(data: bytes) -> str          # "pdf" | "docx"; UnsupportedFormat si no (R6)
def chunk_text(text: str, size: int, overlap: int) -> list[str]
def cosine_similarity(a: list[float], b: list[float]) -> float
def ingest_manual(data: bytes, name: str, settings: Settings, embeddings: EmbeddingsClient,
                  repository: ChunkRepository, new_id: Callable[[], str]) -> ManualUploadResponse
def search_chunks(request: SearchRequest, settings: Settings, embeddings: EmbeddingsClient,
                  repository: ChunkRepository) -> list[SearchResult]

# adapters
class EmbeddingsClient(Protocol):
    def embed(self, texts: list[str]) -> list[list[float]]
class ChunkRepository(Protocol):
    def add_manual(self, manual_id: str, name: str, chunks: list[Chunk]) -> None   # atómico (R10)
    def search(self, query_vector: list[float], top_k: int, threshold: float) -> list[SearchResult]
    def set_active(self, chunk_id: str, active: bool) -> None   # lo usan los tests y la futura edición de fragmentos
```

Detalles:

- `detect_format`: PDF si empieza por `%PDF-`; DOCX si es un ZIP (`PK\x03\x04`) que contiene `word/document.xml`. Vacío (0 bytes) lanza `EmptyDocument` antes de detectar (R7). La extensión y el `Content-Type` se ignoran.
- `chunk_text`: normaliza espacios en blanco consecutivos a uno; ventana deslizante de `size` caracteres con paso `size - overlap`; la última ventana puede ser menor; descarta fragmentos vacíos. Si el texto normalizado queda vacío, `ingest_manual` lanza `EmptyDocument` (R8).
- `manual_id = new_id()` (por defecto `uuid4().hex`, 32 caracteres); `chunk_id = f"{manual_id}-{order}"` (≤ 64 caracteres; `order` desde 1).
- `ingest_manual`: detecta formato → extrae → fragmenta → `embeddings.embed(textos)` (en un solo lote; un fallo se convierte en `EmbeddingsUnavailable`) → `repository.add_manual` (una transacción) → `ManualUploadResponse`. Nada se guarda si algo falla antes (R10).
- `search`: `embed([query])` → `repository.search(vector, top_k, threshold)`. La consulta usa `score = 1 - (embedding <=> :q)` (coseno), `WHERE active AND score >= threshold ORDER BY score DESC LIMIT top_k`; el vector viaja como parámetro de texto `'[x,y,...]'` con `CAST(%s AS vector)`, sin la librería `pgvector` (R13-R16, R25). El filtro de umbral y de `active` va **en la propia consulta**; además `search_chunks` vuelve a filtrar `score >= threshold` y recorta a `top_k` como defensa ante un repositorio defectuoso (R14, R15).
- Esquema: `manuals(manual_id text primary key, name text not null, created_at timestamptz default now())` y `chunks(chunk_id text primary key, manual_id text references manuals, ord int, text text, embedding vector(<EMBEDDINGS_DIM>), active boolean default true)`.
- Un error al llamar a `/embeddings` (red, timeout, no 2xx, forma inesperada, dimensión distinta de `EMBEDDINGS_DIM`) lanza `EmbeddingsUnavailable`; el log registra solo código, nunca el texto.

## Excepciones

Se reutiliza `DomainError` y el handler existente de `main.py`. Se añaden `UnsupportedFormat`, `EmptyDocument` y `EmbeddingsUnavailable`. `422 validation_error` y `401` los dan los handlers y el middleware ya existentes. El stack trace nunca sale al cliente.

## Alternativas descartadas

- **Paquete `pgvector` (Python) y `psycopg`.** Descartados: `psycopg` es LGPL-3.0 (prohibida por `docs/architecture.md` §2); y con `pg8000` basta pasar el vector como texto con `CAST(... AS vector)`, una dependencia menos. Coherente con la elección del orquestador.
- **Detectar el formato por extensión o `Content-Type`.** Descartada: lo controla el cliente; un `.pdf` falso pasaría. Se mira el contenido.
- **Fragmentar por párrafos/oraciones o por tokens.** Descartada para la versión mínima: `CHUNK_SIZE`/`CHUNK_OVERLAP` están definidos en caracteres en el acceptance, no requieren tokenizador (`tiktoken`) y son deterministas. Se puede refinar tras calibrar con un manual real.
- **Devolver siempre los top_k más parecidos y dejar el umbral al orquestador.** Descartada: viola la regla de seguridad «el bot no inventa»; el umbral se aplica en RAG.
- **SDK del proveedor de embeddings.** Descartada: el proveedor no está decidido (`docs/proyecto.md` §12); httpx contra un endpoint compatible con OpenAI, configurable.

## Dependencias nuevas (las instala el humano antes de implementar)

| Nombre | Versión | Licencia | Uso |
|---|---|---|---|
| httpx | `>=0.27,<1` | BSD-3 | cliente de embeddings |
| pg8000 | `>=1.31,<2` | BSD-3 | driver Postgres |
| pypdf | `>=5,<7` | BSD-3 | extraer texto de PDF |
| python-docx | `>=1.1,<2` | MIT | extraer texto de DOCX |
| python-multipart | `>=0.0.9,<1` | Apache 2.0 | lo exige FastAPI para `File`/`Form` |

Para generar el PDF de prueba sin dependencias extra, los tests construyen un PDF mínimo a mano (bytes) o usan `services/rag/tests/fixtures/`; el DOCX se genera con `python-docx` (ya en `requirements.txt`). `scripts/cargar_manual.py` solo usa `httpx` (ya presente en el entorno del orquestador; se documenta en su cabecera que requiere `httpx`).

## Supuestos a confirmar

| Supuesto | Valor por defecto configurable |
|---|---|
| Umbral de similitud (duda abierta §12: calibrar con un manual real) | `RAG_SIMILARITY_THRESHOLD=0.75` |
| Modelo de embeddings (duda abierta §12) | `EMBEDDINGS_MODEL` (sin valor por defecto; cada proveedor usa su nombre) |
| Proveedor de embeddings compatible con `/embeddings` de OpenAI; quién paga la API es duda abierta | `EMBEDDINGS_BASE_URL=https://api.openai.com/v1`, `EMBEDDINGS_API_KEY` |
| Dimensión del vector (fija la columna `vector(N)`; cambiar de modelo con otra dimensión exige recrear la tabla) | `EMBEDDINGS_DIM=1536` |
| Tamaño y solapamiento de fragmentos, en caracteres | `CHUNK_SIZE=1000`, `CHUNK_OVERLAP=200` |
| Tiempo máximo de llamadas salientes | `HTTP_TIMEOUT_SECONDS=10` |
| No se validan `CHUNK_SIZE`, `CHUNK_OVERLAP` ni el rango del umbral al construir `Settings` (el acceptance no lo pide); una configuración incoherente es responsabilidad de quien despliega | — |
| La cobertura del acceptance «tests sin red ni DB, con PDF/DOCX generados» se cumple por proceso en T8/T9 y en la sección de dependencias, no con un requirement | — |
| El orden de fragmentos empieza en 1 y `chunk_id = <manual_id>-<orden>` | — |
| Resubir un manual con el mismo nombre crea un manual nuevo (no reemplaza ni deduplica); qué pasa con fragmentos corregidos a mano al resubir es duda abierta §12 y queda fuera | — |
| Un PDF/DOCX corrupto o con solo imágenes (sin OCR) se trata como «sin texto» (`422 empty_document`) | — |
| Un fallo de embeddings durante la ingesta responde `500 internal_error` (el contrato no define un código específico; cambiarlo es un cambio de contrato) | — |
| Las tablas se crean con `CREATE TABLE IF NOT EXISTS` al primer uso (sin herramienta de migraciones), igual que el orquestador | — |
| Sin límite de tamaño de archivo en esta feature (el tamaño real de los manuales es duda abierta §12) | — |
| La activación/desactivación de fragmentos no tiene ruta HTTP aquí; `set_active` existe en el repositorio para tests y la futura edición de fragmentos | — |
