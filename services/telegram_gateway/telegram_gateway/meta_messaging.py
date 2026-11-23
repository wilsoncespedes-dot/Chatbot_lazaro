"""Lógica pura de Messenger e Instagram Messaging (webhooks Meta, fase 7).

El canal se elige por `object`: `page` → `facebook` e `instagram` → `instagram`
(también se reconoce Instagram entregado con objeto `page` por su id de cuenta).
Los ecos (`is_echo`) y los eventos sin `message` (read, delivery…) se ignoran.
"""
from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Any, Literal

from lazaro_contracts import NormalizedMessage
from pydantic import ValidationError

META_SIGNATURE_HEADER = "X-Hub-Signature-256"
META_FACEBOOK_CHANNEL = "facebook"
META_INSTAGRAM_CHANNEL = "instagram"
META_PAGE_OBJECT = "page"
META_INSTAGRAM_OBJECT = "instagram"
MetaChannel = Literal["facebook", "instagram"]


def _as_id(value: Any) -> str | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (str, int)):
        text = str(value).strip()
        return text or None
    return None


def _text(message: Mapping[str, Any]) -> str | None:
    value = message.get("text")
    if isinstance(value, Mapping):
        value = value.get("body")
    return value if isinstance(value, str) and value.strip() else None


def _matches_channel(
    channel: MetaChannel,
    object_type: str,
    entry_id: str | None,
    recipient_id: str | None,
    page_id: str,
    instagram_account_id: str,
) -> bool:
    if channel == META_FACEBOOK_CHANNEL:
        return (
            object_type == META_PAGE_OBJECT
            and (not page_id or entry_id == page_id)
            and (not recipient_id or not page_id or recipient_id == page_id)
        )
    if object_type == META_INSTAGRAM_OBJECT:
        return not instagram_account_id or entry_id == instagram_account_id
    return (
        object_type == META_PAGE_OBJECT
        and bool(instagram_account_id)
        and (
            entry_id == instagram_account_id
            or recipient_id == instagram_account_id
        )
    )


def parse_meta_webhook(
    payload: object,
    channel: MetaChannel,
    page_id: str,
    instagram_account_id: str,
    received_at: datetime,
) -> list[NormalizedMessage]:
    """R1-R4: normaliza mensajes entrantes; ignora ecos y otros eventos."""
    if not isinstance(payload, dict):
        return []
    object_type = payload.get("object")
    if object_type not in (META_PAGE_OBJECT, META_INSTAGRAM_OBJECT):
        return []
    entries = payload.get("entry")
    if not isinstance(entries, list):
        return []
    messages: list[NormalizedMessage] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        entry_id = _as_id(entry.get("id"))
        events = entry.get("messaging")
        if not isinstance(events, list):
            continue
        for event in events:
            if not isinstance(event, dict):
                continue
            sender = event.get("sender")
            recipient = event.get("recipient")
            if not isinstance(sender, Mapping) or not isinstance(recipient, Mapping):
                continue
            sender_id = _as_id(sender.get("id"))
            recipient_id = _as_id(recipient.get("id"))
            if sender_id is None or sender_id == recipient_id:
                continue
            if not _matches_channel(
                channel,
                object_type,
                entry_id,
                recipient_id,
                page_id,
                instagram_account_id,
            ):
                continue
            message = event.get("message")
            if not isinstance(message, Mapping) or message.get("is_echo") is True:
                continue
            message_id = _as_id(message.get("mid"))
            if message_id is None:
                continue
            text = _text(message)
            try:
                messages.append(
                    NormalizedMessage(
                        channel=channel,
                        external_user_id=sender_id,
                        external_chat_id=sender_id,
                        external_message_id=message_id,
                        kind="text" if text is not None else "unsupported",
                        text=text,
                        received_at=received_at,
                    )
                )
            except ValidationError:
                continue
    return messages


def meta_channel_for_payload(
    payload: object, page_id: str, instagram_account_id: str
) -> MetaChannel | None:
    """Devuelve el primer canal del lote (compatibilidad con la API singular)."""
    channels = meta_channels_for_payload(payload, page_id, instagram_account_id)
    return channels[0] if channels else None


def meta_channels_for_payload(
    payload: object, page_id: str, instagram_account_id: str
) -> tuple[MetaChannel, ...]:
    """R1: separa lotes que incluyan entradas Messenger e Instagram."""
    if not isinstance(payload, dict):
        return ()
    object_type = payload.get("object")
    if object_type == META_INSTAGRAM_OBJECT:
        return (META_INSTAGRAM_CHANNEL,)
    if object_type != META_PAGE_OBJECT:
        return ()
    entries = payload.get("entry")
    if not isinstance(entries, list):
        return ()
    channels: list[MetaChannel] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        if instagram_account_id and _as_id(entry.get("id")) == instagram_account_id:
            if META_INSTAGRAM_CHANNEL not in channels:
                channels.append(META_INSTAGRAM_CHANNEL)
            continue
        entry_id = _as_id(entry.get("id"))
        events = entry.get("messaging")
        if not isinstance(events, list):
            if page_id and entry_id == page_id and META_FACEBOOK_CHANNEL not in channels:
                channels.append(META_FACEBOOK_CHANNEL)
            continue
        for event in events:
            if not isinstance(event, dict):
                continue
            recipient = event.get("recipient")
            recipient_id = (
                _as_id(recipient.get("id")) if isinstance(recipient, Mapping) else None
            )
            if instagram_account_id and (
                entry_id == instagram_account_id or recipient_id == instagram_account_id
            ):
                if META_INSTAGRAM_CHANNEL not in channels:
                    channels.append(META_INSTAGRAM_CHANNEL)
            elif page_id and (entry_id == page_id or recipient_id == page_id):
                if META_FACEBOOK_CHANNEL not in channels:
                    channels.append(META_FACEBOOK_CHANNEL)
    if not channels and page_id:
        return (META_FACEBOOK_CHANNEL,)
    return tuple(channels)
