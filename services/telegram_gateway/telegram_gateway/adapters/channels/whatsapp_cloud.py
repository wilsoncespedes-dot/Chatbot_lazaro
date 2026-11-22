"""Adaptador de puerto para WhatsApp Cloud API."""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any, Callable, ClassVar

from lazaro_contracts import ChannelCapabilities, DeliveryStatus, NormalizedMessage, ResponseBlock
from pydantic import ValidationError

from ...adapters.whatsapp import ChannelAdapter
from ...domain import ChannelNotConfigured, ChannelRecord, ChannelSecrets
from ...registry import CHANNEL_REGISTRY, ChannelContext
from ...whatsapp_cloud import whatsapp_capabilities


@CHANNEL_REGISTRY.register("whatsapp_cloud")
class WhatsAppCloudChannel:
    managed_by_environment: ClassVar[bool] = True

    def __init__(self, client: ChannelAdapter, clock: Callable[[], datetime]) -> None:
        self._client = client
        self._clock = clock

    @classmethod
    def default_capabilities(
        cls, config: Mapping[str, Any] | None = None
    ) -> ChannelCapabilities:
        return ChannelCapabilities(**whatsapp_capabilities(window_open=False))

    @classmethod
    def is_available(cls, context: ChannelContext) -> bool:
        return context.adapters.whatsapp is not None

    @classmethod
    def build(
        cls,
        record: ChannelRecord,
        context: ChannelContext,
        secrets: ChannelSecrets | None,
    ) -> "WhatsAppCloudChannel":
        if context.adapters.whatsapp is None:
            raise ChannelNotConfigured("El canal no está configurado en este servicio.")
        return cls(context.adapters.whatsapp, context.adapters.clock)

    def recibir_mensaje(
        self, payload: Mapping[str, Any]
    ) -> NormalizedMessage | None:
        try:
            return self._client.normalize_incoming(dict(payload), self._clock())
        except (KeyError, TypeError, ValueError, ValidationError):
            return None

    def enviar_mensaje(
        self, destino: str, bloques: Sequence[ResponseBlock]
    ) -> DeliveryStatus:
        return self._client.send(destino, bloques)

    def identificar_usuario(self, payload: Mapping[str, Any]) -> str | None:
        value = payload.get("from")
        if isinstance(value, bool) or value is None:
            return None
        if isinstance(value, (str, int)):
            text = str(value)
            return text if text.strip() else None
        return None

    def capacidades(self, destino: str | None = None) -> ChannelCapabilities:
        capabilities_for = getattr(self._client, "capabilities_for", None)
        if destino is not None and callable(capabilities_for):
            return capabilities_for(destino)
        return self._client.capabilities()
