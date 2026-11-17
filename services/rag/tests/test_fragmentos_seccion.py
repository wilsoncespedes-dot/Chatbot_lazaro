"""Pruebas del troceo por secciones y frases y de la extracción DOCX (#63)."""
from __future__ import annotations

import io
from pathlib import Path

from rag.domain import chunk_text
from rag.extraction import extract_text

MANUAL = (Path(__file__).resolve().parents[3] / "eval" / "manual_ejemplo" / "manual_ejemplo.md").read_text(
    encoding="utf-8"
)


# --- R1, R2: secciones y títulos -------------------------------------------------


def test_each_chunk_carries_its_section_path():
    """R1, R2: un fragmento por sección corta, con la ruta de títulos al inicio."""
    chunks = chunk_text(MANUAL, 1000, 200)
    support = [c for c in chunks if "Horarios de soporte: " in c]
    assert len(support) == 1
    assert support[0].startswith("Manual de ejemplo: Facturador Demo > Horarios de soporte: El soporte")
    assert "copia de seguridad" not in support[0]


def test_sections_are_never_mixed():
    """R1: una sección no comparte fragmento con la siguiente."""
    text = "## Uno\nPrimera frase. Segunda frase.\n## Dos\nTercera frase."
    assert chunk_text(text, 1000, 200) == [
        "Uno: Primera frase. Segunda frase.",
        "Dos: Tercera frase.",
    ]


def test_numbered_headings_but_not_numbered_steps():
    """R2: "2.1 Anulación" es título; "1. Ingresa al menú" es un paso."""
    text = "2.1 Anulación de facturas\n1. Ingresa al menú Ventas\n2. Pulsa Anular"
    assert chunk_text(text, 1000, 200) == [
        "2.1 Anulación de facturas: 1. Ingresa al menú Ventas 2. Pulsa Anular"
    ]


def test_only_last_two_heading_levels_are_kept():
    """R2: la ruta conserva los dos niveles más profundos."""
    text = "# A\n## B\n### C\nTexto."
    assert chunk_text(text, 1000, 200) == ["B > C: Texto."]


# --- R3, R4: tamaño, frases y solapamiento ---------------------------------------


def test_chunks_cut_on_sentences_within_size_and_overlap():
    """R3, R4: no se cortan frases y la última frase se repite si cabe en overlap."""
    sentences = [f"Frase número {i} del manual." for i in range(1, 13)]
    chunks = chunk_text("## Sec\n" + " ".join(sentences), 120, 40)
    assert len(chunks) > 1
    for chunk in chunks:
        assert len(chunk) <= 120
        assert chunk.startswith("Sec: ")
        assert chunk.endswith(".")
    for previous, following in zip(chunks, chunks[1:]):
        last = previous.rsplit(". ", 1)[-1]
        assert following.startswith("Sec: " + last)


def test_long_sentence_is_split_by_words_not_letters():
    """R3: una frase enorme se parte por palabras."""
    words = " ".join(f"palabra{i}" for i in range(60))
    chunks = chunk_text(words, 100, 20)
    assert all(len(c) <= 100 for c in chunks)
    for chunk in chunks:
        assert all(token.startswith("palabra") for token in chunk.split())


def test_heading_too_long_for_size_is_dropped_from_prefix():
    """R3: si el título no deja espacio, el fragmento va sin prefijo."""
    chunks = chunk_text("## " + "T" * 90 + "\nTexto corto.", 100, 20)
    assert chunks == ["Texto corto."]


# --- R5, R6: extracción DOCX ----------------------------------------------------


def _docx() -> bytes:
    from docx import Document

    doc = Document()
    doc.add_heading("Planes", level=1)
    doc.add_paragraph("Compara los planes disponibles.")
    doc.add_heading("Precios", level=2)
    table = doc.add_table(rows=2, cols=3)
    for i, value in enumerate(["Plan", "Usuarios", "Precio"]):
        table.rows[0].cells[i].text = value
    for i, value in enumerate(["Básico", "3", "100"]):
        table.rows[1].cells[i].text = value
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def test_docx_headings_become_markdown_and_rows_stay_together():
    """R5, R6"""
    text = extract_text(_docx(), "docx")
    lines = [line for line in text.splitlines() if line.strip()]
    assert "# Planes" in lines
    assert "## Precios" in lines
    assert "Plan | Usuarios | Precio" in lines
    assert "Básico | 3 | 100" in lines


def test_table_rows_are_sentences_in_chunks():
    """R6: cada fila de la tabla se trata como una frase."""
    text = "## Precios\nPlan | Usuarios | Precio\nBásico | 3 | 100"
    assert chunk_text(text, 1000, 200) == ["Precios: Plan | Usuarios | Precio. Básico | 3 | 100."]
