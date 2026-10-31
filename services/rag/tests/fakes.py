"""Reexporta los adaptadores falsos y generadores de documentos de prueba (sin red ni DB)."""
from __future__ import annotations

import io

from rag.adapters.embeddings import FakeEmbeddings
from rag.adapters.repository import FakeChunkRepository

__all__ = ["FakeEmbeddings", "FakeChunkRepository", "make_pdf", "make_docx", "make_blank_pdf"]


def make_pdf(text: str) -> bytes:
    """PDF mínimo de una página con `text` (construido a mano, con xref correcto)."""
    safe = text.replace("\\", "\\\\").replace("(", "\(").replace(")", "\)")
    stream = f"BT /F1 12 Tf 10 100 Td ({safe}) Tj ET".encode("latin-1")
    objs = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 600 200] /Contents 4 0 R "
        b"/Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for i, body in enumerate(objs, start=1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode() + body + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n".encode() + b"0000000000 65535 f \n"
    for off in offsets:
        out += f"{off:010d} 00000 n \n".encode()
    out += f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return bytes(out)


def make_blank_pdf() -> bytes:
    """PDF válido sin texto extraíble."""
    return make_pdf("")


def make_docx(text: str) -> bytes:
    from docx import Document

    doc = Document()
    doc.add_paragraph(text)
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()
