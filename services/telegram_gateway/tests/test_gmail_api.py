"""R4, R7-R9: parsing MIME sin red y headers de respuesta Gmail."""
from __future__ import annotations

import base64
import logging
from email import message_from_bytes
from email.policy import default

import pytest
from lazaro_contracts import TextBlock

from telegram_gateway.adapters.channels.gmail import GmailChannel
from telegram_gateway.adapters.gmail_api import (
    GmailApiClient,
    GmailApiError,
    added_message_ids,
    plain_text_body,
)
from telegram_gateway.adapters.orchestrator import FakeOrchestratorClient
from telegram_gateway.adapters.telegram import FakeTelegramClient
from telegram_gateway.config import Settings
from telegram_gateway.domain import Adapters, InvalidChannelConfig
from telegram_gateway.registry import ChannelContext


class FakeTransport:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        return self.responses.pop(0)


def _encoded(text: str) -> str:
    return base64.urlsafe_b64encode(text.encode()).decode().rstrip("=")


def test_plain_text_body_ignores_html_and_attachments():
    """R8: no descarga adjuntos ni inserta HTML."""
    body = {"mimeType": "multipart/alternative", "parts": [
        {"mimeType": "text/html", "body": {"data": _encoded("<b>no</b>")}},
        {"mimeType": "text/plain", "body": {"data": _encoded("hola")}},
        {"mimeType": "application/pdf", "filename": "x.pdf", "body": {"attachmentId": "a"}},
    ]}
    assert plain_text_body(body) == "hola"


def test_gmail_factory_rejects_invalid_mailbox_config():
    """R2: el adaptador valida el correo antes de persistir el canal."""
    context = ChannelContext(
        Settings(),
        Adapters(FakeTelegramClient(), object(), FakeOrchestratorClient()),
    )
    with pytest.raises(InvalidChannelConfig):
        GmailChannel.validate_config({"email_address": "direccion-invalida"}, context)


def test_added_message_ids_are_unique_and_ordered():
    """R4: procesa una sola vez cada id repetido en historial."""
    history = {"history": [
        {"messagesAdded": [{"message": {"id": "a"}}, {"message": {"id": "b"}}]},
        {"messagesAdded": [{"message": {"id": "a"}}]},
    ]}
    assert added_message_ids(history) == ["a", "b"]


def test_send_reply_preserves_thread_and_reply_headers():
    """R7: el mensaje se responde al hilo y a su remitente externo."""
    transport = FakeTransport([
        {"access_token": "access"},
        {"messages": [{"payload": {"headers": [
            {"name": "From", "value": "Cliente <client@example.com>"},
            {"name": "Message-ID", "value": "<source@example.com>"},
            {"name": "References", "value": "<older@example.com>"},
            {"name": "Subject", "value": "Ayuda"},
        ]}}]},
        {"id": "sent"},
    ])
    client = GmailApiClient(
        {"client_id": "id", "client_secret": "secret", "refresh_token": "refresh"},
        transport,
    )
    client.send_reply("thread-1", "soporte@example.com", "respuesta")
    method, url, kwargs = transport.calls[-1]
    assert method == "POST" and url.endswith("/messages/send")
    assert kwargs["json_body"]["threadId"] == "thread-1"
    raw = kwargs["json_body"]["raw"]
    raw += "=" * (-len(raw) % 4)
    message = message_from_bytes(base64.urlsafe_b64decode(raw), policy=default)
    assert message["To"] == "client@example.com"
    assert message["Subject"] == "Ayuda"
    assert message["In-Reply-To"] == "<source@example.com>"
    assert message["References"] == "<older@example.com> <source@example.com>"
    assert message.get_content().strip() == "respuesta"


def test_gmail_send_error_logs_no_reply_content_or_oauth_values(caplog):
    """R15: ni el contenido saliente ni las credenciales llegan a los logs."""

    class BrokenGmailClient:
        def send_reply(self, thread_id, sender, text):
            raise GmailApiError(502, "gmail_api_error")

    channel = GmailChannel(
        "soporte-gmail", "soporte@example.com", BrokenGmailClient(), lambda: None
    )
    private_values = (
        "respuesta-privada-8d6f", "client-secret-7a4c", "refresh-token-2b91",
        "access-token-19a3",
    )
    caplog.set_level(logging.WARNING, logger="telegram_gateway.adapters.channels.gmail")
    status = channel.enviar_mensaje(
        "gmail-thread-1",
        [TextBlock(type="text", text=private_values[0])],
    )
    assert status == "failed"
    assert "gmail_send_failed channel_id=soporte-gmail status=502" in caplog.text
    assert all(value not in caplog.text for value in private_values)
