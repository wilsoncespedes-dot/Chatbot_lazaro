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


def _window(text: str, size: int, overlap: int) -> list[str]:
    """Ventana deslizante de `size` caracteres con paso `size - overlap` (último recurso)."""
    step = max(size - overlap, 1)
    pieces: list[str] = []
    start = 0
    while start < len(text):
        piece = text[start:start + size]
        if piece.strip():
            pieces.append(piece)
        if start + size >= len(text):
            break
        start += step
    return pieces


# #63: títulos Markdown ("## Facturas", que también produce la extracción DOCX)
# y numerados de varios niveles ("2.1 Notas crédito"). "1. Ingresa…" es un paso,
# no un título, por eso se exige al menos un punto interior.
_HEADING_MD_RE = re.compile(r"^\s{0,3}(#{1,6})\s+(.+?)\s*#*\s*$")
_HEADING_NUM_RE = re.compile(r"^\s*(\d+(?:\.\d+)+)\.?\s+(\S.{0,78})$")
_SENTENCE_RE = re.compile(r"(?<=[.!?…])\s+")
_HEADING_LEVELS_KEPT = 2


def _heading(line: str) -> tuple[int, str] | None:
    match = _HEADING_MD_RE.match(line)
    if match:
        return len(match.group(1)), " ".join(match.group(2).split())
    match = _HEADING_NUM_RE.match(line)
    if match and not line.rstrip().endswith((".", ",", ";", ":")):
        return match.group(1).count(".") + 1, " ".join(line.split())
    return None


def _sections(text: str) -> list[tuple[str, str]]:
    """R1, R2: (ruta de títulos, cuerpo normalizado) en el orden del documento."""
    sections: list[tuple[str, str]] = []
    stack: list[tuple[int, str]] = []
    body: list[str] = []

    def flush() -> None:
        content = " ".join(" ".join(body).split())
        body.clear()
        if content:
            path = " > ".join(title for _, title in stack[-_HEADING_LEVELS_KEPT:])
            sections.append((path, content))

    for line in text.splitlines():
        heading = _heading(line)
        if heading is None:
            stripped = line.strip()
            # R6: cada fila de tabla ("Plan | Usuarios") cuenta como una frase.
            if " | " in stripped and not stripped.endswith((".", "!", "?", "…")):
                line = f"{stripped}."
            body.append(line)
            continue
        flush()
        level, title = heading
        stack = [item for item in stack if item[0] < level]
        stack.append((level, title))
    flush()
    return sections


def _units(body: str, budget: int, overlap: int) -> list[str]:
    """R3: frases; una frase más larga que el presupuesto se parte por palabras
    y una palabra más larga, por caracteres."""
    units: list[str] = []
    for sentence in _SENTENCE_RE.split(body):
        if len(sentence) <= budget:
            units.append(sentence)
            continue
        for word in sentence.split(" "):
            if len(word) > budget:
                units.extend(_window(word, budget, overlap))
            else:
                units.append(word)
    return units


def _pack(prefix: str, body: str, size: int, overlap: int) -> list[str]:
    """R3, R4: agrupa unidades sin pasar de `size` y repite al inicio las
    unidades finales del fragmento anterior que quepan en `overlap`."""
    budget = size - len(prefix)
    if budget < max(20, size // 4):
        prefix, budget = "", size
    chunks: list[str] = []
    current: list[str] = []
    current_is_overlap = False

    def flush() -> None:
        nonlocal current, current_is_overlap
        if not current:
            return
        chunks.append(prefix + " ".join(current))
        tail: list[str] = []
        for previous in reversed(current):
            if len(" ".join([previous, *tail])) > overlap:
                break
            tail.insert(0, previous)
        current = tail
        current_is_overlap = bool(tail)

    for sentence in _SENTENCE_RE.split(body):
        if not sentence:
            continue
        long_sentence = len(sentence) > budget
        if long_sentence and current:
            if current_is_overlap:
                current = []
                current_is_overlap = False
            else:
                flush()
        for unit in _units(sentence, budget, overlap):
            if current and len(" ".join([*current, unit])) > budget:
                if current_is_overlap:
                    current = []
                    current_is_overlap = False
                else:
                    flush()
                if len(" ".join([*current, unit])) > budget:
                    current = []
            current.append(unit)
            current_is_overlap = False
    if current:
        chunks.append(prefix + " ".join(current))
    return chunks


def chunk_text(text: str, size: int, overlap: int) -> list[str]:
    """#63: fragmentos de hasta `size` caracteres que respetan secciones y frases.

    Cada fragmento empieza con la ruta de títulos de su sección ("Facturas >
    Anulación: …") para que la búsqueda tenga contexto; nunca mezcla dos
    secciones ni corta palabras salvo que una sola palabra exceda `size`.
    """
    chunks: list[str] = []
    for path, body in _sections(text):
        prefix = f"{path}: " if path else ""
        chunks.extend(_pack(prefix, body, size, overlap))
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
