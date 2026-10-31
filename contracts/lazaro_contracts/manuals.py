"""Modelos de POST /manuals (rag)."""
from __future__ import annotations

from typing import Annotated

from pydantic import Field, StringConstraints

from .common import MAX_MANUAL_NAME_LENGTH, ContractModel, Identifier


class ManualUploadRequest(ContractModel):
    """Partes de texto del multipart de POST /manuals (S1); el archivo va en la parte `file`."""

    name: Annotated[str, StringConstraints(min_length=1, max_length=MAX_MANUAL_NAME_LENGTH)]


class ManualUploadResponse(ContractModel):
    """Respuesta 201 de POST /manuals."""

    manual_id: Identifier
    chunks: Annotated[int, Field(ge=1)]
