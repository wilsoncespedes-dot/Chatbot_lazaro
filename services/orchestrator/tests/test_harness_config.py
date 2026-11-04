"""Configuración del harness y de los datos propios del cliente (#39)."""
from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from orchestrator.config import Settings

ROOT = Path(__file__).resolve().parents[3]
ALLOWLIST = '{"mis_datos.v_datos": ["cliente_id", "nombre"]}'


def test_r59_defaults_are_safe():
    """R59: router y datos de clientes apagados; límites y listas con defaults."""
    settings = Settings()
    assert settings.harness_router_enabled is False
    assert settings.harness_max_input_chars == 2000
    assert settings.harness_frustration_escalation is True
    assert settings.client_data_enabled is False
    assert settings.client_data_max_rows == 20
    assert settings.client_data_timeout_ms == 5000
    assert settings.client_data_max_joins == 1
    assert settings.client_data_max_reply_chars == 3500
    assert settings.client_data_rls_setting == "lazaro.cliente_id"
    assert "{request_id}" in settings.suppression_request_reply
    assert settings.harness_injection_pattern_list
    assert settings.harness_suppression_keyword_list


def test_r59_env_example_declares_every_new_variable():
    """R59: las variables nuevas están en .env.example con sus defaults."""
    text = (ROOT / ".env.example").read_text(encoding="utf-8")
    declared = {
        line.split("=", 1)[0].strip()
        for line in text.splitlines()
        if "=" in line and not line.lstrip().startswith("#")
    }
    for name in (
        "HARNESS_ROUTER_ENABLED",
        "HARNESS_MAX_INPUT_CHARS",
        "HARNESS_INJECTION_PATTERNS",
        "HARNESS_FRUSTRATION_ESCALATION",
        "HARNESS_FRUSTRATION_KEYWORDS",
        "HARNESS_SUPPRESSION_KEYWORDS",
        "HARNESS_INPUT_TOO_LONG_REPLY",
        "HARNESS_TOOL_DENIED_REPLY",
        "SUPPRESSION_REQUEST_REPLY",
        "CLIENT_DATA_ENABLED",
        "CLIENT_DATA_DATABASE_URL",
        "CLIENT_DATA_VIEWS_SCHEMA",
        "CLIENT_DATA_ALLOWLIST",
        "CLIENT_DATA_RLS_SETTING",
        "CLIENT_DATA_MAX_ROWS",
        "CLIENT_DATA_TIMEOUT_MS",
        "CLIENT_DATA_MAX_JOINS",
        "CLIENT_DATA_MAX_REPLY_CHARS",
        "CLIENT_DATA_TRUNCATED_NOTE",
        "CLIENT_DATA_DISABLED_REPLY",
        "CLIENT_DATA_REJECTED_REPLY",
        "CLIENT_DATA_UNAVAILABLE_REPLY",
    ):
        assert name in declared


@pytest.mark.parametrize(
    "field,value",
    [
        ("harness_max_input_chars", 99),
        ("harness_max_input_chars", 4097),
        ("client_data_max_rows", 0),
        ("client_data_max_rows", 201),
        ("client_data_timeout_ms", 99),
        ("client_data_timeout_ms", 30001),
        ("client_data_max_joins", -1),
        ("client_data_max_joins", 4),
        ("client_data_max_reply_chars", 199),
        ("client_data_max_reply_chars", 4001),
    ],
)
def test_r63_numeric_variables_out_of_range_fail_at_start(field, value):
    """R63: una variable numérica fuera de rango impide arrancar."""
    with pytest.raises(ValidationError):
        Settings(**{field: value})


def test_suppression_reply_requires_request_id_placeholder():
    """R39, R59: el texto fijo debe permitir sustituir el id de la solicitud."""
    with pytest.raises(ValidationError):
        Settings(suppression_request_reply="Solicitud registrada.")


def _enabled(**overrides) -> Settings:
    values = {
        "client_data_enabled": True,
        "database_url": "postgresql://app@db/lazaro",
        "client_data_database_url": "postgresql://ro@db/lazaro_clientes",
        "client_data_views_schema": "mis_datos",
        "client_data_allowlist": ALLOWLIST,
        "client_data_rls_setting": "lazaro.cliente_id",
    }
    values.update(overrides)
    return Settings(**values)


def test_r35_valid_client_data_config_starts():
    """R35: una configuración completa y distinta de las demás conexiones arranca."""
    settings = _enabled()
    assert settings.client_data_allowlist_map == {
        "mis_datos.v_datos": ("cliente_id", "nombre")
    }


@pytest.mark.parametrize("field", ["client_data_database_url"])
def test_r35_empty_dsn_fails(field):
    """R35: con CLIENT_DATA_ENABLED=true el DSN no puede estar vacío."""
    with pytest.raises(ValidationError) as exc:
        _enabled(**{field: ""})
    assert "CLIENT_DATA_DATABASE_URL" in str(exc.value)


def test_r35_dsn_cannot_equal_database_url():
    """R35: el DSN de clientes no puede ser la conexión de la aplicación."""
    with pytest.raises(ValidationError):
        _enabled(client_data_database_url="postgresql://app@db/lazaro")


def test_r35_dsn_cannot_equal_db_query_dsn():
    """R35: el DSN de clientes no puede reutilizar el del personal."""
    with pytest.raises(ValidationError):
        _enabled(
            db_query_database_url="postgresql://ro@db/lazaro_clientes",
            client_data_database_url="postgresql://ro@db/lazaro_clientes",
        )


@pytest.mark.parametrize(
    "overrides",
    [
        {"client_data_allowlist": ""},
        {"client_data_allowlist": "no json"},
        {"client_data_allowlist": '{"otros.v_datos": ["id"]}'},
        {"client_data_views_schema": "9malo"},
        {"client_data_rls_setting": "sin_punto"},
        {"client_data_rls_setting": "lazaro.cliente-id"},
    ],
)
def test_r35_invalid_allowlist_schema_or_rls_setting_fails(overrides):
    """R35: allowlist, esquema o clave de RLS inválidos impiden arrancar."""
    with pytest.raises(ValidationError):
        _enabled(**overrides)
