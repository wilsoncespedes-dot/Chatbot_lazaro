"""Lógica del servicio handover: casos, avisos, asignación, cierre y vencimiento (sin IO)."""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Callable, Literal, NoReturn

from lazaro_contracts import (
    MAX_TEXT_LENGTH,
    CaseAssignResponse,
    CaseAuthorizeRequest,
    CaseAuthorizeResponse,
    CaseClientMessageRequest,
    CaseClientMessageResponse,
    CaseCloseResponse,
    CaseListItem,
    CaseListResponse,
    CaseTransferRequest,
    CaseTransferResponse,
    CheckTimeoutsResponse,
    HandoverRequest,
    HandoverResponse,
    LastMessage,
    PrivacyPurgeResponse,
)
from pydantic import BaseModel

from .config import Settings

if TYPE_CHECKING:
    from .adapters.gateway import GatewayClient
    from .adapters.repository import CaseRepository

logger = logging.getLogger(__name__)

NOTICE_MESSAGE_MAX_LENGTH = 300
CLIENT_FORWARD_TEMPLATE = "Caso {case_id} | Cliente: {text}"
_INTEGER_PATTERN = re.compile(r"-?[0-9]+")

CaseStatus = Literal["open", "assigned", "timed_out", "closed"]
DenialAction = Literal["reply", "close", "assign", "transfer"]


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


class AdvisorForbidden(DomainError):
    code = "forbidden"
    status_code = 403


class UpstreamError(DomainError):
    code = "upstream_error"
    status_code = 502


class TransferTargetInvalid(DomainError):
    code = "validation_error"
    status_code = 422


class PrivacyNotConfigured(DomainError):
    code = "privacy_not_configured"
    status_code = 503


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


class Denial(BaseModel):
    case_id: str
    advisor_id: str
    action: DenialAction
    at: datetime


RequestResult = Literal["received", "notified", "no_advisors", "error"]


class HandoverRequestRecord(BaseModel):
    request_id: int | None = None
    requested_case_id: str
    case_id: str | None = None
    contact_id: str
    reason: str
    received_at: datetime
    result: RequestResult
    advisors_configured: int
    notices_delivered: int
    messages_count: int


@dataclass
class _RequestTally:
    case_id: str | None = None
    delivered: int = 0


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


def build_client_forward(case_id: str, text: str) -> str:
    """Texto plano `Caso <id> | Cliente: <texto>` recortado a MAX_TEXT_LENGTH. Pura."""
    return CLIENT_FORWARD_TEMPLATE.format(case_id=case_id, text=text)[:MAX_TEXT_LENGTH]


def is_registered_advisor(advisor_id: str | None, settings: Settings) -> bool:
    """R1: igualdad exacta con `str(int)` de algún id de ADVISOR_CHAT_IDS. None → False."""
    if advisor_id is None:
        return False
    registered = {str(advisor_id_value) for advisor_id_value in settings.advisor_ids}
    return advisor_id in registered


def is_orphan_case(case: Case, settings: Settings) -> bool:
    """Caso `assigned` cuyo `advisor_id` (también nulo) no es asesor registrado."""
    return case.status == "assigned" and not is_registered_advisor(case.advisor_id, settings)


def can_act_on_case(
    case: Case, advisor_id: str, action: DenialAction, settings: Settings
) -> bool:
    """Caso no cerrado. Sin asignar → True. `assigned` al asesor → True.

    `assigned` a otro solo se puede cerrar si el caso es huérfano.
    """
    if case.status == "closed":
        return False
    if case.status != "assigned":
        return True
    if case.advisor_id == advisor_id:
        return True
    return action == "close" and is_orphan_case(case, settings)


def list_advisor_cases(
    advisor_id: str, settings: Settings, adapters: Adapters
) -> CaseListResponse:
    """R10-R18: casos gestionables por el asesor, con las acciones de S12."""
    if not is_registered_advisor(advisor_id, settings):
        logger.info("cases_listed count=0")
        return CaseListResponse([])
    registered = [str(advisor) for advisor in settings.advisor_ids]
    cases = adapters.repository.list_cases_for_advisor(
        advisor_id, registered, settings.case_list_limit
    )
    items: list[CaseListItem] = []
    for case in cases:
        actions = [
            action
            for action in ("reply", "assign", "close")
            if can_act_on_case(case, advisor_id, action, settings)
            and not (action == "assign" and case.status == "assigned")
        ]
        if not actions:
            continue
        items.append(
            CaseListItem(
                case_id=case.case_id,
                status=case.status,
                created_at=case.created_at,
                actions=actions,
            )
        )
    logger.info("cases_listed count=%d", len(items))
    return CaseListResponse(items)


def _deny(
    case_id: str, advisor_id: str, action: DenialAction, adapters: Adapters
) -> NoReturn:
    """Registra la denegación y lanza `AdvisorForbidden`; si el registro falla, sube."""
    adapters.repository.add_denial(
        Denial(case_id=case_id, advisor_id=advisor_id, action=action, at=adapters.clock())
    )
    raise AdvisorForbidden("El asesor no está autorizado para esta acción sobre el caso.")


def authorize_case(
    case_id: str, req: CaseAuthorizeRequest, settings: Settings, adapters: Adapters
) -> CaseAuthorizeResponse:
    """R2-R8, R46, R48: decide sin modificar el caso ni enviar nada."""
    advisor_id = req.advisor_id
    action = req.action
    if not is_registered_advisor(advisor_id, settings):
        _deny(case_id, advisor_id, action, adapters)
    case = adapters.repository.get_case(case_id)
    if case is None:
        raise CaseNotFound("El caso no existe.")
    if case.status == "closed":
        raise CaseClosed("El caso está cerrado.")
    if not can_act_on_case(case, advisor_id, action, settings):
        _deny(case_id, advisor_id, action, adapters)
    return CaseAuthorizeResponse(allowed=True, case_id=case_id)


def _start_request(req: HandoverRequest, settings: Settings, adapters: Adapters) -> int | None:
    """R1, R19: crea el registro `received`; si falla, solo deja log y devuelve None."""
    record = HandoverRequestRecord(
        requested_case_id=req.case_id,
        contact_id=req.contact_id,
        reason=req.reason,
        received_at=adapters.clock(),
        result="received",
        advisors_configured=len(settings.advisor_ids),
        notices_delivered=0,
        messages_count=len(req.last_messages),
    )
    try:
        return adapters.repository.add_request(record)
    except Exception as exc:
        logger.error("handover_request_not_recorded code=%s", type(exc).__name__)
        return None


def _finish_request(
    repo: "CaseRepository",
    request_id: int | None,
    case_id: str | None,
    result: RequestResult,
    notices_delivered: int,
) -> None:
    """R3-R5, R8, R11, R12, R20: completa el registro sin alterar la respuesta."""
    if request_id is None:
        return
    try:
        repo.complete_request(request_id, case_id, result, notices_delivered)
    except Exception as exc:
        logger.error(
            "handover_request_update_failed request_id=%s code=%s",
            request_id,
            type(exc).__name__,
        )


def open_case(req: HandoverRequest, settings: Settings, adapters: Adapters) -> HandoverResponse:
    """Registra la solicitud (R1-R12) y delega el traspaso sin cambiar su comportamiento."""
    repo = adapters.repository
    request_id = _start_request(req, settings, adapters)
    tally = _RequestTally()
    try:
        response = _process_handover(req, settings, adapters, tally)
    except Exception:
        logger.error(
            "handover_request_failed request_id=%s case_id=%s", request_id, tally.case_id
        )
        _finish_request(repo, request_id, tally.case_id, "error", tally.delivered)
        raise
    _finish_request(repo, request_id, response.case_id, response.status, tally.delivered)
    return response


def _process_handover(
    req: HandoverRequest, settings: Settings, adapters: Adapters, tally: _RequestTally
) -> HandoverResponse:
    repo = adapters.repository
    case = repo.find_active_case(req.contact_id)
    if case is not None:
        repo.update_last_messages(case.case_id, list(req.last_messages))
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
    tally.case_id = case.case_id

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
        if delivered:
            tally.delivered += 1
        repo.add_notification(
            case.case_id, str(advisor_chat_id), req.reason, adapters.clock(), delivered
        )
        delivered_any = delivered_any or delivered

    if delivered_any:
        return HandoverResponse(status="notified", case_id=case.case_id)

    # R10 (confirmado): el orquestador ya avisa al cliente con NO_ADVISORS_REPLY, así que el
    # caso no debe quedar `open` para que check-timeouts no repita el aviso.
    if case.status == "open":
        repo.mark_timed_out(case.case_id)
    logger.warning("no_advisors case_id=%s", case.case_id)
    return HandoverResponse(status="no_advisors", case_id=case.case_id)


def _resolve_lost_assignment(
    case_id: str, advisor_id: str, adapters: Adapters
) -> CaseAssignResponse:
    """R38-R40: alguien escribió entre la lectura y la escritura condicional."""
    current = adapters.repository.get_case(case_id)
    if current is None:
        raise CaseNotFound("El caso no existe.")
    if current.status == "closed":
        raise CaseClosed("El caso está cerrado.")
    if current.status == "assigned" and current.advisor_id == advisor_id:
        return CaseAssignResponse(status="assigned", case_id=case_id)
    _deny(case_id, advisor_id, "assign", adapters)


def assign_case(
    case_id: str, advisor_id: str, settings: Settings, adapters: Adapters
) -> CaseAssignResponse:
    """R11-R13, R37-R40, R48: asigna con una escritura condicional."""
    if not is_registered_advisor(advisor_id, settings):
        _deny(case_id, advisor_id, "assign", adapters)
    case = adapters.repository.get_case(case_id)
    if case is None:
        raise CaseNotFound("El caso no existe.")
    if case.status == "closed":
        raise CaseClosed("El caso está cerrado.")
    if case.status == "assigned":
        if case.advisor_id == advisor_id:
            return CaseAssignResponse(status="assigned", case_id=case_id)
        _deny(case_id, advisor_id, "assign", adapters)
    if adapters.repository.assign_if_unassigned(case_id, advisor_id, adapters.clock()):
        return CaseAssignResponse(status="assigned", case_id=case_id)
    return _resolve_lost_assignment(case_id, advisor_id, adapters)


def _resolve_lost_transfer(
    case_id: str, advisor_id: str, target_id: str, adapters: Adapters
) -> CaseTransferResponse:
    """R31: si la escritura condicional no cambió filas, decide con el estado actual."""
    current = adapters.repository.get_case(case_id)
    if current is None:
        raise CaseNotFound("El caso no existe.")
    if current.status == "closed":
        raise CaseClosed("El caso está cerrado.")
    if current.status == "assigned" and current.advisor_id == target_id:
        return CaseTransferResponse(
            status="assigned", case_id=case_id, advisor_id=target_id
        )
    _deny(case_id, advisor_id, "transfer", adapters)


def transfer_case(
    case_id: str, req: CaseTransferRequest, settings: Settings, adapters: Adapters
) -> CaseTransferResponse:
    """R27-R31: reasigna con una escritura condicional solo al asesor actual."""
    advisor_id = req.advisor_id
    target_id = req.target_advisor_id
    if not is_registered_advisor(advisor_id, settings):
        _deny(case_id, advisor_id, "transfer", adapters)
    case = adapters.repository.get_case(case_id)
    if case is None:
        raise CaseNotFound("El caso no existe.")
    if case.status == "closed":
        raise CaseClosed("El caso está cerrado.")
    if case.status != "assigned" or case.advisor_id != advisor_id:
        _deny(case_id, advisor_id, "transfer", adapters)
    if not is_registered_advisor(target_id, settings) or target_id == advisor_id:
        raise TransferTargetInvalid(
            "El asesor destino no es válido para transferir el caso."
        )
    if adapters.repository.transfer_if_assigned_to(
        case_id, advisor_id, target_id, adapters.clock()
    ):
        return CaseTransferResponse(
            status="assigned", case_id=case_id, advisor_id=target_id
        )
    return _resolve_lost_transfer(case_id, advisor_id, target_id, adapters)


def _resolve_lost_close(
    case_id: str, advisor_id: str, adapters: Adapters
) -> CaseCloseResponse:
    """R42, R55: si el cierre condicional no escribió, decide con el estado actual."""
    current = adapters.repository.get_case(case_id)
    if current is None:
        raise CaseNotFound("El caso no existe.")
    if current.status == "closed":
        return CaseCloseResponse(status="closed", case_id=case_id)
    _deny(case_id, advisor_id, "close", adapters)


def close_case(
    case_id: str, advisor_id: str, settings: Settings, adapters: Adapters
) -> CaseCloseResponse:
    """R14-R18, R41, R42, R47, R54, R55: cierra con una escritura condicional."""
    if not is_registered_advisor(advisor_id, settings):
        _deny(case_id, advisor_id, "close", adapters)
    case = adapters.repository.get_case(case_id)
    if case is None:
        raise CaseNotFound("El caso no existe.")
    if case.status == "closed":
        return CaseCloseResponse(status="closed", case_id=case_id)
    if (
        case.status == "assigned"
        and case.advisor_id != advisor_id
        and not is_orphan_case(case, settings)
    ):
        _deny(case_id, advisor_id, "close", adapters)
    allowed_assignee = case.advisor_id if is_orphan_case(case, settings) else advisor_id
    if adapters.repository.close_if_still_allowed(
        case_id, advisor_id, allowed_assignee, adapters.clock()
    ):
        return CaseCloseResponse(status="closed", case_id=case_id)
    return _resolve_lost_close(case_id, advisor_id, adapters)


def forward_client_message(
    case_id: str, req: CaseClientMessageRequest, adapters: Adapters
) -> CaseClientMessageResponse:
    """R47-R54: reenvía el mensaje al asesor asignado sin modificar el caso."""
    case = adapters.repository.get_case(case_id)
    if case is None:
        raise CaseNotFound("El caso no existe.")
    if case.status != "assigned":
        return CaseClientMessageResponse(status="not_assigned", case_id=case_id)
    advisor_id = case.advisor_id
    if advisor_id is None or not _INTEGER_PATTERN.fullmatch(advisor_id):
        logger.error("client_message_forward_failed case_id=%s code=invalid_advisor_id", case_id)
        raise UpstreamError("No se pudo enviar el mensaje al asesor.")
    try:
        adapters.gateway.send(int(advisor_id), build_client_forward(case_id, req.text))
    except ServiceUnavailable:
        logger.error("client_message_forward_failed case_id=%s code=send_failed", case_id)
        raise UpstreamError("No se pudo enviar el mensaje al asesor.") from None
    logger.info("client_message_forwarded case_id=%s", case_id)
    return CaseClientMessageResponse(status="forwarded", case_id=case_id)


def count_orphan_cases(settings: Settings, adapters: Adapters) -> int:
    """R49: suma los casos `assigned` cuyo asesor no está registrado."""
    counts = adapters.repository.count_assigned_by_advisor()
    return sum(
        count for advisor_id, count in counts.items() if not is_registered_advisor(
            advisor_id, settings
        )
    )


def log_orphan_cases(settings: Settings, adapters: Adapters) -> None:
    """R49-R51: recuento al arrancar, sin ids y sin bloquear el arranque."""
    try:
        count = count_orphan_cases(settings, adapters)
    except Exception:
        logger.warning("orphan_cases_check_failed")
        return
    logger.info("orphan_cases count=%d", count)
    if count > 0:
        logger.warning("orphan_cases_present count=%d", count)


def check_timeouts(settings: Settings, adapters: Adapters) -> CheckTimeoutsResponse:
    repo = adapters.repository
    now = adapters.clock()
    stale_before = now - timedelta(seconds=settings.handover_timeout_seconds)
    timed_out: list[str] = []
    for case in repo.list_open_cases():
        if (now - case.created_at).total_seconds() < settings.handover_timeout_seconds:
            continue
        if not repo.claim_timeout(case.case_id, now, stale_before):
            continue
        try:
            adapters.gateway.send(case.chat_id, settings.handover_timeout_reply)
        except ServiceUnavailable:
            logger.error("timeout_reply_failed case_id=%s", case.case_id)
            repo.release_timeout_claim(case.case_id)
            continue
        if repo.mark_timed_out(case.case_id):
            timed_out.append(case.case_id)
        else:
            logger.warning("timeout_superseded case_id=%s", case.case_id)
    return CheckTimeoutsResponse(timed_out_cases=timed_out)


def purge_personal_data(settings: Settings, adapters: Adapters) -> PrivacyPurgeResponse:
    """R32-R40: borra casos y solicitudes antiguos con un único reloj."""
    retention = settings.retention_days
    active_max = settings.active_case_max_days
    if retention is None or active_max is None:
        raise PrivacyNotConfigured("La retención de datos no está configurada.")
    now = adapters.clock()
    cutoff = now - timedelta(days=retention)
    active_cutoff = now - timedelta(days=active_max)
    deleted, closed_active_cases = adapters.repository.purge_personal_data(
        cutoff, active_cutoff, now
    )
    return PrivacyPurgeResponse(
        cutoff=cutoff,
        deleted=deleted,
        closed_active_cases=closed_active_cases,
    )
