"""Modelos de PATCH /chunks/{id}, GET /manuals/{id}/chunks y PATCH /chunks/{id}/active (rag)."""
from __future__ import annotations

from typing import Annotated

from pydantic import Field, RootModel, StrictBool, StringConstraints, field_validator

from .common import MAX_MANUAL_NAME_LENGTH, ContractModel, Identifier


class ChunkUpdateRequest(ContractModel):
    """Reemplazo del texto de un fragmento; no se normaliza el valor no vacío."""

    text: Annotated[str, StringConstraints(min_length=1)]

    @field_validator("text")
    @classmethod
    def _reject_blank_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("El texto no puede estar vacío ni contener solo espacios.")
        return value


class ChunkUpdateResponse(ContractModel):
    """Respuesta 200 de PATCH /chunks/{id}: fragmento actualizado."""

    chunk_id: Identifier
    manual_id: Identifier
    manual: Annotated[str, StringConstraints(min_length=1, max_length=MAX_MANUAL_NAME_LENGTH)]
    order: Annotated[int, Field(ge=1)]
    text: Annotated[str, StringConstraints(min_length=1)]
    active: bool


class ChunkItem(ContractModel):
    """Fragmento completo con sus metadatos; mismos campos que ChunkUpdateResponse."""

    chunk_id: Identifier
    manual_id: Identifier
    manual: Annotated[str, StringConstraints(min_length=1, max_length=MAX_MANUAL_NAME_LENGTH)]
    order: Annotated[int, Field(ge=1)]
    text: Annotated[str, StringConstraints(min_length=1)]
    active: bool


class ChunkListResponse(RootModel[list[ChunkItem]]):
    """Respuesta 200 de GET /manuals/{id}/chunks: arreglo JSON de nivel superior."""


class ChunkActiveRequest(ContractModel):
    """Cambio de estado de un fragmento; solo acepta booleanos JSON (R7)."""

    active: StrictBool
