"""Adaptador de puerto para el canal Telegram."""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any, Callable, ClassVar

from lazaro_contracts import ChannelCapabilities, DeliveryStatus, NormalizedMessage, ResponseBlock
from pydantic import ValidationError

from ...adapters.telegram import TelegramChannelAdapter, TelegramClient, telegram_capabilities
from ...domain import (
    ChannelRecord,
    ChannelSecrets,
    extract_callback,
    extract_incoming,
    normalize_callback,
    normalize_incoming,
)
from ...registry import CHANNEL_REGISTRY, ChannelContext


def _valid_update(payload: Mapping[str, Any]) -> dict[str, Any] | None:
    update = dict(payload)
    update_id = update.get("update_id")
    if isinstance(update_id, bool) or not isinstance(update_id, int):
        return None
    return update


@CHANNEL_REGISTRY.register("telegram")
class TelegramChannel:
    managed_by_environment: ClassVar[bool] = True

    def __init__(self, client: TelegramClient, clock: Callable[[], datetime]) -> None:
        self._adapter = TelegramChannelAdapter(client)
        self._clock = clock

    @classmethod
    def is_available(cls, context: ChannelContext) -> bool:
        return True

    @classmethod
    def default_capabilities(
        cls, config: Mapping[str, Any] | None = None
    ) -> ChannelCapabilities:
        return telegram_capabilities()

    @classmethod
    def build(
        cls,
        record: ChannelRecord,
        context: ChannelContext,
        secrets: ChannelSecrets | None,
    ) -> "TelegramChannel":
        return cls(context.adapters.telegram, context.adapters.clock)

    def recibir_mensaje(
        self, payload: Mapping[str, Any]
    ) -> NormalizedMessage | None:
        update = _valid_update(payload)
        if update is None:
            return None
        try:
            if "callback_query" in update:
                callback = extract_callback(update)
                return (
                    normalize_callback(callback, self._clock())
                    if callback is not None
                    else None
                )
            incoming = extract_incoming(update)
            return normalize_incoming(incoming, self._clock()) if incoming else None
        except (KeyError, TypeError, ValueError, ValidationError):
            return None

    def enviar_mensaje(
        self, destino: str, bloques: Sequence[ResponseBlock]
    ) -> DeliveryStatus:
        return self._adapter.send(destino, bloques)

    def identificar_usuario(self, payload: Mapping[str, Any]) -> str | None:
        update = _valid_update(payload)
        if update is None:
            return None
        try:
            if "callback_query" in update:
                callback = extract_callback(update)
                return str(callback.user_id) if callback is not None else None
            incoming = extract_incoming(update)
            return str(incoming.user_id) if incoming is not None else None
        except (KeyError, TypeError, ValueError):
            return None

    def capacidades(self, destino: str | None = None) -> ChannelCapabilities:
        return self._adapter.capabilities()
