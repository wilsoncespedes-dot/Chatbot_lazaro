"""Tests del arranque seguro en producción de handover (#24)."""
from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from handover.config import Settings

ROOT = Path(__file__).resolve().parents[3]
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


def test_advisor_chat_ids_is_no_longer_required():
    """R44, R45: ADVISOR_CHAT_IDS ya no existe ni impide arrancar en producción."""
    settings = Settings(**VALID)
    assert not hasattr(settings, "advisor_chat_ids")


@pytest.mark.parametrize("name", [".env.example", "docker-compose.yml", "render.yaml"])
def test_advisor_chat_ids_is_removed_from_deployment_files(name):
    """R45: la retirada de ADVISOR_CHAT_IDS llega a configuración y despliegue."""
    text = (ROOT / name).read_text(encoding="utf-8")
    assert "ADVISOR_CHAT_IDS" not in text


def test_error_message_does_not_include_values():
    """R20: el error solo nombra las variables afectadas."""
    secret = "VALOR-QUE-NO-DEBE-SALIR"
    text = _failure(service_token=secret)
    assert "SERVICE_TOKEN" in text
    assert secret not in text


def _env_example() -> dict[str, str]:
    values: dict[str, str] = {}
    for line in (ROOT / ".env.example").read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def test_approved_values_pass_production_validation():
    """#57 R7: los valores aprobados de .env.example validan en producción."""
    env = _env_example()
    settings = Settings(
        app_env="production",
        service_token=TOKEN,
        database_url="postgresql://app:clave@db:5432/lazaro",
        telegram_gateway_url="telegram-gateway:8000",
        privacy_retention_days=env["PRIVACY_RETENTION_DAYS"],
        privacy_active_case_max_days=env["PRIVACY_ACTIVE_CASE_MAX_DAYS"],
    )
    assert settings.retention_days == 30
    assert settings.active_case_max_days == 15
    assert settings.retention_configured is True
