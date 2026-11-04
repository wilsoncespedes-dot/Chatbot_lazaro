"""Adaptador de consulta de datos propios del cliente con RLS (feature #39)."""
from __future__ import annotations

import logging
import threading
from typing import Any, Callable, Protocol

from ..db_query import DbQueryUnavailable, QueryResult, ValidatedQuery
from .db_query import verify_view_catalog
from .repository import _pg_connect

logger = logging.getLogger(__name__)

_ROLES_SQL = (
    "SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = current_user"
)


class ClientDataClient(Protocol):
    def run(
        self,
        query: ValidatedQuery,
        cliente_id: str,
        max_rows: int,
        timeout_ms: int,
    ) -> QueryResult: ...


class UnavailableClientData:
    """Cliente de emergencia cuando CLIENT_DATA_ENABLED está apagado; nunca se llama."""

    def run(
        self,
        query: ValidatedQuery,
        cliente_id: str,
        max_rows: int,
        timeout_ms: int,
    ) -> QueryResult:
        raise DbQueryUnavailable("La consulta de datos propios está deshabilitada.")


class PostgresClientDataQuery:
    """Conexión separada con rol de lectura, RLS por parámetro y sonda fallo-cerrado."""

    def __init__(
        self,
        database_url: str,
        allowlist: dict[str, tuple[str, ...]],
        rls_setting: str,
        connect: Callable[[], Any] | None = None,
    ) -> None:
        self._database_url = database_url
        self._allowlist = dict(allowlist)
        self._rls_setting = rls_setting
        self._connect = connect or (lambda: _pg_connect(self._database_url))
        self._lock = threading.Lock()
        self._verified = False

    def run(
        self,
        query: ValidatedQuery,
        cliente_id: str,
        max_rows: int,
        timeout_ms: int,
    ) -> QueryResult:
        with self._lock:
            connection = None
            cursor = None
            try:
                connection = self._connect()
                cursor = connection.cursor()
                cursor.execute("SET TRANSACTION READ ONLY")
                cursor.execute(f"SET LOCAL statement_timeout = {int(timeout_ms)}")
                if not self._verified:
                    self._verify_first_use(cursor)
                    self._verified = True
                cursor.execute(
                    "SELECT set_config(%s, %s, true)",
                    (self._rls_setting, cliente_id),
                )
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
                logger.warning("client_data_query_failed")
                raise DbQueryUnavailable(
                    "No se pudo ejecutar la consulta de datos propios."
                ) from None
            finally:
                if cursor is not None:
                    try:
                        cursor.execute("ROLLBACK")
                    except Exception:
                        logger.warning("client_data_rollback_failed")
                if connection is not None:
                    try:
                        connection.close()
                    except Exception:
                        logger.warning("client_data_close_failed")

    def _verify_first_use(self, cursor: Any) -> None:
        """R29–R31: catálogo, rol sin privilegios y sonda de RLS con setting vacío."""
        cursor.execute(_ROLES_SQL)
        rows = list(cursor.fetchall())
        if rows and (bool(rows[0][0]) or bool(rows[0][1])):
            logger.warning("client_data_role_invalid")
            raise DbQueryUnavailable("El rol de consulta no es válido.")

        verify_view_catalog(cursor, self._allowlist)

        cursor.execute("SELECT set_config(%s, '', true)", (self._rls_setting,))
        for view in self._allowlist:
            cursor.execute(f"SELECT 1 FROM {view} LIMIT 1")
            if list(cursor.fetchall()):
                logger.warning("client_data_rls_probe_failed")
                raise DbQueryUnavailable("La política de filas no está activa.")


class FakeClientData:
    """Simula RLS devolviendo solo las filas del cliente solicitado."""

    def __init__(
        self, rows_by_client: dict[str, QueryResult] | None = None
    ) -> None:
        self.rows_by_client = rows_by_client or {}
        self.calls: list[tuple[ValidatedQuery, str, int, int]] = []

    def run(
        self,
        query: ValidatedQuery,
        cliente_id: str,
        max_rows: int,
        timeout_ms: int,
    ) -> QueryResult:
        self.calls.append((query, cliente_id, max_rows, timeout_ms))
        return self.rows_by_client.get(
            cliente_id, QueryResult(columns=[], rows=[], truncated=False)
        )
