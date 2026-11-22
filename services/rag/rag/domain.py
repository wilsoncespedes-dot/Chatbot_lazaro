"""Dominio del servicio rag: errores, detección de formato, fragmentación e ingesta/búsqueda.

Sin IO: la extracción de texto y los adaptadores entran como dependencias.
"""
from __future__ import annotations

import math
import re
import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable

from lazaro_contracts import (
    ChunkActiveRequest,
    ChunkItem,
    ChunkUpdateRequest,
    ChunkUpdateResponse,
    ManualSummary,
    ManualUploadResponse,
    SearchRequest,
    SearchResult,
)

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


class ChunkNotFound(DomainError):
    code = "not_found"
    status_code = 404


class ManualNotFound(DomainError):
    code = "not_found"
    status_code = 404


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
    """Agrupa frases y líneas; cae a ventanas de caracteres si no hay límites legibles."""
    normalized = " ".join(text.split())
    if not normalized:
        return []
    if size < 1:
        return []
    overlap = max(0, min(overlap, size - 1))

    def split_long_unit(unit: str) -> list[str]:
        words = unit.split()
        pieces: list[str] = []
        current = ""
        for word in words:
            if len(word) > size:
                if current:
                    pieces.append(current)
                    current = ""
                pieces.extend(word[index:index + size] for index in range(0, len(word), size))
                continue
            candidate = f"{current} {word}".strip()
            if len(candidate) > size:
                pieces.append(current)
                current = word
            else:
                current = candidate
        if current:
            pieces.append(current)
        return pieces

    units = [
        " ".join(part.split())
        for part in re.split(r"[\r\n]+|(?<=[.!?])\s+", text)
        if part.strip()
    ]
    if len(units) <= 1 and not re.search(r"[.!?\r\n]", text):
        step = max(size - overlap, 1)
        chunks: list[str] = []
        start = 0
        while start < len(normalized):
            chunks.append(normalized[start:start + size])
            if start + size >= len(normalized):
                break
            start += step
        return chunks

    bounded_units = [
        piece
        for unit in units
        for piece in (split_long_unit(unit) if len(unit) > size else [unit])
    ]
    chunks: list[str] = []
    current: list[str] = []
    current_length = 0
    for unit in bounded_units:
        extra = len(unit) + (1 if current else 0)
        if current and current_length + extra > size:
            chunks.append(" ".join(current))
            previous_context: list[str] = []
            context_length = 0
            for previous in reversed(current):
                candidate_length = len(previous) + (1 if previous_context else 0)
                if context_length + candidate_length > overlap:
                    break
                previous_context.insert(0, previous)
                context_length += candidate_length
            current = previous_context
            current_length = context_length
            extra = len(unit) + (1 if current else 0)
            if current and current_length + extra > size:
                current = []
                current_length = 0
                extra = len(unit)
        current.append(unit)
        current_length += extra
    if current:
        chunks.append(" ".join(current))
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
    if settings.rag_hybrid_enabled:
        found = repository.search_hybrid(
            vectors[0],
            request.query,
            request.top_k,
            threshold,
            settings.rag_hybrid_candidate_limit,
        )
        # El repositorio ya ordena por RRF; aquí solo se defiende el umbral semántico.
        return [r for r in found if r.score >= threshold][: request.top_k]
    found = repository.search(vectors[0], request.top_k, threshold)
    kept = [r for r in found if r.score >= threshold]
    kept.sort(key=lambda r: r.score, reverse=True)
    return kept[: request.top_k]


def list_manuals(repository: "ChunkRepository") -> list[ManualSummary]:
    """Manuales del más reciente al más antiguo (lo decide el repositorio)."""
    return repository.list_manuals()


def list_manual_chunks(
    manual_id: str, repository: "ChunkRepository"
) -> list[ChunkItem]:
    """Todos los fragmentos del manual, activos e inactivos, en orden ascendente."""
    chunks = repository.list_chunks(manual_id)
    if chunks is None:
        raise ManualNotFound("El manual no existe.")
    return [
        ChunkItem(
            chunk_id=chunk.chunk_id,
            manual_id=chunk.manual_id,
            manual=chunk.manual,
            order=chunk.order,
            text=chunk.text,
            active=chunk.active,
        )
        for chunk in chunks
    ]


def set_chunk_active(
    chunk_id: str, request: ChunkActiveRequest, repository: "ChunkRepository"
) -> ChunkItem:
    """Cambia solo `active`; texto, embedding, manual y orden no se tocan."""
    updated = repository.update_active(chunk_id, request.active)
    return ChunkItem(
        chunk_id=updated.chunk_id,
        manual_id=updated.manual_id,
        manual=updated.manual,
        order=updated.order,
        text=updated.text,
        active=updated.active,
    )


def update_chunk_text(
    chunk_id: str,
    request: ChunkUpdateRequest,
    embeddings: "EmbeddingsClient",
    repository: "ChunkRepository",
) -> ChunkUpdateResponse:
    """Recalcula el embedding antes de persistir y conserva los metadatos del fragmento."""
    if not repository.exists(chunk_id):
        raise ChunkNotFound("El fragmento no existe.")
    try:
        vectors = embeddings.embed([request.text])
    except EmbeddingsUnavailable:
        raise
    except Exception as exc:
        raise EmbeddingsUnavailable("No se pudo calcular el embedding del fragmento.") from exc
    if len(vectors) != 1:
        raise EmbeddingsUnavailable("Respuesta de embeddings inesperada.")
    updated = repository.update_text(chunk_id, request.text, list(vectors[0]))
    return ChunkUpdateResponse(
        chunk_id=updated.chunk_id,
        manual_id=updated.manual_id,
        manual=updated.manual,
        order=updated.order,
        text=updated.text,
        active=updated.active,
    )
