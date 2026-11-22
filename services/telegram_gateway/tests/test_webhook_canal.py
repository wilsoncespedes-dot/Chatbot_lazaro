"""R19, R30-R40, R46-R47: adaptador `webhook_generico` y callbacks firmados."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from lazaro_contracts import (
    LAZARO_SIGNATURE_HEADER,
    LAZARO_TIMESTAMP_HEADER,
    MAX_TEXT_LENGTH,
    NormalizedMessage,
    TextBlock,
)
from pydantic import SecretStr

from telegram_gateway.adapters.callback import FakeCallbackClient
from telegram_gateway.adapters.channel_repository import FakeChannelRepository
from telegram_gateway.adapters.channels import WebhookGenericoChannel
from telegram_gateway.adapters.dedup import FakeDedupStore
from telegram_gateway.adapters.orchestrator import FakeOrchestratorClient
from telegram_gateway.adapters.telegram import FakeTelegramClient
from telegram_gateway.config import Settings
from telegram_gateway.domain import (
    Adapters,
    CallbackNetworkError,
    ChannelNotConfigured,
    ChannelRecord,
    ChannelSecrets,
)
from telegram_gateway.main import create_app
from telegram_gateway.ports.canal import Canal
from telegram_gateway.registry import ChannelContext
from telegram_gateway.secret_cipher import SecretCipher
from telegram_gateway.signature import sign_payload
from telegram_gateway.url_guard import CallbackUrlRejected

NOW = datetime(2026, 11, 21, 15, 0, tzinfo=timezone.utc)
SECRET = "secreto-del-canal-generico"
CALLBACK = "https://callback.example.com/lazaro"
TOKEN = "service-token-test"


class _RejectingClient:
    def __init__(self) -> None:
        self.calls = 0

    def post(self, url: str, body: bytes, headers: dict[str, str]) -> int:
        self.calls += 1
        raise CallbackUrlRejected("bloqueada")


def _record(**overrides: Any) -> ChannelRecord:
    values: dict[str, Any] = {
        "id": "canal-externo",
        "name": "Canal externo",
        "adapter_type": "webhook_generico",
        "icon": "globe",
        "color": "#1B6FA8",
        "config": {"callback_url": CALLBACK},
        "active": True,
        "created_at": NOW,
        "has_secrets": True,
        "active_follows_environment": False,
    }
    values.update(overrides)
    return ChannelRecord(**values)


def _context(client) -> ChannelContext:
    adapters = Adapters(
        telegram=FakeTelegramClient(),
        dedup=FakeDedupStore(),
        orchestrator=FakeOrchestratorClient(),
        clock=lambda: NOW,
        callback=client,
    )
    return ChannelContext(settings=Settings(), adapters=adapters)


def _channel(client=None, **overrides) -> WebhookGenericoChannel:
    client = client or FakeCallbackClient()
    return WebhookGenericoChannel.build(
        _record(**overrides), _context(client), ChannelSecrets(secret=SECRET)
    )


def _inbound(**overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "channel": "canal-externo",
        "external_user_id": "usuario-1",
        "external_chat_id": "usuario-1",
        "external_message_id": "msg-1",
        "kind": "text",
        "text": "Hola",
        "received_at": "2026-11-21T15:00:00Z",
    }
    body.update(overrides)
    return body


# ── Adaptador y capacidades ────────────────────────────────────────────────


def test_generic_channel_implements_canal_port():
    """R31: el canal genérico implementa el puerto Canal."""
    assert isinstance(_channel(), Canal)


def test_generic_channel_capabilities_deliver_only_text():
    """R32: sin botones, enlaces, imágenes, archivos ni audio."""
    capabilities = _channel().capacidades()
    assert capabilities.free_text_allowed is True
    assert capabilities.supports_buttons is False
    assert capabilities.supports_links is False
    assert capabilities.supports_images is False
    assert capabilities.supports_files is False
    assert capabilities.supports_audio is False
    assert capabilities.requires_template is False
    assert capabilities.max_options == 0
    assert capabilities.min_list_options == 0
    assert capabilities.max_list_options == 0


def test_build_without_secret_raises_channel_not_configured():
    """R33: construir el canal genérico sin secreto falla cerrado."""
    with pytest.raises(ChannelNotConfigured):
        WebhookGenericoChannel.build(
            _record(), _context(FakeCallbackClient()), None
        )
    with pytest.raises(ChannelNotConfigured):
        WebhookGenericoChannel.build(
            _record(), _context(FakeCallbackClient()), ChannelSecrets()
        )


def test_recibir_mensaje_accepts_only_normalized_inbound_messages():
    """R19: devuelve el NormalizedMessage inbound y None para el resto."""
    channel = _channel()
    message = channel.recibir_mensaje(_inbound())
    assert message is not None and message.direction == "inbound"
    assert message.external_message_id == "msg-1"
    assert channel.recibir_mensaje({"foo": "bar"}) is None
    assert channel.recibir_mensaje(_inbound(direction="outbound")) is None
    assert channel.identificar_usuario(_inbound()) == "usuario-1"
    assert channel.identificar_usuario({"foo": "bar"}) is None


# ── Callback saliente ───────────────────────────────────────────────────────


def test_callback_sends_signed_outbound_normalized_message():
    """R35, R36: POST firmado con el mensaje saliente y un id único `out-`."""
    client = FakeCallbackClient(status=200)
    channel = _channel(client)
    assert channel.enviar_mensaje("usuario-1", [TextBlock(type="text", text="Hola")]) == "sent"
    assert len(client.requests) == 1
    url, body, headers = client.requests[0]
    assert url == CALLBACK
    assert headers["Content-Type"] == "application/json"
    timestamp = headers[LAZARO_TIMESTAMP_HEADER]
    assert timestamp == str(int(NOW.timestamp()))
    assert headers[LAZARO_SIGNATURE_HEADER] == sign_payload(SECRET, timestamp, body)
    message = NormalizedMessage.model_validate_json(body)
    assert message.channel == "canal-externo"
    assert message.direction == "outbound"
    assert message.external_user_id == message.external_chat_id == "usuario-1"
    assert message.kind == "text"
    assert message.text == "Hola"
    assert message.external_message_id.startswith("out-")
    assert message.received_at == NOW


@pytest.mark.parametrize("status", [200, 201, 204])
def test_callback_2xx_is_sent(status):
    """R37: cualquier 2xx es entrega correcta."""
    channel = _channel(FakeCallbackClient(status=status))
    assert channel.enviar_mensaje("u", [TextBlock(type="text", text="Hola")]) == "sent"


@pytest.mark.parametrize("status", [301, 302, 400, 500])
def test_callback_non_2xx_is_failed(status):
    """R38: códigos no 2xx (incluidos 3xx) son envío fallido."""
    channel = _channel(FakeCallbackClient(status=status))
    assert channel.enviar_mensaje("u", [TextBlock(type="text", text="Hola")]) == "failed"


def test_callback_network_error_is_failed_and_logs_only_type(caplog):
    """R39: error de red devuelve failed y registra solo el tipo."""
    channel = _channel(FakeCallbackClient(error=CallbackNetworkError("secreto-interno")))
    with caplog.at_level(logging.WARNING):
        assert (
            channel.enviar_mensaje("u", [TextBlock(type="text", text="Hola")])
            == "failed"
        )
    text = "\n".join(record.getMessage() for record in caplog.records)
    assert "callback_network_error channel_id=canal-externo" in text
    assert "CallbackNetworkError" in text
    assert "secreto-interno" not in text


def test_blocked_callback_makes_no_request_and_logs_without_url(caplog):
    """R46: URL bloqueada no hace petición y avisa sin la URL."""
    client = _RejectingClient()
    channel = _channel(client)
    with caplog.at_level(logging.WARNING):
        assert (
            channel.enviar_mensaje("u", [TextBlock(type="text", text="Hola")])
            == "failed"
        )
    assert client.calls == 1
    text = "\n".join(record.getMessage() for record in caplog.records)
    assert "callback_blocked channel_id=canal-externo" in text
    assert CALLBACK not in text


def test_channel_without_callback_url_cannot_reply():
    """R47: sin config.callback_url enviar_mensaje lanza ChannelNotConfigured."""
    channel = _channel(config={})
    with pytest.raises(ChannelNotConfigured):
        channel.enviar_mensaje("u", [TextBlock(type="text", text="Hola")])


def test_long_text_is_split_in_order_within_the_limit():
    """R40: el texto largo se envía en callbacks consecutivos y en orden."""
    client = FakeCallbackClient(status=200)
    channel = _channel(client)
    first = "a" * 3000
    second = "b" * 3000
    assert (
        channel.enviar_mensaje(
            "u",
            [TextBlock(type="text", text=first), TextBlock(type="text", text=second)],
        )
        == "sent"
    )
    assert len(client.requests) == 2
    texts = [
        NormalizedMessage.model_validate_json(body).text
        for _, body, _ in client.requests
    ]
    assert all(len(text) <= MAX_TEXT_LENGTH for text in texts)
    assert "".join(texts) == f"{first}\n{second}"
    assert texts[0].startswith("a" * 10)
    assert texts[-1].endswith("b" * 10)


def test_long_text_stops_at_first_failed_callback():
    """R40: si un callback falla, se detiene y devuelve failed."""
    client = FakeCallbackClient(status=500)
    channel = _channel(client)
    blocks = [
        TextBlock(type="text", text="a" * 3000),
        TextBlock(type="text", text="b" * 3000),
    ]
    assert channel.enviar_mensaje("u", blocks) == "failed"
    assert len(client.requests) == 1


# ── Validación de config y ruta /send ──────────────────────────────────────


def _route_app(callback: FakeCallbackClient | None = None):
    key = Fernet.generate_key().decode("ascii")
    repository = FakeChannelRepository(clock=lambda: NOW)
    adapters = Adapters(
        telegram=FakeTelegramClient(),
        dedup=FakeDedupStore(),
        orchestrator=FakeOrchestratorClient(),
        clock=lambda: NOW,
        channels=repository,
        callback=callback or FakeCallbackClient(),
    )
    settings = Settings(
        service_token=TOKEN,
        telegram_webhook_secret="telegram-webhook-secret",
        telegram_bot_token="123456:BOT",
        channel_secrets_key=SecretStr(key),
    )
    client = TestClient(create_app(settings, adapters), raise_server_exceptions=False)
    return client, repository


def _create_body(**overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "id": "canal-generico",
        "name": "Canal genérico",
        "adapter_type": "webhook_generico",
        "icon": "globe",
        "color": "#1B6FA8",
        "config": {"callback_url": CALLBACK},
    }
    body.update(overrides)
    return body


def _headers() -> dict[str, str]:
    return {"X-Service-Token": TOKEN}


def test_generic_adapter_type_is_creatable_and_listed():
    """R31: POST /channels con webhook_generico responde 201 y aparece en adapter_types."""
    client, _ = _route_app()
    with client:
        created = client.post("/channels", json=_create_body(), headers=_headers())
        listed = client.get("/channels", headers=_headers())
    assert created.status_code == 201
    assert "webhook_generico" in listed.json()["adapter_types"]


@pytest.mark.parametrize(
    "callback_url",
    [
        "http://callback.example.com/hook",
        "https://usuario@callback.example.com/hook",
        "https:///sin-host",
        "https://callback.example.com/" + "a" * 2048,
    ],
)
def test_invalid_callback_url_is_rejected_without_persisting(callback_url):
    """R34: callback_url inválido responde 422 y no persiste."""
    client, repository = _route_app()
    with client:
        response = client.post(
            "/channels",
            json=_create_body(config={"callback_url": callback_url}),
            headers=_headers(),
        )
    assert response.status_code == 422
    assert response.json()["error"] == "validation_error"
    assert repository.get("canal-generico") is None


def test_channel_without_callback_url_is_valid():
    """R34: ausencia de callback_url es válida."""
    client, _ = _route_app()
    with client:
        response = client.post(
            "/channels", json=_create_body(config={}), headers=_headers()
        )
    assert response.status_code == 201


def test_patch_with_invalid_callback_url_is_rejected_without_changes():
    """R34: PATCH con callback_url inválido responde 422 y conserva la config."""
    client, repository = _route_app()
    with client:
        assert client.post("/channels", json=_create_body(), headers=_headers()).status_code == 201
        response = client.patch(
            "/channels/canal-generico",
            json={"config": {"callback_url": "ftp://callback.example.com/hook"}},
            headers=_headers(),
        )
    assert response.status_code == 422
    assert repository.get("canal-generico").config == {"callback_url": CALLBACK}


def test_send_with_failed_callback_returns_502():
    """R38, R39: un callback no 2xx o de red hace que /send responda 502."""
    for callback in (
        FakeCallbackClient(status=500),
        FakeCallbackClient(error=CallbackNetworkError("red")),
    ):
        client, _ = _route_app(callback=callback)
        with client:
            assert client.post(
                "/channels", json=_create_body(), headers=_headers()
            ).status_code == 201
            response = client.post(
                "/send",
                json={
                    "channel": "canal-generico",
                    "destination": "usuario-1",
                    "blocks": [{"type": "text", "text": "Hola"}],
                },
                headers=_headers(),
            )
        assert response.status_code == 502
        assert response.json()["error"] == "upstream_error"


def test_send_with_blocked_callback_returns_502():
    """R46: una URL bloqueada al enviar responde 502 upstream_error."""
    client, _ = _route_app(callback=FakeCallbackClient(error=CallbackUrlRejected("x")))
    with client:
        assert client.post("/channels", json=_create_body(), headers=_headers()).status_code == 201
        response = client.post(
            "/send",
            json={
                "channel": "canal-generico",
                "destination": "usuario-1",
                "blocks": [{"type": "text", "text": "Hola"}],
            },
            headers=_headers(),
        )
    assert response.status_code == 502
    assert response.json()["error"] == "upstream_error"


def test_channel_secret_and_credentials_never_appear_in_logs(caplog):
    """R30: el secreto del canal no se registra al crear ni al enviar."""
    client, _ = _route_app(callback=FakeCallbackClient(status=500))
    with caplog.at_level(logging.DEBUG), client:
        created = client.post(
            "/channels",
            json=_create_body(credentials={"api_token": "credencial-privada"}),
            headers=_headers(),
        )
        client.post(
            "/send",
            json={
                "channel": "canal-generico",
                "destination": "usuario-1",
                "blocks": [{"type": "text", "text": "Hola"}],
            },
            headers=_headers(),
        )
    secret = created.json()["secret"]
    assert secret not in caplog.text
    assert "credencial-privada" not in caplog.text
