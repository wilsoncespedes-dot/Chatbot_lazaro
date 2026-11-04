"""Adaptador real de WhatsApp Cloud API (Meta) con cliente HTTP inyectado."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Callable, Sequence

import httpx
from lazaro_contracts import (
    ChannelCapabilities,
    DeliveryStatus,
    NormalizedMessage,
    ResponseBlock,
    TemplateBlock,
)

from ..domain import ChannelSendFailed, ChannelWindowClosed
from ..whatsapp_cloud import (
    build_send_payloads,
    normalize_message,
    to_delivery_status,
    translate_error,
    whatsapp_capabilities,
)
from .whatsapp_window import WhatsAppWindowStore

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class WhatsAppCloudConfig:
    access_token: str = field(repr=False)
    phone_number_id: str
    graph_base_url: str
    api_version: str
    template_language: str
    interactive_body_text: str
    window_hours: int


class WhatsAppCloudAdapter:
    """Implementación de `ChannelAdapter` sobre Graph API de Meta."""

    channel = "whatsapp"

    def __init__(
        self,
        config: WhatsAppCloudConfig,
        http: httpx.Client,
        window: WhatsAppWindowStore,
        clock: Callable[[], datetime],
    ) -> None:
        self._config = config
        self._http = http
        self._window = window
        self._clock = clock

    @property
    def messages_url(self) -> str:
        base = self._config.graph_base_url.rstrip("/")
        return (
            f"{base}/{self._config.api_version}/"
            f"{self._config.phone_number_id}/messages"
        )

    def _capabilities(self, *, window_open: bool) -> ChannelCapabilities:
        return ChannelCapabilities(**whatsapp_capabilities(window_open=window_open))

    def capabilities(self) -> ChannelCapabilities:
        """R30: sin destino se asume ventana cerrada."""
        return self._capabilities(window_open=False)

    def capabilities_for(self, destination: str) -> ChannelCapabilities:
        """R28, R29, R42: ventana abierta según el último entrante del wa_id."""
        try:
            last = self._window.last_inbound(destination)
        except Exception as exc:  # noqa: BLE001 - R42 falla abierto y avisa
            logger.warning(
                "No se pudo consultar la ventana de WhatsApp (%s); se trata como abierta",
                type(exc).__name__,
            )
            return self._capabilities(window_open=True)
        if last is None:
            return self._capabilities(window_open=False)
        if last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)
        elapsed = self._clock() - last
        return self._capabilities(
            window_open=elapsed < timedelta(hours=self._config.window_hours)
        )

    def normalize_incoming(
        self, raw: dict, received_at: datetime
    ) -> NormalizedMessage | None:
        return normalize_message(raw, received_at)

    def send(
        self, destination: str, blocks: Sequence[ResponseBlock]
    ) -> DeliveryStatus:
        block_list = list(blocks)
        if any(
            not isinstance(block, TemplateBlock) for block in block_list
        ) and not self.capabilities_for(destination).free_text_allowed:
            raise ChannelWindowClosed(
                "La ventana de atención de WhatsApp está cerrada."
            )
        payloads = build_send_payloads(
            destination,
            block_list,
            self._config.template_language,
            self._config.interactive_body_text,
        )
        headers = {"Authorization": f"Bearer {self._config.access_token}"}
        for payload in payloads:
            try:
                response = self._http.post(
                    self.messages_url, json=payload, headers=headers
                )
            except httpx.HTTPError as exc:
                logger.error(
                    "whatsapp_network_error type=%s", type(exc).__name__
                )
                raise ChannelSendFailed(
                    "No se pudo contactar con Meta para enviar el mensaje."
                ) from None
            if not 200 <= response.status_code < 300:
                try:
                    body: object = response.json()
                except ValueError:
                    body = None
                raise translate_error(response.status_code, body) from None
        return "sent"

    def delivery_status(self, raw: str) -> DeliveryStatus:
        return to_delivery_status(raw)
