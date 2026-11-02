# #25 clasificador_consultas — Design

## Decisión: clasificador local por palabras clave, en el orchestrator

`docs/proyecto.md` §10 deja abierta la opción "llamada barata al modelo o
clasificador por similitud". Se elige la opción mínima: **palabras clave por
categoría, sin LLM ni embeddings**.

- Determinista y testeable sin fakes de red; coste y latencia cero.
- No hay prompt, así que la inyección de instrucciones en el mensaje no puede
  cambiar el resultado más allá de las palabras literales (R20).
- Da la "puntuación por opción" que pide §6 (R13) y un umbral (R15–R18).
- No toca RAG: `POST /search` sigue sin `category` (R23). Usar la categoría
  para filtrar o enrutar queda para una feature futura.

No hay código externo: `referencias/` no existe en este checkout y no se copia
nada (el enrutador de rag-support-bot no da porcentajes; tampoco se inspeccionó).

## Archivos

| Archivo | Cambio |
|---------|--------|
| `orchestrator/classifier.py` (nuevo) | Lógica pura: `Category`, `Classification`, `parse_keywords`, `validate_category_fields`, `parse_threshold`, `classify`. Sin IO. |
| `orchestrator/domain.py` | `Adapters` sin cambios. Nuevas excepciones `CategoryCodeTaken` (409 `category_code_taken`) y `CategoryNotFound` (404 `category_not_found`). `_classify_query(text, contact, settings, adapters)` llamada en `process_message` justo antes de `adapters.rag.search` (R22–R25). |
| `orchestrator/adapters/repository.py` | Tablas y métodos nuevos en Protocol, Fake y Postgres. |
| `orchestrator/admin.py` | `render_categories(categories, threshold, csrf, error=None)`; enlace "Categorías" en el `nav`. |
| `orchestrator/admin_routes.py` | 4 rutas (abajo), mismo orden que #21/#22: sesión → formulario → CSRF → validación → dominio. |
| `orchestrator/config.py` + `.env.example` | `CLASSIFIER_DEFAULT_THRESHOLD`. |
| `tests/test_classifier.py` (nuevo) | R13–R21. |
| `tests/test_admin_categorias.py` (nuevo) | R1–R12, R27. |
| `tests/test_messages_classification.py` (nuevo) | R22–R26. |

## Clasificador

```python
UNCLASSIFIED = "sin_clasificar"
CODE_PATTERN = re.compile(r"^[a-z][a-z0-9_]{0,15}$")

@dataclass(frozen=True)
class Category:
    id: str; code: str; name: str; keywords: tuple[str, ...]; active: bool

@dataclass(frozen=True)
class Classification:
    category: str              # code o "sin_clasificar"
    confidence: float          # [0, 1]
    scores: dict[str, float]   # code -> puntuación, solo activas

def parse_keywords(raw: str) -> tuple[str, ...]        # ValueError si viola límites
def validate_category_fields(code: str | None, name: str, keywords_raw: str) -> tuple[str | None, str, tuple[str, ...]]
def parse_threshold(raw: str) -> float                  # ValueError si no es finito en [0, 1]
def classify(text: str, categories: list[Category], threshold: float) -> Classification
```

Algoritmo de `classify`:

1. `haystack = " " + " ".join(re.split(r"[^a-z0-9]+", normalize_text(text))) + " "`
   (reutiliza `normalize_text` de `domain.py`; si hay import circular se mueve a
   `classifier.py` y `domain.py` lo importa).
2. Para cada categoría activa, `hits = sum(1 for k in set(keywords) if f" {k_norm} " in haystack)`,
   con `k_norm` normalizado igual que el texto. Búsqueda de subcadena, nunca
   `re.compile` de texto del admin (R19–R21).
3. `total = sum(hits)`. Si no hay activas o `total == 0` → `(UNCLASSIFIED, 0.0)` (R17).
4. `score = hits / total`; `best` = máxima. Empate en `best` → `(UNCLASSIFIED, best)`
   (R18); `best < threshold` → `(UNCLASSIFIED, best)` (R16); si no → `(code, best)` (R15).

Las keywords se guardan ya normalizadas por `parse_keywords` (separador coma o
`\n`, `normalize_text`, puntuación → espacio, descarta vacías, deduplica
conservando el orden).

## Flujo de mensajes

```python
def _classify_query(text, contact, settings, adapters) -> None:
    try:
        categories = adapters.repository.list_categories()
        threshold = adapters.repository.get_classifier_threshold()
    except Exception:
        logger.error("classification_failed contact_id=%s", contact.id)
        return
    if threshold is None:
        threshold = settings.classifier_default_threshold
    result = classify(text, categories, threshold)
    adapters.repository.add_event(contact.id, "query_classified",
                                  f"{result.category}:{result.confidence:.2f}", adapters.clock())
```

Se llama en `process_message` después de `is_handover_request` y antes de
`adapters.rag.search`; por tanto los mensajes no elegibles nunca pasan por aquí
(R24). El resultado no se usa en ninguna decisión posterior (R23). El `code`
tiene como máximo 16 caracteres para que `redact_reason` del panel de eventos
no lo oculte (redacta tramos de ≥ 20).

## Persistencia

```sql
CREATE TABLE IF NOT EXISTS query_categories (
  id TEXT PRIMARY KEY, code TEXT UNIQUE NOT NULL, name TEXT NOT NULL,
  keywords TEXT NOT NULL, active BOOLEAN NOT NULL, created_at TIMESTAMPTZ NOT NULL)
CREATE TABLE IF NOT EXISTS app_settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)
```

`keywords` se guarda unido por `\n`. Umbral en `app_settings` con clave
`classifier_threshold`.

```python
# Repository (Protocol + Fake + Postgres)
def list_categories(self) -> list[Category]                     # ORDER BY code
def create_category(self, category: Category, now: datetime) -> bool  # False si code existe (ON CONFLICT (code) DO NOTHING RETURNING id)
def update_category(self, category_id: str, name: str, keywords: tuple[str, ...]) -> bool  # False si no existe
def set_category_active(self, category_id: str, active: bool) -> bool                     # False si no existe
def get_classifier_threshold(self) -> float | None
def set_classifier_threshold(self, value: float) -> None        # INSERT ... ON CONFLICT (key) DO UPDATE
```

`False` se traduce en el dominio a `CategoryCodeTaken` / `CategoryNotFound`.

## Rutas del panel

| Ruta | Éxito | Errores |
|------|-------|---------|
| `GET /admin/categories` | 200 | 303 login |
| `POST /admin/categories` (`code`, `name`, `keywords`) | 303 | 303 login, 403 CSRF, 422, 409 `category_code_taken` |
| `POST /admin/categories/{id}` (`name`, `keywords`) | 303 | 303, 403, 422, 404 `category_not_found` |
| `POST /admin/categories/{id}/active` (`active`) | 303 | 303, 403, 422, 404 |
| `POST /admin/categories/threshold` (`threshold`) | 303 | 303, 403, 422 |

`/admin/categories/threshold` se registra antes que `/admin/categories/{id}`
para que no se interprete como id. El `422` re-renderiza la lista con un mensaje
fijo; nunca devuelve el valor enviado sin escapar.

## Config (`.env.example`)

| Variable | Default |
|----------|---------|
| `CLASSIFIER_DEFAULT_THRESHOLD` | `0.6` (`Field(ge=0, le=1)`) |

## Dependencias

Ninguna nueva.

## Alternativas descartadas

- **Llamada al LLM con la lista de categorías**: coste por mensaje, latencia,
  respuesta no determinista y superficie de inyección de instrucciones; además
  exigiría fakes y validación de salida extra. Excesivo para la versión mínima.
- **Similitud por embeddings contra descripciones**: necesitaría embeddings en
  el orchestrator o una ruta nueva en RAG (cambio de contrato); más piezas sin
  beneficio demostrado con pocas categorías.
- **Pasar la categoría a `POST /search`**: cambiaría la ruta RAG, prohibido por
  el acceptance.

## Supuestos a confirmar

| Supuesto | Default |
|----------|---------|
| Qué son los "servicios técnicos" (§12): no se fijan categorías; el admin las crea | ninguna categoría inicial |
| Umbral inicial | `CLASSIFIER_DEFAULT_THRESHOLD=0.6` hasta que el panel guarde otro |
| Las categorías no se borran, solo se desactivan | — |
| El resultado solo se registra como evento; no cambia enrutamiento ni permisos | — |
