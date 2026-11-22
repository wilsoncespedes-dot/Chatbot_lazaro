"""R11: configuración del umbral de similitud de búsqueda."""
from __future__ import annotations

from rag.config import Settings


def test_threshold_is_read_from_env(monkeypatch):
    """R11: RAG_SIMILARITY_THRESHOLD se lee del entorno sin cambiar el default."""
    monkeypatch.delenv("RAG_SIMILARITY_THRESHOLD", raising=False)
    assert Settings().rag_similarity_threshold == 0.75
    monkeypatch.setenv("RAG_SIMILARITY_THRESHOLD", "0.42")
    assert Settings().rag_similarity_threshold == 0.42
