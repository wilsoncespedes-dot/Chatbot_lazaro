"""Tests de POST /search."""
from __future__ import annotations

from lazaro_contracts import SearchRequest, SearchResult

from rag.config import Settings
from rag.domain import Chunk, search_chunks


def _add(env, texts: list[str], name: str = "Manual A", start: int = 1) -> list[Chunk]:
    vectors = env.embeddings.embed(texts)
    chunks = [
        Chunk(f"m{start}-{i}", f"m{start}", name, i, t, v)
        for i, (t, v) in enumerate(zip(texts, vectors), start=1)
    ]
    env.repo.add_manual(f"m{start}", name, chunks)
    return chunks


def test_search_orders_by_score_desc(make_env):
    """R11: resultados ordenados por score descendente."""
    env = make_env(rag_similarity_threshold=0.1)
    _add(env, ["alfa beta gamma delta", "alfa beta", "alfa", "alfa beta gamma"])
    scores = [r["score"] for r in env.search("alfa beta").json()]
    assert len(scores) >= 2 and scores == sorted(scores, reverse=True)


def test_search_returns_at_most_top_k(make_env):
    """R12: como máximo top_k fragmentos."""
    env = make_env(rag_similarity_threshold=0.0)
    _add(env, [f"alfa palabra{i}" for i in range(6)])
    assert len(env.search("alfa", top_k=3).json()) == 3


def test_search_filters_below_threshold(make_env):
    """R13: solo fragmentos con score >= umbral."""
    env = make_env(rag_similarity_threshold=0.9)
    _add(env, ["alfa beta", "alfa beta gamma delta epsilon zeta"])
    results = env.search("alfa beta").json()
    assert [r["text"] for r in results] == ["alfa beta"]
    assert all(r["score"] >= 0.9 for r in results)


def test_search_returns_empty_when_no_chunk_passes_threshold(make_env):
    """R14: ningún fragmento alcanza el umbral -> 200 con []."""
    env = make_env(rag_similarity_threshold=0.75)
    _add(env, ["alfa beta", "gamma delta"])
    response = env.search("zzz qqq")
    assert response.status_code == 200 and response.json() == []


def test_search_does_not_return_closest_below_threshold(make_env):
    """R15: aunque existan fragmentos parecidos bajo el umbral, no se devuelven."""
    env = make_env(rag_similarity_threshold=0.99)
    _add(env, ["alfa beta gamma", "alfa delta"])
    assert env.search("alfa").json() == []

    # Defensa en profundidad: un repositorio defectuoso que ignora el umbral.
    class Leaky:
        def search(self, vector, top_k, threshold):
            return [SearchResult(chunk_id="x", manual="M", text="t", score=0.2)]

    out = search_chunks(
        SearchRequest(query="q", top_k=5),
        Settings(rag_similarity_threshold=0.75),
        env.embeddings,
        Leaky(),
    )
    assert out == []


def test_search_excludes_inactive_chunks(make_env):
    """R16: un fragmento inactivo nunca aparece, aunque supere el umbral."""
    env = make_env(rag_similarity_threshold=0.5)
    chunks = _add(env, ["alfa beta", "alfa beta"])
    env.repo.set_active(chunks[0].chunk_id, False)
    ids = [r["chunk_id"] for r in env.search("alfa beta").json()]
    assert ids == [chunks[1].chunk_id]


def test_search_ignores_category(make_env):
    """R17: `category` no cambia el resultado."""
    env = make_env(rag_similarity_threshold=0.5)
    _add(env, ["alfa beta", "gamma"])
    with_cat = env.search("alfa beta", category="facturacion").json()
    assert with_cat and with_cat == env.search("alfa beta").json()


def test_search_result_shape(make_env):
    """R11: cada elemento tiene {chunk_id, manual, text, score} válidos."""
    env = make_env(rag_similarity_threshold=0.5)
    _add(env, ["alfa beta"], name="Guía")
    results = env.search("alfa beta").json()
    assert len(results) == 1
    assert set(results[0]) == {"chunk_id", "manual", "text", "score"}
    SearchResult.model_validate(results[0])
    assert results[0]["manual"] == "Guía"
