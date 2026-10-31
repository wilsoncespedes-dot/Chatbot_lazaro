"""Modelos de POST /messages (orchestrator) y POST /send (telegram_gateway)."""
from __future__ import annotations

from typing import Annotated, Literal

from pydantic import AwareDatetime, Field

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
