"""R3–R11, R40: adaptador SIMULADO, capacidades, envío y validación de config."""
from __future__ import annotations

import logging
import socket
from datetime import datetime, timezone
from typing import Any

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from lazaro_contracts import (
    ChannelCapabilities,
    NormalizedMessage,
    TextBlock,
)
from pydantic import SecretStr

from telegram_gateway.adapters.callback import FakeCallbackClient
from telegram_gateway.adapters.channel_repository import FakeChannelRepository
from telegram_gateway.adapters.channels import SimuladoChannel
from telegram_gateway.adapters.dedup import FakeDedupStore
from telegram_gateway.adapters.mailbox import FakeMailboxRepository
from telegram_gateway.adapters.orchestrator import FakeOrchestratorClient
from telegram_gateway.adapters.telegram import FakeTelegramClient
from telegram_gateway.config import Settings
from telegram_gateway.domain import (
    Adapters,
    ChannelNotConfigured,
    ChannelRecord,
    InvalidChannelConfig,
)
from telegram_gateway.main import create_app
from telegram_gateway.ports.canal import Canal
from telegram_gateway.registry import ChannelContext

NOW = datetime(2026, 11, 21, 15, 0, tzinfo=timezone.utc)
TOKEN = "service-token-test"
CHANNEL = "tiktok-simulado"


def _record(**overrides: Any) -> ChannelRecord:
    values: dict[str, Any] = {
        "id": CHANNEL,
        "name": "TikTok",
        "adapter_type": "simulado",
        "icon": "chat",
        "color": "#1B6FA8",
        "config": {},
        "active": True,
        "created_at": NOW,
        "has_secrets": False,
        "active_follows_environment": False,
    }
    values.update(overrides)
    return ChannelRecord(**values)


def _context(
    mailbox: FakeMailboxRepository | None = None,
    callback: FakeCallbackClient | None = None,
) -> ChannelContext:
    adapters = Adapters(
        telegram=FakeTelegramClient(),
        dedup=FakeDedupStore(),
        orchestrator=FakeOrchestratorClient(),
        clock=lambda: NOW,
        mailbox=mailbox or FakeMailboxRepository(),
        callback=callback or FakeCallbackClient(),
    )
    return ChannelContext(settings=Settings(service_token=TOKEN), adapters=adapters)


def _channel(
    *, config: dict | None = None, mailbox: FakeMailboxRepository | None = None
) -> SimuladoChannel:
    return SimuladoChannel.build(
        _record(config=config or {}),
        _context(mailbox),
        None,
    )


def _inbound(**overrides: Any) -> dict[str, Any]:
    values: dict[str, Any] = {
        "channel": CHANNEL,
        "external_user_id": "cliente-demo",
        "external_chat_id": "cliente-demo",
        "external_message_id": "msg-1",
        "kind": "text",
        "text": "Hola",
        "received_at": "2026-11-21T15:00:00Z",
    }
    values.update(overrides)
    return values


def _default_capabilities() -> ChannelCapabilities:
    return ChannelCapabilities(
        free_text_allowed=True,
        max_options=0,
        min_list_options=0,
        max_list_options=0,
        supports_links=False,
        requires_template=False,
        supports_buttons=False,
        supports_images=False,
        supports_files=False,
        supports_audio=False,
    )


def test_simulated_channel_implements_port_name_and_docstring():
    """R4, R40, R3: clase con Simulado, docstring SIMULADO e implementa Canal."""
    channel = _channel()
    assert isinstance(channel, Canal)
    assert "Simulado" in type(channel).__name__
    assert "SIMULADO" in type(channel).__doc__


def test_capabilities_use_defaults_and_custom_values_per_channel():
    """R5: defaults de R5 y dos canales con capacidades distintas."""
    assert _channel().capacidades() == _default_capabilities()
    custom = _channel(
        config={
            "capabilities": {
                "supports_buttons": True,
                "supports_images": True,
                "supports_links": True,
                "max_options": 2,
                "min_list_options": 2,
                "max_list_options": 4,
                "requires_template": True,
            }
        }
    ).capacidades()
    assert custom.supports_buttons is True
    assert custom.supports_images is True
    assert custom.supports_links is True
    assert custom.max_options == 2
    assert custom.min_list_options == 2
    assert custom.max_list_options == 4
    assert custom.requires_template is True
    assert custom != _channel().capacidades()


def test_validate_config_accepts_empty_and_rejects_extra_keys_or_bad_values():
    """R6: config vacío válido; claves extra, tipos o valores inválidos no."""
    context = _context()
    SimuladoChannel.validate_config({}, context)
    SimuladoChannel.validate_config({"capabilities": {}}, context)
    SimuladoChannel.validate_config(
        {"capabilities": {"supports_images": True, "max_options": 3}}, context
    )
    for config in (
        {"modo": "demo"},
        {"capabilities": {"desconocida": True}},
        {"capabilities": {"supports_images": "si"}},
        {"capabilities": {"supports_images": 1}},
        {"capabilities": {"max_options": "3"}},
        {"capabilities": {"max_options": 4}},
        {"capabilities": {"min_list_options": 5, "max_list_options": 4}},
        {"capabilities": []},
    ):
        with pytest.raises(InvalidChannelConfig):
            SimuladoChannel.validate_config(config, context)


def test_build_without_mailbox_is_channel_not_configured():
    """R11: sin adapters.mailbox no se puede construir el canal."""
    context = ChannelContext(
        settings=Settings(),
        adapters=Adapters(
            telegram=FakeTelegramClient(),
            dedup=FakeDedupStore(),
            orchestrator=FakeOrchestratorClient(),
            clock=lambda: NOW,
            mailbox=None,
        ),
    )
    with pytest.raises(ChannelNotConfigured):
        SimuladoChannel.build(_record(), context, None)


def test_recibir_mensaje_and_identificar_usuario_accept_only_inbound():
    """R8: formato normalizado válido; inválido o saliente devuelve None."""
    channel = _channel()
    message = channel.recibir_mensaje(_inbound())
    assert isinstance(message, NormalizedMessage)
    assert message.direction == "inbound"
    assert channel.recibir_mensaje({"foo": "bar"}) is None
    assert channel.recibir_mensaje(_inbound(direction="outbound")) is None
    assert channel.identificar_usuario(_inbound()) == "cliente-demo"
    assert channel.identificar_usuario({"foo": "bar"}) is None
    assert channel.identificar_usuario(_inbound(direction="outbound")) is None


def test_send_writes_reply_chunks_in_order_without_network(monkeypatch):
    """R9: una entrada reply por trozo, en orden, sin sockets ni callback."""
    mailbox = FakeMailboxRepository()
    callback = FakeCallbackClient()

    def forbidden_socket(*args, **kwargs):
        raise AssertionError("el canal simulado no debe abrir sockets")

    monkeypatch.setattr(socket, "socket", forbidden_socket)
    channel = _channel(mailbox=mailbox)
    blocks = [
        TextBlock(type="text", text="a" * 3000),
        TextBlock(type="text", text="b" * 3000),
    ]
    assert channel.enviar_mensaje("cliente-demo", blocks) == "sent"
    entries = mailbox.list(CHANNEL, "cliente-demo", 0, 100, NOW)
    assert len(entries) == 2
    assert all(entry.kind == "reply" for entry in entries)
    assert all(len(entry.text) <= 4096 for entry in entries)
    assert "".join(entry.text for entry in entries) == f"{'a' * 3000}\n{'b' * 3000}"
    assert entries[0].text.startswith("a" * 10)
    assert entries[-1].text.endswith("b" * 10)
    assert callback.requests == []


def test_mailbox_failure_returns_failed_and_logs_only_exception_type(caplog):
    """R10: fallo del buzón -> failed y log solo con el tipo de la excepción."""
    channel = _channel(mailbox=FakeMailboxRepository(fail=True))
    with caplog.at_level(logging.WARNING):
        assert (
            channel.enviar_mensaje("cliente-demo", [TextBlock(type="text", text="Hola")])
            == "failed"
        )
    text = "\n".join(record.getMessage() for record in caplog.records)
    assert "simulado_mailbox_error channel_id=tiktok-simulado" in text
    assert "OSError" in text
    assert "mailbox unavailable" not in text


def test_hooks_record_client_and_rejection_entries():
    """R21–R23: los hooks dejan entradas client y rejected con el motivo."""
    mailbox = FakeMailboxRepository()
    channel = _channel(mailbox=mailbox)
    message = channel.recibir_mensaje(_inbound())
    assert message is not None
    channel.registrar_entrada(message)
    reason = "El orquestador respondió 422." + "x" * 250
    channel.registrar_rechazo(message, reason)
    entries = mailbox.list(CHANNEL, "cliente-demo", 0, 100, NOW)
    assert [entry.kind for entry in entries] == ["client", "rejected"]
    assert entries[0].text == "Hola"
    assert entries[1].text == reason[:200]
    assert len(entries[1].text) == 200


def _route_app(
    *,
    mailbox: FakeMailboxRepository | None = None,
    key: str | None = None,
):
    repository = FakeChannelRepository(clock=lambda: NOW)
    adapters = Adapters(
        telegram=FakeTelegramClient(),
        dedup=FakeDedupStore(),
        orchestrator=FakeOrchestratorClient(),
        clock=lambda: NOW,
        channels=repository,
        mailbox=mailbox or FakeMailboxRepository(),
    )
    settings = Settings(
        service_token=TOKEN,
        telegram_webhook_secret="telegram-webhook-secret",
        telegram_bot_token="123456:BOT",
        channel_secrets_key=SecretStr(key or Fernet.generate_key().decode("ascii")),
    )
    return TestClient(create_app(settings, adapters), raise_server_exceptions=False), repository


def _headers() -> dict[str, str]:
    return {"X-Service-Token": TOKEN}


def _create_body(**overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "id": CHANNEL,
        "name": "TikTok",
        "adapter_type": "simulado",
        "icon": "chat",
        "color": "#1B6FA8",
        "config": {},
    }
    body.update(overrides)
    return body


def test_post_channels_accepts_simulado_and_lists_it():
    """R3: POST /channels con simulado responde 201 y aparece en adapter_types."""
    client, _ = _route_app()
    with client:
        created = client.post("/channels", json=_create_body(), headers=_headers())
        listed = client.get("/channels", headers=_headers())
    assert created.status_code == 201
    assert created.json()["secret"]
    assert "simulado" in listed.json()["adapter_types"]


@pytest.mark.parametrize(
    "config",
    [
        {"modo": "demo"},
        {"capabilities": {"desconocida": True}},
        {"capabilities": {"supports_images": "no"}},
        {"capabilities": {"max_options": 4}},
    ],
)
def test_invalid_simulated_config_is_rejected_without_persisting(config):
    """R6: config inválido responde 422 y no persiste ni en POST ni en PATCH."""
    client, repository = _route_app()
    with client:
        created = client.post(
            "/channels", json=_create_body(config=config), headers=_headers()
        )
        assert repository.get(CHANNEL) is None
        assert client.post("/channels", json=_create_body(), headers=_headers()).status_code == 201
        patched = client.patch(
            f"/channels/{CHANNEL}", json={"config": config}, headers=_headers()
        )
    assert created.status_code == 422
    assert created.json()["error"] == "validation_error"
    assert patched.status_code == 422
    assert patched.json()["error"] == "validation_error"
    assert repository.get(CHANNEL).config == {}


def test_send_with_failed_mailbox_returns_502():
    """R10: si el buzón falla, POST /send responde 502 upstream_error."""
    client, _ = _route_app(mailbox=FakeMailboxRepository(fail=True))
    with client:
        assert client.post(
            "/channels", json=_create_body(), headers=_headers()
        ).status_code == 201
        response = client.post(
            "/send",
            json={
                "channel": CHANNEL,
                "destination": "cliente-demo",
                "blocks": [{"type": "text", "text": "Hola"}],
            },
            headers=_headers(),
        )
    assert response.status_code == 502
    assert response.json()["error"] == "upstream_error"


def test_send_degrades_image_into_text_in_the_mailbox():
    """R7: ImageBlock con supports_images=false se degrada y queda en el buzón."""
    mailbox = FakeMailboxRepository()
    client, _ = _route_app(mailbox=mailbox)
    with client:
        assert client.post(
            "/channels", json=_create_body(), headers=_headers()
        ).status_code == 201
        response = client.post(
            "/send",
            json={
                "channel": CHANNEL,
                "destination": "cliente-demo",
                "blocks": [
                    {
                        "type": "image",
                        "url": "https://media.example.test/photo.jpg",
                        "alt_text": "Foto",
                    }
                ],
            },
            headers=_headers(),
        )
    assert response.status_code == 200
    entries = mailbox.list(CHANNEL, "cliente-demo", 0, 100, NOW)
    assert len(entries) == 1
    assert "Foto: https://media.example.test/photo.jpg" == entries[0].text
