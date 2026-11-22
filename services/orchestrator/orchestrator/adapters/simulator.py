"""Cliente HTTP del canal SIMULADO y su versión falsa (#63)."""
from __future__ import annotations

from typing import Protocol

import httpx
from lazaro_contracts import (
    SERVICE_TOKEN_HEADER,
    ChannelInfo,
    ChannelListResponse,
    MailboxEntry,
    MailboxResponse,
    SimulatedInboundResponse,
)
from pydantic import ValidationError

from ..domain import ServiceUnavailable

SIMULATED_ADAPTER_TYPE = "simulado"


class SimulatorUnavailable(ServiceUnavailable):
    """El gateway no responde o responde algo inválido para el simulador."""


class SimulatorClient(Protocol):
    def list_channels(self) -> list[ChannelInfo]:
        """Canales registrados con adapter_type = simulado."""
        ...

    def simulate(
        self, channel_id: str, external_user_id: str, text: str
    ) -> SimulatedInboundResponse: ...

    def mailbox(
        self, channel_id: str, destination: str, after: int = 0
    ) -> MailboxResponse: ...


class HttpSimulatorClient:
    """Solo usa las tres rutas del simulador y nunca recibe secretos."""

    def __init__(
        self,
        base_url: str,
        service_token: str,
        timeout: float = 10,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._service_token = service_token
        self._timeout = timeout
        self._transport = transport

    def _request(self, method: str, path: str, **kwargs):
        headers = {SERVICE_TOKEN_HEADER: self._service_token}
        try:
            with httpx.Client(
                timeout=self._timeout,
                transport=self._transport,
                follow_redirects=False,
            ) as client:
                response = client.request(
                    method, f"{self._base_url}{path}", headers=headers, **kwargs
                )
        except (httpx.HTTPError, ValueError):
            raise SimulatorUnavailable("El gateway no está disponible.") from None
        if not 200 <= response.status_code < 300:
            raise SimulatorUnavailable("El gateway no está disponible.")
        try:
            return response.json()
        except ValueError:
            raise SimulatorUnavailable("El gateway no está disponible.") from None

    def list_channels(self) -> list[ChannelInfo]:
        payload = self._request("GET", "/channels")
        try:
            listing = ChannelListResponse.model_validate(payload)
        except (TypeError, ValueError, ValidationError):
            raise SimulatorUnavailable("El gateway no está disponible.") from None
        return [
            channel
            for channel in listing.channels
            if channel.adapter_type == SIMULATED_ADAPTER_TYPE
        ]

    def simulate(
        self, channel_id: str, external_user_id: str, text: str
    ) -> SimulatedInboundResponse:
        payload = self._request(
            "POST",
            f"/channels/{channel_id}/simulate",
            json={"external_user_id": external_user_id, "text": text},
        )
        try:
            return SimulatedInboundResponse.model_validate(payload)
        except (TypeError, ValueError, ValidationError):
            raise SimulatorUnavailable("El gateway no está disponible.") from None

    def mailbox(
        self, channel_id: str, destination: str, after: int = 0
    ) -> MailboxResponse:
        payload = self._request(
            "GET",
            f"/channels/{channel_id}/mailbox",
            params={"destination": destination, "after": after},
        )
        try:
            return MailboxResponse.model_validate(payload)
        except (TypeError, ValueError, ValidationError):
            raise SimulatorUnavailable("El gateway no está disponible.") from None


class FakeSimulatorClient:
    def __init__(
        self,
        channels: list[ChannelInfo] | None = None,
        entries: list[MailboxEntry] | None = None,
        *,
        fail: bool = False,
        forwarded: bool = True,
        reason: str | None = None,
    ) -> None:
        self.channels = list(channels or [])
        self.entries = list(entries or [])
        self.fail = fail
        self.forwarded = forwarded
        self.reason = reason
        self.calls: list[tuple] = []

    def list_channels(self) -> list[ChannelInfo]:
        self.calls.append(("list_channels",))
        if self.fail:
            raise SimulatorUnavailable("gateway caído")
        return [
            channel
            for channel in self.channels
            if channel.adapter_type == SIMULATED_ADAPTER_TYPE
        ]

    def simulate(
        self, channel_id: str, external_user_id: str, text: str
    ) -> SimulatedInboundResponse:
        self.calls.append(("simulate", channel_id, external_user_id, text))
        if self.fail:
            raise SimulatorUnavailable("gateway caído")
        return SimulatedInboundResponse(
            status="accepted",
            forwarded=self.forwarded,
            reason=self.reason,
        )

    def mailbox(
        self, channel_id: str, destination: str, after: int = 0
    ) -> MailboxResponse:
        self.calls.append(("mailbox", channel_id, destination, after))
        if self.fail:
            raise SimulatorUnavailable("gateway caído")
        entries = [
            entry
            for entry in self.entries
            if entry.channel == channel_id
            and entry.destination == destination
            and entry.id > after
        ]
        return MailboxResponse(channel=channel_id, entries=entries)
