# Implementación — #18 candado_repositorio_orquestador

**Estado:** READY_FOR_REVIEW (implementado por OpenCode/DeepSeek en reintento 2026-11-01; `init.sh` verde).

## Cambios

- `services/orchestrator/orchestrator/adapters/repository.py`: `import threading`,
  `self._lock = threading.Lock()` en `PostgresRepository.__init__` y cuerpo de `_run` dentro de
  `with self._lock:`. Docstring de la clase actualizado. SQL, firmas, `_SCHEMA`, `_connection()`,
  `FakeRepository` y el `Protocol` sin cambios.
- `services/orchestrator/tests/test_repository_lock.py`: tres tests nuevos con conexión falsa
  propia (no se toca `test_adapters.py`).

## Trazabilidad

- R1 → `services/orchestrator/tests/test_repository_lock.py::test_postgres_repository_serializes_statements_across_threads`
- R2 → `services/orchestrator/tests/test_repository_lock.py::test_postgres_repository_serializes_statements_across_threads`
- R3 → `services/orchestrator/tests/test_repository_lock.py::test_postgres_repository_connects_once_with_concurrent_first_use`
- R4 → `services/orchestrator/tests/test_repository_lock.py::test_postgres_repository_releases_lock_after_error`
- R5 → `services/orchestrator/tests/test_adapters.py::test_postgres_repository_uses_parameters_only` (sin cambios)
- R6 → `services/orchestrator/tests/test_adapters.py::test_postgres_repository_connects_lazily` (sin cambios)
- R7 → suite existente de `services/orchestrator/tests/` sin cambios + los tres tests nuevos

## Tasks

T1-T5 completadas por OpenCode; T6 verificada por el implementer Claude (ver abajo).

## Resultado de `./init.sh` (implementer Claude, 2026-11-01)

- feature_list.json válido (18 features), specs presentes, ningún .env en git.
- pytest: **1017 passed**, 1 warning (deprecación httpx en starlette.testclient, ajena). Modo: nocturno.
- `git status services/orchestrator/tests/`: solo aparece nuevo `test_repository_lock.py` atribuible a esta
  feature; `test_adapters.py` sin cambios (las otras modificaciones de tests del orquestador vienen de
  features anteriores no commiteadas).
- OpenCode no modificó `feature_list.json` (#18 sigue `in_progress`).
- Intento previo bloqueado (OpenCode colgado) resuelto: este run terminó en ~2 min con `done`.
