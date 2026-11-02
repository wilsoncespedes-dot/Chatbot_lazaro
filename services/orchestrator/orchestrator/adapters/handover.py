"""Cliente de handover (POST /handover, /authorize y /assign) con versión falsa."""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Protocol
from urllib.parse import quote

import httpx
from lazaro_contracts import (
    SERVICE_TOKEN_HEADER,
    CaseAssignRequest,
    CaseAssignResponse,
    CaseAuthorizeAction,
    CaseAuthorizeRequest,
    CaseAuthorizeResponse,
    CaseClientMessageRequest,
    CaseClientMessageResponse,
    CaseCloseRequest,
    CaseCloseResponse,
    CaseListItem,
    CaseListResponse,
    ErrorResponse,
    HandoverRequest,
    HandoverResponse,
)
from pydantic import ValidationError

from ..domain import AuthorizationDenied, ForwardRejected, ServiceUnavailable

logger = logging.getLogger(__name__)

_DENIAL_CODES = {403: "forbidden", 404: "not_found", 409: "case_closed"}
_FORWARD_REJECTION_CODES = {404: "not_found", 502: "upstream_error"}


class HandoverClient(Protocol):
    def request(self, req: HandoverRequest) -> HandoverResponse: ...

    def assign(self, case_id: str, advisor_id: str) -> CaseAssignResponse: ...

    def try_assign(self, case_id: str, advisor_id: str) -> CaseAssignResponse: ...

    def authorize(
        self, case_id: str, advisor_id: str, action: CaseAuthorizeAction
    ) -> CaseAuthorizeResponse: ...

    def list_cases(self, advisor_id: str) -> CaseListResponse: ...

    def forward_client_message(
        self, case_id: str, text: str, at: datetime
    ) -> CaseClientMessageResponse: ...

    def close(self, case_id: str, advisor_id: str) -> CaseCloseResponse: ...



class HttpHandoverClient:
    def __init__(self, base_url: str, service_token: str, timeout: float = 10) -> None:
        self._base_url = base_url.rstrip("/")
        self._service_token = service_token
        self._timeout = timeout

    def request(self, req: HandoverRequest) -> HandoverResponse:
        try:
            response = httpx.post(
                f"{self._base_url}/handover",
                content=req.model_dump_json(),
                headers={
                    SERVICE_TOKEN_HEADER: self._service_token,
                    "Content-Type": "application/json",
                },
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
                headers={
                    SERVICE_TOKEN_HEADER: self._service_token,
                    "Content-Type": "application/json",
                },
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
                headers={
                    SERVICE_TOKEN_HEADER: self._service_token,
                    "Content-Type": "application/json",
                },
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

    def list_cases(self, advisor_id: str) -> CaseListResponse:
        try:
            response = httpx.get(
                f"{self._base_url}/cases",
                params={"advisor_id": advisor_id},
                headers={SERVICE_TOKEN_HEADER: self._service_token},
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

    def authorize(
        self, case_id: str, advisor_id: str, action: CaseAuthorizeAction
    ) -> CaseAuthorizeResponse:
        try:
            body = CaseAuthorizeRequest(advisor_id=advisor_id, action=action)
            response = httpx.post(
                f"{self._base_url}/cases/{quote(case_id, safe='')}/authorize",
                content=body.model_dump_json(),
                headers={
                    SERVICE_TOKEN_HEADER: self._service_token,
                    "Content-Type": "application/json",
                },
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
                headers={
                    SERVICE_TOKEN_HEADER: self._service_token,
                    "Content-Type": "application/json",
                },
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

    def close(self, case_id: str, advisor_id: str) -> CaseCloseResponse:
        try:
            body = CaseCloseRequest(advisor_id=advisor_id)
            response = httpx.post(
                f"{self._base_url}/cases/{quote(case_id, safe='')}/close",
                content=body.model_dump_json(),
                headers={
                    SERVICE_TOKEN_HEADER: self._service_token,
                    "Content-Type": "application/json",
                },
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
        status: str = "notified",
        fail: bool = False,
        fail_assign: bool = False,
        authorize_error: str | None = None,
        fail_authorize: bool = False,
        authorized_advisors: set[str] | None = None,
        client_message_status: str = "not_assigned",
        client_message_error: str | None = None,
        fail_client_message: bool = False,
        close_error: str | None = None,
        fail_close: bool = False,
        assign_error: str | None = None,
        fail_try_assign: bool = False,
        case_list: list[CaseListItem] | None = None,
        fail_list_cases: bool = False,
    ) -> None:
        self.requests: list[HandoverRequest] = []
        self.assigned: list[tuple[str, str]] = []
        self.try_assigned: list[tuple[str, str]] = []
        self.authorized: list[tuple[str, str, str]] = []
        self.listed: list[str] = []
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
        self.close_error = close_error
        self.fail_close = fail_close
        self.assign_error = assign_error
        self.fail_try_assign = fail_try_assign
        self.case_list = case_list or []
        self.fail_list_cases = fail_list_cases

    def request(self, req: HandoverRequest) -> HandoverResponse:
        self.requests.append(req)
        if self.fail:
            raise ServiceUnavailable("Handover caído")
        return HandoverResponse(status=self.status, case_id=req.case_id)  # type: ignore[arg-type]

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

    def list_cases(self, advisor_id: str) -> CaseListResponse:
        self.listed.append(advisor_id)
        if self.fail_list_cases:
            raise ServiceUnavailable("Handover caído")
        return CaseListResponse(self.case_list)

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

    def close(self, case_id: str, advisor_id: str) -> CaseCloseResponse:
        self.closed.append((case_id, advisor_id))
        if self.fail_close:
            raise ServiceUnavailable("Handover caído")
        if self.close_error:
            raise AuthorizationDenied(self.close_error)
        return CaseCloseResponse(status="closed", case_id=case_id)

