"""SQL de `PostgresRepository.foreign_session_windows` sin parámetros NULL (#45)."""
from __future__ import annotations

from datetime import datetime, timezone

from orchestrator.adapters.repository import PostgresRepository
from orchestrator.memory import session_window

NOW = datetime(2026, 2, 3, 4, 5, 6, tzinfo=timezone.utc)
START = datetime(2026, 2, 1, 9, 0, tzinfo=timezone.utc)
LAST = datetime(2026, 2, 1, 9, 30, tzinfo=timezone.utc)
END = datetime(2026, 2, 1, 10, 0, tzinfo=timezone.utc)


class _IndeterminateDatatype(Exception):
    """Emula el 42P18: PostgreSQL no puede inferir el tipo de un parámetro NULL."""


class Cursor:
    def __init__(self, rows: list[tuple]) -> None:
        self.rows = rows
        self.statements: list[tuple[str, tuple]] = []

    def execute(self, sql: str, params: tuple = ()) -> None:
        self.statements.append((sql, tuple(params)))
        if "IS NULL" in sql and any(value is None for value in params):
            raise _IndeterminateDatatype("42P18")

    def fetchall(self) -> list[tuple]:
        return list(self.rows)


class Conn:
    def __init__(self, rows: list[tuple]) -> None:
        self._cursor = Cursor(rows)

    def cursor(self) -> Cursor:
        return self._cursor

    def commit(self) -> None:
        pass

    def rollback(self) -> None:
        pass


def _repo(rows: list[tuple]) -> tuple[PostgresRepository, Conn]:
    conn = Conn(rows)
    repo = PostgresRepository("postgresql://x", connect=lambda: conn)
    return repo, conn


def _session_queries(conn: Conn) -> list[tuple[str, tuple]]:
    return [
        (sql, params)
        for sql, params in conn._cursor.statements
        if "FROM client_sessions" in sql
    ]


def test_none_profile_filters_only_by_contact():
    """R1, R3: `profile_id=None` -> una sentencia por `contact_id`, sin NULL."""
    repo, conn = _repo([])

    repo.foreign_session_windows("c1", None, 30, NOW)

    queries = _session_queries(conn)
    assert len(queries) == 1
    sql, params = queries[0]
    assert "contact_id = %s" in sql
    assert params == ("c1",)
    assert "IS NULL" not in sql
    assert "profile_id <>" not in sql
    assert None not in params


def test_profile_filters_foreign_profiles():
    """R2, R3: `profile_id` no nulo -> `profile_id <> %s`, sin NULL."""
    repo, conn = _repo([])

    repo.foreign_session_windows("c1", "p1", 30, NOW)

    queries = _session_queries(conn)
    assert len(queries) == 1
    sql, params = queries[0]
    assert "contact_id = %s" in sql
    assert "profile_id <> %s" in sql
    assert params == ("c1", "p1")
    assert "IS NULL" not in sql
    assert None not in params


def test_none_profile_maps_rows_in_order():
    """R4: cada fila se mapea a `session_window` en el mismo orden (sin perfil)."""
    rows = [
        ("p2", START, LAST, None),
        ("p1", START, LAST, END),
    ]
    repo, _ = _repo(rows)

    result = repo.foreign_session_windows("c1", None, 30, NOW)

    assert result == [
        session_window(START, LAST, None, NOW, 30),
        session_window(START, LAST, END, NOW, 30),
    ]


def test_profile_maps_rows_in_order():
    """R4: cada fila se mapea a `session_window` en el mismo orden (con perfil)."""
    rows = [
        ("p2", START, LAST, None),
        ("p1", START, LAST, END),
    ]
    repo, _ = _repo(rows)

    result = repo.foreign_session_windows("c1", "p9", 30, NOW)

    assert result == [
        session_window(START, LAST, None, NOW, 30),
        session_window(START, LAST, END, NOW, 30),
    ]
