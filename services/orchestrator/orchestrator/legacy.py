"""Capa legacy del flujo histórico de Telegram (#65, design §4).

Es el único módulo del orquestador con nombres de canal literales. El payload
histórico `MessageRequest` (ids numéricos `telegram_user_id`/`chat_id`) y las
columnas `telegram_user_id`/`chat_id` del repositorio pertenecen a ese canal;
todo lo demás decide por la política del canal (`channels.py`).
"""
from __future__ import annotations

from lazaro_contracts import MessageRequest, NormalizedMessage

LEGACY_CHANNEL = "telegram"


def legacy_from_normalized(message: NormalizedMessage) -> MessageRequest | None:
    """Traduce solo el payload canónico del canal legacy con texto al flujo histórico.

    Los demás canales conservan sus ids externos como texto y se procesan por el
    flujo multicanal; nunca se convierten a `telegram_user_id`.
    """
    if message.channel != LEGACY_CHANNEL or message.kind != "text" or not message.text:
        return None
    return MessageRequest(
        update_id=int(message.external_message_id),
        telegram_user_id=int(message.external_user_id),
        chat_id=int(message.external_chat_id),
        text=message.text,
        received_at=message.received_at,
    )


def legacy_chat_id(channel: str, chat_id: int | None) -> int | None:
    """El `chat_id` numérico histórico solo existe en el canal legacy."""
    return chat_id if channel == LEGACY_CHANNEL else None


def is_legacy(channel: str | None) -> bool:
    return channel == LEGACY_CHANNEL
