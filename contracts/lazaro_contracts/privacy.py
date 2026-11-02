"""Modelos de POST /privacy/purge de orchestrator y handover (#27)."""
from __future__ import annotations

from pydantic import AwareDatetime, Field

from .common import ContractModel


class PrivacyPurgeRequest(ContractModel):
    """Cuerpo vacío {} de POST /privacy/purge."""


class PrivacyPurgeResponse(ContractModel):
    """Resultado de una purga: corte, filas borradas y casos activos cerrados."""

    cutoff: AwareDatetime
    deleted: dict[str, int]
    # Handover: casos activos cerrados y borrados (R35); orchestrator: 0 (R27).
    closed_active_cases: int = Field(default=0, ge=0)
