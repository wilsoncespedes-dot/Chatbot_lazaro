"""Puerto hexagonal de un canal de mensajería."""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Protocol, runtime_checkable

from lazaro_contracts import ChannelCapabilities, DeliveryStatus, NormalizedMessage, ResponseBlock


@runtime_checkable
class Canal(Protocol):
    def recibir_mensaje(
        self, payload: Mapping[str, Any]
    ) -> NormalizedMessage | None: ...

    def enviar_mensaje(
        self, destino: str, bloques: Sequence[ResponseBlock]
    ) -> DeliveryStatus: ...

    def identificar_usuario(self, payload: Mapping[str, Any]) -> str | None: ...

    def capacidades(self, destino: str | None = None) -> ChannelCapabilities: ...
