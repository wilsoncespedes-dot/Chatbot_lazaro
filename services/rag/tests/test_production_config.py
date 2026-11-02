"""Tests del arranque seguro en producción de rag (#24)."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from rag.config import Settings

TOKEN = "s" * 40
VALID = {
    "app_env": "production",
    "service_token": TOKEN,
    "database_url": "postgresql://app:clave@db:5432/lazaro",
    "embeddings_api_key": "clave-real",
    "embeddings_model": "modelo-embeddings",
}


def _failure(**overrides) -> str:
    with pytest.raises(ValidationError) as exc:
        Settings(**{**VALID, **overrides})
    return str(exc.value)


def test_valid_production_settings_are_accepted():
    """R14: con todas las obligatorias válidas el servicio arranca."""
    assert Settings(**VALID).app_env == "production"


def test_invalid_app_env_is_rejected():
    """R13: un APP_ENV desconocido impide arrancar."""
    assert "APP_ENV" in _failure(app_env="staging")


@pytest.mark.parametrize(
    "name",
    ["SERVICE_TOKEN", "DATABASE_URL", "EMBEDDINGS_API_KEY", "EMBEDDINGS_MODEL"],
)
def test_missing_required_variable_is_rejected(name):
    """R14: una obligatoria vacía impide arrancar en producción."""
    # `Settings` construye campos snake_case; el error debe nombrar la variable.
    assert name in _failure(**{name.lower(): ""})


def test_placeholder_is_rejected_case_insensitive():
    """R15: un placeholder conocido impide arrancar."""
    assert "EMBEDDINGS_MODEL" in _failure(embeddings_model="Placeholder")


def test_short_service_token_is_rejected():
    """R16: SERVICE_TOKEN con menos de 32 caracteres impide arrancar."""
    assert "SERVICE_TOKEN" in _failure(service_token="x" * 31)


def test_development_database_credentials_are_rejected():
    """R17: DATABASE_URL con lazaro:lazaro@ impide arrancar."""
    text = _failure(database_url="postgresql://lazaro:lazaro@postgres:5432/lazaro")
    assert "DATABASE_URL" in text


def test_error_message_does_not_include_values():
    """R20: el error solo nombra las variables afectadas."""
    secret = "VALOR-QUE-NO-DEBE-SALIR"
    text = _failure(embeddings_api_key="", embeddings_model=secret)
    assert "EMBEDDINGS_API_KEY" in text
    assert secret not in text
