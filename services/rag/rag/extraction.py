"""Extracción de texto de PDF y DOCX (IO de ficheros)."""
from __future__ import annotations

import io

from .domain import EmptyDocument


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
            parts = [p.text for p in doc.paragraphs]
            for table in doc.tables:
                for row in table.rows:
                    for cell in row.cells:
                        parts.append(cell.text)
            return "\n".join(parts)
    except Exception as exc:
        raise EmptyDocument("No se pudo leer el documento.") from exc
    raise EmptyDocument("Formato sin extractor.")
