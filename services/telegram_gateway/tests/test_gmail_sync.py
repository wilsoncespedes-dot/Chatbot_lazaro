"""R3-R7, R10-R13: cursor Gmail, ruta de recepción y reintento."""
from __future__ import annotations

import base64
from datetime import datetime, timezone
from email.utils import format_datetime

from fastapi.testclient import TestClient
from cryptography.fernet import Fernet
from lazaro_contracts import SERVICE_TOKEN_HEADER

from telegram_gateway.adapters.channel_repository import FakeChannelRepository
from telegram_gateway.adapters.dedup import FakeDedupStore
from telegram_gateway.adapters.gmail_history import FakeGmailHistoryRepository
from telegram_gateway.adapters.gmail_api import GmailApiError
from telegram_gateway.adapters.orchestrator import FakeOrchestratorClient
from telegram_gateway.adapters.telegram import FakeTelegramClient
from telegram_gateway.config import Settings
from telegram_gateway.domain import Adapters, ChannelRecord, ChannelSecrets
from telegram_gateway.main import create_app

TOKEN = "svc-token"
NOW = datetime(2026, 1, 2, tzinfo=timezone.utc)


class FakeGmailTransport:
    def __init__(self):
        self.history_error = False
        self.message_error = False
        self.messages = {
            "m1": {
                "id": "m1", "threadId": "t1", "labelIds": ["INBOX"],
                "internalDate": "1767312000000",
                "payload": {
                    "mimeType": "text/plain",
                    "headers": [
                        {"name": "From", "value": "cliente@example.com"},
                        {"name": "Subject", "value": "Consulta"},
                    ],
                    "body": {"data": base64.urlsafe_b64encode("hola".encode()).decode().rstrip("=")},
                },
            },
            "own": {
                "id": "own", "threadId": "t1", "labelIds": ["INBOX", "SENT"],
                "payload": {"mimeType": "text/plain", "headers": [
                    {"name": "From", "value": "soporte@example.com"}
                ], "body": {"data": "aG9sYQ"}},
            },
            "old": {"id": "old", "threadId": "t1", "labelIds": ["SENT"]},
        }
        self.history_calls = 0

    def request(self, method, url, **kwargs):
        if url.endswith("oauth2.googleapis.com/token"):
            return {"access_token": "test-access"}
        if url.endswith("/profile"):
            return {"emailAddress": "soporte@example.com", "historyId": "20"}
        if url.endswith("/history"):
            self.history_calls += 1
            if self.history_error:
                raise GmailApiError(404, "expired")
            return {
                "historyId": "30",
                "history": [{"messagesAdded": [
                    {"message": {"id": "m1"}},
                    {"message": {"id": "own"}},
                    {"message": {"id": "old"}},
                ]}],
            }
        if "/messages/" in url:
            if self.message_error:
                raise GmailApiError(404, "message_not_found")
            message_id = url.rsplit("/", 1)[-1]
            return self.messages[message_id]
        return {"id": "sent"}


def _app(*, fail_orchestrator: bool = False, channel_active: bool = True):
    settings = Settings(
        service_token=TOKEN,
        telegram_webhook_secret="hook",
        telegram_bot_token="123456:TOKEN",
        channel_secrets_key=Fernet.generate_key().decode("ascii"),
        message_grouping_enabled=False,
    )
    channels = FakeChannelRepository()
    channel = ChannelRecord(
        id="soporte-gmail", name="Soporte", adapter_type="gmail_api",
        icon="✉️", color="#C2410C", config={"email_address": "soporte@example.com"},
        active=channel_active, created_at=NOW, has_secrets=False,
        active_follows_environment=False,
    )
    from telegram_gateway.secret_cipher import SecretCipher
    cipher = SecretCipher(settings.channel_secrets_key.get_secret_value())
    encrypted = cipher.encrypt(ChannelSecrets(credentials={
        "client_id": "id", "client_secret": "secret", "refresh_token": "refresh"
    }))
    channels.create(channel, encrypted)
    transport = FakeGmailTransport()
    history = FakeGmailHistoryRepository()
    orchestrator = FakeOrchestratorClient(fail=fail_orchestrator)
    adapters = Adapters(
        FakeTelegramClient(), FakeDedupStore(), orchestrator,
        clock=lambda: NOW, channels=channels, gmail_transport=transport,
        gmail_history=history,
    )
    app = create_app(settings, adapters)
    return TestClient(app), history, transport, orchestrator


def test_gmail_sync_initializes_then_only_forwards_inbox_external_text():
    """R3-R7, R10: no backfill; new Inbox message delivered once."""
    client, history, transport, orchestrator = _app()
    headers = {SERVICE_TOKEN_HEADER: TOKEN}
    first = client.post("/channels/soporte-gmail/gmail/sync", headers=headers)
    assert first.json() == {"status": "initialized", "processed": 0}
    assert history.cursors["soporte-gmail"] == "20"
    second = client.post("/channels/soporte-gmail/gmail/sync", headers=headers)
    assert second.json() == {"status": "synced", "processed": 1}
    assert history.cursors["soporte-gmail"] == "30"
    assert len(orchestrator.received) == 1
    message = orchestrator.received[0]
    assert message.external_user_id == "cliente@example.com"
    assert message.external_chat_id == "t1"
    assert message.external_message_id == "m1"
    assert message.text == "hola"


def test_gmail_sync_requires_service_token():
    """R10: rutas internas exigen autenticación entre servicios."""
    client, _, _, _ = _app()
    response = client.post("/channels/soporte-gmail/gmail/sync")
    assert response.status_code == 401


def test_gmail_sync_rejects_inactive_channel():
    """R12: un canal Gmail inactivo no sincroniza."""
    client, _, _, _ = _app(channel_active=False)
    response = client.post(
        "/channels/soporte-gmail/gmail/sync", headers={SERVICE_TOKEN_HEADER: TOKEN}
    )
    assert response.status_code == 422
    assert response.json()["error"] == "channel_inactive"


def test_gmail_sync_keeps_cursor_when_orchestrator_fails():
    """R5-R6: se conserva cursor cuando el orquestador no acepta mensajes."""
    client, history, _, _ = _app(fail_orchestrator=True)
    history.set_cursor("soporte-gmail", "20")
    response = client.post(
        "/channels/soporte-gmail/gmail/sync", headers={SERVICE_TOKEN_HEADER: TOKEN}
    )
    assert response.status_code == 502
    assert history.cursors["soporte-gmail"] == "20"


def test_gmail_expired_history_keeps_cursor_until_explicit_reset():
    """R12-R13: cursor vencido se conserva y solo cambia con reset explícito."""
    client, history, transport, _ = _app()
    headers = {SERVICE_TOKEN_HEADER: TOKEN}
    history.set_cursor("soporte-gmail", "expired-cursor")
    transport.history_error = True
    failed = client.post("/channels/soporte-gmail/gmail/sync", headers=headers)
    assert failed.status_code == 409
    assert failed.json()["error"] == "gmail_history_expired"
    assert history.cursors["soporte-gmail"] == "expired-cursor"
    reset = client.post(
        "/channels/soporte-gmail/gmail/reset-cursor", headers=headers
    )
    assert reset.status_code == 200
    assert history.cursors["soporte-gmail"] == "20"


def test_gmail_message_404_does_not_masquerade_as_expired_history():
    """R13-R14: un mensaje borrado no fuerza un reset que omita historial."""
    client, history, transport, _ = _app()
    history.set_cursor("soporte-gmail", "20")
    transport.message_error = True
    response = client.post(
        "/channels/soporte-gmail/gmail/sync", headers={SERVICE_TOKEN_HEADER: TOKEN}
    )
    assert response.status_code == 502
    assert response.json()["error"] == "gmail_sync_failed"
    assert history.cursors["soporte-gmail"] == "20"
