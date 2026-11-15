"""Configuración del segundo factor del panel (#54)."""
from __future__ import annotations

import base64
from pathlib import Path

import pytest
from pydantic import ValidationError

from orchestrator.config import Settings

ROOT = Path(__file__).resolve().parents[3]
VALID_KEY = base64.urlsafe_b64encode(b"k" * 32).decode("ascii")
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
    "identity_login_required": True,
}


def test_required_defaults_by_environment():
    """R21: obligatorio solo en producción cuando no está definido."""
    assert Settings().panel_2fa_required_effective is False
    assert Settings(**{**PRODUCTION, "panel_2fa_encryption_key": VALID_KEY}).panel_2fa_required_effective is True


@pytest.mark.parametrize("value", [True, False])
def test_explicit_required_is_respected_in_any_environment(value):
    """R22: un valor explícito manda en desarrollo y en producción."""
    assert Settings(panel_2fa_required=value).panel_2fa_required_effective is value
    settings = Settings(
        **{**PRODUCTION, "panel_2fa_encryption_key": VALID_KEY},
        panel_2fa_required=value,
    )
    assert settings.panel_2fa_required_effective is value


def test_empty_required_variable_means_unset():
    """R21: una variable vacía equivale a no definirla."""
    assert Settings(panel_2fa_required="").panel_2fa_required is None


def test_production_requires_a_valid_encryption_key():
    """R41: sin clave válida no se arranca y el error solo nombra la variable."""
    with pytest.raises(ValidationError) as exc:
        Settings(**PRODUCTION)
    text = str(exc.value)
    assert "PANEL_2FA_ENCRYPTION_KEY" in text
    assert VALID_KEY not in text


def test_production_rejects_invalid_key():
    """R41: una clave que no son 32 bytes en base64 urlsafe se rechaza."""
    with pytest.raises(ValidationError) as exc:
        Settings(**{**PRODUCTION, "panel_2fa_encryption_key": "no-es-una-clave"})
    assert "PANEL_2FA_ENCRYPTION_KEY" in str(exc.value)


def test_production_with_valid_key_keeps_required_true():
    """R42: en producción, sin PANEL_2FA_REQUIRED, el valor efectivo es true."""
    settings = Settings(**{**PRODUCTION, "panel_2fa_encryption_key": VALID_KEY})
    assert settings.panel_2fa_required_effective is True


@pytest.mark.parametrize(
    "overrides",
    [
        {"panel_2fa_window_steps": -1},
        {"panel_2fa_window_steps": 3},
        {"panel_2fa_recovery_codes": 3},
        {"panel_2fa_recovery_codes": 21},
        {"panel_2fa_issuer": ""},
        {"panel_2fa_issuer": " "},
        {"panel_2fa_issuer": "x" * 65},
    ],
)
def test_invalid_ranges_are_rejected(overrides):
    """R43: ventana, número de códigos y emisor se validan al construir Settings."""
    with pytest.raises(ValidationError):
        Settings(**overrides)


def test_documented_variables_exist_in_env_example_render_and_docs():
    """R44: las cinco variables figuran sin valores secretos."""
    names = [
        "PANEL_2FA_REQUIRED",
        "PANEL_2FA_ENCRYPTION_KEY",
        "PANEL_2FA_ISSUER",
        "PANEL_2FA_WINDOW_STEPS",
        "PANEL_2FA_RECOVERY_CODES",
    ]
    env_text = (ROOT / ".env.example").read_text(encoding="utf-8")
    render_text = (ROOT / "render.yaml").read_text(encoding="utf-8")
    docs_text = (ROOT / "docs" / "despliegue.md").read_text(encoding="utf-8")
    for name in names:
        assert name in env_text
        assert name in render_text
        assert name in docs_text
    key_block = render_text[
        render_text.index("- key: PANEL_2FA_ENCRYPTION_KEY"):
        render_text.index("- key: PANEL_2FA_ENCRYPTION_KEY") + 120
    ]
    assert "sync: false" in key_block
    assert VALID_KEY not in env_text + render_text + docs_text
