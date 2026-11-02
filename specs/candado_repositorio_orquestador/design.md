# Design — candado_repositorio_orquestador

## 1. Contexto

`PostgresRepository` (`services/orchestrator/orchestrator/adapters/repository.py`) guarda una
única conexión pg8000 en `self._conn`, abierta en el primer uso por `_connection()`. Las rutas
síncronas de FastAPI y las `BackgroundTasks` se ejecutan en el pool de hilos, así que dos
peticiones pueden llamar a `_run` a la vez sobre la misma conexión (pg8000 no es seguro entre
hilos para una misma conexión) y dos primeros usos simultáneos pueden abrir dos conexiones. La
#14 resolvió lo mismo en handover (`specs/autorizacion_asesores/design.md` §3.5, R44-R45); esta
feature copia ese patrón dentro del repo (código propio, sin licencia externa).

## 2. Archivos

| Acción | Archivo | Cambio |
|--------|---------|--------|
| modificar | `services/orchestrator/orchestrator/adapters/repository.py` | `import threading`; `self._lock = threading.Lock()` en `PostgresRepository.__init__`; cuerpo de `_run` dentro de `with self._lock:`; docstring de la clase menciona el candado |
| crear | `services/orchestrator/tests/test_repository_lock.py` | tests de R1-R4 |

No se tocan `contracts/`, `main.py`, `domain.py`, `FakeRepository`, el `Protocol`, `_SCHEMA`, el SQL
ni los tests existentes. Sin dependencias nuevas (`threading` es de la biblioteca estándar).

## 3. Código

```python
import threading

class PostgresRepository:
    """SQL siempre parametrizado (%s); la conexión se abre en el primer uso.

    Un threading.Lock serializa todo el uso de la conexión compartida (#18).
    """

    def __init__(self, database_url, connect=None, new_id=None) -> None:
        ...                                   # sin cambios
        self._conn: Any = None
        self._lock = threading.Lock()

    def _run(self, sql: str, params: tuple, fetch: bool = False) -> list:
        with self._lock:
            conn = self._connection()         # apertura y esquema bajo el candado (R3)
            cur = conn.cursor()
            try:
                cur.execute(sql, params)
                rows = list(cur.fetchall()) if fetch else []
                conn.commit()
                return rows
            except Exception:
                conn.rollback()
                raise                         # `with` libera el candado (R4)
```

- `_connection()` sigue sin candado propio: solo se llama desde `_run`, ya bajo el candado.
- `threading.Lock` (no reentrante) basta: ningún método llama a `_run` dentro de otro `_run`.
- `self._new_id()` en `get_or_create_contact` se evalúa fuera del candado (antes de llamar a
  `_run`); no toca la conexión.
- `get_or_create_contact` hace dos `_run` (INSERT ... ON CONFLICT DO NOTHING y SELECT); entre
  ambos otro hilo puede ejecutar sentencias. Es correcto: cada `_run` ya era su propia
  transacción con `commit`, y el SELECT lee el contacto confirmado por quien lo haya insertado.
  Sin cambio respecto a hoy.

## 4. Tests (`tests/test_repository_lock.py`)

Conexión falsa propia del archivo (no se reutiliza `_FakeConn` de `test_adapters.py` para no
tocarlo). Mismo esquema que `services/handover/tests/test_repository.py`
(`test_postgres_repository_serializes_statements_across_threads`,
`test_postgres_repository_connects_once_with_concurrent_first_use`):

- El cursor falso, en `execute`, incrementa un contador `inside`, registra `max`, anota
  `repo._lock.locked()`, duerme ~2 ms y decrementa.
- Dos hilos con `threading.Barrier(2)` arrancan a la vez y llaman varias veces a métodos
  públicos (`add_event`, `last_messages`, `mark_update_if_new`, `get_or_create_contact`).
- `join(timeout=5)` y aserción `not thread.is_alive()` para que un bloqueo falle en lugar de
  colgar la suite.

## 5. Alternativas descartadas

- **Pool de conexiones o conexión por petición.** Más código y posiblemente dependencias para un
  tráfico bajo; el humano eligió el candado (D2 de la #12), igual que en handover.
- **`threading.RLock`.** Innecesario: no hay reentrada; un `Lock` hace que una reentrada
  accidental futura se note (bloqueo en tests) en lugar de ocultarse.
- **Candado en cada método público en vez de en `_run`.** Duplica código y deja fuera
  `_connection()`; `_run` es el único punto que toca la conexión.

## 6. Defaults registrados

- Nombre del atributo `_lock`, igual que en handover, para que los tests puedan comprobar
  `locked()`.
- Archivo de tests nuevo en vez de ampliar `test_adapters.py`: evita cualquier cambio en tests
  existentes (criterio 3).
