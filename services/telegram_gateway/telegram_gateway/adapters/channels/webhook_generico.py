"""Adaptador de puerto para el canal genérico firmado (`webhook_generico`)."""
from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any, Callable, ClassVar
from uuid import uuid4

from lazaro_contracts import (
    LAZARO_SIGNATURE_HEADER,
    LAZARO_TIMESTAMP_HEADER,
    MAX_TEXT_LENGTH,
    ChannelCapabilities,
    DeliveryStatus,
    NormalizedMessage,
    ResponseBlock,
)
from pydantic import ValidationError

from ...adapters.callback import CallbackClient
from ...adapters.telegram import render_blocks
from ...domain import (
    CallbackNetworkError,
    ChannelNotConfigured,
    ChannelRecord,
    ChannelSecrets,
    InvalidChannelConfig,
)
from ...registry import CHANNEL_REGISTRY, ChannelContext
from ...signature import sign_payload
from ...url_guard import CallbackUrlRejected, validate_callback_url_syntax

logger = logging.getLogger(__name__)

CHANNEL_TYPE = "webhook_generico"


_CAPABILITIES = ChannelCapabilities(
    free_text_allowed=True,
    max_options=0,
    min_list_options=0,
    max_list_options=0,
    supports_links=False,
    requires_template=False,
    supports_buttons=False,
    supports_images=False,
    supports_files=False,
    supports_audio=False,
)


def _split_text(text: str, limit: int) -> list[str]:
    return [text[index : index + limit] for index in range(0, len(text), limit)]


@CHANNEL_REGISTRY.register(CHANNEL_TYPE)
class WebhookGenericoChannel:
    managed_by_environment: ClassVar[bool] = False

    def __init__(
        self,
        channel_id: str,
        callback_url: str | None,
        secret: str,
        client: CallbackClient,
        clock: Callable[[], datetime],
    ) -> None:
        self._channel_id = channel_id
        self._callback_url = callback_url
        self._secret = secret
        self._client = client
        self._clock = clock

    @classmethod
    def is_available(cls, context: ChannelContext) -> bool:
        return True

    @classmethod
    def build(
        cls,
        record: ChannelRecord,
        context: ChannelContext,
        secrets: ChannelSecrets | None,
    ) -> "WebhookGenericoChannel":
        if secrets is None or secrets.secret is None:
            raise ChannelNotConfigured("El canal no tiene secreto de firma.")
        client = context.adapters.callback
        if client is None:
            raise ChannelNotConfigured("El canal no está configurado en este servicio.")
        callback_url = record.config.get("callback_url")
        if callback_url is not None and not isinstance(callback_url, str):
            raise ChannelNotConfigured("config.callback_url no es válido.")
        return cls(
            record.id,
            callback_url,
            secrets.secret,
            client,
            context.adapters.clock,
        )

    @classmethod
    def validate_config(cls, config: Mapping[str, Any], context: ChannelContext) -> None:
        callback_url = config.get("callback_url")
        if callback_url is None:
            return
        if not isinstance(callback_url, str):
            raise InvalidChannelConfig("config.callback_url debe ser una URL https.")
        try:
            validate_callback_url_syntax(
                callback_url, context.settings.webhook_allow_private_callbacks
            )
        except CallbackUrlRejected:
            raise InvalidChannelConfig("config.callback_url no es válida.") from None

    def recibir_mensaje(
        self, payload: Mapping[str, Any]
    ) -> NormalizedMessage | None:
        try:
            message = NormalizedMessage.model_validate(dict(payload))
        except (TypeError, ValueError, ValidationError):
            return None
        if message.direction != "inbound":
            return None
        return message

    def identificar_usuario(self, payload: Mapping[str, Any]) -> str | None:
        try:
            message = NormalizedMessage.model_validate(dict(payload))
        except (TypeError, ValueError, ValidationError):
            return None
        if message.direction != "inbound":
            return None
        return message.external_user_id

    def capacidades(self, destino: str | None = None) -> ChannelCapabilities:
        return _CAPABILITIES

    @classmethod
    def default_capabilities(
        cls, config: Mapping[str, Any] | None = None
    ) -> ChannelCapabilities:
        return _CAPABILITIES

    def _body(self, destination: str, text: str) -> tuple[bytes, int]:
        message = NormalizedMessage(
            channel=self._channel_id,
            external_user_id=destination,
            external_chat_id=destination,
            external_message_id=f"out-{uuid4().hex}",
            kind="text",
            text=text,
            received_at=self._clock(),
            direction="outbound",
        )
        body = message.model_dump_json(exclude_none=True).encode("utf-8")
        return body, int(self._clock().timestamp())

    def enviar_mensaje(
        self, destino: str, bloques: Sequence[ResponseBlock]
    ) -> DeliveryStatus:
        if not self._callback_url:
            raise ChannelNotConfigured("El canal no tiene config.callback_url.")
        text = "\n".join(render_blocks([block]) for block in bloques)
        for chunk in _split_text(text, MAX_TEXT_LENGTH):
            body, timestamp = self._body(destino, chunk)
            headers = {
                "Content-Type": "application/json",
                LAZARO_TIMESTAMP_HEADER: str(timestamp),
                LAZARO_SIGNATURE_HEADER: sign_payload(self._secret, timestamp, body),
            }
            try:
                status = self._client.post(self._callback_url, body, headers)
            except CallbackUrlRejected:
                logger.warning("callback_blocked channel_id=%s", self._channel_id)
                return "failed"
            except CallbackNetworkError as exc:
                logger.warning(
                    "callback_network_error channel_id=%s code=%s",
                    self._channel_id,
                    type(exc).__name__,
                )
                return "failed"
            if not 200 <= status < 300:
                logger.warning(
                    "callback_failed channel_id=%s status=%s",
                    self._channel_id,
                    status,
                )
                return "failed"
        return "sent"
