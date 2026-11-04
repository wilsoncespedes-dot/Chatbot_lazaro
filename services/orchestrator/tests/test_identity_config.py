"""Configuración de identidad y arranque seguro en producción (#38, T5)."""
from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from orchestrator.config import Settings

ROOT = Path(__file__).resolve().parents[3]
IDENTITY_VARS = [
    "IDENTITY_PUBLIC_BASE_URL",
    "IDENTITY_LINK_SIGNING_KEY",
    "IDENTITY_LOGIN_REQUIRED",
    "IDENTITY_LINK_TTL_MINUTES",
    "IDENTITY_SESSION_IDLE_MINUTES",
    "IDENTITY_LOGIN_MAX_ATTEMPTS",
    "IDENTITY_LOCKOUT_MINUTES",
    "CREDENTIAL_VALIDITY_DAYS",
    "CREDENTIAL_EXPIRY_NOTICE_DAYS",
    "IDENTITY_LOGOUT_COMMANDS",
    "PASSWORD_SCRYPT_N",
]

PRODUCTION = {
    "app_env": "production",
    "service_token": "s" * 40,
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
    "identity_public_base_url": "https://orchestrator.example",
    "identity_link_signing_key": "k" * 32,
}


def test_defaults_match_the_documented_table():
    """R6: TTL por defecto 15 y rangos del design."""
    settings = Settings()
    assert settings.identity_link_ttl_minutes == 15
    assert settings.identity_session_idle_minutes == 60
    assert settings.identity_login_max_attempts == 5
    assert settings.identity_lockout_minutes == 15
    assert settings.credential_validity_days == 30
    assert settings.credential_expiry_notice_days == 5
    assert settings.identity_login_required is True
    assert settings.password_scrypt_n == 32768
    assert settings.identity_logout_command_list == (
        "/salir",
        "cerrar sesion",
        "cerrar sesión",
    )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("identity_link_ttl_minutes", 0),
        ("identity_link_ttl_minutes", 1441),
        ("identity_session_idle_minutes", 4),
        ("identity_login_max_attempts", 0),
        ("identity_lockout_minutes", 1441),
        ("credential_validity_days", 0),
        ("credential_expiry_notice_days", 61),
        ("password_scrypt_n", 16000),
    ],
)
def test_identity_settings_ranges(field, value):
    """R6: valores fuera de rango se rechazan al construir Settings."""
    with pytest.raises(ValidationError):
        Settings(**{field: value})


@pytest.mark.parametrize(
    ("overrides", "expected"),
    [
        ({"identity_public_base_url": "http://inseguro"}, "IDENTITY_PUBLIC_BASE_URL"),
        ({"identity_public_base_url": ""}, "IDENTITY_PUBLIC_BASE_URL"),
        ({"identity_link_signing_key": "corta"}, "IDENTITY_LINK_SIGNING_KEY"),
        ({"identity_login_required": False}, "IDENTITY_LOGIN_REQUIRED"),
    ],
)
def test_production_identity_requirements(overrides, expected):
    """R8, R50: producción exige https, clave >= 32 y login activo."""
    with pytest.raises(ValidationError) as exc:
        Settings(**{**PRODUCTION, **overrides})
    assert expected in str(exc.value)


def test_env_example_and_render_declare_identity_variables():
    """R8, R50: las variables nuevas están documentadas y en el Blueprint."""
    env_text = (ROOT / ".env.example").read_text(encoding="utf-8")
    declared = {
        line.split("=", 1)[0].strip()
        for line in env_text.splitlines()
        if "=" in line and not line.lstrip().startswith("#")
    }
    for name in IDENTITY_VARS:
        assert name in declared, name

    render_text = (ROOT / "render.yaml").read_text(encoding="utf-8")
    assert "IDENTITY_PUBLIC_BASE_URL" in render_text
    assert "IDENTITY_LINK_SIGNING_KEY" in render_text
