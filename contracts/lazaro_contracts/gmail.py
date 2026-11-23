"""Modelos de rutas internas para sincronizar el canal Gmail."""
from __future__ import annotations

from typing import Literal

from pydantic import Field

from .common import ContractModel


class GmailSyncResponse(ContractModel):
    status: Literal["initialized", "synced"]
    processed: int = Field(ge=0)


class GmailCursorResetResponse(ContractModel):
    status: Literal["reset"]
