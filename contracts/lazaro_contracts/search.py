"""Modelos de POST /search (rag)."""
from __future__ import annotations

from typing import Annotated

from pydantic import Field, RootModel, StringConstraints

from .common import (
    MAX_MANUAL_NAME_LENGTH,
    MAX_TEXT_LENGTH,
    MAX_TOP_K,
    ContractModel,
    Identifier,
)


class SearchRequest(ContractModel):
    """Consulta de búsqueda semántica sobre los manuales."""

    query: Annotated[str, StringConstraints(min_length=1, max_length=MAX_TEXT_LENGTH)]
    top_k: Annotated[int, Field(ge=1, le=MAX_TOP_K)]
    # S7: opcional; RAG la ignora hasta que exista el clasificador.
    category: Identifier | None = None


class SearchResult(ContractModel):
    """Un fragmento de manual que supera el umbral de similitud."""

    chunk_id: Identifier
    manual: Annotated[str, StringConstraints(min_length=1, max_length=MAX_MANUAL_NAME_LENGTH)]
    text: Annotated[str, StringConstraints(min_length=1)]
    score: Annotated[float, Field(ge=-1.0, le=1.0)]


class SearchResponse(RootModel[list[SearchResult]]):
    """Respuesta 200 de POST /search: arreglo JSON de nivel superior (S10)."""
