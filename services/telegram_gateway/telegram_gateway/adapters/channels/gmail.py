"""Adaptador de correo Gmail API para el gateway multicanal."""
from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from email.utils import parseaddr
from typing import Any, Callable, ClassVar

from lazaro_contracts import ChannelCapabilities, DeliveryStatus, NormalizedMessage, ResponseBlock
from pydantic import ValidationError

from ...adapters.gmail_api import (
    GmailApiClient,
    GmailApiError,
    GmailTransport,
    _headers,
    plain_text_body,
)
from ...adapters.telegram import render_blocks
from ...domain import ChannelNotConfigured, ChannelRecord, ChannelSecrets, InvalidChannelConfig
from ...registry import CHANNEL_REGISTRY, ChannelContext

logger = logging.getLogger(__name__)
CHANNEL_TYPE = "gmail_api"
_CAPABILITIES = ChannelCapabilities(
    free_text_allowed=True,
    max_options=0,
    min_list_options=0,
    max_list_options=0,
    supports_links=True,
    requires_template=False,
    supports_buttons=False,
    supports_images=False,
    supports_files=False,
    supports_audio=False,
)


def _received_at(value: Any, fallback: datetime) -> datetime:
    try:
        return datetime.fromtimestamp(int(value) / 1000, tz=timezone.utc)
    except (ValueError, TypeError, OverflowError):
        return fallback


@CHANNEL_REGISTRY.register(CHANNEL_TYPE)
class GmailChannel:
    """Canal Gmail; procesa cuerpos de texto y responde por `threadId`."""

    managed_by_environment: ClassVar[bool] = False

    def __init__(
        self,
        channel_id: str,
        email_address: str,
        client: GmailApiClient,
        clock: Callable[[], datetime],
    ) -> None:
        self._channel_id = channel_id
        self._email_address = email_address
        self._client = client
        self._clock = clock

    @classmethod
    def is_available(cls, context: ChannelContext) -> bool:
        return context.adapters.gmail_transport is not None

    @classmethod
    def validate_config(cls, config: Mapping[str, Any], context: ChannelContext) -> None:
        address = config.get("email_address")
        parsed = parseaddr(address)[1] if isinstance(address, str) else ""
        if not parsed or parsed.casefold() != address.strip().casefold() or "@" not in parsed:
            raise InvalidChannelConfig("config.email_address debe ser un correo válido.")

    @classmethod
    def default_capabilities(
        cls, config: Mapping[str, Any] | None = None
    ) -> ChannelCapabilities:
        return _CAPABILITIES

    @classmethod
    def build(
        cls,
        record: ChannelRecord,
        context: ChannelContext,
        secrets: ChannelSecrets | None,
    ) -> "GmailChannel":
        if secrets is None or context.adapters.gmail_transport is None:
            raise ChannelNotConfigured("El canal Gmail no está configurado.")
        email_address = record.config.get("email_address")
        if not isinstance(email_address, str):
            raise ChannelNotConfigured("Falta config.email_address del canal Gmail.")
        try:
            client = GmailApiClient(secrets.credentials, context.adapters.gmail_transport)
        except ChannelNotConfigured:
            raise
        return cls(record.id, email_address, client, context.adapters.clock)

    @property
    def client(self) -> GmailApiClient:
        return self._client

    @property
    def email_address(self) -> str:
        return self._email_address

    def recibir_mensaje(self, payload: Mapping[str, Any]) -> NormalizedMessage | None:
        try:
            message_id = payload.get("id")
            thread_id = payload.get("threadId")
            body = payload.get("payload")
            if not isinstance(message_id, str) or not isinstance(thread_id, str):
                return None
            if not isinstance(body, dict):
                return None
            headers = _headers(payload)
            sender = parseaddr(headers.get("from", ""))[1]
            if not sender or sender.casefold() == self._email_address.casefold():
                return None
            text = plain_text_body(body)
            metadata: dict[str, Any] = {}
            subject = headers.get("subject", "")
            if subject:
                metadata["subject"] = subject[:256]
            return NormalizedMessage(
                channel=self._channel_id,
                external_user_id=sender,
                external_chat_id=thread_id,
                external_message_id=message_id,
                kind="text" if text else "unsupported",
                text=text,
                received_at=_received_at(payload.get("internalDate"), self._clock()),
                metadata=metadata,
            )
        except (TypeError, ValueError, ValidationError):
            return None

    def identificar_usuario(self, payload: Mapping[str, Any]) -> str | None:
        message = self.recibir_mensaje(payload)
        return message.external_user_id if message is not None else None

    def capacidades(self, destino: str | None = None) -> ChannelCapabilities:
        return _CAPABILITIES

    def enviar_mensaje(
        self, destino: str, bloques: Sequence[ResponseBlock]
    ) -> DeliveryStatus:
        text = "\n\n".join(render_blocks([block]) for block in bloques).strip()
        if not text:
            return "failed"
        try:
            self._client.send_reply(destino, self._email_address, text)
        except GmailApiError as exc:
            logger.warning(
                "gmail_send_failed channel_id=%s status=%s code=%s",
                self._channel_id,
                exc.status_code,
                exc.code,
            )
            return "failed"
        return "sent"
