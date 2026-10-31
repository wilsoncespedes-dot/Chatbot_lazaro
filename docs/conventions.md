# Convenciones de código

> Homogeneidad extrema. La IA predice mejor cuando el repositorio se parece
> a sí mismo en todas partes. Un equipo principiante también.

## Estilo Python

- **Versión:** Python 3.12 (sintaxis `list[str]`, `X | None`).
- **Formato:** PEP 8, líneas de máximo 100 caracteres.
- **Imports:** stdlib, luego terceros, luego locales; un bloque cada uno.
- **Strings:** comillas dobles. f-strings para interpolar.
- **Tipos:** toda función pública lleva anotaciones de tipo.
- **Idioma:** código (nombres de variables, funciones, clases) en inglés;
  mensajes al usuario final, docs y comentarios en español.

## Nombres

| Tipo                    | Convención        | Ejemplo                       |
|-------------------------|-------------------|-------------------------------|
| Servicios / paquetes    | `snake_case`      | `telegram_gateway`            |
| Módulos                 | `snake_case`      | `domain.py`                   |
| Clases                  | `PascalCase`      | `SearchRequest`, `FakeLLM`    |
| Funciones / variables   | `snake_case`      | `search_chunks`               |
| Constantes              | `UPPER_SNAKE`     | `DEFAULT_TOP_K`               |
| Variables de entorno    | `UPPER_SNAKE`     | `RAG_SIMILARITY_THRESHOLD`    |
| Rutas HTTP              | minúsculas, plural| `/messages`, `/cases/{id}/reply` |
| Privadas                | prefijo `_`       | `_build_prompt`               |

## Estructura de cada módulo

```python
"""Una línea describiendo el propósito del módulo."""
from __future__ import annotations

import logging

from fastapi import FastAPI

from orchestrator.domain import decide_reply

logger = logging.getLogger(__name__)
```

## FastAPI

- Cada app se crea con una función `create_app(settings, adapters) -> FastAPI`
  para poder inyectar adaptadores falsos en los tests. `main.py` expone
  `app = create_app(...)` con los adaptadores reales.
- Cuerpos de request/response: modelos de `lazaro_contracts` (si es una ruta
  entre servicios) o modelos Pydantic locales.
- Errores: lanzar una excepción del dominio y convertirla con un exception
  handler a `{"error", "message"}`. Códigos de error en `snake_case`
  (`unauthorized`, `not_found`, `duplicate_update`, `unsupported_format`).
- `GET /health` en todos los servicios → `{"status": "ok", "service": "<nombre>"}`.

## Adaptadores

```python
class LLMClient(Protocol):
    def complete(self, system: str, user: str) -> str: ...

class FakeLLM:                 # en el mismo módulo o en tests/fakes.py
    def __init__(self, reply: str) -> None: ...
```

Un adaptador por cosa externa. Los fakes viven junto al adaptador o en
`tests/fakes.py` del servicio.

## Tests

- pytest. Archivos `services/<servicio>/tests/test_<tema>.py`.
- Nombres descriptivos: `test_search_returns_empty_when_no_chunk_passes_threshold`.
- Rutas HTTP con `fastapi.testclient.TestClient` sobre `create_app(...)` con fakes.
- Archivos temporales con el fixture `tmp_path`.
- **Prohibido en tests:** red real, claves reales, depender de Docker o de
  que Postgres/Redis estén levantados. (Los tests de integración con Docker
  son opcionales y van marcados `@pytest.mark.integration`, excluidos por
  defecto.)
- Cada test indica en su docstring qué requirement cubre: `"""R3: ..."""`.

## Manejo de errores

```python
class DomainError(Exception):
    code = "domain_error"
    status_code = 400

class NotFound(DomainError):
    code = "not_found"
    status_code = 404
```

## Comentarios

Por defecto **no** se escriben. Solo cuando explican un *por qué* no obvio
(invariante sutil, workaround, supuesto a confirmar). Los nombres hacen el resto.
