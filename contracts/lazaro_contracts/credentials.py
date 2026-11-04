"""Modelos de POST /credentials/expiry-notices del orchestrator (#42)."""
from __future__ import annotations

from pydantic import Field

from .common import ContractModel


class ExpiryNoticeRunRequest(ContractModel):
    """Cuerpo vacío {} de POST /credentials/expiry-notices."""


class ExpiryNoticeRunResponse(ContractModel):
    """Resultado de una pasada de avisos de vencimiento."""

    enabled: bool
    candidates: int = Field(ge=0)
    sent_text: int = Field(ge=0)
    sent_template: int = Field(ge=0)
    failed: int = Field(ge=0)
    skipped: dict[str, int]
