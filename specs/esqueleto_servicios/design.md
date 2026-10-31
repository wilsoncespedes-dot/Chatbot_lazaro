# Design — esqueleto_servicios (feature #2)

> **Revisión 2.** Responde a `progress/specreview_esqueleto_servicios.md`
> siguiendo la vía 1 recomendada: **no se tocan `pytest.ini` ni `docs/`**,
> no existe `tests/infra/`, no se usa PyYAML y las dependencias se instalan solo
> con `python -m pip install -r services/<svc>/requirements.txt`.

## 1. Alcance

Crea los 4 servicios vacíos (`telegram_gateway`, `orchestrator`, `rag`,
`handover`) con la forma de `docs/architecture.md` §1, la base común que
fijan `contracts/CONTRATOS.md` §Reglas comunes (token de servicio, errores
`{error, message}`, `GET /health`), Docker Compose con Postgres+pgvector y
Redis, el script SQL de inicialización, la CI y los tests.

**Fuera de alcance:** cualquier ruta de negocio (`/messages`, `/send`,
`/search`, `/handover`, `/cases/...`, `/manuals`, el webhook de Telegram),
adaptadores reales (Postgres, Redis, Telegram, LLM), modelos de base de datos,
despliegue en Render. `contracts/` **no se toca** (cambiar un contrato es una
feature propia).

## 2. Archivos

### Se crean (×4, uno por `<svc>`)

```
services/<svc>/
├── <svc>/
│   ├── __init__.py          # docstring de una línea
│   ├── main.py              # create_app(), app, middleware de token, handlers de error, GET /health
│   ├── config.py            # Settings (pydantic-settings)
│   ├── domain.py            # DomainError (sin IO)
│   └── adapters/
│       └── __init__.py      # vacío salvo docstring; los adaptadores llegan con cada feature
├── tests/
│   └── test_<svc>_app.py    # tests de A–D, R24, R26, R27, R30, R38, R41, R42 para este servicio
├── requirements.txt
└── Dockerfile
```

### Se crea (solo en `orchestrator`)

```
services/orchestrator/tests/test_orchestrator_infra.py   # tests de los artefactos globales (§7.3)
```

Se borra `services/.gitkeep` (la carpeta deja de estar vacía).

### Se crean (una vez)

| Archivo | Contenido |
|---|---|
| `docker-compose.yml` | §5 |
| `scripts/db/init/01_extensions.sql` | `CREATE EXTENSION IF NOT EXISTS vector;` |
| `.github/workflows/ci.yml` | §6 |
| `.dockerignore` | `.env`, `.env.*`, `!.env.example`, `.venv/`, `**/__pycache__/`, `.git/`, `.pytest_cache/`, `referencias/`, `progress/`, `specs/` — para que `.env` nunca entre en una imagen |

`scripts/db/init/` cuelga de `scripts/`, que ya está en el mapa de
`docs/architecture.md` §1: no es una carpeta de primer nivel nueva. `.github/`
la exige el acceptance 7.

### Se modifican

| Archivo | Cambio |
|---|---|
| `.env.example` | Añadir bloque `# Postgres (contenedor)` con `POSTGRES_USER=lazaro`, `POSTGRES_PASSWORD=lazaro`, `POSTGRES_DB=lazaro` (coherentes con el `DATABASE_URL` ya existente). No se borra nada. |
| `requirements-dev.txt` | Añadir las 4 líneas `-r services/<svc>/requirements.txt`. Conservar las líneas existentes. **No** se añade ningún paquete nuevo. |

### No se modifican (bloqueados por `.claude/settings.json` / `nocturno.md`)

`pytest.ini`, `conftest.py` raíz, `init.sh`, `docs/**`, `AGENTS.md`,
`.claude/**`, `contracts/**`. El diseño funciona con la configuración actual:
`testpaths = services contracts eval scripts` ya recoge `services/*/tests/`, y
`docs/specs.md` §Trazabilidad ya admite tests en `services/*/tests/`.

## 3. Firmas nuevas (idénticas en los 4 servicios salvo `SERVICE_NAME`)

### `<svc>/config.py`

```python
"""Configuración del servicio <svc> leída de variables de entorno."""
from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")

    service_token: str = ""
```

- Sin `env_file`: en Docker las variables llegan por `env_file: [.env]` de
  compose; en tests se pasan `Settings(service_token="...")` explícitamente.
  Así ningún test ni agente lee `.env`.
- Default `""` para que `import <svc>.main` no falle sin entorno (R41); un
  token vacío hace que todo lo protegido responda 401 (R15, S1).

### `<svc>/domain.py`

```python
class DomainError(Exception):
    code = "domain_error"
    status_code = 400
```

Las subclases concretas (`NotFound`, `Unauthorized`…) las añade cada feature.
No se añade `Unauthorized` aquí: el 401 lo produce el middleware directamente.

### `<svc>/main.py`

```python
SERVICE_NAME = "<svc>"
PUBLIC_PATHS: frozenset[str] = frozenset({"/health"})

def create_app(settings: Settings | None = None) -> FastAPI: ...
app = create_app()
```

Dentro de `create_app`:

1. `settings = settings or Settings()`.
2. `FastAPI(title=SERVICE_NAME)`.
3. **Middleware de token** (`@app.middleware("http")`):
   - Si `request.url.path in PUBLIC_PATHS` → `call_next`.
   - Si no: `token = request.headers.get(SERVICE_TOKEN_HEADER)` (constante de
     `lazaro_contracts`). Si `settings.service_token == ""` o `token is None`
     o `not hmac.compare_digest(token.encode(), settings.service_token.encode())`
     → `JSONResponse(401, {"error": "unauthorized", "message": "Falta X-Service-Token o no es válido."})`.
   - Se hace como middleware (no como dependencia por ruta) para que también
     cubra rutas inexistentes (R13), cualquier método (R14) y `/docs`,
     `/openapi.json`.
   - Feature 3 añadirá `/telegram/webhook` a `PUBLIC_PATHS` del gateway.
4. **Handlers de error** (todos devuelven `ErrorResponse(...).model_dump()`):
   - `DomainError` → `exc.status_code`, `{"error": exc.code, "message": str(exc)}` (R20).
   - `starlette.exceptions.HTTPException` → `404` ⇒ `not_found`; `405` ⇒
     `method_not_allowed`; otro ⇒ `http_error`; `message` = `str(exc.detail)` o
     texto fijo en español (R17).
   - `fastapi.exceptions.RequestValidationError` → `422`, `validation_error`,
     `message` fijo «El cuerpo de la petición no es válido.» (R18). No se
     devuelve el detalle de Pydantic para no reflejar la entrada.
   - `Exception` → `500`, `internal_error` (R19), `message` fijo «Error
     interno.» (R42); se registra con `logger.exception`. Nunca stack trace en
     la respuesta.
5. **`GET /health`** → `HealthResponse(status="ok", service=SERVICE_NAME)`,
   `response_model=HealthResponse` (R8–R10).

Esta lógica (≈60 líneas) se **duplica** en los 4 `main.py`: los servicios no
pueden importarse entre sí (`docs/architecture.md` §3.1) y meterla en
`lazaro_contracts` cambiaría el paquete de contratos (alternativa descartada,
§10).

## 4. Errores y excepciones

| HTTP | `error` | Origen |
|---|---|---|
| 401 | `unauthorized` | middleware de token |
| 404 | `not_found` | ruta inexistente con token válido |
| 405 | `method_not_allowed` | método no permitido con token válido (sin R propio; no se prueba) |
| 422 | `validation_error` | `RequestValidationError` |
| 500 | `internal_error` | excepción no controlada |
| `status_code` | `code` | subclases de `DomainError` |

## 5. Docker

### `services/<svc>/Dockerfile` (contexto de build = raíz del repo)

```dockerfile
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY contracts/requirements.txt /tmp/contracts-requirements.txt
COPY services/<svc>/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/contracts-requirements.txt -r /tmp/requirements.txt
COPY contracts/lazaro_contracts ./lazaro_contracts
COPY services/<svc>/<svc> ./<svc>
RUN useradd --create-home --uid 10001 app
USER app
EXPOSE 8000
CMD ["uvicorn", "<svc>.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

**Decisión sin requirement (B2 del specreview):** el contenedor corre con el
usuario no root `app` (`useradd` + `USER app`). Es buena práctica de
endurecimiento que no exige el acceptance, así que no tiene `R<n>` ni test; el
implementer la aplica tal cual y el reviewer no la exige como trazable.

### `docker-compose.yml`

Formato **obligatorio** (los tests lo leen como texto, §7.2): YAML en estilo
bloque con sangría de **2 espacios**, claves de primer nivel en la columna 0,
nombres de servicio con sangría 2 y sus claves con sangría 4. `env_file`,
`ports` y `build` en estilo flujo de una sola línea, exactamente como abajo.

```yaml
services:
  postgres:
    image: pgvector/pgvector:pg16
    env_file: [.env]
    volumes:
      - pgdata:/var/lib/postgresql/data
      - ./scripts/db/init:/docker-entrypoint-initdb.d:ro
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U $${POSTGRES_USER} -d $${POSTGRES_DB}"]
      interval: 5s
      retries: 10
  redis:
    image: redis:7.2-alpine
  telegram_gateway:
    build: {context: ., dockerfile: services/telegram_gateway/Dockerfile}
    env_file: [.env]
    ports: ["8001:8000"]
    depends_on: [redis]
  orchestrator:   # igual: build propio, env_file: [.env], ports: ["8002:8000"], depends_on postgres (service_healthy) y redis
  rag:            # igual: ports: ["8003:8000"], depends_on postgres (service_healthy)
  handover:       # igual: ports: ["8004:8000"], depends_on postgres (service_healthy)
volumes:
  pgdata:
```

- Puerto interno siempre `8000` (coincide con `*_URL=http://<svc>:8000` ya
  presentes en `.env.example`); host `8001`–`8004` en el orden de la tabla de
  `requirements.md`.
- `$${...}` es escape de compose (lo expande el shell del contenedor, no
  compose), así que no cuenta como interpolación para R31. Si el implementer
  usa alguna `${VAR}` real, debe añadir `VAR` a `.env.example` (R31).
- Postgres no publica puerto al host (no hace falta para la versión mínima;
  se puede añadir en una feature posterior).

## 6. CI — `.github/workflows/ci.yml`

Formato obligatorio (los tests lo leen como texto, §7.3): sangría de 2
espacios y `on:` en estilo bloque como abajo.

```yaml
name: ci
on:
  push:
  pull_request:
jobs:
  tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: python -m pip install --upgrade pip
      - run: pip install -r requirements-dev.txt
      - run: python -m pytest
```

No necesita `.env` ni secretos: los tests no leen `.env` ni usan red. En CI
(máquina efímera de GitHub) se instala con `requirements-dev.txt`, que tras
esta feature incluye los 4 `requirements.txt` de servicio (R37). Esa regla de
`nocturno.md` aplica al `.venv` local, no al runner de CI.

## 7. Tests

### 7.1 Colección en pytest (R39)

Contexto ya existente y **no modificable**: `pytest.ini` usa
`testpaths = services contracts eval scripts` y `--import-mode=importlib`; el
`conftest.py` raíz añade `contracts/`, la raíz y cada `services/<svc>/` a
`sys.path`, de modo que `import rag.main` funciona desde cualquier test.

Reglas para que `python -m pytest` desde la raíz no choque:

1. **Sin `__init__.py`** en `services/<svc>/tests/` (con `importlib` no hacen
   falta y evitan un paquete `tests` repetido).
2. **Sin `conftest.py`** nuevos en `services/<svc>/tests/`: los fixtures y
   helpers viven dentro de cada archivo de test. El único `conftest.py` sigue
   siendo el de la raíz.
3. **Nombres de archivo de test únicos en todo el repo — regla OBLIGATORIA,
   no relajable.** Con `--import-mode=importlib`, pytest 8.x intenta primero
   importar un archivo de test sin `__init__.py` por su nombre de módulo
   (`stem`) y reutiliza `sys.modules[stem]` si ya existe: dos archivos con el
   mismo nombre pueden ejecutar el módulo equivocado **sin avisar**. Nombres
   fijados: `test_telegram_gateway_app.py`, `test_orchestrator_app.py`,
   `test_rag_app.py`, `test_handover_app.py`, `test_orchestrator_infra.py`
   (ninguno coincide con los de `contracts/tests/`).
4. Los tests **no importan** módulos de otros tests (nada de `from tests...` ni
   `fakes.py` compartidos). El helper de lectura del compose (§7.2) se
   **duplica** en cada archivo que lo necesita.
5. Los paquetes de los servicios tienen nombres únicos y distintos de
   `tests`, `contracts`, `scripts`, `eval`.
6. Las rutas de archivos del repo se calculan desde el propio test:
   `ROOT = Path(__file__).resolve().parents[3]` (`tests` → `<svc>` →
   `services` → raíz) y `SERVICE_DIR = Path(__file__).resolve().parents[1]`.

### 7.2 Lectura de YAML como texto (sin PyYAML)

No se añade ningún parser YAML (alternativa F descartada, §10). Los tests leen
`docker-compose.yml` y `ci.yml` con `Path.read_text(encoding="utf-8")` y usan
un helper local de bloques por sangría:

```python
def _block(text: str, key: str, indent: int) -> str:
    """Devuelve las líneas hijas de `key:` situada exactamente en la columna `indent`.

    Busca la primera línea que, sin comentario final, sea `' ' * indent + key + ':'`
    (con o sin valor detrás). Devuelve esa línea y las siguientes hasta la
    primera línea no vacía cuya sangría sea <= indent. Si no la encuentra,
    devuelve "" (el test falla con un assert explícito).
    """
```

Uso: `services = _block(compose, "services", 0)` y
`svc = _block(services, "<svc>", 2)`. Dentro del bloque se aplican regex
acotadas a una línea:

| Comprobación | Regex sobre el bloque del servicio |
|---|---|
| `env_file` incluye `.env` (R24, R25) | `^\s+env_file:\s*\[([^\]]*)\]\s*$` y `.env` ∈ elementos separados por coma (strip) |
| puerto publicado (R26) | `^\s+ports:\s*\[.*["']?8001:8000["']?.*\]\s*$` (con el puerto del servicio) |
| build desde la raíz (R27) | `^\s+build:\s*\{(.*)\}\s*$`; en el contenido, `context:\s*\.\s*(,|$)` y `dockerfile:\s*services/<svc>/Dockerfile\s*(,|$)` |
| imagen (R22, R23) | `^\s+image:\s*(\S+)\s*$` |
| montaje init (R29) | línea que contiene `./scripts/db/init:/docker-entrypoint-initdb.d` |

### 7.3 Archivos de test

#### `services/<svc>/tests/test_<svc>_app.py` (×4)

Fixture local `client` = `TestClient(create_app(Settings(service_token="test-token")))`.
Para R18–R20 y R42 el test registra rutas de prueba sobre la app devuelta por
`create_app` (p. ej. `@app.post("/_test/echo")` con un modelo Pydantic,
`@app.get("/_test/boom")` que lanza `RuntimeError("secreto-interno")`,
`@app.get("/_test/domain")` que lanza una subclase local de `DomainError` con
`code="teapot"`, `status_code=418`); para R19 y R42 se usa
`TestClient(app, raise_server_exceptions=False)`.

Tests mínimos (cada uno con `"""R<n>: ..."""` en su docstring):

| Test | R |
|---|---|
| `test_service_layout_exists` (rutas relativas a `SERVICE_DIR`) | R1 |
| `test_create_app_returns_fastapi` | R2 |
| `test_module_exposes_fastapi_app` | R3 |
| `test_settings_reads_service_token_from_env` (`monkeypatch.setenv`) | R4 |
| `test_requirements_txt_matches_design` (lee el archivo; compara nombres de paquete con §8.1 y comprueba `>=` y `<`) | R5 |
| `test_dockerfile_base_image_and_cmd` | R6 |
| `test_health_returns_ok_without_token` | R8, R38 |
| `test_health_body_matches_contract` | R9 |
| `test_health_ignores_wrong_token` | R10 |
| `test_missing_token_returns_401` | R11, R38 |
| `test_wrong_token_returns_401` | R12 |
| `test_unknown_route_without_token_returns_401_not_404` | R13 |
| `test_post_without_token_returns_401` | R14 |
| `test_empty_configured_token_rejects_everything` | R15 |
| `test_valid_token_passes_auth` | R16 |
| `test_unknown_route_with_token_returns_not_found_error` | R17 |
| `test_invalid_body_returns_validation_error` | R18 |
| `test_unhandled_exception_returns_internal_error` | R19 |
| `test_domain_error_maps_to_its_code_and_status` | R20 |
| `test_compose_service_reads_env_file` (bloque de este servicio) | R24 |
| `test_compose_service_publishes_expected_port` | R26 |
| `test_compose_service_builds_from_root_with_own_dockerfile` | R27 |
| `test_settings_fields_are_in_env_example` (`Settings.model_fields` en mayúsculas vs líneas `NOMBRE=` de `.env.example`) | R30 |
| `test_module_app_imports_without_service_token` (`monkeypatch.delenv("SERVICE_TOKEN", raising=False)` + `importlib.reload`) | R41 |
| `test_unhandled_exception_message_hides_details` (`"secreto-interno"` ∉ `message`) | R42 |

#### `services/orchestrator/tests/test_orchestrator_infra.py` (una vez)

Tests de los artefactos globales del repositorio. Se elige `orchestrator`
porque es el servicio central que coordina a los demás y el único que en
compose depende a la vez de `postgres` y de `redis` (supuesto S5).

| Test | R |
|---|---|
| `test_compose_defines_all_services` | R21 |
| `test_postgres_uses_pgvector_image` | R22 |
| `test_redis_uses_bsd_licensed_image` | R23 |
| `test_postgres_reads_env_file` | R25 |
| `test_init_sql_enables_vector` | R28 |
| `test_postgres_mounts_init_scripts` | R29 |
| `test_compose_interpolated_vars_are_in_env_example` (regex `(?<!\$)\$\{([A-Z0-9_]+)` sobre el texto completo) | R31 |
| `test_env_example_has_postgres_vars` | R32 |
| `test_ci_triggers_on_push_and_pull_request` (`_block(ci, "on", 0)` contiene líneas `^\s+push:` y `^\s+pull_request:`) | R33 |
| `test_ci_installs_dev_requirements` (línea que contiene `pip install -r requirements-dev.txt`) | R34 |
| `test_ci_runs_pytest` (línea `run:` que contiene `python -m pytest`) | R35 |
| `test_ci_uses_python_312` (`actions/setup-python@` y `python-version:\s*["']?3\.12["']?`) | R36 |
| `test_dev_requirements_include_every_service` (4 líneas `-r services/<svc>/requirements.txt`) | R37 |

#### Verificación por ejecución

R39, R40 y R43 se verifican ejecutando `python -m pytest` (y
`python -m pytest --co -q` para la lista recogida) y `./init.sh` desde la
raíz; el implementer pega el resumen de las salidas en
`progress/impl_esqueleto_servicios.md`.

## 8. Dependencias

> **Instalación en el `.venv` local (modo nocturno, `nocturno.md` §Dependencias):**
> solo con `<python de init.sh> -m pip install -r services/<svc>/requirements.txt`,
> una vez por cada uno de los 4 servicios. No se usa `pip install <paquete>`
> suelto ni `pip install -r requirements-dev.txt` en local. `pytest` y `httpx`
> ya están instalados en el `.venv`; `pydantic` llega con `contracts` (ya
> instalado) y con §8.1. Si una instalación falla o se deniega, la feature
> queda `blocked` con el error; no buscar vías alternativas.

### 8.1 `services/<svc>/requirements.txt` (idéntico en los 4 servicios)

| Paquete | Versión | Licencia | Para qué |
|---|---|---|---|
| `fastapi` | `>=0.115,<1` | MIT | App HTTP, `TestClient` |
| `uvicorn` | `>=0.30,<1` | BSD-3-Clause | Servidor ASGI (`CMD` del Dockerfile) |
| `pydantic` | `>=2.12,<3` | MIT | Modelos (misma cota que `contracts/requirements.txt`) |
| `pydantic-settings` | `>=2.4,<3` | MIT | `Settings` de `config.py` |

Contenido exacto del archivo:

```
fastapi>=0.115,<1
uvicorn>=0.30,<1
pydantic>=2.12,<3
pydantic-settings>=2.4,<3
```

`uvicorn` va sin extras `[standard]` (evita `uvloop`/`httptools` compilados,
innecesarios aquí y sin soporte en Windows). Las dependencias transitivas
(`starlette`, `anyio`, `typing-extensions`, `python-dotenv`, `click`, `h11`…)
llegan solas con estas.

### 8.2 `requirements-dev.txt` (CI y desarrollo)

Sin paquetes nuevos. Ya contiene `pytest>=8,<9` (MIT), `httpx>=0.27,<1`
(BSD-3-Clause; lo necesita `fastapi.testclient.TestClient`) y
`-r contracts/requirements.txt`. Esta feature solo añade las 4 líneas
`-r services/<svc>/requirements.txt` (R37).

Nota: el `.venv` local usa CPython 3.14; todas las cotas de §8.1 tienen ruedas
para 3.12 y 3.14.

### 8.3 Imágenes Docker (no se instalan en el `.venv`)

`python:3.12-slim`, `pgvector/pgvector:pg16` (PostgreSQL License + pgvector
PostgreSQL License), `redis:7.2-alpine` (Redis 7.2, BSD-3-Clause). Se evita
Redis ≥7.4 (RSALv2/SSPL) y Redis 8 (incluye AGPL), prohibidas por
`docs/architecture.md` §2. (Ver S4.)

## 9. Supuestos a confirmar

| Id | Supuesto | Valor por defecto / dónde se cambia |
|---|---|---|
| S1 | Si `SERVICE_TOKEN` está vacío, el servicio **falla cerrado**: rechaza todo lo protegido con 401 (en vez de fallar al arrancar). Así `import main` funciona en tests y nunca queda un servicio abierto por olvido. | `SERVICE_TOKEN` en `.env` |
| S2 | Puertos publicados: `telegram_gateway`→8001, `orchestrator`→8002, `rag`→8003, `handover`→8004 (el acceptance fija el rango, no el orden). | `docker-compose.yml` |
| S3 | Credenciales de Postgres de desarrollo `lazaro/lazaro/lazaro`, coherentes con el `DATABASE_URL` ya presente en `.env.example`. Solo valores de ejemplo; en Render se cambian. | `POSTGRES_*` en `.env` |
| S4 | Se fija `redis:7.2-alpine` (último Redis BSD) porque 7.4+ es RSALv2/SSPL y 8.x ofrece AGPL. El humano confirma si prefiere migrar a Valkey (BSD, compatible) cuando 7.2 deje de tener soporte. | `docker-compose.yml` |
| S5 | Los tests de los artefactos globales (compose, SQL, `.env.example`, CI, `requirements-dev.txt`) viven en `services/orchestrator/tests/test_orchestrator_infra.py`, porque `pytest.ini` y `docs/` no se pueden cambiar en esta feature. Si el humano prefiere una carpeta propia (`tests/infra/`), lo hace en una feature de arnés que modifique `pytest.ini`, `docs/architecture.md` §1 y `docs/specs.md` §Trazabilidad, y mueva el archivo. | `services/orchestrator/tests/` |

Ninguna duda de `docs/proyecto.md` §12 se toca en esta feature.

## 10. Alternativas descartadas

- **A. Dependencia FastAPI (`Depends(verify_token)`) por ruta en vez de
  middleware.** Descartada: no cubre rutas inexistentes (darían 404 y
  revelarían el mapa de rutas, R13) y obliga a no olvidar el `Depends` en cada
  ruta nueva. El middleware protege por defecto y la excepción es explícita
  (`PUBLIC_PATHS`).
- **B. Carpeta de primer nivel `tests/infra/` para los tests de compose/CI/SQL.**
  Era la opción de la revisión 1. Descartada ahora por restricciones duras:
  (1) `pytest.ini` no se puede editar (`.claude/settings.json` deniega
  `Edit(/pytest.ini)`) y su `testpaths` no incluye `tests`, así que esos tests
  nunca se ejecutarían; (2) `docs/specs.md` §Trazabilidad solo admite tests en
  `services/*/tests/`, `contracts/tests/` o `eval/`, y `docs/` no se puede
  editar; (3) `docs/architecture.md` §1 prohíbe carpetas de primer nivel que el
  acceptance no pide. Se acepta el coste de colgar la infraestructura global de
  un servicio (S5): cada servicio prueba su propia entrada del compose
  (R24, R26, R27) y lo global va a `orchestrator`.
- **C. Mover el middleware y los handlers a `lazaro_contracts`** para no
  duplicarlos 4 veces. Descartada: `docs/architecture.md` §3.2 dice que cambiar
  `contracts/` es una feature propia, y `lazaro_contracts` solo debe tener
  modelos. Se acepta la duplicación (≈60 líneas) y se puede extraer en una
  feature futura.
- **D. `Settings` con `service_token` obligatorio (sin default)**. Descartada:
  `app = create_app()` a nivel de módulo fallaría al importar sin entorno y
  los tests tendrían que fijar variables globales (R41, S1).
- **E. Comprobar el compose con `docker compose config` en los tests.**
  Descartada: los tests no pueden depender de Docker (`docs/conventions.md`).
- **F. Parsear `docker-compose.yml` y `ci.yml` con PyYAML.** Descartada:
  `nocturno.md` §Dependencias solo permite instalar paquetes de un
  `services/<svc>/requirements.txt`, y meter `pyyaml` ahí solo para tests lo
  añadiría a la imagen de producción sin uso. Se leen como texto con un formato
  fijado (§5, §6) y el helper `_block` (§7.2).
