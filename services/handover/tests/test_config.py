"""Tests de la configuración del servicio handover."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from handover.config import Settings

ENV_VARS = [
    "ADVISOR_CHAT_IDS",
    "HANDOVER_TIMEOUT_SECONDS",
    "HANDOVER_TIMEOUT_REPLY",
    "HTTP_TIMEOUT_SECONDS",
    "DATABASE_URL",
    "TELEGRAM_GATEWAY_URL",
]


@pytest.fixture()
def clean_env(monkeypatch):
    for name in ENV_VARS:
        monkeypatch.delenv(name, raising=False)
    return monkeypatch


def test_advisor_ids_discards_blank_and_non_numeric(clean_env):
    """R23: ADVISOR_CHAT_IDS se separa por comas; vacíos y no numéricos se descartan."""
    clean_env.setenv("ADVISOR_CHAT_IDS", " 111, ,abc,222,,-1003, 4x ")
    assert Settings().advisor_ids == [111, 222, -1003]


def test_advisor_ids_empty_by_default(clean_env):
    """R23: sin ADVISOR_CHAT_IDS no hay asesores."""
    assert Settings().advisor_ids == []


def test_timeout_defaults_to_300(clean_env):
    """R23: valores por defecto de la espera y del texto de vencimiento."""
    settings = Settings()
    assert settings.handover_timeout_seconds == 300
    assert settings.handover_timeout_reply.strip()
    assert settings.http_timeout_seconds == 10


def test_settings_read_from_env(clean_env):
    """R23: los valores se leen de variables de entorno."""
    clean_env.setenv("HANDOVER_TIMEOUT_SECONDS", "45")
    clean_env.setenv("HANDOVER_TIMEOUT_REPLY", "Sigue en espera")
    clean_env.setenv("TELEGRAM_GATEWAY_URL", "http://gw:8000")
    clean_env.setenv("DATABASE_URL", "postgresql://u:p@h/db")
    settings = Settings()
    assert settings.handover_timeout_seconds == 45
    assert settings.handover_timeout_reply == "Sigue en espera"
    assert settings.telegram_gateway_url == "http://gw:8000"
    assert settings.database_url == "postgresql://u:p@h/db"


@pytest.mark.parametrize("value", ["0", "-5"])
def test_timeout_below_one_is_rejected(clean_env, value):
    """R23: HANDOVER_TIMEOUT_SECONDS debe ser un entero >= 1."""
    clean_env.setenv("HANDOVER_TIMEOUT_SECONDS", value)
    with pytest.raises(ValidationError):
        Settings()
