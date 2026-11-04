"""Adaptador del orquestador (POST /messages) con versión falsa."""
from __future__ import annotations

from typing import Protocol

import httpx
from lazaro_contracts import SERVICE_TOKEN_HEADER, MessageRequest, NormalizedMessage

from ..domain import OrchestratorError


class OrchestratorClient(Protocol):
    def post_message(
        self, request: MessageRequest | NormalizedMessage
    ) -> None:  # lanza OrchestratorError
        ...


class HttpOrchestratorClient:
    def __init__(self, base_url: str, service_token: str, timeout: float = 10) -> None:
        self._base_url = base_url.rstrip("/")
        self._service_token = service_token
        self._timeout = timeout

    def post_message(self, request: MessageRequest | NormalizedMessage) -> None:
        try:
            response = httpx.post(
                f"{self._base_url}/messages",
                content=request.model_dump_json(),
                headers={
                    SERVICE_TOKEN_HEADER: self._service_token,
                    "Content-Type": "application/json",
                },
                timeout=self._timeout,
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise OrchestratorError(
                f"El orquestador respondió {exc.response.status_code}."
            ) from None
        except httpx.HTTPError as exc:
            raise OrchestratorError(
                f"No se pudo contactar con el orquestador ({type(exc).__name__})."
            ) from None


class FakeOrchestratorClient:
    def __init__(self, fail: bool = False) -> None:
        self.received: list[MessageRequest | NormalizedMessage] = []
        self.fail = fail

    def post_message(self, request: MessageRequest | NormalizedMessage) -> None:
        if self.fail:
            raise OrchestratorError("orquestador caído")
        self.received.append(request)
