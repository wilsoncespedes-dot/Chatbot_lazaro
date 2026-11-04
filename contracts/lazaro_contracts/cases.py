"""Modelos de /handover, /cases/{id}/reply, /cases/{id}/close, /cases/check-timeouts
/cases/{id}/assign, /cases/{id}/authorize y /cases/{id}/client-message."""
from __future__ import annotations

from typing import Annotated, Literal

from pydantic import AwareDatetime, Field, RootModel, field_validator

from .common import (
    MAX_CASE_LIST_LIMIT,
    MAX_LAST_MESSAGES,
    ContractModel,
    Identifier,
    MessageText,
)

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


class CaseTransferRequest(ContractModel):
    """Transferencia de un caso de un asesor a otro (#41 R26)."""

    # S6: en la versión mínima, el chat_id del asesor en decimal.
    advisor_id: Identifier
    target_advisor_id: Identifier


class CaseTransferResponse(ContractModel):
    """Respuesta 200 de POST /cases/{id}/transfer (#41 R26)."""

    status: Literal["assigned"]
    case_id: Identifier
    advisor_id: Identifier


# S12: acciones que se autorizan.
CaseAuthorizeAction = Literal["reply", "close"]


class CaseAuthorizeRequest(ContractModel):
    """Consulta de si un asesor puede responder o cerrar un caso (S12)."""

    # S6: en la versión mínima, el chat_id del asesor en decimal.
    advisor_id: Identifier
    action: CaseAuthorizeAction


class CaseAuthorizeResponse(ContractModel):
    """Respuesta 200 de POST /cases/{id}/authorize; una denegación es 403 (S12)."""

    allowed: Literal[True]
    case_id: Identifier


class CheckTimeoutsRequest(ContractModel):
    """Cuerpo vacío {} de POST /cases/check-timeouts."""


class CheckTimeoutsResponse(ContractModel):
    """Respuesta 200 de POST /cases/check-timeouts con los casos vencidos."""

    timed_out_cases: list[Identifier]


class CaseClientMessageRequest(ContractModel):
    """Mensaje de un cliente que el orquestador pide reenviar al asesor del caso (S13)."""

    text: MessageText
    at: AwareDatetime


class CaseClientMessageResponse(ContractModel):
    """Respuesta 200 de POST /cases/{id}/client-message (S13)."""

    status: Literal["forwarded", "not_assigned"]
    case_id: Identifier


# S14: acciones que el panel puede ofrecer para un caso listado.
CaseListAction = Literal["reply", "assign", "close"]
CaseListStatus = Literal["open", "timed_out", "assigned"]


class CaseListQuery(ContractModel):
    """Parámetro de query de GET /cases: el asesor que pide su listado (S14)."""

    advisor_id: Identifier


class CaseListItem(ContractModel):
    """Un caso del listado de GET /cases, sin datos de contacto ni conversación (S14)."""

    case_id: Identifier
    status: CaseListStatus
    created_at: AwareDatetime
    actions: Annotated[list[CaseListAction], Field(min_length=1)]

    @field_validator("actions")
    @classmethod
    def _actions_without_duplicates(cls, value: list[CaseListAction]) -> list[CaseListAction]:
        if len(value) != len(set(value)):
            raise ValueError("actions no puede repetir acciones")
        return value


class CaseListResponse(RootModel[list[CaseListItem]]):
    """Respuesta 200 de GET /cases: arreglo JSON de nivel superior (S14)."""

    root: Annotated[list[CaseListItem], Field(max_length=MAX_CASE_LIST_LIMIT)]
