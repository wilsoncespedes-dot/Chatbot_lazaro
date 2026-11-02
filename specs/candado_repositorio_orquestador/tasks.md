# Tasks — candado_repositorio_orquestador

Solo `services/orchestrator/`. Sin dependencias nuevas. Cada test lleva en su docstring el
`R<n>` de este spec que cubre (`"""R1, R2: ..."""`). Se ejecutan en orden.

## Código (`orchestrator/adapters/repository.py`)

- [x] T1 — Añadir `import threading` y `self._lock = threading.Lock()` al final de `PostgresRepository.__init__`. Cubre: R1.
- [x] T2 — Envolver el cuerpo entero de `_run` (incluidos `_connection()`, `cursor()`, `execute`, `fetchall`, `commit`/`rollback` y el `raise`) en `with self._lock:` tal como en design.md §3; actualizar el docstring de la clase. No cambiar SQL, firmas, `_SCHEMA`, `_connection()` ni `FakeRepository`. Cubre: R1, R2, R3, R4, R5, R6, R7.

## Tests nuevos (`tests/test_repository_lock.py`)

- [x] T3 — `test_postgres_repository_serializes_statements_across_threads`: conexión falsa cuyo `execute` mide `inside`/`max`, anota `repo._lock.locked()` y duerme ~2 ms; dos hilos con `Barrier(2)` llaman 5 veces cada uno a `add_event`, `last_messages`, `mark_update_if_new` y `get_or_create_contact` (el `fetchall` falso devuelve filas válidas para cada SELECT). Afirma sin errores en los hilos, hilos terminados tras `join(timeout=5)`, `max == 1` y todas las anotaciones de `locked()` en `True`. Cubre: R1, R2.
- [x] T4 — `test_postgres_repository_connects_once_with_concurrent_first_use`: `connect` falso que cuenta llamadas y duerme ~10 ms; dos hilos con `Barrier(2)` hacen su primera operación a la vez. Afirma una sola llamada a `connect` y que las sentencias `CREATE TABLE` registradas son exactamente `len(_SCHEMA)`. Cubre: R3.
- [x] T5 — `test_postgres_repository_releases_lock_after_error`: `execute` falso que lanza `RuntimeError` en una sentencia concreta; el llamador recibe ese `RuntimeError`, se registró `rollback`, `repo._lock.locked()` es `False` después, y una operación posterior desde otro hilo termina (join con timeout, hilo no vivo). Cubre: R4.

## Cierre

- [x] T6 — Ejecutar `./init.sh` (todo verde; `test_postgres_repository_uses_parameters_only` y `test_postgres_repository_connects_lazily` de `test_adapters.py` pasan sin cambios; `git diff --stat services/orchestrator/tests/` solo muestra el archivo nuevo) y escribir `progress/impl_candado_repositorio_orquestador.md` con el mapa R1-R7 → test. Cubre: R5, R6, R7.
