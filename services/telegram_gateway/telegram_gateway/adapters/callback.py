"""Cliente HTTP del callback saliente con la IP validada fijada (anti-SSRF)."""
from __future__ import annotations

import ipaddress
from collections.abc import Mapping
from typing import Any, Protocol
from urllib.parse import urlsplit, urlunsplit

import httpx

from ..domain import CallbackNetworkError
from ..url_guard import Resolver, system_resolver, validate_callback_url


class CallbackClient(Protocol):
    def post(self, url: str, body: bytes, headers: Mapping[str, str]) -> int:
        """Envía `body` y devuelve el código HTTP; puede lanzar."""
        ...


def _url_with_address(url: str, address: str) -> str:
    parts = urlsplit(url)
    host = address
    try:
        if ipaddress.ip_address(address.split("%", 1)[0]).version == 6:
            host = f"[{address}]"
    except ValueError:
        pass
    netloc = host
    if parts.port is not None:
        netloc = f"{host}:{parts.port}"
    return urlunsplit((parts.scheme, netloc, parts.path or "/", parts.query, ""))


class HttpCallbackClient:
    def __init__(
        self,
        timeout: float,
        allow_private: bool = False,
        resolver: Resolver = system_resolver,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._timeout = timeout
        self._allow_private = allow_private
        self._resolver = resolver
        self._transport = transport

    def post(self, url: str, body: bytes, headers: Mapping[str, str]) -> int:
        host, addresses = validate_callback_url(
            url, self._resolver, self._allow_private
        )
        target = _url_with_address(url, addresses[0])
        parts = urlsplit(url)
        request_headers = dict(headers)
        request_headers["Host"] = parts.netloc
        extensions: dict[str, Any] = {"sni_hostname": host}
        try:
            with httpx.Client(
                timeout=self._timeout,
                follow_redirects=False,
                transport=self._transport,
            ) as client:
                response = client.post(
                    target,
                    content=body,
                    headers=request_headers,
                    extensions=extensions,
                )
                return response.status_code
        except httpx.HTTPError as exc:
            raise CallbackNetworkError(type(exc).__name__) from None


class FakeCallbackClient:
    def __init__(self, status: int = 200, error: BaseException | None = None) -> None:
        self.status = status
        self.error = error
        self.requests: list[tuple[str, bytes, dict[str, str]]] = []

    def post(self, url: str, body: bytes, headers: Mapping[str, str]) -> int:
        self.requests.append((url, body, dict(headers)))
        if self.error is not None:
            raise self.error
        return self.status
