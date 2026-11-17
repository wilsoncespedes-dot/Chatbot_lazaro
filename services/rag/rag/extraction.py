"""Extracción de texto de PDF y DOCX (IO de ficheros)."""
from __future__ import annotations

import io

from .domain import EmptyDocument

# #63: estilos de título de Word en inglés y en español ("Heading 2", "Título 2").
_HEADING_STYLES = ("heading", "título", "titulo", "title")


def _docx_paragraph(paragraph) -> str:
    """R5: un párrafo con estilo de título sale como "## Título" para el troceo."""
    text = paragraph.text.strip()
    style = (getattr(paragraph.style, "name", "") or "").casefold()
    if not text or not style.startswith(_HEADING_STYLES):
        return paragraph.text
    digits = "".join(ch for ch in style if ch.isdigit())
    level = min(int(digits), 6) if digits else 1
    return f"{'#' * level} {text}"


def _docx_row(row) -> str:
    """R6: las celdas de una fila quedan juntas ("Plan | Usuarios | Precio");
    las celdas combinadas no se repiten."""
    cells: list[str] = []
    for cell in row.cells:
        text = " ".join(cell.text.split())
        if text and (not cells or cells[-1] != text):
            cells.append(text)
    return " | ".join(cells)


def extract_text(data: bytes, fmt: str) -> str:
    """Devuelve el texto del documento; un archivo ilegible lanza EmptyDocument."""
    try:
        if fmt == "pdf":
            from pypdf import PdfReader

            reader = PdfReader(io.BytesIO(data))
            return "\n".join((page.extract_text() or "") for page in reader.pages)
        if fmt == "docx":
            from docx import Document

            doc = Document(io.BytesIO(data))
            parts = [_docx_paragraph(p) for p in doc.paragraphs]
            for table in doc.tables:
                for row in table.rows:
                    parts.append(_docx_row(row))
            return "\n".join(parts)
    except Exception as exc:
        raise EmptyDocument("No se pudo leer el documento.") from exc
    raise EmptyDocument("Formato sin extractor.")
