"""Modelos de POST /messages (orchestrator) y POST /send (telegram_gateway)."""
from __future__ import annotations

from typing import Annotated, Literal

from pydantic import AwareDatetime, Field

from .channels import NormalizedMessage
from .common import ContractModel, MessageText


class MessageRequest(ContractModel):
    """Mensaje de texto de un cliente que el gateway entrega al orquestador."""

    update_id: Annotated[int, Field(ge=0)]
    telegram_user_id: int
    chat_id: int
    text: MessageText
    received_at: AwareDatetime


class MessageResponse(ContractModel):
    """Respuesta 202 de POST /messages."""

    status: Literal["accepted", "duplicate"]


class SendRequest(ContractModel):
    """Texto que el gateway debe enviar a un chat de Telegram."""

    chat_id: int
    text: MessageText


class SendResponse(ContractModel):
    """Respuesta 200 de POST /send."""

    sent: Literal[True]


def normalize_legacy_message(request: MessageRequest) -> NormalizedMessage:
    """Traduce el payload Telegram histórico al modelo común (canal telegram)."""
    return NormalizedMessage(
        channel="telegram",
        external_user_id=str(request.telegram_user_id),
        external_chat_id=str(request.chat_id),
        external_message_id=str(request.update_id),
        kind="text",
        text=request.text,
        received_at=request.received_at,
    )
