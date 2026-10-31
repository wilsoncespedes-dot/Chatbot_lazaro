"""Modelos de /handover, /cases/{id}/reply, /cases/{id}/close, /cases/check-timeouts
y /cases/{id}/assign."""
from __future__ import annotations

from typing import Annotated, Literal

from pydantic import AwareDatetime, Field

from .common import MAX_LAST_MESSAGES, ContractModel, Identifier, MessageText

# S5: invalid_answer queda reservado para la feature 6.
HandoverReason = Literal["no_relevant_chunks", "user_request", "invalid_answer"]


class LastMessage(ContractModel):
    """Un mensaje reciente de la conversación (S2)."""

    role: Literal["user", "bot", "advisor"]
    text: MessageText
    at: AwareDatetime


class HandoverRequest(ContractModel):
    """Petición del orquestador para pasar la conversación a un asesor."""

    # S3: lo genera el orquestador; handover puede reutilizar un caso abierto.
    case_id: Identifier
    contact_id: Identifier
    # S4: handover avisa al cliente al vencer la espera.
    chat_id: int
    reason: HandoverReason
    last_messages: Annotated[list[LastMessage], Field(max_length=MAX_LAST_MESSAGES)]


class HandoverResponse(ContractModel):
    """Respuesta 200 de POST /handover con el caso efectivo (S3)."""

    status: Literal["notified", "no_advisors"]
    case_id: Identifier


class CaseReplyRequest(ContractModel):
    """Respuesta de un asesor que el orquestador reenvía al cliente."""

    # S6: en la versión mínima, el chat_id del asesor en decimal.
    advisor_id: Identifier
    text: MessageText


class CaseReplyResponse(ContractModel):
    """Respuesta 200 de POST /cases/{id}/reply."""

    sent: Literal[True]


class CaseCloseRequest(ContractModel):
    """Cierre de un caso por un asesor."""

    advisor_id: Identifier


class CaseCloseResponse(ContractModel):
    """Respuesta 200 de POST /cases/{id}/close (idempotente, S8)."""

    status: Literal["closed"]
    case_id: Identifier


class CaseAssignRequest(ContractModel):
    """Asignación de un caso a un asesor (la pide el orquestador, S11)."""

    # S6: en la versión mínima, el chat_id del asesor en decimal.
    advisor_id: Identifier


class CaseAssignResponse(ContractModel):
    """Respuesta 200 de POST /cases/{id}/assign (idempotente si ya estaba assigned, S11)."""

    status: Literal["assigned"]
    case_id: Identifier


class CheckTimeoutsRequest(ContractModel):
    """Cuerpo vacío {} de POST /cases/check-timeouts."""


class CheckTimeoutsResponse(ContractModel):
    """Respuesta 200 de POST /cases/check-timeouts con los casos vencidos."""

    timed_out_cases: list[Identifier]
