"""Almacenamiento de fragmentos: interfaz, versión en memoria y pgvector (pg8000)."""
from __future__ import annotations

from dataclasses import replace
from typing import Any, Callable, Protocol
from urllib.parse import unquote, urlparse

from lazaro_contracts import SearchResult

from ..domain import Chunk, cosine_similarity


class ChunkRepository(Protocol):
    def add_manual(self, manual_id: str, name: str, chunks: list[Chunk]) -> None: ...

    def search(
        self, query_vector: list[float], top_k: int, threshold: float
    ) -> list[SearchResult]: ...

    def set_active(self, chunk_id: str, active: bool) -> None: ...


class FakeChunkRepository:
    def __init__(self) -> None:
        self.manuals: dict[str, str] = {}
        self.chunks: list[Chunk] = []

    def add_manual(self, manual_id: str, name: str, chunks: list[Chunk]) -> None:
        self.manuals[manual_id] = name
        self.chunks.extend(chunks)

    def search(
        self, query_vector: list[float], top_k: int, threshold: float
    ) -> list[SearchResult]:
        scored = [
            (cosine_similarity(query_vector, c.embedding), c) for c in self.chunks if c.active
        ]
        scored = [(s, c) for s, c in scored if s >= threshold]
        scored.sort(key=lambda sc: sc[0], reverse=True)
        return [
            SearchResult(chunk_id=c.chunk_id, manual=c.manual, text=c.text, score=min(s, 1.0))
            for s, c in scored[:top_k]
        ]

    def set_active(self, chunk_id: str, active: bool) -> None:
        for i, c in enumerate(self.chunks):
            if c.chunk_id == chunk_id:
                self.chunks[i] = replace(c, active=active)


def _pg_connect(database_url: str) -> Any:
    import pg8000.dbapi

    parsed = urlparse(database_url)
    return pg8000.dbapi.connect(
        user=unquote(parsed.username or ""),
        password=unquote(parsed.password or ""),
        host=parsed.hostname or "localhost",
        port=parsed.port or 5432,
        database=(parsed.path or "/").lstrip("/"),
    )


def _vector_literal(vector: list[float]) -> str:
    return "[" + ",".join(repr(float(x)) for x in vector) + "]"


class PgVectorChunkRepository:
    """SQL siempre parametrizado (%s); la conexión se abre en el primer uso."""

    def __init__(
        self,
        database_url: str,
        dim: int = 1536,
        connect: Callable[[], Any] | None = None,
    ) -> None:
        self._database_url = database_url
        self._dim = int(dim)
        self._connect = connect or (lambda: _pg_connect(self._database_url))
        self._conn: Any = None

    def _schema(self) -> tuple[str, ...]:
        return (
            "CREATE EXTENSION IF NOT EXISTS vector",
            "CREATE TABLE IF NOT EXISTS manuals ("
            "manual_id TEXT PRIMARY KEY, name TEXT NOT NULL, "
            "created_at TIMESTAMPTZ DEFAULT now())",
            "CREATE TABLE IF NOT EXISTS chunks ("
            "chunk_id TEXT PRIMARY KEY, manual_id TEXT REFERENCES manuals(manual_id), "
            f"ord INT, text TEXT, embedding vector({self._dim}), "
            "active BOOLEAN DEFAULT TRUE)",
        )

    def _connection(self) -> Any:
        if self._conn is None:
            conn = self._connect()
            cur = conn.cursor()
            for statement in self._schema():
                cur.execute(statement)
            conn.commit()
            self._conn = conn
        return self._conn

    def add_manual(self, manual_id: str, name: str, chunks: list[Chunk]) -> None:
        conn = self._connection()
        cur = conn.cursor()
        try:
            cur.execute(
                "INSERT INTO manuals (manual_id, name) VALUES (%s, %s)", (manual_id, name)
            )
            for c in chunks:
                cur.execute(
                    "INSERT INTO chunks (chunk_id, manual_id, ord, text, embedding, active) "
                    "VALUES (%s, %s, %s, %s, CAST(%s AS vector), %s)",
                    (c.chunk_id, c.manual_id, c.order, c.text, _vector_literal(c.embedding), c.active),
                )
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    def search(
        self, query_vector: list[float], top_k: int, threshold: float
    ) -> list[SearchResult]:
        conn = self._connection()
        cur = conn.cursor()
        try:
            cur.execute(
                "SELECT chunk_id, manual, text, score FROM ("
                "SELECT c.chunk_id AS chunk_id, m.name AS manual, c.text AS text, "
                "1 - (c.embedding <=> CAST(%s AS vector)) AS score "
                "FROM chunks c JOIN manuals m ON m.manual_id = c.manual_id "
                "WHERE c.active) s "
                "WHERE score >= %s ORDER BY score DESC LIMIT %s",
                (_vector_literal(query_vector), threshold, top_k),
            )
            rows = list(cur.fetchall())
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        return [
            SearchResult(chunk_id=r[0], manual=r[1], text=r[2], score=max(-1.0, min(1.0, float(r[3]))))
            for r in rows
        ]

    def set_active(self, chunk_id: str, active: bool) -> None:
        conn = self._connection()
        cur = conn.cursor()
        try:
            cur.execute("UPDATE chunks SET active = %s WHERE chunk_id = %s", (active, chunk_id))
            conn.commit()
        except Exception:
            conn.rollback()
            raise
