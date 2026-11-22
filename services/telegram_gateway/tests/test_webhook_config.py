"""R48-R51: configuración del webhook genérico y del modo de desarrollo."""
from __future__ import annotations

from pathlib import Path

import pytest
from lazaro_contracts import DEFAULT_SIGNATURE_WINDOW_SECONDS
from pydantic import ValidationError

from telegram_gateway.config import Settings

ROOT = Path(__file__).resolve().parents[3]
PRODUCTION = {
    "app_env": "production",
    "service_token": "s" * 40,
    "telegram_bot_token": "123456:BOT-TOKEN",
    "telegram_webhook_secret": "w" * 40,
    "redis_url": "redis://redis:6379/0",
    "orchestrator_url": "orchestrator:8000",
}


def test_webhook_settings_default_values():
    """R48, R50: valores por defecto seguros del webhook."""
    settings = Settings()
    assert settings.webhook_signature_window_seconds == DEFAULT_SIGNATURE_WINDOW_SECONDS
    assert settings.webhook_signature_window_seconds == 300
    assert settings.webhook_max_body_bytes == 1048576
    assert settings.webhook_allow_private_callbacks is False


@pytest.mark.parametrize("value", [0, -1, 3601, "no-numero"])
def test_signature_window_out_of_range_is_rejected(value):
    """R50: la ventana debe ser un entero entre 1 y 3600."""
    with pytest.raises(ValidationError):
        Settings(webhook_signature_window_seconds=value)


@pytest.mark.parametrize("value", [1023, 10_485_761, "no-numero"])
def test_max_body_bytes_out_of_range_is_rejected(value):
    """R50: el límite debe ser un entero entre 1024 y 10485760."""
    with pytest.raises(ValidationError):
        Settings(webhook_max_body_bytes=value)


def test_boundary_values_are_accepted():
    """R50: los extremos del rango son válidos."""
    settings = Settings(
        webhook_signature_window_seconds=1, webhook_max_body_bytes=1024
    )
    assert settings.webhook_signature_window_seconds == 1
    assert settings.webhook_max_body_bytes == 1024
    wide = Settings(
        webhook_signature_window_seconds=3600, webhook_max_body_bytes=10_485_760
    )
    assert wide.webhook_signature_window_seconds == 3600
    assert wide.webhook_max_body_bytes == 10_485_760


def test_production_rejects_private_callbacks():
    """R49: producción con WEBHOOK_ALLOW_PRIVATE_CALLBACKS=true no arranca."""
    with pytest.raises(ValidationError) as exc:
        Settings(**PRODUCTION, webhook_allow_private_callbacks=True)
    assert "WEBHOOK_ALLOW_PRIVATE_CALLBACKS" in str(exc.value)


def test_development_allows_private_callbacks():
    """R48: el modo de desarrollo admite el ajuste sin fallar al arrancar."""
    settings = Settings(
        app_env="development", webhook_allow_private_callbacks=True
    )
    assert settings.webhook_allow_private_callbacks is True


def test_env_example_declares_webhook_settings_with_ssrf_warning():
    """R51: .env.example declara las tres variables y avisa del riesgo SSRF."""
    text = (ROOT / ".env.example").read_text(encoding="utf-8")
    assert "WEBHOOK_SIGNATURE_WINDOW_SECONDS=300" in text
    assert "WEBHOOK_MAX_BODY_BYTES=1048576" in text
    assert "WEBHOOK_ALLOW_PRIVATE_CALLBACKS=false" in text
    assert "SSRF" in text
