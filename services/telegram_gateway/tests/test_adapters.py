"""Adaptador Telegram: los bloques de solo texto no llevan teclado (#46 R32)."""
from __future__ import annotations

from lazaro_contracts import TextBlock

from telegram_gateway.adapters.telegram import (
    FakeTelegramClient,
    TelegramChannelAdapter,
)


def test_text_only_blocks_send_without_reply_markup():
    """R46 R32: con solo TextBlock se llama a send_message con reply_markup None."""
    client = FakeTelegramClient()
    adapter = TelegramChannelAdapter(client)

    status = adapter.send(
        "77",
        [
            TextBlock(type="text", text="Aviso"),
            TextBlock(type="text", text="Escribe ACEPTO"),
        ],
    )

    assert status == "sent"
    assert client.sent == [(77, "Aviso\nEscribe ACEPTO")]
    assert client.reply_markups == [None]
