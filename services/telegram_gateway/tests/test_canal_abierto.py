"""Guardas del gateway para el contrato de canal abierto (#60)."""
from __future__ import annotations

import json
from datetime import datetime, timezone

import httpx
import pytest
from fastapi.testclient import TestClient
from lazaro_contracts import (
    ChannelCapabilities,
    ImageBlock,
    LinkBlock,
    NormalizedMessage,
    TextBlock,
)

from telegram_gateway.adapters.dedup import FakeDedupStore
from telegram_gateway.adapters.orchestrator import FakeOrchestratorClient
from telegram_gateway.adapters.telegram import (
    FakeTelegramClient,
    TelegramChannelAdapter,
)
from telegram_gateway.adapters.whatsapp import FakeWhatsAppAdapter
from telegram_gateway.config import Settings
from telegram_gateway.domain import (
    Adapters,
    extract_callback,
    extract_incoming,
    normalize_callback,
    normalize_incoming,
    send_response,
)
from telegram_gateway.main import create_app
from telegram_gateway.whatsapp_cloud import normalize_message, whatsapp_capabilities

SERVICE_TOKEN = "svc-token"
WEBHOOK_SECRET = "hook-secret"
HEADERS = {"X-Service-Token": SERVICE_TOKEN}
NOW = datetime(2026, 11, 21, 15, 0, tzinfo=timezone.utc)
HISTORICAL_KEYS = {
    "channel",
    "external_user_id",
    "external_chat_id",
    "external_message_id",
    "kind",
    "text",
    "button_id",
    "button_proof",
    "received_at",
}
IMAGE = {
    "type": "image",
    "url": "https://x.example.com/a.jpg",
    "alt_text": "Foto del producto",
}


def make_client(*, whatsapp=None):
    settings = Settings(
        service_token=SERVICE_TOKEN,
        telegram_webhook_secret=WEBHOOK_SECRET,
        telegram_bot_token="123456:BOT",
        dedup_ttl_seconds=123,
    )
    telegram = FakeTelegramClient()
    adapters = Adapters(
        telegram,
        FakeDedupStore(),
        FakeOrchestratorClient(),
        whatsapp=whatsapp,
    )
    return TestClient(create_app(settings, adapters)), telegram


def _send(client: TestClient, channel: str, blocks: list[dict], destination: str = "77"):
    return client.post(
        "/send",
        json={"channel": channel, "destination": destination, "blocks": blocks},
        headers=HEADERS,
    )


# ── R39: canal sin adaptador ────────────────────────────────────────────────


@pytest.mark.parametrize("channel", ["canal-externo", "canal-sin-adaptador"])
def test_send_unknown_channel_returns_422_without_sending(channel: str):
    """R39: un canal sin adaptador responde 422 y no envía por ningún canal."""
    whatsapp = FakeWhatsAppAdapter()
    client, telegram = make_client(whatsapp=whatsapp)
    response = _send(client, channel, [{"type": "text", "text": "Hola"}])
    assert response.status_code == 422
    assert response.json()["error"] == "validation_error"
    assert telegram.sent == []
    assert whatsapp.sent == []


def test_send_unknown_channel_is_422_even_without_whatsapp():
    """R39: sin WhatsApp configurado un canal desconocido sigue siendo 422, no 502."""
    client, telegram = make_client(whatsapp=None)
    response = _send(
        client, "canal-sin-adaptador", [{"type": "text", "text": "Hola"}]
    )
    assert response.status_code == 422
    assert response.json()["error"] == "validation_error"
    assert telegram.sent == []


# ── R40: bloque imagen sin capacidad ────────────────────────────────────────


@pytest.mark.parametrize("channel", ["telegram", "whatsapp"])
@pytest.mark.parametrize(
    "blocks",
    [
        [IMAGE],
        [{"type": "text", "text": "Mira:"}, IMAGE],
    ],
)
def test_send_image_block_is_degraded_on_current_channels(channel, blocks):
    """R18, R21: los canales actuales reciben un enlace en lugar de la imagen."""
    whatsapp = FakeWhatsAppAdapter()
    client, telegram = make_client(whatsapp=whatsapp)
    response = _send(client, channel, blocks)
    assert response.status_code == 200
    if channel == "telegram":
        assert "Foto del producto: https://x.example.com/a.jpg" in telegram.sent[-1][1]
    else:
        sent_blocks = whatsapp.sent[-1][1]
        assert any(
            isinstance(block, LinkBlock)
            and block.text == "Foto del producto"
            and block.url == "https://x.example.com/a.jpg"
            for block in sent_blocks
        )


class _ImageCapableAdapter:
    def capabilities(self) -> ChannelCapabilities:
        return ChannelCapabilities(
            free_text_allowed=True,
            max_options=3,
            min_list_options=4,
            max_list_options=10,
            supports_links=True,
            requires_template=False,
            supports_images=True,
        )

    def send(self, destination, blocks):
        self.sent = (destination, list(blocks))
        return "sent"


class _NoImageAdapter:
    def capabilities(self) -> ChannelCapabilities:
        return ChannelCapabilities(
            free_text_allowed=True,
            max_options=3,
            min_list_options=4,
            max_list_options=10,
            supports_links=True,
            requires_template=False,
        )

    def send(self, destination, blocks):
        self.sent = (destination, list(blocks))
        return "sent"


def test_send_response_allows_image_when_capability_is_declared():
    """R40: con supports_images el núcleo entrega el bloque al adaptador."""
    adapter = _ImageCapableAdapter()
    status = send_response(
        adapter,
        "77",
        [TextBlock(type="text", text="Mira:"), ImageBlock.model_validate(IMAGE)],
    )
    assert status == "sent"
    assert isinstance(adapter.sent[1][1], ImageBlock)


def test_send_response_degrades_image_without_capability():
    """R18, R21: sin supports_images el núcleo envía un LinkBlock."""
    adapter = _NoImageAdapter()
    assert send_response(adapter, "77", [ImageBlock.model_validate(IMAGE)]) == "sent"
    assert adapter.sent[1] == [
        LinkBlock(type="link", text="Foto del producto", url="https://x.example.com/a.jpg")
    ]


# ── R41: capacidades de los adaptadores actuales ────────────────────────────


@pytest.mark.parametrize(
    "capabilities",
    [
        TelegramChannelAdapter(FakeTelegramClient()).capabilities(),
        ChannelCapabilities(**whatsapp_capabilities(window_open=True)),
        ChannelCapabilities(**whatsapp_capabilities(window_open=False)),
        FakeWhatsAppAdapter().capabilities(),
    ],
)
def test_current_adapters_keep_their_capabilities(capabilities):
    """R41: Telegram y WhatsApp informan botones sí y multimedia no."""
    assert capabilities.supports_buttons is True
    assert capabilities.supports_images is False
    assert capabilities.supports_files is False
    assert capabilities.supports_audio is False


# ── R42: payload reenviado al orquestador ──────────────────────────────────


def test_forwarded_payload_has_only_historical_keys(monkeypatch):
    """R42: el JSON de POST /messages conserva solo las claves históricas."""
    from telegram_gateway.adapters import orchestrator as orchestrator_module

    calls: list[dict] = []

    def fake_post(url, **kwargs):
        calls.append(kwargs)
        return httpx.Response(200, request=httpx.Request("POST", url))

    monkeypatch.setattr(orchestrator_module.httpx, "post", fake_post)
    client = orchestrator_module.HttpOrchestratorClient("http://orchestrator", SERVICE_TOKEN)

    text_update = {
        "update_id": 10,
        "message": {
            "message_id": 90,
            "from": {"id": 55},
            "chat": {"id": 77},
            "text": "hola",
        },
    }
    callback_update = {
        "update_id": 11,
        "callback_query": {
            "id": "cb-1",
            "from": {"id": 55},
            "message": {"chat": {"id": 77}},
            "data": "privacy.accept:abc",
        },
    }
    telegram_text = normalize_incoming(extract_incoming(text_update), NOW)
    telegram_button = normalize_callback(extract_callback(callback_update), NOW)
    whatsapp_unsupported = normalize_message(
        {"from": "57300", "id": "wamid-1", "type": "image"}, NOW
    )
    assert isinstance(telegram_text, NormalizedMessage)
    assert isinstance(whatsapp_unsupported, NormalizedMessage)

    for message in (telegram_text, telegram_button, whatsapp_unsupported):
        client.post_message(message)
        assert set(json.loads(calls[-1]["content"])) == HISTORICAL_KEYS
