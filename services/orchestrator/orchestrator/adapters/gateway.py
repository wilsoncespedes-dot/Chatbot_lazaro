"""Cliente del gateway de Telegram (POST /send) con versión falsa."""
from __future__ import annotations

import logging
from typing import Protocol

import httpx
from lazaro_contracts import SERVICE_TOKEN_HEADER, SendRequest

from ..domain import ServiceUnavailable

logger = logging.getLogger(__name__)


class GatewayClient(Protocol):
    def send(self, chat_id: int, text: str) -> None: ...


class HttpGatewayClient:
    def __init__(self, base_url: str, service_token: str, timeout: float = 10) -> None:
        self._base_url = base_url.rstrip("/")
        self._service_token = service_token
        self._timeout = timeout

    def send(self, chat_id: int, text: str) -> None:
        try:
            body = SendRequest(chat_id=chat_id, text=text)
            response = httpx.post(
                f"{self._base_url}/send",
                content=body.model_dump_json(),
                headers={
                    SERVICE_TOKEN_HEADER: self._service_token,
                    "Content-Type": "application/json",
                },
                timeout=self._timeout,
            )
            response.raise_for_status()
        except (httpx.HTTPError, ValueError) as exc:
            logger.error("gateway_error code=%s", type(exc).__name__)
            raise ServiceUnavailable("Gateway no disponible.") from None


class FakeGatewayClient:
    def __init__(self, fail: bool = False) -> None:
        self.sent: list[tuple[int, str]] = []
        self.fail = fail

    def send(self, chat_id: int, text: str) -> None:
        if self.fail:
            raise ServiceUnavailable("Gateway caído")
        self.sent.append((chat_id, text))
