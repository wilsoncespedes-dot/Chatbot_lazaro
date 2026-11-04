"""Tests del arranque seguro en producción de orchestrator (#24)."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from orchestrator.config import Settings

TOKEN = "s" * 40
VALID = {
    "app_env": "production",
    "service_token": TOKEN,
    "database_url": "postgresql://app:clave@db:5432/lazaro",
    "rag_url": "rag:8000",
    "handover_url": "handover:8000",
    "telegram_gateway_url": "telegram-gateway:8000",
    "llm_api_key": "clave-real",
    "llm_model": "modelo-barato",
    "privacy_notice_text": "Aviso. Acepto el tratamiento de mis datos.",
    "privacy_notice_version": "v1",
    "privacy_accept_phrase": "Acepto el tratamiento de mis datos.",
    "privacy_accepted_reply": "Gracias.",
    "privacy_retention_days": "90",
    # #38: identidad de clientes
    "identity_public_base_url": "https://orchestrator.example",
    "identity_link_signing_key": "k" * 32,
    "identity_login_required": True,
}


def _failure(**overrides) -> str:
    with pytest.raises(ValidationError) as exc:
        Settings(**{**VALID, **overrides})
    return str(exc.value)


def test_valid_production_settings_normalize_internal_urls():
    """R12: las URLs internas host:puerto se normalizan con http://."""
    settings = Settings(**VALID)
    assert settings.rag_url == "http://rag:8000"
    assert settings.handover_url == "http://handover:8000"
    assert settings.telegram_gateway_url == "http://telegram-gateway:8000"


def test_invalid_app_env_is_rejected():
    """R13: un APP_ENV desconocido impide arrancar."""
    assert "APP_ENV" in _failure(app_env="staging")


@pytest.mark.parametrize(
    "name",
    [
        "SERVICE_TOKEN",
        "DATABASE_URL",
        "RAG_URL",
        "HANDOVER_URL",
        "TELEGRAM_GATEWAY_URL",
        "LLM_API_KEY",
        "LLM_MODEL",
        "PRIVACY_NOTICE_TEXT",
        "PRIVACY_NOTICE_VERSION",
        "PRIVACY_ACCEPT_PHRASE",
        "PRIVACY_ACCEPTED_REPLY",
        "PRIVACY_RETENTION_DAYS",
    ],
)
def test_missing_required_variable_is_rejected(name):
    """R14: una obligatoria vacía impide arrancar en producción."""
    # `Settings` construye campos snake_case; el error debe nombrar la variable.
    assert name in _failure(**{name.lower(): ""})


def test_development_database_credentials_are_rejected():
    """R17: DATABASE_URL con lazaro:lazaro@ impide arrancar."""
    text = _failure(database_url="postgresql://lazaro:lazaro@postgres:5432/lazaro")
    assert "DATABASE_URL" in text


def test_short_service_token_is_rejected():
    """R16: SERVICE_TOKEN con menos de 32 caracteres impide arrancar."""
    assert "SERVICE_TOKEN" in _failure(service_token="x" * 31)


def test_insecure_admin_cookie_is_rejected():
    """R19: ADMIN_COOKIE_SECURE=false impide arrancar en producción."""
    assert "ADMIN_COOKIE_SECURE" in _failure(admin_cookie_secure=False)


def test_placeholder_is_rejected_case_insensitive():
    """R15: un placeholder conocido impide arrancar."""
    assert "LLM_MODEL" in _failure(llm_model="CHANGEME")


def test_error_message_does_not_include_values():
    """R20: el error solo nombra las variables afectadas."""
    secret = "VALOR-QUE-NO-DEBE-SALIR"
    text = _failure(service_token=secret)
    assert "SERVICE_TOKEN" in text
    assert secret not in text
