"""Cliente de handover (POST /handover y POST /cases/{id}/assign) con versión falsa."""
from __future__ import annotations

import logging
from typing import Protocol
from urllib.parse import quote

import httpx
from lazaro_contracts import (
    SERVICE_TOKEN_HEADER,
    CaseAssignRequest,
    CaseAssignResponse,
    HandoverRequest,
    HandoverResponse,
)
from pydantic import ValidationError

from ..domain import ServiceUnavailable

logger = logging.getLogger(__name__)


class HandoverClient(Protocol):
    def request(self, req: HandoverRequest) -> HandoverResponse: ...

    def assign(self, case_id: str, advisor_id: str) -> CaseAssignResponse: ...


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


class FakeHandoverClient:
    def __init__(
        self, status: str = "notified", fail: bool = False, fail_assign: bool = False
    ) -> None:
        self.requests: list[HandoverRequest] = []
        self.assigned: list[tuple[str, str]] = []
        self.status = status
        self.fail = fail
        self.fail_assign = fail_assign

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
