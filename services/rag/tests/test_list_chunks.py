"""Tests de GET /manuals, GET /manuals/{id}/chunks y PATCH /chunks/{id}/active."""
from __future__ import annotations

import pytest
from lazaro_contracts import (
    ChunkItem,
    ChunkListResponse,
    ErrorResponse,
    ManualListResponse,
)

from rag.domain import Chunk

HEADERS = {"X-Service-Token": "svc-token"}


def _chunk(env, chunk_id: str, manual_id: str, manual: str, order: int, text: str,
           active: bool = True) -> Chunk:
    vector = env.embeddings.embed([text])[0]
    return Chunk(chunk_id, manual_id, manual, order, text, vector, active=active)


def _add_manual(env, manual_id: str, name: str, entries: list[tuple[str, bool]]) -> list[Chunk]:
    chunks = [
        _chunk(env, f"{manual_id}-{order}", manual_id, name, order, text, active)
        for order, (text, active) in enumerate(entries, start=1)
    ]
    env.repo.add_manual(manual_id, name, chunks)
    return chunks


def _error(response, status: int, code: str) -> dict:
    assert response.status_code == status
    body = response.json()
    ErrorResponse.model_validate(body)
    assert body["error"] == code
    return body


def _patch_active(env, chunk_id: str, payload, headers: dict | None = None):
    return env.client.patch(
        f"/chunks/{chunk_id}/active",
        json=payload,
        headers=HEADERS if headers is None else headers,
    )


def test_list_manuals_returns_newest_first_with_chunk_counts(env):
    """R2: GET /manuals devuelve manual_id, name y chunks, el más reciente primero."""
    _add_manual(env, "m1", "Manual Antiguo", [("uno", True)])
    _add_manual(env, "m2", "Manual Nuevo", [("dos", True), ("tres", False)])

    response = env.client.get("/manuals", headers=HEADERS)
    assert response.status_code == 200
    body = ManualListResponse.model_validate(response.json())
    assert [manual.manual_id for manual in body.root] == ["m2", "m1"]
    assert body.root[0].name == "Manual Nuevo"
    assert body.root[0].chunks == 2
    assert body.root[1].chunks == 1


def test_list_manuals_returns_empty_list(env):
    """R2: sin manuales la respuesta es el arreglo vacío."""
    response = env.client.get("/manuals", headers=HEADERS)
    assert response.status_code == 200
    assert ManualListResponse.model_validate(response.json()).root == []


def test_list_chunks_returns_all_active_and_inactive_in_order(env):
    """R3: todos los fragmentos del manual, activos e inactivos, en orden ascendente."""
    _add_manual(env, "m1", "Manual A", [("primero", True), ("segundo", False)])
    _add_manual(env, "m2", "Manual B", [("ajeno", True)])

    response = env.client.get("/manuals/m1/chunks", headers=HEADERS)
    assert response.status_code == 200
    body = ChunkListResponse.model_validate(response.json())
    assert [chunk.chunk_id for chunk in body.root] == ["m1-1", "m1-2"]
    assert [chunk.order for chunk in body.root] == [1, 2]
    assert [chunk.active for chunk in body.root] == [True, False]
    first = body.root[0]
    assert (first.manual_id, first.manual, first.text) == ("m1", "Manual A", "primero")


def test_list_chunks_unknown_manual_returns_404(env):
    """R4: un manual_id inexistente -> 404 not_found."""
    _error(env.client.get("/manuals/no-existe/chunks", headers=HEADERS), 404, "not_found")


def test_patch_active_false_and_true_keeps_text_embedding_manual_and_order(env):
    """R5: guarda el estado y no cambia texto, embedding, manual ni orden."""
    chunks = _add_manual(env, "m1", "Manual A", [("texto original", True)])
    original = chunks[0]

    response = _patch_active(env, "m1-1", {"active": False})
    assert response.status_code == 200
    body = ChunkItem.model_validate(response.json())
    assert body.active is False
    stored = env.repo.chunks[0]
    assert stored.active is False
    assert (stored.text, stored.embedding, stored.manual, stored.order, stored.manual_id) == (
        original.text,
        original.embedding,
        original.manual,
        original.order,
        original.manual_id,
    )

    response = _patch_active(env, "m1-1", {"active": True})
    assert response.status_code == 200
    assert ChunkItem.model_validate(response.json()).active is True
    assert env.repo.chunks[0].active is True


def test_patch_active_unknown_chunk_returns_404_without_changes(env):
    """R6: un chunk_id inexistente -> 404 not_found sin modificar otros fragmentos."""
    original = _add_manual(env, "m1", "Manual A", [("uno", True), ("dos", False)])
    _error(_patch_active(env, "no-existe", {"active": False}), 404, "not_found")
    assert env.repo.chunks == original


def test_patch_active_rejects_invalid_bodies_without_changes(env):
    """R7: sin active, no booleano o campos extra -> 422 validation_error."""
    original = _add_manual(env, "m1", "Manual A", [("uno", True)])
    invalid = [
        {},
        {"active": "true"},
        {"active": "false"},
        {"active": 1},
        {"active": 0},
        {"active": True, "extra": "x"},
    ]
    for payload in invalid:
        _error(_patch_active(env, "m1-1", payload), 422, "validation_error")
        assert env.repo.chunks == original


def test_new_routes_require_service_token(env):
    """R8: sin token o con token incorrecto -> 401 si leer ni modificar datos."""
    original = _add_manual(env, "m1", "Manual A", [("uno", True)])
    for headers in ({}, {"X-Service-Token": "mal"}):
        _error(env.client.get("/manuals", headers=headers), 401, "unauthorized")
        _error(
            env.client.get("/manuals/m1/chunks", headers=headers),
            401,
            "unauthorized",
        )
        _error(_patch_active(env, "m1-1", {"active": False}, headers=headers), 401,
               "unauthorized")
    assert env.repo.chunks == original


class _ListConn:
    def __init__(self, all_rows, one_row=(1,)):
        self.executed: list = []
        self.all_rows = all_rows
        self.one_row = one_row
        self.rollbacks = 0

    def cursor(self):
        return self

    def execute(self, sql, params=()):
        self.executed.append((sql, params))

    def fetchall(self):
        return list(self.all_rows)

    def fetchone(self):
        return self.one_row

    def commit(self):
        pass

    def rollback(self):
        self.rollbacks += 1


def test_pgvector_list_manuals_counts_chunks_and_orders_newest_first():
    """R2: la consulta agrupa por manual, cuenta fragmentos y ordena por fecha."""
    from rag.adapters.repository import PgVectorChunkRepository

    conn = _ListConn(all_rows=[("m1", "Manual A", 2)])
    repo = PgVectorChunkRepository("postgresql://x", 3, connect=lambda: conn)
    manuals = repo.list_manuals()
    sql, params = conn.executed[-1]
    assert "LEFT JOIN chunks" in sql and "COUNT(c.chunk_id)" in sql
    assert "ORDER BY m.created_at DESC" in sql
    assert params == ()
    assert (manuals[0].manual_id, manuals[0].name, manuals[0].chunks) == (
        "m1",
        "Manual A",
        2,
    )


def test_pgvector_list_chunks_is_parameterized_and_ordered():
    """R3: el manual_id va como parámetro y los fragmentos se ordenan por ord."""
    from rag.adapters.repository import PgVectorChunkRepository

    conn = _ListConn(
        all_rows=[("c1", "m1", "Manual A", 1, "texto", False)],
        one_row=(1,),
    )
    repo = PgVectorChunkRepository("postgresql://x", 3, connect=lambda: conn)
    chunks = repo.list_chunks("m1")
    sql, params = conn.executed[-1]
    assert sql.endswith("WHERE c.manual_id = %s ORDER BY c.ord")
    assert params == ("m1",)
    assert (chunks[0].chunk_id, chunks[0].order, chunks[0].active) == ("c1", 1, False)


def test_pgvector_list_chunks_unknown_manual_returns_none():
    """R4: si el manual no existe la consulta no devuelve fragmentos."""
    from rag.adapters.repository import PgVectorChunkRepository

    conn = _ListConn(all_rows=[], one_row=None)
    repo = PgVectorChunkRepository("postgresql://x", 3, connect=lambda: conn)
    assert repo.list_chunks("no-existe") is None
    selects = [sql for sql, _ in conn.executed if sql.startswith("SELECT")]
    assert selects == ["SELECT 1 FROM manuals WHERE manual_id = %s"]


class _UpdateConn:
    def __init__(self, row, rowcount: int = 1):
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


def test_pgvector_update_active_is_parameterized_and_only_updates_active():
    """R5: el UPDATE de active usa parámetros y no toca text ni embedding."""
    from rag.adapters.repository import PgVectorChunkRepository

    conn = _UpdateConn(row=("c1", "m1", "Manual A", 2, "texto", False))
    repo = PgVectorChunkRepository("postgresql://x", 3, connect=lambda: conn)
    updated = repo.update_active("c1", False)
    update_sql, update_params = next(
        (sql, params) for sql, params in conn.executed if sql.startswith("UPDATE chunks SET")
    )
    assert "SET active = %s" in update_sql
    assert "text" not in update_sql and "embedding" not in update_sql
    assert update_params == (False, "c1")
    assert updated.active is False
    assert (updated.chunk_id, updated.manual_id, updated.manual, updated.order, updated.text) == (
        "c1",
        "m1",
        "Manual A",
        2,
        "texto",
    )


def test_pgvector_update_active_missing_chunk_rolls_back():
    """R6: un chunk_id inexistente no se escribe y revierte la transacción."""
    from rag.adapters.repository import PgVectorChunkRepository
    from rag.domain import ChunkNotFound

    conn = _UpdateConn(row=None, rowcount=0)
    repo = PgVectorChunkRepository("postgresql://x", 3, connect=lambda: conn)
    with pytest.raises(ChunkNotFound):
        repo.update_active("no-existe", False)
    assert conn.rollbacks == 1
