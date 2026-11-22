"""Adaptadores externos del servidor MCP: RAG, Postgres y auditoría."""
from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Any, Callable, Protocol
from urllib.parse import unquote, urlparse

import httpx
from lazaro_contracts import SERVICE_TOKEN_HEADER

from .tools import AuditRecord

logger = logging.getLogger(__name__)

_SELECT_OFFERS_SQL = (
    "SELECT id, destino, titulo, precio_cop, valido_desde, valido_hasta, "
    "es_demo, etiqueta FROM demo_ofertas "
    "WHERE destino ILIKE %s AND valido_hasta >= %s AND valido_desde <= %s "
    "ORDER BY valido_desde, id LIMIT %s"
)

_INSERT_AUDIT_SQL = (
    "INSERT INTO mcp_auditoria "
    "(herramienta, args_sha256, filas, estado, cliente_sha256, creado_en) "
    "VALUES (%s, %s, %s, %s, %s, %s)"
)


def pg_connect(database_url: str) -> Any:
    import pg8000.dbapi

    parsed = urlparse(database_url)
    return pg8000.dbapi.connect(
        user=unquote(parsed.username or ""),
        password=unquote(parsed.password or ""),
        host=parsed.hostname or "localhost",
        port=parsed.port or 5432,
        database=(parsed.path or "/").lstrip("/"),
    )


def _jsonable(value: object) -> object:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return value


class RagSearch(Protocol):
    def search(self, consulta: str, top_k: int) -> list[dict[str, Any]]: ...


class HttpRagSearch:
    """R4: única llamada externa permitida, `POST /search` con token."""

    def __init__(self, base_url: str, service_token: str, timeout: float = 10) -> None:
        self._base_url = base_url.rstrip("/")
        self._service_token = service_token
        self._timeout = timeout

    def search(self, consulta: str, top_k: int) -> list[dict[str, Any]]:
        try:
            response = httpx.post(
                f"{self._base_url}/search",
                json={"query": consulta, "top_k": top_k},
                headers={SERVICE_TOKEN_HEADER: self._service_token},
                timeout=self._timeout,
            )
            response.raise_for_status()
            data = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            logger.error("rag_search_failed code=%s", type(exc).__name__)
            raise RuntimeError("RAG no disponible.") from None
        if not isinstance(data, list):
            logger.error("rag_search_invalid_response")
            raise RuntimeError("RAG no disponible.")
        return [dict(item) for item in data if isinstance(item, dict)]


class FakeRagSearch:
    def __init__(
        self,
        results: list[dict[str, Any]] | None = None,
        fail: bool = False,
    ) -> None:
        self.results = list(results or [])
        self.fail = fail
        self.calls: list[tuple[str, int]] = []

    def search(self, consulta: str, top_k: int) -> list[dict[str, Any]]:
        self.calls.append((consulta, top_k))
        if self.fail:
            raise RuntimeError("RAG caído")
        return [dict(row) for row in self.results]


class DemoOffersStore(Protocol):
    def buscar(
        self, destino: str, desde: date, hasta: date, max_rows: int
    ) -> list[dict[str, Any]]: ...


class PostgresDemoOffers:
    """R3: SELECT parametrizado dentro de una transacción READ ONLY."""

    def __init__(
        self, database_url: str, connect: Callable[[], Any] | None = None
    ) -> None:
        self._database_url = database_url
        self._connect = connect or (lambda: pg_connect(self._database_url))

    def buscar(
        self, destino: str, desde: date, hasta: date, max_rows: int
    ) -> list[dict[str, Any]]:
        connection = self._connect()
        cursor = connection.cursor()
        try:
            cursor.execute("SET TRANSACTION READ ONLY")
            cursor.execute(
                _SELECT_OFFERS_SQL,
                (f"%{destino}%", desde, hasta, int(max_rows)),
            )
            description = getattr(cursor, "description", None) or []
            columns = [entry[0] for entry in description]
            return [
                {column: _jsonable(value) for column, value in zip(columns, row)}
                for row in cursor.fetchall()
            ]
        finally:
            try:
                cursor.execute("ROLLBACK")
            except Exception:
                logger.warning("demo_offers_rollback_failed")
            try:
                connection.close()
            except Exception:
                logger.warning("demo_offers_close_failed")


class FakeDemoOffers:
    def __init__(
        self,
        rows: list[dict[str, Any]] | None = None,
        fail: bool = False,
    ) -> None:
        self.rows = list(rows or [])
        self.fail = fail
        self.calls: list[tuple[str, date, date, int]] = []

    def buscar(
        self, destino: str, desde: date, hasta: date, max_rows: int
    ) -> list[dict[str, Any]]:
        self.calls.append((destino, desde, hasta, max_rows))
        if self.fail:
            raise RuntimeError("Postgres caído")
        return [dict(row) for row in self.rows]


class AuditSink(Protocol):
    def record(self, record: AuditRecord) -> None: ...


class PostgresAuditSink:
    """R9, R10: guarda hashes y métricas, nunca valores ni filas."""

    def __init__(
        self, database_url: str, connect: Callable[[], Any] | None = None
    ) -> None:
        self._database_url = database_url
        self._connect = connect or (lambda: pg_connect(self._database_url))

    def record(self, record: AuditRecord) -> None:
        connection = self._connect()
        try:
            cursor = connection.cursor()
            cursor.execute(
                _INSERT_AUDIT_SQL,
                (
                    record.herramienta,
                    record.args_sha256,
                    record.filas,
                    record.estado,
                    record.cliente_sha256,
                    record.creado_en,
                ),
            )
            connection.commit()
        finally:
            connection.close()


class FakeAuditSink:
    def __init__(self, fail: bool = False) -> None:
        self.fail = fail
        self.records: list[AuditRecord] = []

    def record(self, record: AuditRecord) -> None:
        if self.fail:
            raise RuntimeError("Auditoría no disponible.")
        self.records.append(record)
