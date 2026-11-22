"""Contratos del canal SIMULADO y de su buzón de pruebas (#63)."""
from __future__ import annotations

from typing import Annotated, Literal

from pydantic import AwareDatetime, Field, StringConstraints

from .channels import Channel, ExternalIdentifier
from .common import MAX_TEXT_LENGTH, ContractModel

SIMULATED_EXTERNAL_ID_PATTERN = r"^[A-Za-z0-9_.:-]{1,64}$"
MAX_SIMULATED_REASON_LENGTH = 200

SimulatedExternalId = Annotated[
    str,
    StringConstraints(min_length=1, max_length=64, pattern=SIMULATED_EXTERNAL_ID_PATTERN),
]
MailboxKind = Literal["client", "reply", "rejected"]


class MailboxEntry(ContractModel):
    """Una entrada del buzón: solo texto, destino y tipo; nunca secretos."""

    id: int = Field(ge=1)
    channel: Channel
    destination: ExternalIdentifier
    kind: MailboxKind
    text: str = Field(min_length=1, max_length=MAX_TEXT_LENGTH)
    created_at: AwareDatetime


class MailboxResponse(ContractModel):
    channel: Channel
    entries: list[MailboxEntry]


class SimulatedInboundRequest(ContractModel):
    external_user_id: SimulatedExternalId
    text: str = Field(min_length=1, max_length=MAX_TEXT_LENGTH)


class SimulatedInboundResponse(ContractModel):
    status: Literal["accepted", "duplicate"]
    forwarded: bool
    reason: str | None = Field(None, max_length=MAX_SIMULATED_REASON_LENGTH)
