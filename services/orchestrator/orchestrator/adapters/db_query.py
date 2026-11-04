"""Adaptador de consulta de lectura: conexión propia, READ ONLY y verificación."""
from __future__ import annotations

import logging
import threading
from typing import Any, Callable, Protocol

from ..db_query import DbQueryUnavailable, QueryResult, ValidatedQuery
from .repository import _pg_connect

logger = logging.getLogger(__name__)

_VIEW_KINDS_SQL = (
    "SELECT n.nspname || '.' || c.relname, c.relkind "
    "FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
    "WHERE n.nspname || '.' || c.relname = ANY(%s)"
)

_VIEW_COLUMNS_SQL = (
    "SELECT n.nspname || '.' || c.relname, a.attname "
    "FROM pg_attribute a JOIN pg_class c ON c.oid = a.attrelid "
    "JOIN pg_namespace n ON n.oid = c.relnamespace "
    "WHERE n.nspname || '.' || c.relname = ANY(%s) "
    "AND a.attnum > 0 AND NOT a.attisdropped"
)


def verify_view_catalog(
    cursor: Any, allowlist: dict[str, tuple[str, ...]]
) -> None:
    """R29: cada vista debe existir como `relkind = 'v'` con exactamente sus columnas."""
    names = list(allowlist)
    cursor.execute(_VIEW_KINDS_SQL, (names,))
    kinds = {row[0]: row[1] for row in cursor.fetchall()}
    for name in names:
        if kinds.get(name) != "v":
            logger.warning("db_query_catalog_invalid")
            raise DbQueryUnavailable("La configuración de vistas no es válida.")

    cursor.execute(_VIEW_COLUMNS_SQL, (names,))
    actual: dict[str, set[str]] = {}
    for name, column in cursor.fetchall():
        actual.setdefault(name, set()).add(column)
    for name, allowed in allowlist.items():
        if actual.get(name, set()) != set(allowed):
            logger.warning("db_query_catalog_invalid")
            raise DbQueryUnavailable("La configuración de vistas no es válida.")


class DbQueryClient(Protocol):
    def run(
        self, query: ValidatedQuery, max_rows: int, timeout_ms: int
    ) -> QueryResult: ...


class UnavailableDbQuery:
    """Cliente de emergencia cuando DB_QUERY_ENABLED está apagado; nunca se llama."""

    def run(
        self, query: ValidatedQuery, max_rows: int, timeout_ms: int
    ) -> QueryResult:
        raise DbQueryUnavailable("Las consultas de datos están deshabilitadas.")


class PostgresReadOnlyQuery:
    """Conexión separada de solo lectura; serializa el uso de su conexión."""

    def __init__(
        self,
        database_url: str,
        allowlist: dict[str, tuple[str, ...]],
        connect: Callable[[], Any] | None = None,
    ) -> None:
        self._database_url = database_url
        self._allowlist = dict(allowlist)
        self._connect = connect or (lambda: _pg_connect(self._database_url))
        self._lock = threading.Lock()
        self._verified = False

    def run(
        self, query: ValidatedQuery, max_rows: int, timeout_ms: int
    ) -> QueryResult:
        with self._lock:
            connection = None
            cursor = None
            try:
                connection = self._connect()
                cursor = connection.cursor()
                cursor.execute("SET TRANSACTION READ ONLY")
                cursor.execute(
                    f"SET LOCAL statement_timeout = {int(timeout_ms)}"
                )
                if not self._verified:
                    self._verify_catalog(cursor)
                    self._verified = True
                cursor.execute(
                    f"SELECT * FROM ({query.sql}) AS q LIMIT {int(max_rows) + 1}"
                )
                rows = list(cursor.fetchall())
                description = getattr(cursor, "description", None) or []
                columns = [entry[0] for entry in description]
                truncated = len(rows) > max_rows
                return QueryResult(
                    columns=columns, rows=rows[:max_rows], truncated=truncated
                )
            except DbQueryUnavailable:
                raise
            except Exception:
                logger.warning("db_query_failed")
                raise DbQueryUnavailable("No se pudo ejecutar la consulta.") from None
            finally:
                if cursor is not None:
                    try:
                        cursor.execute("ROLLBACK")
                    except Exception:
                        logger.warning("db_query_rollback_failed")
                if connection is not None:
                    try:
                        connection.close()
                    except Exception:
                        logger.warning("db_query_close_failed")

    def _verify_catalog(self, cursor: Any) -> None:
        verify_view_catalog(cursor, self._allowlist)


class FakeDbQuery:
    def __init__(
        self,
        result: QueryResult | None = None,
        fail: bool = False,
        error: Exception | None = None,
    ) -> None:
        self.result = result or QueryResult(columns=[], rows=[], truncated=False)
        self.fail = fail
        self.error = error
        self.calls: list[tuple[ValidatedQuery, int, int]] = []

    def run(
        self, query: ValidatedQuery, max_rows: int, timeout_ms: int
    ) -> QueryResult:
        self.calls.append((query, max_rows, timeout_ms))
        if self.error is not None:
            raise self.error
        if self.fail:
            raise DbQueryUnavailable("Consulta no disponible.")
        return self.result
