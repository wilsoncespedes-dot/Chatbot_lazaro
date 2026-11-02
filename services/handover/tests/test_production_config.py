"""Tests del arranque seguro en producción de handover (#24)."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from handover.config import Settings

TOKEN = "s" * 40
VALID = {
    "app_env": "production",
    "service_token": TOKEN,
    "database_url": "postgresql://app:clave@db:5432/lazaro",
    "telegram_gateway_url": "telegram-gateway:8000",
    "privacy_retention_days": "90",
    "privacy_active_case_max_days": "30",
}


def _failure(**overrides) -> str:
    with pytest.raises(ValidationError) as exc:
        Settings(**{**VALID, **overrides})
    return str(exc.value)


def test_valid_production_settings_normalize_gateway_url():
    """R12: TELEGRAM_GATEWAY_URL host:puerto se normaliza con http://."""
    settings = Settings(**VALID)
    assert settings.telegram_gateway_url == "http://telegram-gateway:8000"


def test_invalid_app_env_is_rejected():
    """R13: un APP_ENV desconocido impide arrancar."""
    assert "APP_ENV" in _failure(app_env="staging")


@pytest.mark.parametrize(
    "name",
    [
        "SERVICE_TOKEN",
        "DATABASE_URL",
        "TELEGRAM_GATEWAY_URL",
        "PRIVACY_RETENTION_DAYS",
        "PRIVACY_ACTIVE_CASE_MAX_DAYS",
    ],
)
def test_missing_required_variable_is_rejected(name):
    """R14: una obligatoria vacía impide arrancar en producción."""
    # `Settings` construye campos snake_case; el error debe nombrar la variable.
    assert name in _failure(**{name.lower(): ""})


def test_placeholder_is_rejected_case_insensitive():
    """R15: un placeholder conocido impide arrancar."""
    assert "SERVICE_TOKEN" in _failure(service_token="xxx")


def test_short_service_token_is_rejected():
    """R16: SERVICE_TOKEN con menos de 32 caracteres impide arrancar."""
    assert "SERVICE_TOKEN" in _failure(service_token="x" * 31)


def test_development_database_credentials_are_rejected():
    """R17: DATABASE_URL con lazaro:lazaro@ impide arrancar."""
    text = _failure(database_url="postgresql://lazaro:lazaro@postgres:5432/lazaro")
    assert "DATABASE_URL" in text


def test_invalid_advisor_ids_still_prevent_startup():
    """R14: una ADVISOR_CHAT_IDS inválida sigue impidiendo arrancar."""
    assert "ADVISOR_CHAT_IDS" in _failure(advisor_chat_ids="111,abc")


def test_error_message_does_not_include_values():
    """R20: el error solo nombra las variables afectadas."""
    secret = "VALOR-QUE-NO-DEBE-SALIR"
    text = _failure(service_token=secret)
    assert "SERVICE_TOKEN" in text
    assert secret not in text
