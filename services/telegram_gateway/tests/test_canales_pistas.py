"""R3–R5, R27 (#66): pistas de credenciales, consent_mode del simulado y canal inactivo."""
from __future__ import annotations

from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from pydantic import SecretStr

from telegram_gateway.adapters.channel_repository import (
    ChannelChanges,
    FakeChannelRepository,
    _row_to_record,
)
from telegram_gateway.adapters.dedup import FakeDedupStore
from telegram_gateway.adapters.orchestrator import FakeOrchestratorClient
from telegram_gateway.adapters.telegram import FakeTelegramClient
from telegram_gateway.config import Settings
from telegram_gateway.domain import Adapters
from telegram_gateway.main import create_app
from telegram_gateway.registry import CHANNEL_REGISTRY

TOKEN = "service-token-test"
HEADERS = {"X-Service-Token": TOKEN}
SECRET_VALUE = "credencial-privada-9876"


def _client() -> tuple[TestClient, FakeChannelRepository]:
    repository = FakeChannelRepository()
    adapters = Adapters(
        telegram=FakeTelegramClient(),
        dedup=FakeDedupStore(),
        orchestrator=FakeOrchestratorClient(),
        channels=repository,
        channel_registry=CHANNEL_REGISTRY.copy(),
    )
    settings = Settings(
        service_token=TOKEN,
        telegram_webhook_secret="telegram-webhook-secret",
        telegram_bot_token="123456:BOT",
        channel_secrets_key=SecretStr(Fernet.generate_key().decode("ascii")),
    )
    return TestClient(create_app(settings, adapters), raise_server_exceptions=False), repository


def _create(client: TestClient, **overrides):
    body = {
        "id": "canal-demo",
        "name": "Canal demo",
        "adapter_type": "simulado",
        "icon": "chat",
        "color": "#1B6FA8",
        "config": {"consent_mode": "boton"},
        "credentials": {"api_token": SECRET_VALUE, "pin": "123"},
    }
    body.update(overrides)
    return client.post("/channels", json=body, headers=HEADERS)


def test_create_stores_only_hints_and_lists_them():
    """R3, R5: el alta guarda pistas (no valores) y el simulado acepta consent_mode."""
    client, repository = _client()
    with client:
        created = _create(client)
        assert created.status_code == 201, created.text
        listing = client.get("/channels", headers=HEADERS)
    info = next(c for c in listing.json()["channels"] if c["id"] == "canal-demo")
    assert info["credential_hints"] == {"api_token": "…9876", "pin": "…"}
    assert info["config"] == {"consent_mode": "boton"}
    assert SECRET_VALUE not in listing.text
    record = repository.get("canal-demo")
    assert record.credential_hints == {"api_token": "…9876", "pin": "…"}


def test_replacing_credentials_updates_hints_and_empty_clears_them():
    """R3, R4: reemplazar credenciales recalcula las pistas; `{}` las vacía."""
    client, _ = _client()
    with client:
        _create(client)
        updated = client.patch(
            "/channels/canal-demo",
            json={"credentials": {"nuevo_token": "abcdefgh-ZZZZ"}},
            headers=HEADERS,
        )
        assert updated.json()["credential_hints"] == {"nuevo_token": "…ZZZZ"}
        renamed = client.patch("/channels/canal-demo", json={"name": "Otro"}, headers=HEADERS)
        assert renamed.json()["credential_hints"] == {"nuevo_token": "…ZZZZ"}
        cleared = client.patch("/channels/canal-demo", json={"credentials": {}}, headers=HEADERS)
        assert cleared.json()["credential_hints"] == {}


def test_simulated_channel_still_rejects_unknown_config_keys():
    """R5: solo se añade consent_mode; otras claves siguen rechazadas."""
    client, _ = _client()
    with client:
        response = _create(client, config={"otra": 1})
    assert response.status_code == 422


def test_inactive_channel_webhook_is_404_and_send_is_rejected():
    """R27: un canal inactivo responde 404 en su webhook y no envía nada."""
    client, _ = _client()
    with client:
        _create(client)
        off = client.patch("/channels/canal-demo/active", json={"active": False}, headers=HEADERS)
        assert off.json()["active"] is False
        webhook = client.post("/webhooks/canal-demo", content=b"{}")
        assert webhook.status_code == 404
        send = client.post(
            "/send",
            json={
                "channel": "canal-demo",
                "destination": "d-1",
                "blocks": [{"type": "text", "text": "Hola"}],
            },
            headers=HEADERS,
        )
        assert send.status_code == 422
        assert send.json()["error"] == "channel_inactive"


def test_row_without_hints_column_maps_to_empty_hints():
    """Compatibilidad: filas de 10 columnas (antes de la migración) dan `{}`."""
    row = ("x1", "X", "simulado", "chat", "#1B6FA8", "{}", True, None, False, False)
    assert _row_to_record(row).credential_hints == {}
    assert _row_to_record(row + ('{"a": "…1234"}',)).credential_hints == {"a": "…1234"}


def test_fake_update_without_hints_keeps_previous():
    client, repository = _client()
    with client:
        _create(client)
    repository.update("canal-demo", ChannelChanges(name="Nuevo"))
    assert repository.get("canal-demo").credential_hints == {"api_token": "…9876", "pin": "…"}
