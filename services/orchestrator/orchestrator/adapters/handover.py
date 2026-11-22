"""Cliente de handover (POST /handover, /authorize y /assign) con versión falsa."""
from __future__ import annotations

import logging
import threading
from datetime import datetime
from typing import Callable, Protocol
from urllib.parse import quote

import httpx
from lazaro_contracts import (
    SERVICE_TOKEN_HEADER,
    AdvisorRosterSyncRequest,
    AdvisorRosterSyncResponse,
    CaseAssignRequest,
    CaseAssignResponse,
    CaseAutoAssignRequest,
    CaseAutoAssignResponse,
    CaseAuthorizeAction,
    CaseAuthorizeRequest,
    CaseAuthorizeResponse,
    CaseClientMessageRequest,
    CaseClientMessageResponse,
    CaseCloseRequest,
    CaseCloseResponse,
    CaseListItem,
    CaseListResponse,
    CaseReassignRequest,
    CaseReassignResponse,
    CaseTakeRequest,
    CaseTakeResponse,
    CaseTransferRequest,
    CaseTransferResponse,
    ErrorResponse,
    HandoverRequest,
    HandoverResponse,
)
from pydantic import ValidationError

from ..domain import AuthorizationDenied, ForwardRejected, ServiceUnavailable

logger = logging.getLogger(__name__)

_DENIAL_CODES = {403: "forbidden", 404: "not_found", 409: "case_closed"}
_TRANSFER_DENIAL_CODES = {**_DENIAL_CODES, 422: "validation_error"}
_REASSIGN_DENIAL_CODES = {
    403: {"forbidden"},
    404: {"not_found"},
    409: {"case_closed", "case_changed", "case_not_assigned"},
    422: {"validation_error"},
}
_FORWARD_REJECTION_CODES = {404: "not_found", 502: "upstream_error"}


class HandoverClient(Protocol):
    def request(self, req: HandoverRequest) -> HandoverResponse: ...

    def sync_roster(self, req: AdvisorRosterSyncRequest) -> AdvisorRosterSyncResponse: ...

    def assign(self, case_id: str, advisor_id: str) -> CaseAssignResponse: ...

    def try_assign(self, case_id: str, advisor_id: str) -> CaseAssignResponse: ...

    def auto_assign(
        self, case_id: str, candidate_ids: list[str], strategy: str = "por_carga"
    ) -> CaseAutoAssignResponse: ...

    def authorize(
        self, case_id: str, advisor_id: str, action: CaseAuthorizeAction
    ) -> CaseAuthorizeResponse: ...

    def list_cases(
        self, advisor_id: str, scope: str = "mine"
    ) -> CaseListResponse: ...

    def transfer(
        self, case_id: str, advisor_id: str, target_advisor_id: str
    ) -> CaseTransferResponse: ...

    def reassign(
        self, case_id: str, advisor_id: str, target_advisor_id: str
    ) -> CaseReassignResponse: ...

    def forward_client_message(
        self, case_id: str, text: str, at: datetime
    ) -> CaseClientMessageResponse: ...

    def close(self, case_id: str, advisor_id: str) -> CaseCloseResponse: ...

    def take(self, req: CaseTakeRequest) -> CaseTakeResponse: ...


class HttpHandoverClient:
    def __init__(
        self,
        base_url: str,
        service_token: str,
        timeout: float = 10,
        generation_provider: Callable[[], int] | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._service_token = service_token
        self._timeout = timeout
        self._generation_provider = generation_provider

    def _headers(self, content_type: bool = False) -> dict[str, str]:
        headers = {SERVICE_TOKEN_HEADER: self._service_token}
        if content_type:
            headers["Content-Type"] = "application/json"
        if self._generation_provider is not None:
            headers["X-Advisor-Roster-Generation"] = str(self._generation_provider())
        return headers

    def sync_roster(
        self, req: AdvisorRosterSyncRequest
    ) -> AdvisorRosterSyncResponse:
        try:
            response = httpx.post(
                f"{self._base_url}/advisors/sync",
                content=req.model_dump_json(),
                headers=self._headers(content_type=True),
                timeout=self._timeout,
            )
            response.raise_for_status()
            return AdvisorRosterSyncResponse.model_validate(response.json())
        except (httpx.HTTPError, ValueError, ValidationError) as exc:
            logger.error("handover_roster_sync_error code=%s", type(exc).__name__)
            raise ServiceUnavailable("Handover no disponible.") from None

    def request(self, req: HandoverRequest) -> HandoverResponse:
        try:
            response = httpx.post(
                f"{self._base_url}/handover",
                content=req.model_dump_json(),
                headers=self._headers(content_type=True),
                timeout=self._timeout,
            )
            response.raise_for_status()
            return HandoverResponse.model_validate(response.json())
        except (httpx.HTTPError, ValueError, ValidationError) as exc:
            logger.error("handover_error code=%s", type(exc).__name__)
            raise ServiceUnavailable("Handover no disponible.") from None

    def assign(self, case_id: str, advisor_id: str) -> CaseAssignResponse:
        try:
            body = CaseAssignRequest(advisor_id=advisor_id)
            response = httpx.post(
                f"{self._base_url}/cases/{quote(case_id, safe='')}/assign",
                content=body.model_dump_json(),
                headers=self._headers(content_type=True),
                timeout=self._timeout,
            )
            response.raise_for_status()
            return CaseAssignResponse.model_validate(response.json())
        except (httpx.HTTPError, ValueError, ValidationError) as exc:
            logger.error("handover_assign_error code=%s", type(exc).__name__)
            raise ServiceUnavailable("Handover no disponible.") from None

    def try_assign(self, case_id: str, advisor_id: str) -> CaseAssignResponse:
        try:
            body = CaseAssignRequest(advisor_id=advisor_id)
            response = httpx.post(
                f"{self._base_url}/cases/{quote(case_id, safe='')}/assign",
                content=body.model_dump_json(),
                headers=self._headers(content_type=True),
                timeout=self._timeout,
            )
        except httpx.HTTPError as exc:
            logger.error("handover_assign_error code=%s", type(exc).__name__)
            raise ServiceUnavailable("Handover no disponible.") from None

        if response.status_code in _DENIAL_CODES:
            expected = _DENIAL_CODES[response.status_code]
            try:
                error = ErrorResponse.model_validate(response.json())
            except (ValueError, ValidationError):
                logger.error("handover_assign_error code=%s", response.status_code)
                raise ServiceUnavailable("Handover no disponible.") from None
            if error.error != expected:
                logger.error("handover_assign_error code=%s", response.status_code)
                raise ServiceUnavailable("Handover no disponible.") from None
            raise AuthorizationDenied(error.error)

        if response.status_code == 200:
            try:
                parsed = CaseAssignResponse.model_validate(response.json())
            except (ValueError, ValidationError):
                logger.error("handover_assign_error code=invalid_response")
                raise ServiceUnavailable("Handover no disponible.") from None
            if parsed.case_id != case_id:
                logger.error("handover_assign_error code=case_mismatch")
                raise ServiceUnavailable("Handover no disponible.") from None
            return parsed

        logger.error("handover_assign_error code=%s", response.status_code)
        raise ServiceUnavailable("Handover no disponible.")

    def auto_assign(
        self, case_id: str, candidate_ids: list[str], strategy: str = "por_carga"
    ) -> CaseAutoAssignResponse:
        try:
            body = CaseAutoAssignRequest(candidate_ids=candidate_ids, strategy=strategy)
            response = httpx.post(
                f"{self._base_url}/cases/{quote(case_id, safe='')}/auto-assign",
                content=body.model_dump_json(),
                headers=self._headers(content_type=True),
                timeout=self._timeout,
            )
            response.raise_for_status()
            parsed = CaseAutoAssignResponse.model_validate(response.json())
        except (httpx.HTTPError, ValueError, ValidationError) as exc:
            logger.error("handover_auto_assign_error code=%s", type(exc).__name__)
            raise ServiceUnavailable("Handover no disponible.") from None
        if parsed.case_id != case_id:
            logger.error("handover_auto_assign_error code=case_mismatch")
            raise ServiceUnavailable("Handover no disponible.")
        return parsed

    def list_cases(
        self, advisor_id: str, scope: str = "mine"
    ) -> CaseListResponse:
        params = {"advisor_id": advisor_id}
        if scope != "mine":
            params["scope"] = scope
        try:
            response = httpx.get(
                f"{self._base_url}/cases",
                params=params,
                headers=self._headers(),
                timeout=self._timeout,
            )
        except httpx.HTTPError as exc:
            logger.error("handover_list_cases_error code=%s", type(exc).__name__)
            raise ServiceUnavailable("Handover no disponible.") from None

        if response.status_code == 200:
            try:
                return CaseListResponse.model_validate(response.json())
            except (ValueError, ValidationError):
                logger.error("handover_list_cases_error code=invalid_response")
                raise ServiceUnavailable("Handover no disponible.") from None

        logger.error("handover_list_cases_error code=%s", response.status_code)
        raise ServiceUnavailable("Handover no disponible.")

    def transfer(
        self, case_id: str, advisor_id: str, target_advisor_id: str
    ) -> CaseTransferResponse:
        try:
            body = CaseTransferRequest(
                advisor_id=advisor_id, target_advisor_id=target_advisor_id
            )
            response = httpx.post(
                f"{self._base_url}/cases/{quote(case_id, safe='')}/transfer",
                content=body.model_dump_json(),
                headers=self._headers(content_type=True),
                timeout=self._timeout,
            )
        except (httpx.HTTPError, ValueError) as exc:
            logger.error("handover_transfer_error code=%s", type(exc).__name__)
            raise ServiceUnavailable("Handover no disponible.") from None

        if response.status_code in _TRANSFER_DENIAL_CODES:
            expected = _TRANSFER_DENIAL_CODES[response.status_code]
            try:
                error = ErrorResponse.model_validate(response.json())
            except (ValueError, ValidationError):
                logger.error("handover_transfer_error code=%s", response.status_code)
                raise ServiceUnavailable("Handover no disponible.") from None
            if error.error != expected:
                logger.error("handover_transfer_error code=%s", response.status_code)
                raise ServiceUnavailable("Handover no disponible.") from None
            raise AuthorizationDenied(error.error)

        if response.status_code == 200:
            try:
                parsed = CaseTransferResponse.model_validate(response.json())
            except (ValueError, ValidationError):
                logger.error("handover_transfer_error code=invalid_response")
                raise ServiceUnavailable("Handover no disponible.") from None
            if parsed.case_id != case_id or parsed.advisor_id != target_advisor_id:
                logger.error("handover_transfer_error code=case_mismatch")
                raise ServiceUnavailable("Handover no disponible.") from None
            return parsed

        logger.error("handover_transfer_error code=%s", response.status_code)
        raise ServiceUnavailable("Handover no disponible.")

    def reassign(
        self, case_id: str, advisor_id: str, target_advisor_id: str
    ) -> CaseReassignResponse:
        try:
            body = CaseReassignRequest(
                advisor_id=advisor_id, target_advisor_id=target_advisor_id
            )
            response = httpx.post(
                f"{self._base_url}/cases/{quote(case_id, safe='')}/reassign",
                content=body.model_dump_json(),
                headers=self._headers(content_type=True),
                timeout=self._timeout,
            )
        except (httpx.HTTPError, ValueError) as exc:
            logger.error("handover_reassign_error code=%s", type(exc).__name__)
            raise ServiceUnavailable("Handover no disponible.") from None

        if response.status_code in _REASSIGN_DENIAL_CODES:
            try:
                error = ErrorResponse.model_validate(response.json())
            except (ValueError, ValidationError):
                logger.error("handover_reassign_error code=%s", response.status_code)
                raise ServiceUnavailable("Handover no disponible.") from None
            if error.error not in _REASSIGN_DENIAL_CODES[response.status_code]:
                logger.error("handover_reassign_error code=%s", response.status_code)
                raise ServiceUnavailable("Handover no disponible.") from None
            raise AuthorizationDenied(error.error)

        if response.status_code == 200:
            try:
                parsed = CaseReassignResponse.model_validate(response.json())
            except (ValueError, ValidationError):
                logger.error("handover_reassign_error code=invalid_response")
                raise ServiceUnavailable("Handover no disponible.") from None
            if (
                parsed.case_id != case_id
                or parsed.advisor_id != target_advisor_id
            ):
                logger.error("handover_reassign_error code=case_mismatch")
                raise ServiceUnavailable("Handover no disponible.") from None
            return parsed

        logger.error("handover_reassign_error code=%s", response.status_code)
        raise ServiceUnavailable("Handover no disponible.")

    def authorize(
        self, case_id: str, advisor_id: str, action: CaseAuthorizeAction
    ) -> CaseAuthorizeResponse:
        try:
            body = CaseAuthorizeRequest(advisor_id=advisor_id, action=action)
            response = httpx.post(
                f"{self._base_url}/cases/{quote(case_id, safe='')}/authorize",
                content=body.model_dump_json(),
                headers=self._headers(content_type=True),
                timeout=self._timeout,
            )
        except httpx.HTTPError as exc:
            logger.error("handover_authorize_error code=%s", type(exc).__name__)
            raise ServiceUnavailable("Handover no disponible.") from None

        if response.status_code in _DENIAL_CODES:
            expected = _DENIAL_CODES[response.status_code]
            try:
                error = ErrorResponse.model_validate(response.json())
            except (ValueError, ValidationError):
                logger.error("handover_authorize_error code=%s", response.status_code)
                raise ServiceUnavailable("Handover no disponible.") from None
            if error.error != expected:
                logger.error("handover_authorize_error code=%s", response.status_code)
                raise ServiceUnavailable("Handover no disponible.") from None
            raise AuthorizationDenied(error.error)

        if response.status_code == 200:
            try:
                parsed = CaseAuthorizeResponse.model_validate(response.json())
            except (ValueError, ValidationError):
                logger.error("handover_authorize_error code=invalid_response")
                raise ServiceUnavailable("Handover no disponible.") from None
            if parsed.case_id != case_id:
                logger.error("handover_authorize_error code=case_mismatch")
                raise ServiceUnavailable("Handover no disponible.") from None
            return parsed

        logger.error("handover_authorize_error code=%s", response.status_code)
        raise ServiceUnavailable("Handover no disponible.")

    def forward_client_message(
        self, case_id: str, text: str, at: datetime
    ) -> CaseClientMessageResponse:
        try:
            body = CaseClientMessageRequest(text=text, at=at)
            response = httpx.post(
                f"{self._base_url}/cases/{quote(case_id, safe='')}/client-message",
                content=body.model_dump_json(),
                headers=self._headers(content_type=True),
                timeout=self._timeout,
            )
        except (httpx.HTTPError, ValueError) as exc:
            logger.error("handover_client_message_error code=%s", type(exc).__name__)
            raise ServiceUnavailable("Handover no disponible.") from None

        if response.status_code in _FORWARD_REJECTION_CODES:
            expected = _FORWARD_REJECTION_CODES[response.status_code]
            try:
                error = ErrorResponse.model_validate(response.json())
            except (ValueError, ValidationError):
                logger.error("handover_client_message_error code=%s", response.status_code)
                raise ServiceUnavailable("Handover no disponible.") from None
            if error.error != expected:
                logger.error("handover_client_message_error code=%s", response.status_code)
                raise ServiceUnavailable("Handover no disponible.") from None
            raise ForwardRejected(error.error)

        if response.status_code == 200:
            try:
                parsed = CaseClientMessageResponse.model_validate(response.json())
            except (ValueError, ValidationError):
                logger.error("handover_client_message_error code=invalid_response")
                raise ServiceUnavailable("Handover no disponible.") from None
            if parsed.case_id != case_id:
                logger.error("handover_client_message_error code=case_mismatch")
                raise ServiceUnavailable("Handover no disponible.") from None
            return parsed

        logger.error("handover_client_message_error code=%s", response.status_code)
        raise ServiceUnavailable("Handover no disponible.")

    def take(self, req: CaseTakeRequest) -> CaseTakeResponse:
        try:
            response = httpx.post(
                f"{self._base_url}/cases/take",
                content=req.model_dump_json(),
                headers=self._headers(content_type=True),
                timeout=self._timeout,
            )
        except httpx.HTTPError as exc:
            logger.error("handover_take_error code=%s", type(exc).__name__)
            raise ServiceUnavailable("Handover no disponible.") from None

        if response.status_code in (403, 409):
            try:
                error = ErrorResponse.model_validate(response.json())
            except (ValueError, ValidationError):
                logger.error("handover_take_error code=%s", response.status_code)
                raise ServiceUnavailable("Handover no disponible.") from None
            expected = {403: {"forbidden"}, 409: {"case_changed"}}
            if error.error not in expected[response.status_code]:
                logger.error("handover_take_error code=%s", response.status_code)
                raise ServiceUnavailable("Handover no disponible.") from None
            raise AuthorizationDenied(error.error)

        if response.status_code == 200:
            try:
                parsed = CaseTakeResponse.model_validate(response.json())
            except (ValueError, ValidationError):
                logger.error("handover_take_error code=invalid_response")
                raise ServiceUnavailable("Handover no disponible.") from None
            return parsed

        logger.error("handover_take_error code=%s", response.status_code)
        raise ServiceUnavailable("Handover no disponible.")

    def close(self, case_id: str, advisor_id: str) -> CaseCloseResponse:
        try:
            body = CaseCloseRequest(advisor_id=advisor_id)
            response = httpx.post(
                f"{self._base_url}/cases/{quote(case_id, safe='')}/close",
                content=body.model_dump_json(),
                headers=self._headers(content_type=True),
                timeout=self._timeout,
            )
        except httpx.HTTPError as exc:
            logger.error("handover_close_error code=%s", type(exc).__name__)
            raise ServiceUnavailable("Handover no disponible.") from None

        if response.status_code in _DENIAL_CODES:
            expected = _DENIAL_CODES[response.status_code]
            try:
                error = ErrorResponse.model_validate(response.json())
            except (ValueError, ValidationError):
                logger.error("handover_close_error code=%s", response.status_code)
                raise ServiceUnavailable("Handover no disponible.") from None
            if error.error != expected:
                logger.error("handover_close_error code=%s", response.status_code)
                raise ServiceUnavailable("Handover no disponible.") from None
            raise AuthorizationDenied(error.error)

        if response.status_code == 200:
            try:
                parsed = CaseCloseResponse.model_validate(response.json())
            except (ValueError, ValidationError):
                logger.error("handover_close_error code=invalid_response")
                raise ServiceUnavailable("Handover no disponible.") from None
            if parsed.case_id != case_id:
                logger.error("handover_close_error code=case_mismatch")
                raise ServiceUnavailable("Handover no disponible.") from None
            return parsed

        logger.error("handover_close_error code=%s", response.status_code)
        raise ServiceUnavailable("Handover no disponible.")


class FakeHandoverClient:
    def __init__(
        self,
        status: str = "queued",
        fail: bool = False,
        fail_assign: bool = False,
        authorize_error: str | None = None,
        fail_authorize: bool = False,
        authorized_advisors: set[str] | None = None,
        client_message_status: str = "not_assigned",
        client_message_error: str | None = None,
        fail_client_message: bool = False,
        transfer_error: str | None = None,
        fail_transfer: bool = False,
        close_error: str | None = None,
        fail_close: bool = False,
        assign_error: str | None = None,
        fail_try_assign: bool = False,
        auto_assign_status: str = "assigned",
        auto_assign_advisor_id: str | None = None,
        fail_auto_assign: bool = False,
        case_list: list[CaseListItem] | None = None,
        fail_list_cases: bool = False,
        fail_sync: bool = False,
        reassign_error: str | None = None,
        fail_reassign: bool = False,
        take_created: bool = True,
        take_case_id: str | None = None,
        take_error: str | None = None,
        fail_take: bool = False,
    ) -> None:
        self.requests: list[HandoverRequest] = []
        self.roster_syncs: list[AdvisorRosterSyncRequest] = []
        self.fail_sync = fail_sync
        self.assigned: list[tuple[str, str]] = []
        self.try_assigned: list[tuple[str, str]] = []
        self.auto_assigned: list[tuple[str, tuple[str, ...]]] = []
        self.auto_assign_strategies: list[str] = []
        self.authorized: list[tuple[str, str, str]] = []
        self.listed: list[str] = []
        self.listed_all: list[str] = []
        self.listed_overview: list[str] = []
        self.taken: list[CaseTakeRequest] = []
        self.transferred: list[tuple[str, str, str]] = []
        self.reassigned: list[tuple[str, str, str]] = []
        self.client_messages: list[tuple[str, str, datetime]] = []
        self.closed: list[tuple[str, str]] = []
        self.status = status
        self.fail = fail
        self.fail_assign = fail_assign
        self.authorize_error = authorize_error
        self.fail_authorize = fail_authorize
        self.authorized_advisors = authorized_advisors
        self.client_message_status = client_message_status
        self.client_message_error = client_message_error
        self.fail_client_message = fail_client_message
        self.transfer_error = transfer_error
        self.fail_transfer = fail_transfer
        self.close_error = close_error
        self.fail_close = fail_close
        self.assign_error = assign_error
        self.fail_try_assign = fail_try_assign
        self.auto_assign_status = auto_assign_status
        self.auto_assign_advisor_id = auto_assign_advisor_id
        self.fail_auto_assign = fail_auto_assign
        self.case_list = case_list or []
        self.fail_list_cases = fail_list_cases
        self.reassign_error = reassign_error
        self.fail_reassign = fail_reassign
        self.take_created = take_created
        self.take_case_id = take_case_id
        self.take_error = take_error
        self.fail_take = fail_take
        self._take_assignments: dict[str, tuple[str, str]] = {}
        self._take_lock = threading.Lock()

    def request(self, req: HandoverRequest) -> HandoverResponse:
        self.requests.append(req)
        if self.fail:
            raise ServiceUnavailable("Handover caído")
        return HandoverResponse(status=self.status, case_id=req.case_id)  # type: ignore[arg-type]

    def sync_roster(
        self, req: AdvisorRosterSyncRequest
    ) -> AdvisorRosterSyncResponse:
        self.roster_syncs.append(req)
        if self.fail_sync:
            raise ServiceUnavailable("Handover caído")
        return AdvisorRosterSyncResponse(
            status="synced",
            generation=req.generation,
            advisors=sum(
                1
                for entry in req.profiles
                if entry.role in ("asesor", "supervisor")
            ),
            orphaned_cases=0,
        )

    def assign(self, case_id: str, advisor_id: str) -> CaseAssignResponse:
        self.assigned.append((case_id, advisor_id))
        if self.fail_assign:
            raise ServiceUnavailable("Handover caído")
        return CaseAssignResponse(status="assigned", case_id=case_id)

    def try_assign(self, case_id: str, advisor_id: str) -> CaseAssignResponse:
        self.try_assigned.append((case_id, advisor_id))
        if self.fail_try_assign:
            raise ServiceUnavailable("Handover caído")
        if self.assign_error:
            raise AuthorizationDenied(self.assign_error)
        return CaseAssignResponse(status="assigned", case_id=case_id)

    def auto_assign(
        self, case_id: str, candidate_ids: list[str], strategy: str = "por_carga"
    ) -> CaseAutoAssignResponse:
        self.auto_assigned.append((case_id, tuple(candidate_ids)))
        self.auto_assign_strategies.append(strategy)
        if self.fail_auto_assign:
            raise ServiceUnavailable("Handover caído")
        advisor_id = self.auto_assign_advisor_id
        if advisor_id is None and self.auto_assign_status == "assigned":
            advisor_id = candidate_ids[0] if candidate_ids else None
        return CaseAutoAssignResponse(
            status=self.auto_assign_status,  # type: ignore[arg-type]
            case_id=case_id,
            advisor_id=advisor_id,
        )

    def list_cases(
        self, advisor_id: str, scope: str = "mine"
    ) -> CaseListResponse:
        if scope == "all":
            self.listed_all.append(advisor_id)
        elif scope == "overview":
            self.listed_overview.append(advisor_id)
        else:
            self.listed.append(advisor_id)
        if self.fail_list_cases:
            raise ServiceUnavailable("Handover caído")
        return CaseListResponse(self.case_list)

    def transfer(
        self, case_id: str, advisor_id: str, target_advisor_id: str
    ) -> CaseTransferResponse:
        self.transferred.append((case_id, advisor_id, target_advisor_id))
        if self.fail_transfer:
            raise ServiceUnavailable("Handover caído")
        if self.transfer_error:
            raise AuthorizationDenied(self.transfer_error)
        return CaseTransferResponse(
            status="assigned", case_id=case_id, advisor_id=target_advisor_id
        )

    def reassign(
        self, case_id: str, advisor_id: str, target_advisor_id: str
    ) -> CaseReassignResponse:
        self.reassigned.append((case_id, advisor_id, target_advisor_id))
        if self.fail_reassign:
            raise ServiceUnavailable("Handover caído")
        if self.reassign_error:
            raise AuthorizationDenied(self.reassign_error)
        return CaseReassignResponse(
            status="assigned",
            case_id=case_id,
            previous_advisor_id="previous",
            advisor_id=target_advisor_id,
        )

    def authorize(
        self, case_id: str, advisor_id: str, action: CaseAuthorizeAction
    ) -> CaseAuthorizeResponse:
        self.authorized.append((case_id, advisor_id, action))
        if (
            self.authorized_advisors is not None
            and advisor_id not in self.authorized_advisors
        ):
            raise AuthorizationDenied("forbidden")
        if self.fail_authorize:
            raise ServiceUnavailable("Handover caído")
        if self.authorize_error:
            raise AuthorizationDenied(self.authorize_error)
        return CaseAuthorizeResponse(allowed=True, case_id=case_id)

    def forward_client_message(
        self, case_id: str, text: str, at: datetime
    ) -> CaseClientMessageResponse:
        self.client_messages.append((case_id, text, at))
        if self.fail_client_message:
            raise ServiceUnavailable("Handover caído")
        if self.client_message_error:
            raise ForwardRejected(self.client_message_error)
        return CaseClientMessageResponse(
            status=self.client_message_status,  # type: ignore[arg-type]
            case_id=case_id,
        )

    def take(self, req: CaseTakeRequest) -> CaseTakeResponse:
        self.taken.append(req)
        if self.fail_take:
            raise ServiceUnavailable("Handover caído")
        if self.take_error:
            raise AuthorizationDenied(self.take_error)
        with self._take_lock:
            assigned = self._take_assignments.get(req.contact_id)
            if assigned is not None:
                case_id, advisor_id = assigned
                if advisor_id != req.advisor_id:
                    raise AuthorizationDenied("case_changed")
                return CaseTakeResponse(
                    status="taken", case_id=case_id, created=False
                )
            case_id = self.take_case_id or req.case_id
            self._take_assignments[req.contact_id] = (case_id, req.advisor_id)
            return CaseTakeResponse(
                status="taken", case_id=case_id, created=self.take_created
            )

    def close(self, case_id: str, advisor_id: str) -> CaseCloseResponse:
        self.closed.append((case_id, advisor_id))
        if self.fail_close:
            raise ServiceUnavailable("Handover caído")
        if self.close_error:
            raise AuthorizationDenied(self.close_error)
        return CaseCloseResponse(status="closed", case_id=case_id)

