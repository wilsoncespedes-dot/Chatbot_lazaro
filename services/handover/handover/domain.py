"""Lógica del servicio handover: casos, avisos, asignación, cierre y vencimiento (sin IO)."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Callable, Literal

from lazaro_contracts import (
    MAX_TEXT_LENGTH,
    CaseAssignResponse,
    CaseCloseResponse,
    CheckTimeoutsResponse,
    HandoverRequest,
    HandoverResponse,
    LastMessage,
)
from pydantic import BaseModel

from .config import Settings

if TYPE_CHECKING:
    from .adapters.gateway import GatewayClient
    from .adapters.repository import CaseRepository

logger = logging.getLogger(__name__)

NOTICE_MESSAGE_MAX_LENGTH = 300

CaseStatus = Literal["open", "assigned", "timed_out", "closed"]


class DomainError(Exception):
    """Base de los errores de negocio; cada subclase fija su código y su HTTP status."""

    code = "domain_error"
    status_code = 400


class CaseNotFound(DomainError):
    code = "not_found"
    status_code = 404


class CaseClosed(DomainError):
    code = "case_closed"
    status_code = 409


class ServiceUnavailable(Exception):
    """Interna: la lanza el cliente del gateway; nunca llega al exterior."""


class Case(BaseModel):
    case_id: str
    contact_id: str
    chat_id: int
    reason: str
    status: CaseStatus
    advisor_id: str | None = None
    last_messages: list[LastMessage]
    created_at: datetime
    assigned_at: datetime | None = None
    closed_at: datetime | None = None
    closed_by: str | None = None


class Notification(BaseModel):
    case_id: str
    advisor_id: str
    reason: str
    at: datetime
    delivered: bool


@dataclass
class Adapters:
    repository: "CaseRepository"
    gateway: "GatewayClient"
    clock: Callable[[], datetime]


def build_advisor_notice(case_id: str, reason: str, last_messages: list[LastMessage]) -> str:
    """Aviso en texto plano: cabecera y una línea `[rol] texto` por mensaje (≤ 4096)."""
    lines = [f"Caso {case_id} | Motivo: {reason}"]
    for message in last_messages:
        lines.append(f"[{message.role}] {message.text[:NOTICE_MESSAGE_MAX_LENGTH]}")
    return "\n".join(lines)[:MAX_TEXT_LENGTH]


def open_case(req: HandoverRequest, settings: Settings, adapters: Adapters) -> HandoverResponse:
    repo = adapters.repository
    case = repo.find_active_case(req.contact_id)
    if case is not None:
        case = case.model_copy(update={"last_messages": list(req.last_messages)})
        repo.update_case(case)
    else:
        case = Case(
            case_id=req.case_id,
            contact_id=req.contact_id,
            chat_id=req.chat_id,
            reason=req.reason,
            status="open",
            last_messages=list(req.last_messages),
            created_at=adapters.clock(),
        )
        repo.create_case(case)

    notice = build_advisor_notice(case.case_id, req.reason, req.last_messages)
    delivered_any = False
    for advisor_chat_id in settings.advisor_ids:
        try:
            adapters.gateway.send(advisor_chat_id, notice)
            delivered = True
        except ServiceUnavailable:
            logger.error(
                "advisor_notice_failed case_id=%s advisor_id=%s", case.case_id, advisor_chat_id
            )
            delivered = False
        repo.add_notification(
            case.case_id, str(advisor_chat_id), req.reason, adapters.clock(), delivered
        )
        delivered_any = delivered_any or delivered

    if delivered_any:
        return HandoverResponse(status="notified", case_id=case.case_id)

    # R10 (confirmado): el orquestador ya avisa al cliente con NO_ADVISORS_REPLY, así que el
    # caso no debe quedar `open` para que check-timeouts no repita el aviso.
    if case.status == "open":
        repo.update_case(case.model_copy(update={"status": "timed_out"}))
    logger.warning("no_advisors case_id=%s", case.case_id)
    return HandoverResponse(status="no_advisors", case_id=case.case_id)


def assign_case(case_id: str, advisor_id: str, adapters: Adapters) -> CaseAssignResponse:
    repo = adapters.repository
    case = repo.get_case(case_id)
    if case is None:
        raise CaseNotFound("El caso no existe.")
    if case.status == "closed":
        raise CaseClosed("El caso está cerrado.")
    if case.status != "assigned":
        repo.update_case(
            case.model_copy(
                update={
                    "status": "assigned",
                    "advisor_id": advisor_id,
                    "assigned_at": adapters.clock(),
                }
            )
        )
    return CaseAssignResponse(status="assigned", case_id=case_id)


def close_case(case_id: str, advisor_id: str, adapters: Adapters) -> CaseCloseResponse:
    repo = adapters.repository
    case = repo.get_case(case_id)
    if case is None:
        raise CaseNotFound("El caso no existe.")
    if case.status != "closed":
        repo.update_case(
            case.model_copy(
                update={
                    "status": "closed",
                    "closed_by": advisor_id,
                    "closed_at": adapters.clock(),
                }
            )
        )
    return CaseCloseResponse(status="closed", case_id=case_id)


def check_timeouts(settings: Settings, adapters: Adapters) -> CheckTimeoutsResponse:
    repo = adapters.repository
    now = adapters.clock()
    timed_out: list[str] = []
    for case in repo.list_open_cases():
        if (now - case.created_at).total_seconds() < settings.handover_timeout_seconds:
            continue
        try:
            adapters.gateway.send(case.chat_id, settings.handover_timeout_reply)
        except ServiceUnavailable:
            logger.error("timeout_reply_failed case_id=%s", case.case_id)
            continue
        repo.update_case(case.model_copy(update={"status": "timed_out"}))
        timed_out.append(case.case_id)
    return CheckTimeoutsResponse(timed_out_cases=timed_out)
