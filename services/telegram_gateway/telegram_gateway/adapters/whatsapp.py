"""Interfaz común de canal y adaptador falso de WhatsApp (sin red ni credenciales)."""
from __future__ import annotations

from datetime import datetime
from typing import Protocol, Sequence, cast

from lazaro_contracts import (
    ChannelCapabilities,
    DeliveryStatus,
    MAX_LIST_OPTIONS,
    MAX_OPTION_COUNT,
    MIN_LIST_OPTIONS,
    NormalizedMessage,
    ResponseBlock,
    TemplateBlock,
)

from ..domain import ChannelSendFailed, ChannelWindowClosed, TemplateNotApproved


class ChannelAdapter(Protocol):
    channel: str

    def capabilities(self) -> ChannelCapabilities: ...

    def normalize_incoming(
        self, raw: dict, received_at: datetime
    ) -> NormalizedMessage | None: ...

    def send(
        self, destination: str, blocks: Sequence[ResponseBlock]
    ) -> DeliveryStatus: ...

    def delivery_status(self, raw: str) -> DeliveryStatus: ...


class FakeWhatsAppAdapter:
    """Adaptador de WhatsApp para pruebas: no abre sockets ni lee secretos."""

    channel = "whatsapp"

    def __init__(
        self,
        *,
        window_open: bool = True,
        approved_templates: Sequence[str] = (),
        delivery_status_on_send: DeliveryStatus = "sent",
        fail: bool = False,
    ) -> None:
        self.window_open = window_open
        self.approved_templates = set(approved_templates)
        self.delivery_status_on_send = delivery_status_on_send
        self.fail = fail
        self.sent: list[tuple[str, list[ResponseBlock]]] = []

    def capabilities(self) -> ChannelCapabilities:
        return ChannelCapabilities(
            free_text_allowed=self.window_open,
            max_options=MAX_OPTION_COUNT,
            min_list_options=MIN_LIST_OPTIONS,
            max_list_options=MAX_LIST_OPTIONS,
            supports_links=True,
            requires_template=not self.window_open,
        )

    def normalize_incoming(
        self, raw: dict, received_at: datetime
    ) -> NormalizedMessage | None:
        user_id = raw.get("from", raw.get("user_id"))
        chat_id = raw.get("chat_id", user_id)
        message_id = raw.get("message_id")
        if user_id is None or chat_id is None or message_id is None:
            return None
        kind = raw.get("type", "text")
        text = raw.get("text")
        button_id = raw.get("button_id")
        if kind == "text" and not text:
            return None
        if kind == "button" and not button_id:
            return None
        if kind not in ("text", "button"):
            kind = "unsupported"
        return NormalizedMessage(
            channel="whatsapp",
            external_user_id=str(user_id),
            external_chat_id=str(chat_id),
            external_message_id=str(message_id),
            kind=kind,
            text=text if kind == "text" else None,
            button_id=button_id if kind == "button" else None,
            received_at=received_at,
        )

    def send(
        self, destination: str, blocks: Sequence[ResponseBlock]
    ) -> DeliveryStatus:
        block_list = list(blocks)
        if not self.window_open:
            templates = [block for block in block_list if isinstance(block, TemplateBlock)]
            if len(templates) != len(block_list):
                raise ChannelWindowClosed(
                    "La ventana de WhatsApp está cerrada; solo se permiten plantillas."
                )
            if any(block.name not in self.approved_templates for block in templates):
                raise TemplateNotApproved(
                    "La plantilla no está aprobada para este canal."
                )
        if self.fail:
            raise ChannelSendFailed("El adaptador de WhatsApp no pudo enviar.")
        self.sent.append((destination, block_list))
        return self.delivery_status_on_send

    def delivery_status(self, raw: str) -> DeliveryStatus:
        normalized = raw.strip().lower()
        if normalized in ("sent", "delivered", "read", "failed"):
            return cast(DeliveryStatus, normalized)
        return "failed"
