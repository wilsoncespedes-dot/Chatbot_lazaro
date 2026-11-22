"""Salida del dominio hacia la tabla `outbox` (#64).

El dominio deja de llamar al gateway del canal en la petición: escribe el
mensaje y su salida en la misma transacción. El worker `enviar_salientes` es el
único que entrega al gateway.
"""
from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import TYPE_CHECKING, Callable

from lazaro_contracts import ResponseBlock, TextBlock

from ..domain import OutboxEntry, ServiceUnavailable, destination_key
from ..legacy import LEGACY_CHANNEL, is_legacy

if TYPE_CHECKING:
    from ..domain import Contact
    from .repository import Repository


class OutboxGatewayClient:
    """Implementa `GatewayClient` encolando filas de `outbox` en vez de enviar."""

    def __init__(
        self,
        repository: "Repository",
        clock: Callable[[], datetime],
        kind: str = "notice",
    ) -> None:
        self._repository = repository
        self._clock = clock
        self._kind = kind

    def _enqueue(
        self,
        channel: str,
        destination: str,
        blocks: Sequence[ResponseBlock],
        contact_id: str | None = None,
        kind: str | None = None,
    ) -> None:
        entry = OutboxEntry(
            contact_id=contact_id,
            destination_key=destination_key(channel, destination),
            channel=channel,
            destination=destination,
            kind=kind or self._kind,
            blocks=list(blocks),
        )
        try:
            self._repository.enqueue_outbound(entry)
        except ServiceUnavailable:
            raise
        except Exception as exc:  # noqa: BLE001 - la cola escribe en Postgres
            raise ServiceUnavailable("No se pudo encolar la salida.") from exc

    def send(self, chat_id: int, text: str) -> None:
        self._enqueue(
            LEGACY_CHANNEL,
            str(chat_id),
            [TextBlock(type="text", text=text)],
        )

    def send_channel(self, channel: str, destination: str, text: str) -> None:
        self._enqueue(
            channel,
            destination,
            [TextBlock(type="text", text=text)],
        )

    def send_channel_blocks(
        self, channel: str, destination: str, blocks: Sequence[ResponseBlock]
    ) -> None:
        self._enqueue(channel, destination, blocks)

    def with_message(
        self, contact: "Contact", role: str, text: str, kind: str
    ) -> None:
        destination = (
            str(contact.chat_id)
            if is_legacy(contact.channel) and contact.chat_id is not None
            else contact.external_chat_id
        )
        entry = OutboxEntry(
            contact_id=contact.id,
            destination_key=destination_key(contact.channel, destination),
            channel=contact.channel,
            destination=destination,
            kind=kind,
            blocks=[TextBlock(type="text", text=text)],
        )
        try:
            self._repository.add_message_with_outbox(
                contact.id, role, text, self._clock(), entry
            )
        except ServiceUnavailable:
            raise
        except Exception as exc:  # noqa: BLE001
            raise ServiceUnavailable("No se pudo guardar la salida.") from exc
