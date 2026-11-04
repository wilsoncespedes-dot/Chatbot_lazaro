"""Cliente del gateway multicanal (POST /send) con versión falsa."""
from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import Protocol

import httpx
from lazaro_contracts import (
    SERVICE_TOKEN_HEADER,
    ChannelSendRequest,
    ResponseBlock,
    SendRequest,
    TextBlock,
)

from ..domain import ChannelRejected, ServiceUnavailable

logger = logging.getLogger(__name__)


class GatewayClient(Protocol):
    def send(self, chat_id: int, text: str) -> None: ...

    def send_channel(self, channel: str, destination: str, text: str) -> None: ...

    def send_channel_blocks(
        self, channel: str, destination: str, blocks: Sequence[ResponseBlock]
    ) -> None: ...


class ChannelBoundGateway:
    """Envía las respuestas al canal y destino del mensaje canónico en curso."""

    def __init__(self, inner: GatewayClient, channel: str, destination: str) -> None:
        self._inner = inner
        self._channel = channel
        self._destination = destination

    def send(self, chat_id: int, text: str) -> None:
        self._inner.send_channel(self._channel, self._destination, text)


class HttpGatewayClient:
    def __init__(self, base_url: str, service_token: str, timeout: float = 10) -> None:
        self._base_url = base_url.rstrip("/")
        self._service_token = service_token
        self._timeout = timeout

    def _post(self, body: SendRequest | ChannelSendRequest) -> None:
        try:
            response = httpx.post(
                f"{self._base_url}/send",
                content=body.model_dump_json(),
                headers={
                    SERVICE_TOKEN_HEADER: self._service_token,
                    "Content-Type": "application/json",
                },
                timeout=self._timeout,
            )
        except (httpx.HTTPError, ValueError) as exc:
            logger.error("gateway_error code=%s", type(exc).__name__)
            raise ServiceUnavailable("Gateway no disponible.") from None
        if response.status_code == 422:
            logger.warning("gateway_channel_rejected code=422")
            raise ChannelRejected("El canal rechazó el envío.")
        try:
            response.raise_for_status()
        except httpx.HTTPError as exc:
            logger.error("gateway_error code=%s", type(exc).__name__)
            raise ServiceUnavailable("Gateway no disponible.") from None

    def send(self, chat_id: int, text: str) -> None:
        self._post(SendRequest(chat_id=chat_id, text=text))

    def send_channel(self, channel: str, destination: str, text: str) -> None:
        self._post(
            ChannelSendRequest(
                channel=channel,  # type: ignore[arg-type]
                destination=destination,
                blocks=[TextBlock(type="text", text=text)],
            )
        )

    def send_channel_blocks(
        self, channel: str, destination: str, blocks: Sequence[ResponseBlock]
    ) -> None:
        self._post(
            ChannelSendRequest(
                channel=channel,  # type: ignore[arg-type]
                destination=destination,
                blocks=list(blocks),
            )
        )


class FakeGatewayClient:
    def __init__(
        self,
        fail: bool = False,
        fail_for: set[int] | None = None,
        reject_channel: bool = False,
    ) -> None:
        self.sent: list[tuple[int, str]] = []
        self.channel_sent: list[tuple[str, str, str]] = []
        self.blocks_sent: list[tuple[str, str, list[ResponseBlock]]] = []
        self.fail = fail
        self.fail_for: set[int] = set(fail_for or ())
        self.reject_channel = reject_channel

    def send(self, chat_id: int, text: str) -> None:
        if self.fail or chat_id in self.fail_for:
            raise ServiceUnavailable("Gateway caído")
        if self.reject_channel:
            raise ChannelRejected("El canal rechazó el envío.")
        self.sent.append((chat_id, text))

    def send_channel(self, channel: str, destination: str, text: str) -> None:
        if self.fail:
            raise ServiceUnavailable("Gateway caído")
        if self.reject_channel:
            raise ChannelRejected("El canal rechazó el envío.")
        self.channel_sent.append((channel, destination, text))

    def send_channel_blocks(
        self, channel: str, destination: str, blocks: Sequence[ResponseBlock]
    ) -> None:
        if self.fail:
            raise ServiceUnavailable("Gateway caído")
        if self.reject_channel:
            raise ChannelRejected("El canal rechazó el envío.")
        stored = list(blocks)
        self.blocks_sent.append((channel, destination, stored))
        texts = [
            block.text for block in stored if isinstance(block, TextBlock)
        ]
        rendered = "\n".join(texts)
        if texts:
            self.channel_sent.append((channel, destination, rendered))
        if channel == "telegram":
            try:
                chat_id = int(destination)
            except (TypeError, ValueError):
                return
            self.sent.append((chat_id, rendered))
