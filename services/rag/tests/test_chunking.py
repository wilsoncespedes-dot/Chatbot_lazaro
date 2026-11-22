"""Tests de la fragmentación de texto."""
from __future__ import annotations

from rag.domain import chunk_text
from rag_tests_fakes import make_docx


def test_chunks_respect_size_and_overlap():
    """R3: fragmentos de <= size caracteres que comparten `overlap` con el anterior."""
    text = "".join(chr(97 + i % 26) for i in range(250))
    chunks = chunk_text(text, 100, 20)
    assert len(chunks) >= 3
    assert all(len(c) <= 100 for c in chunks)
    for prev, nxt in zip(chunks, chunks[1:]):
        assert prev[-20:] == nxt[:20]
    assert chunks[0] + "".join(c[20:] for c in chunks[1:]) == text


def test_short_text_gives_single_chunk():
    """R3: un texto corto da un solo fragmento; vacío no da ninguno."""
    assert chunk_text("hola   mundo\n", 100, 20) == ["hola mundo"]
    assert chunk_text("  \n ", 100, 20) == []


def test_chunks_prefer_sentence_boundaries_and_split_overlong_sentences_by_word():
    """R3, R4: respeta frases y mantiene el máximo al dividir una frase extensa."""
    text = "Primera oración. Segunda oración. " + "palabra " * 40

    chunks = chunk_text(text, 45, 10)

    assert len(chunks) > 1
    assert all(len(chunk) <= 45 for chunk in chunks)
    assert chunks[0] == "Primera oración. Segunda oración."
    assert "palabra palabra" in " ".join(chunks)


def test_chunk_order_starts_at_one(env):
    """R4: el orden de los fragmentos guardados empieza en 1 y es consecutivo."""
    env.upload(make_docx(" ".join(["texto"] * 100)))
    assert [c.order for c in env.repo.chunks] == list(range(1, len(env.repo.chunks) + 1))
    assert env.repo.chunks[0].order == 1
