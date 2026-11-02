"""Tests de las utilidades puras de configuración de producción (#24)."""
from __future__ import annotations

import pytest

from lazaro_contracts.production import (
    MIN_SERVICE_TOKEN_LENGTH,
    PLACEHOLDERS,
    ProductionConfigError,
    is_valid_webhook_secret,
    normalize_service_url,
    parse_app_env,
    production_problems,
)

REQUIRED = ("SERVICE_TOKEN", "DATABASE_URL", "LLM_API_KEY")
VALID = {
    "SERVICE_TOKEN": "t" * MIN_SERVICE_TOKEN_LENGTH,
    "DATABASE_URL": "postgresql://app:clave@db:5432/lazaro",
    "LLM_API_KEY": "clave-real",
}


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("handover:8000", "http://handover:8000"),
        ("http://handover:8000", "http://handover:8000"),
        ("https://example.com/base", "https://example.com/base"),
        ("", ""),
        ("  rag:8000  ", "http://rag:8000"),
    ],
)
def test_normalize_service_url(value, expected):
    """R12: `host:puerto` pasa a `http://host:puerto`; el resto no cambia."""
    assert normalize_service_url(value) == expected


@pytest.mark.parametrize("value", ["development", "production"])
def test_parse_app_env_accepts_known_values(value):
    """R13: APP_ENV admite development y production."""
    assert parse_app_env(value) == value


@pytest.mark.parametrize("value", ["staging", "PRODUCTION", "", "prod"])
def test_parse_app_env_rejects_other_values(value):
    """R13: cualquier otro APP_ENV se rechaza."""
    with pytest.raises(ValueError):
        parse_app_env(value)


def test_production_problems_accepts_valid_values():
    """R14, R16, R17: una configuración válida no tiene problemas."""
    assert production_problems(VALID, REQUIRED) == []


def test_production_problems_accepts_settings_field_names():
    """R14, R16, R17: model_dump() en snake_case no produce falsos positivos."""
    snake_case = {name.lower(): value for name, value in VALID.items()}
    assert production_problems(snake_case, REQUIRED) == []


def test_production_problems_reports_uppercase_names_for_snake_case_values():
    """R20: con valores snake_case los problemas conservan el nombre UPPERCASE."""
    snake_case = {name.lower(): value for name, value in VALID.items()}
    snake_case["llm_api_key"] = ""
    assert production_problems(snake_case, REQUIRED) == ["LLM_API_KEY"]


@pytest.mark.parametrize("name", REQUIRED)
def test_production_problems_reports_empty_values(name):
    """R14: una obligatoria vacía se nombra."""
    values = {**VALID, name: ""}
    assert name in production_problems(values, REQUIRED)


@pytest.mark.parametrize("placeholder", sorted(PLACEHOLDERS))
def test_production_problems_rejects_placeholders_case_insensitive(placeholder):
    """R15: los placeholders conocidos se rechazan sin distinguir mayúsculas."""
    values = {**VALID, "LLM_API_KEY": placeholder.upper()}
    assert "LLM_API_KEY" in production_problems(values, REQUIRED)


def test_production_problems_rejects_short_service_token():
    """R16: SERVICE_TOKEN con menos de 32 caracteres no es válido."""
    values = {**VALID, "SERVICE_TOKEN": "c" * (MIN_SERVICE_TOKEN_LENGTH - 1)}
    assert "SERVICE_TOKEN" in production_problems(values, REQUIRED)


def test_production_problems_rejects_development_database_credentials():
    """R17: DATABASE_URL no puede llevar las credenciales de desarrollo."""
    values = {
        **VALID,
        "DATABASE_URL": "postgresql://lazaro:lazaro@postgres:5432/lazaro",
    }
    assert "DATABASE_URL" in production_problems(values, REQUIRED)


def test_production_problems_names_only_variables():
    """R20: la lista de problemas solo contiene nombres, nunca valores."""
    secret = "VALOR-QUE-NO-DEBE-SALIR"
    values = {**VALID, "SERVICE_TOKEN": secret, "LLM_API_KEY": ""}
    problems = production_problems(values, REQUIRED)
    assert "LLM_API_KEY" in problems
    assert all(secret not in problem for problem in problems)
    assert all(problem.isupper() or problem.isdigit() or "_" in problem for problem in problems)


def test_production_config_error_message_names_variables_without_values():
    """R20: ProductionConfigError nombra variables y omite sus valores."""
    error = ProductionConfigError(["SERVICE_TOKEN", "DATABASE_URL"])
    assert str(error) == (
        "Configuración de producción inválida: SERVICE_TOKEN, DATABASE_URL"
    )
    assert error.names == ["SERVICE_TOKEN", "DATABASE_URL"]


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("a" * 32, True),
        ("A_Z-9" + "b" * 27, True),
        ("a" * 256, True),
        ("a" * 31, False),
        ("a" * 257, False),
        ("a" * 31 + "+", False),
        ("a" * 31 + "/", False),
        ("", False),
        ("cambia-esto", False),
    ],
)
def test_is_valid_webhook_secret(value, expected):
    """R18: el secret_token de Telegram exige 32-256 de [A-Za-z0-9_-]."""
    assert is_valid_webhook_secret(value) is expected
