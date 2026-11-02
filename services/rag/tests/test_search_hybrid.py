"""Tests de la búsqueda híbrida de POST /search (#31)."""
from __future__ import annotations

import pytest
from lazaro_contracts import SearchRequest, SearchResponse, SearchResult

from rag.adapters.repository import (
    FakeChunkRepository,
    PgVectorChunkRepository,
    reciprocal_rank_fusion,
)
from rag.config import Settings
from rag.domain import Chunk, cosine_similarity, search_chunks
from rag_tests_fakes import FakeEmbeddings


def _add(
    repo: FakeChunkRepository,
    embeddings: FakeEmbeddings,
    texts: list[str],
    manual_id: str = "m1",
    name: str = "Manual A",
) -> list[Chunk]:
    vectors = embeddings.embed(texts)
    chunks = [
        Chunk(f"{manual_id}-{i}", manual_id, name, i, text, vector)
        for i, (text, vector) in enumerate(zip(texts, vectors), start=1)
    ]
    repo.add_manual(manual_id, name, chunks)
    return chunks


def _hybrid(
    repo: FakeChunkRepository,
    embeddings: FakeEmbeddings,
    query: str,
    *,
    top_k: int = 5,
    threshold: float = 0.0,
    candidate_limit: int = 50,
) -> list[SearchResult]:
    vector = embeddings.embed([query])[0]
    return repo.search_hybrid(vector, query, top_k, threshold, candidate_limit)


def test_default_flag_is_off_and_candidate_limit_is_50():
    """R5: el modo híbrido queda apagado por defecto y el límite es configurable."""
    settings = Settings()
    assert settings.rag_hybrid_enabled is False
    assert settings.rag_hybrid_candidate_limit == 50


def test_hybrid_unions_semantic_and_lexical_candidates():
    """R1: el resultado une candidatos de ambas fuentes, sin duplicar chunk_id."""
    repo = FakeChunkRepository()
    embeddings = FakeEmbeddings()
    chunks = _add(repo, embeddings, ["alfa zeta zeta zeta", "alfa"])

    # Con candidate_limit=1, la semántica elige el segundo y la textual el primero.
    results = _hybrid(repo, embeddings, "alfa", candidate_limit=1, threshold=0.3)

    assert {r.chunk_id for r in results} == {chunks[0].chunk_id, chunks[1].chunk_id}
    assert len(results) == 2


def test_hybrid_deduplicates_the_same_chunk_from_both_sources():
    """R1: un fragmento que aparece en las dos listas se devuelve una sola vez."""
    repo = FakeChunkRepository()
    embeddings = FakeEmbeddings()
    chunks = _add(repo, embeddings, ["alfa beta", "gamma delta"])
    results = _hybrid(repo, embeddings, "alfa beta")
    ids = [r.chunk_id for r in results]
    assert ids.count(chunks[0].chunk_id) == 1


def test_hybrid_orders_by_rrf_and_returns_the_semantic_score():
    """R2, R3: RRF ordena, pero el score devuelto es la similitud semántica."""
    repo = FakeChunkRepository()
    embeddings = FakeEmbeddings()
    texts = ["alfa alfa alfa zeta gamma", "alfa", "alfa alfa zeta"]
    chunks = _add(repo, embeddings, texts)

    results = _hybrid(repo, embeddings, "alfa", threshold=0.8)

    # El orden semántico sería m1-2, m1-1, m1-3; el RRF pone primero m1-1.
    assert [r.chunk_id for r in results] == ["m1-1", "m1-2", "m1-3"]
    query_vector = embeddings.embed(["alfa"])[0]
    expected = {
        c.chunk_id: cosine_similarity(query_vector, c.embedding) for c in chunks
    }
    assert results[0].score == pytest.approx(expected["m1-1"])
    assert results[0].score > 0.9  # No es el score RRF (~0.0325).


def test_rrf_k_is_60_and_combines_one_based_ranks():
    """R2: la constante RRF es 60 y suma los rangos de las dos listas."""
    fused = reciprocal_rank_fusion({"a": 1}, {"a": 1})
    assert fused["a"] == pytest.approx(2 / 61)


def test_hybrid_threshold_rejects_low_semantic_score_even_with_lexical_match():
    """R3: un acierto textual bajo el umbral semántico no se devuelve."""
    repo = FakeChunkRepository()
    embeddings = FakeEmbeddings()
    _add(repo, embeddings, ["alfa zeta zeta zeta"])

    assert _hybrid(repo, embeddings, "alfa", threshold=0.75) == []


def test_hybrid_threshold_keeps_only_semantic_candidates():
    """R3: se aceptan únicamente los fragmentos que superan el umbral."""
    repo = FakeChunkRepository()
    embeddings = FakeEmbeddings()
    _add(repo, embeddings, ["alfa alfa alfa zeta gamma", "alfa", "alfa alfa zeta"])

    results = _hybrid(repo, embeddings, "alfa", threshold=0.95)

    assert [r.chunk_id for r in results] == ["m1-2"]
    assert results[0].score == pytest.approx(1.0)


def test_hybrid_respects_top_k_and_active_filter():
    """R4: se respeta top_k y ningún fragmento inactivo aparece."""
    repo = FakeChunkRepository()
    embeddings = FakeEmbeddings()
    chunks = _add(
        repo,
        embeddings,
        ["alfa alfa alfa zeta gamma", "alfa", "alfa alfa zeta", "beta"],
    )
    repo.set_active(chunks[0].chunk_id, False)

    results = _hybrid(repo, embeddings, "alfa", top_k=2, threshold=0.0)

    assert len(results) == 2
    assert chunks[0].chunk_id not in {r.chunk_id for r in results}


def test_hybrid_returns_empty_when_both_sources_have_no_candidates():
    """R4: sin candidatos semánticos ni textuales la respuesta es vacía."""
    repo = FakeChunkRepository()
    assert _hybrid(repo, FakeEmbeddings(), "alfa") == []


def test_hybrid_keeps_semantic_candidates_when_only_the_lexical_side_is_empty():
    """R1, R3: sin coincidencia textual se devuelve el candidato semántico válido."""
    repo = FakeChunkRepository()
    embeddings = FakeEmbeddings()
    chunk = _add(repo, embeddings, ["beta gamma"])[0]
    query_vector = embeddings.embed(["alfa"])[0]
    semantic_score = cosine_similarity(query_vector, chunk.embedding)
    threshold = max(-1.0, min(semantic_score, 1.0))

    results = _hybrid(repo, embeddings, "alfa", threshold=threshold)

    assert [r.chunk_id for r in results] == [chunk.chunk_id]
    assert results[0].score == pytest.approx(semantic_score)


def test_hybrid_ignores_category_like_the_legacy_search(make_env):
    """R4: `category` conserva el comportamiento existente (se ignora)."""
    env = make_env(rag_hybrid_enabled=True, rag_similarity_threshold=0.5)
    _add(env.repo, env.embeddings, ["alfa beta"], manual_id="m9")

    with_category = env.search("alfa beta", category="facturacion").json()
    assert with_category and with_category == env.search("alfa beta").json()


def test_hybrid_mode_keeps_http_contract(make_env):
    """R5: en modo híbrido la ruta conserva token, validación y forma del contrato."""
    env = make_env(rag_hybrid_enabled=True, rag_similarity_threshold=0.5)
    _add(env.repo, env.embeddings, ["alfa beta"], manual_id="m9")

    response = env.search("alfa beta")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    SearchResponse.model_validate(data)
    assert set(data[0]) == {"chunk_id", "manual", "text", "score"}

    assert env.search("alfa beta", headers={}).status_code == 401
    invalid = env.client.post(
        "/search",
        json={"query": "alfa", "top_k": 0},
        headers={"X-Service-Token": env.settings.service_token},
    )
    assert invalid.status_code == 422


class _LegacyOnly:
    def search(self, query_vector, top_k, threshold):
        return [SearchResult(chunk_id="c1", manual="M", text="t", score=0.9)]

    def search_hybrid(self, *args, **kwargs):
        raise AssertionError("no debe usarse la búsqueda híbrida")


def test_disabled_flag_uses_the_existing_semantic_search():
    """R5: con el flag apagado se llama al método semántico existente."""
    results = search_chunks(
        SearchRequest(query="hola", top_k=5),
        Settings(rag_similarity_threshold=0.5),
        FakeEmbeddings(),
        _LegacyOnly(),
    )
    assert [r.chunk_id for r in results] == ["c1"]


class _RecordingHybrid:
    def __init__(self) -> None:
        self.calls: list[tuple] = []

    def search(self, *args, **kwargs):
        raise AssertionError("no debe usarse la búsqueda semántica")

    def search_hybrid(self, *args):
        self.calls.append(args)
        return [SearchResult(chunk_id="c1", manual="M", text="t", score=0.9)]


def test_hybrid_enabled_delegates_with_the_configured_parameters():
    """R1, R4, R5: el flag pasa query, top_k, umbral y el límite configurado."""
    repository = _RecordingHybrid()
    settings = Settings(
        rag_hybrid_enabled=True,
        rag_hybrid_candidate_limit=7,
        rag_similarity_threshold=0.5,
    )

    results = search_chunks(
        SearchRequest(query="hola mundo", top_k=3), settings, FakeEmbeddings(), repository
    )

    _, query_text, top_k, threshold, candidate_limit = repository.calls[0]
    assert query_text == "hola mundo"
    assert (top_k, threshold, candidate_limit) == (3, 0.5, 7)
    assert [r.chunk_id for r in results] == ["c1"]


class _HybridConn:
    def __init__(self, rows=None):
        self.executed: list[tuple[str, tuple]] = []
        self.rows = rows or []
        self.rollbacks = 0

    def cursor(self):
        return self

    def execute(self, sql, params=()):
        self.executed.append((sql, params))

    def fetchall(self):
        return self.rows

    def commit(self):
        pass

    def rollback(self):
        self.rollbacks += 1


def test_pgvector_hybrid_uses_spanish_full_text_and_parameterized_sql():
    """R1–R4: SQL con full-text español, pgvector, RRF y parámetros."""
    query = "alfa'); DROP TABLE chunks;--"
    conn = _HybridConn(rows=[("c1", "Manual", "texto", 0.9)])
    repo = PgVectorChunkRepository("postgresql://x", 3, connect=lambda: conn)

    results = repo.search_hybrid([1.0, 0.0, 0.0], query, 4, 0.75, 50)

    sql, params = conn.executed[-1]
    assert "websearch_to_tsquery('spanish'" in sql
    assert "ts_rank_cd" in sql
    assert "<=>" in sql
    assert "c.active" in sql
    assert "1.0 / (60 + s.rank)" in sql
    assert "ORDER BY f.rrf DESC" in sql
    assert "LIMIT %s" in sql
    # R1–R4: ambos CTE ordenan por rank antes de recortar a candidate_limit.
    assert sql.count("ORDER BY rank LIMIT %s") == 2
    assert query not in sql
    assert query in params
    assert params[-2:] == (0.75, 4)
    assert results[0].chunk_id == "c1" and results[0].score == pytest.approx(0.9)


def test_pgvector_schema_adds_the_active_spanish_gin_index():
    """R1: existe un índice GIN de texto español limitado a fragmentos activos."""
    repo = PgVectorChunkRepository("postgresql://x", 3, connect=lambda: _HybridConn())
    schema = repo._schema()
    assert any(
        "USING GIN" in statement and "to_tsvector('spanish'" in statement
        for statement in schema
    )
