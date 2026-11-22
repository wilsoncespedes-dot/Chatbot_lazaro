"""R34, R35: cliente del simulador del orquestador (HTTP y falso)."""
from __future__ import annotations

import json
from datetime import datetime, timezone

import httpx
import pytest
from lazaro_contracts import (
    SERVICE_TOKEN_HEADER,
    ChannelInfo,
    MailboxEntry,
)

from orchestrator.adapters.simulator import (
    FakeSimulatorClient,
    HttpSimulatorClient,
    SimulatorUnavailable,
)

NOW = datetime(2026, 11, 21, 15, 0, tzinfo=timezone.utc)
TOKEN = "service-token-test"
BASE = "http://gateway:8000"
CHANNEL = "tiktok-simulado"
CHANNEL_INFO = {
    "id": CHANNEL,
    "name": "TikTok",
    "adapter_type": "simulado",
    "icon": "chat",
    "color": "#1B6FA8",
    "config": {},
    "active": True,
    "configured": True,
    "has_secrets": True,
    "managed_by_environment": False,
    "created_at": "2026-11-21T15:00:00Z",
}
TELEGRAM_INFO = {**CHANNEL_INFO, "id": "telegram", "name": "Telegram", "adapter_type": "telegram"}
ENTRY = {
    "id": 1,
    "channel": CHANNEL,
    "destination": "cliente-demo",
    "kind": "client",
    "text": "Hola",
    "created_at": "2026-11-21T15:00:00Z",
}


def _client(handler, token: str = TOKEN) -> HttpSimulatorClient:
    return HttpSimulatorClient(
        BASE, token, transport=httpx.MockTransport(handler)
    )


def _listing(handler_extra=None):
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers[SERVICE_TOKEN_HEADER] == TOKEN
        if handler_extra is not None:
            extra = handler_extra(request)
            if extra is not None:
                return extra
        if request.url.path == "/channels":
            return httpx.Response(
                200,
                json={
                    "channels": [CHANNEL_INFO, TELEGRAM_INFO],
                    "adapter_types": ["webhook_generico", "simulado"],
                },
            )
        if request.url.path == f"/channels/{CHANNEL}/mailbox":
            return httpx.Response(
                200, json={"channel": CHANNEL, "entries": [ENTRY]}
            )
        if request.url.path == f"/channels/{CHANNEL}/simulate":
            return httpx.Response(200, json={"status": "accepted", "forwarded": True})
        return httpx.Response(404, json={"error": "not_found", "message": "x"})

    return handler


def test_list_channels_sends_token_filters_and_uses_only_get_channels():
    """R35: X-Service-Token, filtro simulado y solo GET /channels."""
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return _listing()(request)

    channels = _client(handler).list_channels()
    assert [channel.id for channel in channels] == [CHANNEL]
    assert all(isinstance(channel, ChannelInfo) for channel in channels)
    assert len(calls) == 1
    assert calls[0].method == "GET"
    assert calls[0].url.path == "/channels"
    assert calls[0].headers[SERVICE_TOKEN_HEADER] == TOKEN
    assert "secret" not in ChannelInfo.model_fields


def test_simulate_posts_only_the_simulate_route():
    """R35: simulate llama a POST /channels/{id}/simulate con el cuerpo del contrato."""
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return _listing()(request)

    response = _client(handler).simulate(CHANNEL, "cliente-demo", "Hola")
    assert response.status == "accepted"
    assert response.forwarded is True
    assert len(calls) == 1
    assert calls[0].method == "POST"
    assert calls[0].url.path == f"/channels/{CHANNEL}/simulate"
    assert json.loads(calls[0].content) == {
        "external_user_id": "cliente-demo",
        "text": "Hola",
    }


def test_mailbox_uses_only_the_mailbox_route_with_destination_and_after():
    """R35: mailbox llama a GET /channels/{id}/mailbox con sus parámetros."""
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return _listing()(request)

    response = _client(handler).mailbox(CHANNEL, "cliente-demo", after=3)
    assert response.channel == CHANNEL
    assert response.entries == [MailboxEntry.model_validate(ENTRY)]
    assert len(calls) == 1
    assert calls[0].method == "GET"
    assert calls[0].url.path == f"/channels/{CHANNEL}/mailbox"
    assert calls[0].url.params["destination"] == "cliente-demo"
    assert calls[0].url.params["after"] == "3"


@pytest.mark.parametrize("status", [400, 404, 422, 500, 503])
def test_non_2xx_is_simulator_unavailable(status):
    """R34: cualquier respuesta no 2xx se traduce a SimulatorUnavailable."""
    client = _client(lambda request: httpx.Response(status, text="secreto"))
    with pytest.raises(SimulatorUnavailable):
        client.list_channels()


def test_network_error_and_invalid_json_are_simulator_unavailable():
    """R34: error de transporte o JSON inválido no expone detalles."""

    def network_error(request):
        raise httpx.ConnectError(f"{TOKEN} no responde")

    with pytest.raises(SimulatorUnavailable) as error:
        _client(network_error).simulate(CHANNEL, "cliente-demo", "Hola")
    assert TOKEN not in str(error.value)

    client = _client(lambda request: httpx.Response(200, text="no-json"))
    with pytest.raises(SimulatorUnavailable) as invalid:
        client.mailbox(CHANNEL, "cliente-demo")
    assert TOKEN not in str(invalid.value)


def test_fake_simulator_filters_calls_and_can_fail():
    """R35: la versión falsa permite comprobar llamadas y simular caídas."""
    simulado = ChannelInfo.model_validate(CHANNEL_INFO)
    telegram = ChannelInfo.model_validate(TELEGRAM_INFO)
    entry = MailboxEntry.model_validate(ENTRY)
    fake = FakeSimulatorClient(
        channels=[simulado, telegram], entries=[entry], forwarded=False, reason="no"
    )
    assert [channel.id for channel in fake.list_channels()] == [CHANNEL]
    response = fake.simulate(CHANNEL, "cliente-demo", "Hola")
    assert response.forwarded is False and response.reason == "no"
    mailbox = fake.mailbox(CHANNEL, "cliente-demo")
    assert mailbox.entries == [entry]
    assert fake.calls == [
        ("list_channels",),
        ("simulate", CHANNEL, "cliente-demo", "Hola"),
        ("mailbox", CHANNEL, "cliente-demo", 0),
    ]

    failing = FakeSimulatorClient(fail=True)
    with pytest.raises(SimulatorUnavailable):
        failing.list_channels()
