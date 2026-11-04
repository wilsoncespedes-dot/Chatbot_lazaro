"""Configuración de WhatsApp Cloud API en telegram_gateway (#43)."""
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from telegram_gateway.adapters.dedup import FakeDedupStore
from telegram_gateway.adapters.orchestrator import FakeOrchestratorClient
from telegram_gateway.adapters.telegram import FakeTelegramClient
from telegram_gateway.adapters.whatsapp_cloud import WhatsAppCloudAdapter
from telegram_gateway.config import Settings
from telegram_gateway.domain import Adapters
from telegram_gateway.main import build_default_adapters, create_app

ROOT = Path(__file__).resolve().parents[3]
HEADERS = {"X-Service-Token": "svc-token"}

BASE = {
    "service_token": "svc-token",
    "telegram_webhook_secret": "hook-secret",
    "telegram_bot_token": "123456:BOT",
    "message_grouping_enabled": False,
    "whatsapp_enabled": True,
    "whatsapp_access_token": "ACCESS-TOKEN-VALUE",
    "whatsapp_app_secret": "APP-SECRET-VALUE",
    "whatsapp_verify_token": "VERIFY-TOKEN-VALUE",
    "whatsapp_phone_number_id": "PN-1",
}


def disabled_client() -> tuple[TestClient, Settings]:
    settings = Settings(
        service_token="svc-token",
        telegram_webhook_secret="hook-secret",
        telegram_bot_token="123456:BOT",
        message_grouping_enabled=False,
        whatsapp_enabled=False,
    )
    adapters = Adapters(
        FakeTelegramClient(), FakeDedupStore(), FakeOrchestratorClient()
    )
    return TestClient(create_app(settings, adapters)), settings


def test_disabled_whatsapp_has_no_adapter_and_send_returns_502():
    """R1: con WHATSAPP_ENABLED=false /send whatsapp falla cerrado."""
    client, _settings = disabled_client()
    response = client.post(
        "/send",
        json={
            "channel": "whatsapp",
            "destination": "57300",
            "blocks": [{"type": "text", "text": "Hola"}],
        },
        headers=HEADERS,
    )
    assert response.status_code == 502
    assert response.json()["error"] == "upstream_error"


def test_disabled_whatsapp_webhook_returns_404():
    """R2: sin WhatsApp habilitado el webhook no existe."""
    client, _settings = disabled_client()
    get = client.get(
        "/whatsapp/webhook",
        params={
            "hub.mode": "subscribe",
            "hub.verify_token": "x",
            "hub.challenge": "1",
        },
    )
    post = client.post("/whatsapp/webhook", content=b"{}")
    assert get.status_code == 404 and get.json()["error"] == "not_found"
    assert post.status_code == 404 and post.json()["error"] == "not_found"


def test_disabled_default_build_has_no_whatsapp_adapter():
    """R1: el constructor por defecto respeta WHATSAPP_ENABLED=false."""
    settings = Settings(
        service_token="svc-token",
        telegram_webhook_secret="hook-secret",
        telegram_bot_token="123456:BOT",
        whatsapp_enabled=False,
    )
    adapters = build_default_adapters(settings)
    assert adapters.whatsapp is None
    assert adapters.whatsapp_window is None


@pytest.mark.parametrize(
    "field, variable",
    [
        ("whatsapp_access_token", "WHATSAPP_ACCESS_TOKEN"),
        ("whatsapp_app_secret", "WHATSAPP_APP_SECRET"),
        ("whatsapp_verify_token", "WHATSAPP_VERIFY_TOKEN"),
        ("whatsapp_phone_number_id", "WHATSAPP_PHONE_NUMBER_ID"),
    ],
)
def test_enabled_whatsapp_requires_each_secret(field, variable):
    """R3: falta una variable → error que solo la nombra."""
    with pytest.raises(ValidationError) as info:
        Settings(**{**BASE, field: ""})
    text = str(info.value)
    assert variable in text
    assert "ACCESS-TOKEN-VALUE" not in text
    assert "APP-SECRET-VALUE" not in text
    assert "VERIFY-TOKEN-VALUE" not in text


def test_enabled_valid_settings_build_the_real_adapter():
    """R4: con configuración válida se construye WhatsAppCloudAdapter."""
    adapters = build_default_adapters(Settings(**BASE))
    assert isinstance(adapters.whatsapp, WhatsAppCloudAdapter)
    assert adapters.whatsapp_window is not None


def test_secrets_are_not_in_repr():
    """R5: los secretos no aparecen en el repr de Settings ni del adaptador."""
    settings = Settings(**BASE)
    assert "ACCESS-TOKEN-VALUE" not in repr(settings)
    assert "APP-SECRET-VALUE" not in repr(settings)
    assert "VERIFY-TOKEN-VALUE" not in repr(settings)
    adapter = build_default_adapters(settings).whatsapp
    assert "ACCESS-TOKEN-VALUE" not in repr(adapter)
    assert "APP-SECRET-VALUE" not in repr(adapter)


def test_env_example_declares_whatsapp_variables_with_empty_secrets():
    """R7: .env.example lista todas las variables y deja vacíos los secretos."""
    text = (ROOT / ".env.example").read_text(encoding="utf-8")
    declared = {
        line.split("=", 1)[0].strip()
        for line in text.splitlines()
        if "=" in line and not line.lstrip().startswith("#")
    }
    for name in (
        "WHATSAPP_ENABLED",
        "WHATSAPP_ACCESS_TOKEN",
        "WHATSAPP_APP_SECRET",
        "WHATSAPP_VERIFY_TOKEN",
        "WHATSAPP_PHONE_NUMBER_ID",
        "WHATSAPP_GRAPH_BASE_URL",
        "WHATSAPP_GRAPH_API_VERSION",
        "WHATSAPP_TEMPLATE_LANGUAGE",
        "WHATSAPP_INTERACTIVE_BODY_TEXT",
    ):
        assert name in declared, name
    for name in (
        "WHATSAPP_ACCESS_TOKEN",
        "WHATSAPP_APP_SECRET",
        "WHATSAPP_VERIFY_TOKEN",
        "WHATSAPP_PHONE_NUMBER_ID",
    ):
        line = next(
            line for line in text.splitlines() if line.startswith(f"{name}=")
        )
        assert line == f"{name}="


@pytest.mark.parametrize(
    "overrides",
    [
        {"whatsapp_graph_api_version": "21.0"},
        {"whatsapp_template_language": "ES"},
        {"whatsapp_interactive_body_text": ""},
        {"whatsapp_interactive_body_text": "x" * 1025},
        {"whatsapp_window_hours": 0},
        {"whatsapp_window_hours": 25},
    ],
)
def test_invalid_format_is_rejected(overrides):
    """R3: la configuración de formato también se valida."""
    with pytest.raises(ValidationError):
        Settings(**{**BASE, **overrides})
