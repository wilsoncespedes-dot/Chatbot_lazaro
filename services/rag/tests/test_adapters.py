"""Tests de los adaptadores de embeddings y del repositorio pgvector (sin red ni DB)."""
from __future__ import annotations

import httpx
import pytest

from rag.adapters.embeddings import FakeEmbeddings, HttpEmbeddingsClient
from rag.adapters.repository import PgVectorChunkRepository
from rag.domain import Chunk, ChunkNotFound, EmbeddingsUnavailable, cosine_similarity


def test_fake_embeddings_is_deterministic():
    """R23: mismo texto -> mismo vector en instancias distintas."""
    assert FakeEmbeddings().embed(["hola mundo"]) == FakeEmbeddings().embed(["hola mundo"])


def test_fake_embeddings_same_text_cosine_one():
    """R24: textos iguales -> similitud coseno 1.0."""
    a, b = FakeEmbeddings().embed(["instalar modulo", "instalar modulo"])
    assert cosine_similarity(a, b) == pytest.approx(1.0)


def _client(handler, dim=3) -> HttpEmbeddingsClient:
    http = httpx.Client(transport=httpx.MockTransport(handler))
    return HttpEmbeddingsClient("http://emb/v1", "key", "m", dim, 1, client=http)


def test_http_embeddings_ok_parses_openai_format():
    """R22: el cliente real habla el formato /embeddings de OpenAI."""

    def handler(request):
        assert request.url.path == "/v1/embeddings"
        return httpx.Response(200, json={"data": [{"index": 0, "embedding": [1, 0, 0]}]})

    assert _client(handler).embed(["a"]) == [[1.0, 0.0, 0.0]]


def test_http_embeddings_error_raises_embeddings_unavailable():
    """R10: no 2xx, red caída, forma o dimensión inesperada -> EmbeddingsUnavailable."""

    def boom(request):
        raise httpx.ConnectError("caído")

    cases = [
        lambda r: httpx.Response(500, text="x"),
        boom,
        lambda r: httpx.Response(200, json={"foo": 1}),
        lambda r: httpx.Response(200, json={"data": [{"embedding": [1, 2]}]}),
    ]
    for handler in cases:
        with pytest.raises(EmbeddingsUnavailable):
            _client(handler).embed(["a"])


class FakeConn:
    def __init__(self, rows=None, fail_on: str | None = None):
        self.executed: list = []
        self.rows = rows or []
        self.fail_on = fail_on
        self.rollbacks = 0

    def cursor(self):
        return self

    def execute(self, sql, params=()):
        if self.fail_on and sql.startswith(self.fail_on):
            raise RuntimeError("db")
        self.executed.append((sql, params))

    def fetchall(self):
        return self.rows

    def commit(self):
        pass

    def rollback(self):
        self.rollbacks += 1


SECRET = "TEXTO-SECRETO-DEL-MANUAL'; DROP TABLE chunks;--"


def test_pgvector_repository_uses_parameters_only():
    """R25: el texto de manuales y consultas va en parámetros, nunca en el SQL."""
    conn = FakeConn()
    repo = PgVectorChunkRepository("postgresql://x", 3, connect=lambda: conn)
    repo.add_manual("m1", SECRET, [Chunk("m1-1", "m1", SECRET, 1, SECRET, [0.1, 0.2, 0.3])])
    repo.search([0.1, 0.2, 0.3], 5, 0.75)
    assert conn.executed
    for sql, _ in conn.executed:
        assert "TEXTO-SECRETO" not in sql and "DROP TABLE chunks;--" not in sql
    assert any(SECRET in params for _, params in conn.executed if params)


def test_pgvector_search_sql_filters_active_and_threshold():
    """R13, R16: el filtro de activo y umbral va en la consulta, con LIMIT y orden."""
    conn = FakeConn(rows=[("c1", "Manual", "texto", 0.9)])
    repo = PgVectorChunkRepository("postgresql://x", 3, connect=lambda: conn)
    results = repo.search([1.0, 0.0, 0.0], 4, 0.8)
    sql, params = conn.executed[-1]
    assert "c.active" in sql and "score >= %s" in sql and "ORDER BY score DESC" in sql
    assert "LIMIT %s" in sql and "<=>" in sql
    assert params[1:] == (0.8, 4)
    assert results[0].chunk_id == "c1" and results[0].score == pytest.approx(0.9)


def test_pgvector_add_manual_rolls_back_on_error():
    """R10: si falla un INSERT se revierte la transacción."""
    conn = FakeConn(fail_on="INSERT INTO chunks")
    repo = PgVectorChunkRepository("postgresql://x", 3, connect=lambda: conn)
    with pytest.raises(RuntimeError):
        repo.add_manual("m", "n", [Chunk("m-1", "m", "n", 1, "t", [0.0, 0.0, 1.0])])
    assert conn.rollbacks == 1


class UpdateConn:
    """Conexión falsa con rowcount y fetchone para la actualización de fragmentos."""

    def __init__(self, row=None, rowcount: int = 1):
        self.executed: list = []
        self.row = row
        self.rowcount = rowcount
        self.rollbacks = 0

    def cursor(self):
        return self

    def execute(self, sql, params=()):
        self.executed.append((sql, params))

    def fetchone(self):
        return self.row

    def commit(self):
        pass

    def rollback(self):
        self.rollbacks += 1


def test_pgvector_update_text_is_parameterized_and_keeps_metadata():
    """R6, R7: texto y vector se escriben juntos; el resto de columnas no se toca."""
    conn = UpdateConn(row=("c1", "m1", "Manual A", 2, SECRET, True))
    repo = PgVectorChunkRepository("postgresql://x", 3, connect=lambda: conn)
    updated = repo.update_text("c1", SECRET, [0.1, 0.2, 0.3])
    update_sql, update_params = next(
        (sql, params) for sql, params in conn.executed if sql.startswith("UPDATE chunks SET")
    )
    assert "text = %s" in update_sql
    assert "embedding = CAST(%s AS vector)" in update_sql
    assert "active" not in update_sql.split("SET", 1)[1]
    assert "INSERT" not in update_sql and "DELETE" not in update_sql
    assert SECRET not in update_sql and "DROP TABLE chunks;--" not in update_sql
    assert update_params[0] == SECRET
    assert updated.text == SECRET
    assert (updated.chunk_id, updated.manual_id, updated.manual, updated.order) == (
        "c1",
        "m1",
        "Manual A",
        2,
    )
    assert updated.active is True


def test_pgvector_update_text_missing_chunk_raises_not_found_and_rolls_back():
    """R9, R10: si no existe el id no se escribe nada y se revierte la transacción."""
    conn = UpdateConn(row=None, rowcount=0)
    repo = PgVectorChunkRepository("postgresql://x", 3, connect=lambda: conn)
    with pytest.raises(ChunkNotFound):
        repo.update_text("no-existe", "texto", [0.0, 0.0, 1.0])
    assert conn.rollbacks == 1

