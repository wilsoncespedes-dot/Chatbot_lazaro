"""Tests del arranque seguro en producción de telegram_gateway (#24)."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from telegram_gateway.config import Settings

TOKEN = "s" * 40
SECRET = "w" * 40
VALID = {
    "app_env": "production",
    "service_token": TOKEN,
    "telegram_bot_token": "123456:BOT-TOKEN",
    "telegram_webhook_secret": SECRET,
    "redis_url": "redis://redis:6379/0",
    "orchestrator_url": "orchestrator:8000",
}


def _failure(**overrides) -> str:
    with pytest.raises(ValidationError) as exc:
        Settings(**{**VALID, **overrides})
    return str(exc.value)


def test_valid_production_settings_normalize_orchestrator_url():
    """R12: en producción ORCHESTRATOR_URL host:puerto se normaliza con http://."""
    settings = Settings(**VALID)
    assert settings.orchestrator_url == "http://orchestrator:8000"


def test_invalid_app_env_is_rejected():
    """R13: un APP_ENV desconocido impide arrancar."""
    text = _failure(app_env="staging")
    assert "APP_ENV" in text


@pytest.mark.parametrize(
    "name",
    [
        "SERVICE_TOKEN",
        "TELEGRAM_BOT_TOKEN",
        "TELEGRAM_WEBHOOK_SECRET",
        "REDIS_URL",
        "ORCHESTRATOR_URL",
    ],
)
def test_missing_required_variable_is_rejected(name):
    """R14: una obligatoria vacía impide arrancar en producción."""
    # `Settings` construye campos snake_case; el error debe nombrar la variable.
    assert name in _failure(**{name.lower(): ""})


def test_placeholder_is_rejected_case_insensitive():
    """R15: un placeholder conocido impide arrancar."""
    assert "TELEGRAM_BOT_TOKEN" in _failure(telegram_bot_token="SeCrEt")


def test_short_service_token_is_rejected():
    """R16: SERVICE_TOKEN con menos de 32 caracteres impide arrancar."""
    assert "SERVICE_TOKEN" in _failure(service_token="x" * 31)


def test_invalid_webhook_secret_is_rejected():
    """R18: el secret_token debe cumplir la regex de Telegram."""
    assert "TELEGRAM_WEBHOOK_SECRET" in _failure(telegram_webhook_secret="a" * 31)


def test_webhook_secret_with_invalid_characters_is_rejected():
    """R18: +, / y = no son válidos para secret_token."""
    assert "TELEGRAM_WEBHOOK_SECRET" in _failure(telegram_webhook_secret="a" * 31 + "+")


def test_error_message_does_not_include_values():
    """R20: el error solo nombra las variables afectadas."""
    secret = "VALOR-QUE-NO-DEBE-SALIR"
    text = _failure(service_token=secret, telegram_bot_token="")
    assert "TELEGRAM_BOT_TOKEN" in text
    assert secret not in text
