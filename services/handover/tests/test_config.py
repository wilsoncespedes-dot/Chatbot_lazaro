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
    "PRIVACY_RETENTION_DAYS",
    "PRIVACY_ACTIVE_CASE_MAX_DAYS",
    "CASE_LIST_LIMIT",
]


@pytest.fixture()
def clean_env(monkeypatch):
    for name in ENV_VARS:
        monkeypatch.delenv(name, raising=False)
    return monkeypatch


def test_advisor_ids_discards_blank_entries(clean_env):
    """R2 (#10); R23 (#7), modificado por R2 (#10): las entradas vacías se descartan."""
    clean_env.setenv("ADVISOR_CHAT_IDS", " 111, ,222,,-1003, ")
    assert Settings().advisor_ids == [111, 222, -1003]


@pytest.mark.parametrize(
    "value",
    [" 111, ,abc,222,,-1003, 4x ", "111,1.5", "111,+5", "111,1_000"],
)
def test_advisor_ids_rejects_non_numeric_entry(clean_env, value):
    """R3: una entrada no vacía que no es un entero (solo `-?[0-9]+`) lanza ValidationError."""
    clean_env.setenv("ADVISOR_CHAT_IDS", value)
    with pytest.raises(ValidationError):
        Settings()


def test_non_numeric_error_reports_position_and_value(clean_env):
    """R4, R8: el error indica la posición y el valor inválido y no repite los ids válidos."""
    clean_env.setenv("ADVISOR_CHAT_IDS", " 111, ,abc,222,,-1003, 4x ")
    with pytest.raises(ValidationError) as excinfo:
        Settings()
    message = str(excinfo.value)
    assert "la entrada 3 ('abc')" in message
    assert "111" not in message
    assert "222" not in message
    assert "-1003" not in message


def test_advisor_ids_strips_surrounding_spaces(clean_env):
    """R1: los espacios (y tabuladores) que rodean cada entrada se quitan antes de validar."""
    clean_env.setenv("ADVISOR_CHAT_IDS", "  111 ,\t222  ")
    assert Settings().advisor_ids == [111, 222]


@pytest.mark.parametrize("value", [",,,", " , , ", ""])
def test_advisor_ids_only_commas_is_empty(clean_env, value):
    """R2: solo comas, espacios o la cadena vacía dan una lista vacía sin error."""
    clean_env.setenv("ADVISOR_CHAT_IDS", value)
    assert Settings().advisor_ids == []


@pytest.mark.parametrize("value", ["111,222,111", "7,007"])
def test_advisor_ids_rejects_duplicate(clean_env, value):
    """R5: dos entradas con el mismo valor entero lanzan ValidationError."""
    clean_env.setenv("ADVISOR_CHAT_IDS", value)
    with pytest.raises(ValidationError):
        Settings()


def test_duplicate_error_reports_positions(clean_env):
    """R6: el error de duplicado da las posiciones de las dos primeras apariciones."""
    clean_env.setenv("ADVISOR_CHAT_IDS", "111,222,,111")
    with pytest.raises(ValidationError) as excinfo:
        Settings()
    assert "la entrada 4 repite el id de la entrada 1" in str(excinfo.value)


def test_advisor_ids_accepts_negative_ids(clean_env):
    """R7: los ids negativos (grupos y canales de Telegram) son válidos y -7 no es 7."""
    clean_env.setenv("ADVISOR_CHAT_IDS", "-1001234567890,-5,42")
    assert Settings().advisor_ids == [-1001234567890, -5, 42]
    clean_env.setenv("ADVISOR_CHAT_IDS", "-7,7")
    assert Settings().advisor_ids == [-7, 7]


@pytest.mark.parametrize(
    ("value", "hidden_ids"),
    [
        ("987654321,abc", ("987654321",)),
        ("987654321,123123,987654321", ("987654321", "123123")),
    ],
)
def test_config_error_does_not_echo_valid_ids(clean_env, value, hidden_ids):
    """R8: el texto del error no contiene entradas válidas de ADVISOR_CHAT_IDS."""
    clean_env.setenv("ADVISOR_CHAT_IDS", value)
    with pytest.raises(ValidationError) as excinfo:
        Settings()
    message = str(excinfo.value)
    for hidden in hidden_ids:
        assert hidden not in message


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
    """R30: cada plazo no vacío debe ser un entero >= 1, también en desarrollo."""
    clean_env.setenv(name, value)
    with pytest.raises(ValidationError):
        Settings()


@pytest.mark.parametrize(
    ("retention", "active"),
    [("30", "30"), ("30", "31")],
)
def test_active_case_limit_must_be_strictly_less(clean_env, retention, active):
    """R31: PRIVACY_ACTIVE_CASE_MAX_DAYS debe ser estrictamente menor que la retención."""
    clean_env.setenv("PRIVACY_RETENTION_DAYS", retention)
    clean_env.setenv("PRIVACY_ACTIVE_CASE_MAX_DAYS", active)
    with pytest.raises(ValidationError):
        Settings()


def test_active_case_limit_below_retention_is_valid(clean_env):
    """R31: un límite menor que la retención es válido."""
    clean_env.setenv("PRIVACY_RETENTION_DAYS", "30")
    clean_env.setenv("PRIVACY_ACTIVE_CASE_MAX_DAYS", "7")
    settings = Settings()
    assert settings.retention_configured is True
    assert (settings.retention_days, settings.active_case_max_days) == (30, 7)


def test_case_list_limit_defaults_to_50(clean_env):
    """contrato_listar_casos_asesor R22: sin CASE_LIST_LIMIT vale 50."""
    assert Settings().case_list_limit == 50


def test_case_list_limit_reads_env(clean_env):
    """contrato_listar_casos_asesor R17: CASE_LIST_LIMIT se lee del entorno."""
    clean_env.setenv("CASE_LIST_LIMIT", "2")
    assert Settings().case_list_limit == 2


@pytest.mark.parametrize("value", ["0", "201", "abc"])
def test_case_list_limit_rejects_out_of_range(clean_env, value):
    """contrato_listar_casos_asesor R17: fuera de 1–200 o no entero no construye Settings."""
    clean_env.setenv("CASE_LIST_LIMIT", value)
    with pytest.raises(ValidationError):
        Settings()

