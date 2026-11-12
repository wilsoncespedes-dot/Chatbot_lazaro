# #45 corregir_foreign_session_windows — Design

## Causa
`AND (%s IS NULL OR profile_id <> %s)` con `profile_id=None`: psycopg envía el
primer `%s` como parámetro sin tipo; PostgreSQL no puede deducirlo en
`$2 IS NULL` y lanza 42P18 (`IndeterminateDatatype`). El error sube como 500 en
`GET /asesor/cases/<id>` (llamada en `domain.py:3187`).

## Archivos a tocar
- `services/orchestrator/orchestrator/adapters/repository.py` — solo
  `PostgresRepository.foreign_session_windows` (~línea 2847).
- `services/orchestrator/tests/test_foreign_session_windows.py` — nuevo.

Sin cambios en `FakeRepository`, `domain.py`, firmas, contratos, esquema ni
configuración.

## Cambio
Firma igual:
`foreign_session_windows(self, contact_id: str, profile_id: str | None, idle_minutes: int, now: datetime) -> list[tuple[datetime, datetime, datetime]]`.

Ramas SQL separadas con un prefijo común:

```
base = ("SELECT profile_id, started_at, last_activity_at, ended_at "
        "FROM client_sessions WHERE contact_id = %s")
if profile_id is None:
    rows = self._run(base, (contact_id,), fetch=True)
else:
    rows = self._run(base + " AND profile_id <> %s", (contact_id, profile_id), fetch=True)
```

El mapeo de filas a `session_window(...)` no cambia. Sin nuevas excepciones:
los errores de la base se propagan como hoy vía `_run` (rollback + raise).

## Pruebas
Estilo del repositorio (p. ej. `test_identity_repository.py::test_postgres_identity_sql_is_parameterized`):
`PostgresRepository("postgresql://x", connect=lambda: Conn())` con `Conn`/`Cursor`
falsos que capturan `(sql, params)` y devuelven filas preparadas. El `Cursor`
falso emula el 42P18: lanza una excepción si la SQL contiene `IS NULL` aplicado
a `%s` y algún parámetro es `None`. No hay Postgres real en la suite; no se
añade (fuera de alcance para un bugfix).

## Alternativa descartada
`%s::text IS NULL OR profile_id <> %s::text`: también evita 42P18 y es
compatible con `profile_id TEXT`, pero sigue enviando `None` como parámetro y
duplica el valor; la condición `OR` con parámetro impide al planificador usar
el índice `client_sessions (profile_id)` de forma directa. Las ramas separadas
son igual de simples, más legibles y verificables por la SQL emitida.
