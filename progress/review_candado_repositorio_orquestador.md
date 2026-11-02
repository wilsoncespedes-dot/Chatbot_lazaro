# Review — feature 18 candado_repositorio_orquestador

**Veredicto:** APPROVED

## Trazabilidad requirements ↔ tests
- R1: [x] cubierto por `services/orchestrator/tests/test_repository_lock.py::test_postgres_repository_serializes_statements_across_threads` (`max == 1`)
- R2: [x] cubierto por `test_postgres_repository_serializes_statements_across_threads` (`repo._lock.locked()` anotado dentro de `execute`, todo `True`)
- R3: [x] cubierto por `test_postgres_repository_connects_once_with_concurrent_first_use` (`calls == [1]`, `CREATE TABLE` == `len(_SCHEMA)`)
- R4: [x] cubierto por `test_postgres_repository_releases_lock_after_error` (RuntimeError propagado, `rollbacks == [1]`, `_lock.locked() is False`, otro hilo termina)
- R5: [x] cubierto por `services/orchestrator/tests/test_adapters.py::test_postgres_repository_uses_parameters_only` (archivo sin cambios en `git diff`)
- R6: [x] cubierto por `test_adapters.py::test_postgres_repository_connects_lazily` (sin cambios)
- R7: [x] suite existente del orquestador intacta; el diff de `repository.py` solo añade `import threading`, `self._lock` y `with self._lock:` en `_run` (líneas ~4, ~139, ~152-162); SQL, firmas, `_SCHEMA`, `_connection()`, `FakeRepository` y `Protocol` sin tocar.

## Tasks completas
- T1: [x]
- T2: [x]
- T3: [x]
- T4: [x]
- T5: [x]
- T6: [ ] en `tasks.md`, pero justificado y ejecutado: `progress/impl_candado_repositorio_orquestador.md` documenta `./init.sh` verde (1017 passed) y el mapa R1-R7; confirmado por esta revisión. El leader puede marcarla `[x]` al cerrar.

## Tests eliminados o debilitados
Ninguno. `git diff --stat services/orchestrator/tests/` solo muestra `test_case_reply.py` (parametrize ampliado con 403, refuerzo) y `test_security.py` (+62 líneas), ambos de features anteriores sin commitear; `test_adapters.py` intacto; único archivo nuevo de esta feature: `test_repository_lock.py`.

## Checkpoints
- C1: [x] archivos base y docs presentes; `./init.sh` exit 0 (1017 passed, 1 warning ajeno de httpx/starlette).
- C2: [x] una sola feature `in_progress` (#18).
- C3: [x] cambio confinado a `services/orchestrator/`; sin dependencias nuevas (`threading` es stdlib); SQL sigue parametrizado `%s`; sin print/eval/TODOs.
- C4: [x] tests con conexión falsa, sin Postgres real; todos verdes.
- C5: [x] sin archivos sospechosos atribuibles a esta feature (los no trackeados restantes son de otras features/arnés).
- C6: [x] spec completo con 3 archivos; cada R<n> con test concreto.

## Cambios requeridos
Ninguno bloqueante.
