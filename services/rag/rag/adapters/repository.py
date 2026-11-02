"""Almacenamiento de fragmentos: interfaz, versión en memoria y pgvector (pg8000)."""
from __future__ import annotations

import re
import unicodedata
from dataclasses import replace
from typing import Any, Callable, Protocol
from urllib.parse import unquote, urlparse

from lazaro_contracts import ManualSummary, SearchResult

from ..domain import Chunk, ChunkNotFound, cosine_similarity

RRF_K = 60


def _lexical_tokens(text: str) -> list[str]:
    """Tokeniza sin acentos ni mayúsculas; aproxima el analizador español en tests."""
    normalized = unicodedata.normalize("NFKD", text.casefold())
    normalized = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    return re.findall(r"[a-z0-9]+", normalized)


def reciprocal_rank_fusion(
    semantic_ranks: dict[str, int],
    lexical_ranks: dict[str, int],
    k: int = RRF_K,
) -> dict[str, float]:
    """Combina rangos 1-based. El resultado solo ordena, nunca es el score de respuesta."""
    fused: dict[str, float] = {}
    for chunk_id in set(semantic_ranks) | set(lexical_ranks):
        score = 0.0
        if chunk_id in semantic_ranks:
            score += 1.0 / (k + semantic_ranks[chunk_id])
        if chunk_id in lexical_ranks:
            score += 1.0 / (k + lexical_ranks[chunk_id])
        fused[chunk_id] = score
    return fused


class ChunkRepository(Protocol):
    def add_manual(self, manual_id: str, name: str, chunks: list[Chunk]) -> None: ...

    def search(
        self, query_vector: list[float], top_k: int, threshold: float
    ) -> list[SearchResult]: ...

    def search_hybrid(
        self,
        query_vector: list[float],
        query_text: str,
        top_k: int,
        threshold: float,
        candidate_limit: int,
    ) -> list[SearchResult]: ...

    def set_active(self, chunk_id: str, active: bool) -> None: ...

    def exists(self, chunk_id: str) -> bool: ...

    def update_text(self, chunk_id: str, text: str, embedding: list[float]) -> Chunk: ...

    def list_manuals(self) -> list[ManualSummary]: ...

    def list_chunks(self, manual_id: str) -> list[Chunk] | None: ...

    def update_active(self, chunk_id: str, active: bool) -> Chunk: ...


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

    def search_hybrid(
        self,
        query_vector: list[float],
        query_text: str,
        top_k: int,
        threshold: float,
        candidate_limit: int,
    ) -> list[SearchResult]:
        active = [c for c in self.chunks if c.active]
        semantic = sorted(
            ((cosine_similarity(query_vector, c.embedding), c) for c in active),
            key=lambda pair: (-pair[0], pair[1].chunk_id),
        )
        semantic_scores = {
            c.chunk_id: max(-1.0, min(score, 1.0)) for score, c in semantic
        }
        semantic_ranks = {
            c.chunk_id: rank
            for rank, (_, c) in enumerate(semantic[:candidate_limit], start=1)
        }
        lexical_ranks = self._lexical_ranks(query_text, active, candidate_limit)
        fused = reciprocal_rank_fusion(semantic_ranks, lexical_ranks)
        accepted = [
            chunk_id
            for chunk_id in fused
            if semantic_scores.get(chunk_id, -1.0) >= threshold
        ]
        accepted.sort(
            key=lambda chunk_id: (
                -fused[chunk_id],
                -semantic_scores[chunk_id],
                chunk_id,
            )
        )
        by_id = {c.chunk_id: c for c in active}
        return [
            SearchResult(
                chunk_id=chunk_id,
                manual=by_id[chunk_id].manual,
                text=by_id[chunk_id].text,
                score=semantic_scores[chunk_id],
            )
            for chunk_id in accepted[:top_k]
        ]

    @staticmethod
    def _lexical_ranks(
        query_text: str, active: list[Chunk], candidate_limit: int
    ) -> dict[str, int]:
        terms = set(_lexical_tokens(query_text))
        if not terms:
            return {}
        scored = []
        for chunk in active:
            tokens = _lexical_tokens(chunk.text)
            matches = sum(tokens.count(term) for term in terms)
            if matches:
                scored.append((matches, chunk))
        scored.sort(key=lambda pair: (-pair[0], pair[1].chunk_id))
        return {
            chunk.chunk_id: rank
            for rank, (_, chunk) in enumerate(scored[:candidate_limit], start=1)
        }

    def set_active(self, chunk_id: str, active: bool) -> None:
        for i, c in enumerate(self.chunks):
            if c.chunk_id == chunk_id:
                self.chunks[i] = replace(c, active=active)

    def exists(self, chunk_id: str) -> bool:
        return any(c.chunk_id == chunk_id for c in self.chunks)

    def update_text(self, chunk_id: str, text: str, embedding: list[float]) -> Chunk:
        for i, c in enumerate(self.chunks):
            if c.chunk_id == chunk_id:
                updated = replace(c, text=text, embedding=list(embedding))
                self.chunks[i] = updated
                return updated
        raise ChunkNotFound("El fragmento no existe.")

    def list_manuals(self) -> list[ManualSummary]:
        """El más reciente primero: orden inverso al de inserción."""
        return [
            ManualSummary(
                manual_id=manual_id,
                name=name,
                chunks=sum(1 for c in self.chunks if c.manual_id == manual_id),
            )
            for manual_id, name in reversed(list(self.manuals.items()))
        ]

    def list_chunks(self, manual_id: str) -> list[Chunk] | None:
        if manual_id not in self.manuals:
            return None
        return sorted(
            (c for c in self.chunks if c.manual_id == manual_id),
            key=lambda c: c.order,
        )

    def update_active(self, chunk_id: str, active: bool) -> Chunk:
        for i, c in enumerate(self.chunks):
            if c.chunk_id == chunk_id:
                updated = replace(c, active=active)
                self.chunks[i] = updated
                return updated
        raise ChunkNotFound("El fragmento no existe.")


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
            "CREATE INDEX IF NOT EXISTS chunks_text_spanish_gin ON chunks "
            "USING GIN (to_tsvector('spanish', text)) WHERE active",
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

    def search_hybrid(
        self,
        query_vector: list[float],
        query_text: str,
        top_k: int,
        threshold: float,
        candidate_limit: int,
    ) -> list[SearchResult]:
        """Semántica + full-text español, unidas por chunk_id y ordenadas por RRF.

        El score que se devuelve es siempre la similitud semántica original
        (`1 - distancia coseno`); el RRF solo decide el orden de los candidatos.
        """
        conn = self._connection()
        cur = conn.cursor()
        vector = _vector_literal(query_vector)
        try:
            cur.execute(
                "WITH semantic AS ("
                "SELECT c.chunk_id AS chunk_id, "
                "1 - (c.embedding <=> CAST(%s AS vector)) AS score, "
                "ROW_NUMBER() OVER ("
                "ORDER BY c.embedding <=> CAST(%s AS vector), c.chunk_id) AS rank "
                "FROM chunks c WHERE c.active ORDER BY rank LIMIT %s), "
                "lexical AS ("
                "SELECT c.chunk_id AS chunk_id, "
                "1 - (c.embedding <=> CAST(%s AS vector)) AS score, "
                "ROW_NUMBER() OVER ("
                "ORDER BY ts_rank_cd(to_tsvector('spanish', c.text), "
                "websearch_to_tsquery('spanish', %s)) DESC, c.chunk_id) AS rank "
                "FROM chunks c WHERE c.active "
                "AND to_tsvector('spanish', c.text) @@ websearch_to_tsquery('spanish', %s) "
                "ORDER BY rank LIMIT %s), "
                "fused AS ("
                "SELECT COALESCE(s.chunk_id, l.chunk_id) AS chunk_id, "
                "COALESCE(s.score, l.score) AS score, "
                "COALESCE(1.0 / (60 + s.rank), 0) + COALESCE(1.0 / (60 + l.rank), 0) AS rrf "
                "FROM semantic s FULL OUTER JOIN lexical l ON s.chunk_id = l.chunk_id) "
                "SELECT c.chunk_id, m.name AS manual, c.text, f.score "
                "FROM fused f "
                "JOIN chunks c ON c.chunk_id = f.chunk_id "
                "JOIN manuals m ON m.manual_id = c.manual_id "
                "WHERE f.score >= %s "
                "ORDER BY f.rrf DESC, f.score DESC, f.chunk_id "
                "LIMIT %s",
                (
                    vector,
                    vector,
                    candidate_limit,
                    vector,
                    query_text,
                    query_text,
                    candidate_limit,
                    threshold,
                    top_k,
                ),
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

    def exists(self, chunk_id: str) -> bool:
        conn = self._connection()
        cur = conn.cursor()
        try:
            cur.execute("SELECT 1 FROM chunks WHERE chunk_id = %s", (chunk_id,))
            row = cur.fetchone()
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        return row is not None

    def update_text(self, chunk_id: str, text: str, embedding: list[float]) -> Chunk:
        """Texto y vector se escriben en la misma sentencia; los metadatos no se tocan."""
        conn = self._connection()
        cur = conn.cursor()
        try:
            cur.execute(
                "UPDATE chunks SET text = %s, embedding = CAST(%s AS vector) "
                "WHERE chunk_id = %s",
                (text, _vector_literal(embedding), chunk_id),
            )
            if cur.rowcount == 0:
                raise ChunkNotFound("El fragmento no existe.")
            cur.execute(
                "SELECT c.chunk_id, c.manual_id, m.name, c.ord, c.text, c.active "
                "FROM chunks c JOIN manuals m ON m.manual_id = c.manual_id "
                "WHERE c.chunk_id = %s",
                (chunk_id,),
            )
            row = cur.fetchone()
            if row is None:
                raise ChunkNotFound("El fragmento no existe.")
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        return Chunk(
            chunk_id=row[0],
            manual_id=row[1],
            manual=row[2],
            order=row[3],
            text=row[4],
            embedding=list(embedding),
            active=bool(row[5]),
        )

    def list_manuals(self) -> list[ManualSummary]:
        conn = self._connection()
        cur = conn.cursor()
        try:
            cur.execute(
                "SELECT m.manual_id, m.name, COUNT(c.chunk_id) "
                "FROM manuals m LEFT JOIN chunks c ON c.manual_id = m.manual_id "
                "GROUP BY m.manual_id, m.name, m.created_at "
                "ORDER BY m.created_at DESC, m.manual_id"
            )
            rows = list(cur.fetchall())
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        return [
            ManualSummary(manual_id=row[0], name=row[1], chunks=int(row[2]))
            for row in rows
        ]

    def list_chunks(self, manual_id: str) -> list[Chunk] | None:
        conn = self._connection()
        cur = conn.cursor()
        try:
            cur.execute(
                "SELECT 1 FROM manuals WHERE manual_id = %s", (manual_id,)
            )
            if cur.fetchone() is None:
                conn.commit()
                return None
            cur.execute(
                "SELECT c.chunk_id, c.manual_id, m.name, c.ord, c.text, c.active "
                "FROM chunks c JOIN manuals m ON m.manual_id = c.manual_id "
                "WHERE c.manual_id = %s ORDER BY c.ord",
                (manual_id,),
            )
            rows = list(cur.fetchall())
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        return [
            Chunk(
                chunk_id=row[0],
                manual_id=row[1],
                manual=row[2],
                order=row[3],
                text=row[4],
                embedding=[],
                active=bool(row[5]),
            )
            for row in rows
        ]

    def update_active(self, chunk_id: str, active: bool) -> Chunk:
        """Solo cambia `active`; el resto de columnas no aparece en el UPDATE."""
        conn = self._connection()
        cur = conn.cursor()
        try:
            cur.execute(
                "UPDATE chunks SET active = %s WHERE chunk_id = %s",
                (active, chunk_id),
            )
            if cur.rowcount == 0:
                raise ChunkNotFound("El fragmento no existe.")
            cur.execute(
                "SELECT c.chunk_id, c.manual_id, m.name, c.ord, c.text, c.active "
                "FROM chunks c JOIN manuals m ON m.manual_id = c.manual_id "
                "WHERE c.chunk_id = %s",
                (chunk_id,),
            )
            row = cur.fetchone()
            if row is None:
                raise ChunkNotFound("El fragmento no existe.")
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        return Chunk(
            chunk_id=row[0],
            manual_id=row[1],
            manual=row[2],
            order=row[3],
            text=row[4],
            embedding=[],
            active=bool(row[5]),
        )
