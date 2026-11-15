"""Tests de la configuración del servicio handover."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from handover.config import Settings

ENV_VARS = [
    "HANDOVER_TIMEOUT_SECONDS",
    "HANDOVER_TIMEOUT_REPLY",
    "HTTP_TIMEOUT_SECONDS",
    "DATABASE_URL",
    "TELEGRAM_GATEWAY_URL",
    "PRIVACY_RETENTION_DAYS",
    "PRIVACY_ACTIVE_CASE_MAX_DAYS",
    "CASE_LIST_LIMIT",
]


@pytest.fixture()
def clean_env(monkeypatch):
    for name in ENV_VARS:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.delenv("ADVISOR_CHAT_IDS", raising=False)
    return monkeypatch


def test_settings_work_without_advisor_chat_ids(clean_env):
    """R44: handover arranca sin ADVISOR_CHAT_IDS y sin validar ids Telegram."""
    settings = Settings()
    assert not hasattr(settings, "advisor_ids")


def test_timeout_defaults_to_300(clean_env):
    """R44: valores por defecto de la espera y del texto de vencimiento."""
    settings = Settings()
    assert settings.handover_timeout_seconds == 300
    assert settings.handover_timeout_reply.strip()
    assert settings.http_timeout_seconds == 10


def test_settings_read_from_env(clean_env):
    """R44: los valores se leen de variables de entorno."""
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
    """R44: HANDOVER_TIMEOUT_SECONDS debe ser un entero >= 1."""
    clean_env.setenv("HANDOVER_TIMEOUT_SECONDS", value)
    with pytest.raises(ValidationError):
        Settings()


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("PRIVACY_RETENTION_DAYS", "0"),
        ("PRIVACY_RETENTION_DAYS", "-1"),
        ("PRIVACY_RETENTION_DAYS", "abc"),
        ("PRIVACY_ACTIVE_CASE_MAX_DAYS", "0"),
        ("PRIVACY_ACTIVE_CASE_MAX_DAYS", "-1"),
        ("PRIVACY_ACTIVE_CASE_MAX_DAYS", "abc"),
    ],
)
def test_privacy_days_must_be_positive_integer(clean_env, name, value):
    """R44: cada plazo no vacío debe ser un entero >= 1, también en desarrollo."""
    clean_env.setenv(name, value)
    with pytest.raises(ValidationError):
        Settings()


@pytest.mark.parametrize(
    ("retention", "active"),
    [("30", "30"), ("30", "31")],
)
def test_active_case_limit_must_be_strictly_less(clean_env, retention, active):
    """R44: PRIVACY_ACTIVE_CASE_MAX_DAYS debe ser estrictamente menor que la retención."""
    clean_env.setenv("PRIVACY_RETENTION_DAYS", retention)
    clean_env.setenv("PRIVACY_ACTIVE_CASE_MAX_DAYS", active)
    with pytest.raises(ValidationError):
        Settings()


def test_active_case_limit_below_retention_is_valid(clean_env):
    """R44: un límite menor que la retención es válido."""
    clean_env.setenv("PRIVACY_RETENTION_DAYS", "30")
    clean_env.setenv("PRIVACY_ACTIVE_CASE_MAX_DAYS", "7")
    settings = Settings()
    assert settings.retention_configured is True
    assert (settings.retention_days, settings.active_case_max_days) == (30, 7)


def test_case_list_limit_defaults_to_50(clean_env):
    """R44: sin CASE_LIST_LIMIT vale 50."""
    assert Settings().case_list_limit == 50


def test_case_list_limit_reads_env(clean_env):
    """R44: CASE_LIST_LIMIT se lee del entorno."""
    clean_env.setenv("CASE_LIST_LIMIT", "2")
    assert Settings().case_list_limit == 2


@pytest.mark.parametrize("value", ["0", "201", "abc"])
def test_case_list_limit_rejects_out_of_range(clean_env, value):
    """R44: fuera de 1–200 o no entero no construye Settings."""
    clean_env.setenv("CASE_LIST_LIMIT", value)
    with pytest.raises(ValidationError):
        Settings()
