"""Dominio del servicio rag: errores, detección de formato, fragmentación e ingesta/búsqueda.

Sin IO: la extracción de texto y los adaptadores entran como dependencias.
"""
from __future__ import annotations

import math
import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable

from lazaro_contracts import ManualUploadResponse, SearchRequest, SearchResult

if TYPE_CHECKING:  # solo para anotaciones; evita importaciones circulares
    from .adapters.embeddings import EmbeddingsClient
    from .adapters.repository import ChunkRepository
    from .config import Settings


class DomainError(Exception):
    """Base de los errores de negocio; cada subclase fija su código y su HTTP status."""

    code = "domain_error"
    status_code = 400


class UnsupportedFormat(DomainError):
    code = "unsupported_format"
    status_code = 415


class EmptyDocument(DomainError):
    code = "empty_document"
    status_code = 422


class EmbeddingsUnavailable(DomainError):
    code = "internal_error"
    status_code = 500


@dataclass(frozen=True)
class Chunk:
    chunk_id: str
    manual_id: str
    manual: str
    order: int
    text: str
    embedding: list[float]
    active: bool = True


def detect_format(data: bytes) -> str:
    """Decide por el contenido: 'pdf' o 'docx'. Vacío -> EmptyDocument; otro -> UnsupportedFormat."""
    if len(data) == 0:
        raise EmptyDocument("El archivo está vacío.")
    if data.startswith(b"%PDF-"):
        return "pdf"
    if data.startswith(b"PK\x03\x04"):
        import io
        import zipfile

        try:
            with zipfile.ZipFile(io.BytesIO(data)) as zf:
                if "word/document.xml" in zf.namelist():
                    return "docx"
        except zipfile.BadZipFile:
            pass
    raise UnsupportedFormat("Solo se aceptan archivos PDF o DOCX.")


def chunk_text(text: str, size: int, overlap: int) -> list[str]:
    """Ventana deslizante de `size` caracteres con paso `size - overlap` sobre texto normalizado."""
    normalized = " ".join(text.split())
    if not normalized:
        return []
    step = max(size - overlap, 1)
    chunks: list[str] = []
    start = 0
    while start < len(normalized):
        piece = normalized[start:start + size]
        if piece.strip():
            chunks.append(piece)
        if start + size >= len(normalized):
            break
        start += step
    return chunks


def cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def ingest_manual(
    data: bytes,
    name: str,
    settings: "Settings",
    embeddings: "EmbeddingsClient",
    repository: "ChunkRepository",
    new_id: Callable[[], str] = lambda: uuid.uuid4().hex,
    extract: Callable[[bytes, str], str] | None = None,
) -> ManualUploadResponse:
    if extract is None:
        from .extraction import extract_text as extract

    fmt = detect_format(data)
    text = extract(data, fmt)
    pieces = chunk_text(text, settings.chunk_size, settings.chunk_overlap)
    if not pieces:
        raise EmptyDocument("El documento no contiene texto extraíble.")
    try:
        vectors = embeddings.embed(pieces)
    except EmbeddingsUnavailable:
        raise
    except Exception as exc:
        raise EmbeddingsUnavailable("No se pudieron calcular los embeddings.") from exc
    if len(vectors) != len(pieces):
        raise EmbeddingsUnavailable("Respuesta de embeddings inesperada.")
    manual_id = new_id()
    chunks = [
        Chunk(
            chunk_id=f"{manual_id}-{order}",
            manual_id=manual_id,
            manual=name,
            order=order,
            text=piece,
            embedding=list(vector),
            active=True,
        )
        for order, (piece, vector) in enumerate(zip(pieces, vectors), start=1)
    ]
    repository.add_manual(manual_id, name, chunks)
    return ManualUploadResponse(manual_id=manual_id, chunks=len(chunks))


def search_chunks(
    request: SearchRequest,
    settings: "Settings",
    embeddings: "EmbeddingsClient",
    repository: "ChunkRepository",
) -> list[SearchResult]:
    """`request.category` se ignora (S7)."""
    try:
        vectors = embeddings.embed([request.query])
    except EmbeddingsUnavailable:
        raise
    except Exception as exc:
        raise EmbeddingsUnavailable("No se pudo calcular el embedding de la consulta.") from exc
    threshold = settings.rag_similarity_threshold
    found = repository.search(vectors[0], request.top_k, threshold)
    kept = [r for r in found if r.score >= threshold]
    kept.sort(key=lambda r: r.score, reverse=True)
    return kept[: request.top_k]
