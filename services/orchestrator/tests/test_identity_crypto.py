"""Firma de enlaces, hash de credenciales, estados y política (#38, T1-T4)."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

import pytest

from orchestrator.accounts import (
    hash_password,
    hash_password_scrypt,
    verify_password,
)
from orchestrator.config import Settings
from orchestrator.identity import (
    LINK_PREFIX,
    credential_allows_access,
    credential_status,
    days_remaining,
    is_logout_command,
    resolve_identity_policy,
    sign_login_token,
    verify_login_token_signature,
)

NOW = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
PASSWORD = "clave-segura-123"
LINK_KEY = "k" * 32


# --- R19, R20 -------------------------------------------------------------------


def test_scrypt_hash_format_salt_and_verification():
    """R19, R20: formato scrypt$n$r$p$sal$hash, sal distinta y verificación."""
    stored = hash_password_scrypt(PASSWORD, 16384)
    scheme, n, r, p, salt_hex, digest_hex = stored.split("$")
    assert scheme == "scrypt"
    assert (int(n), int(r), int(p)) == (16384, 8, 1)
    assert len(bytes.fromhex(salt_hex)) == 16
    assert len(bytes.fromhex(digest_hex)) == 32
    assert verify_password(PASSWORD, stored) is True
    assert verify_password(PASSWORD + "x", stored) is False
    assert hash_password_scrypt(PASSWORD, 16384) != stored


def test_pbkdf2_hashes_from_20_still_verify():
    """R20: los hashes PBKDF2 existentes siguen siendo válidos."""
    stored = hash_password(PASSWORD, 1000)
    assert verify_password(PASSWORD, stored) is True
    assert verify_password("otra", stored) is False


def test_unknown_prefix_is_rejected():
    """R20: un prefijo desconocido no se interpreta como contraseña válida."""
    assert verify_password(PASSWORD, "md5$abc") is False
    assert verify_password(PASSWORD, "") is False


# --- R3, R13 --------------------------------------------------------------------


def test_login_token_format_and_signature():
    """R3: `<nonce>.<hmac>` verificable con la misma clave."""
    token = sign_login_token(LINK_KEY)
    nonce, signature = token.split(".", 1)
    assert nonce and signature and len(signature) == 64
    assert verify_login_token_signature(token, LINK_KEY) is True
    assert verify_login_token_signature(token, "x" * 32) is False


def test_altered_or_malformed_token_is_rejected():
    """R13: token alterado, sin punto o vacío no pasa la firma."""
    token = sign_login_token(LINK_KEY)
    assert verify_login_token_signature(token + "0", LINK_KEY) is False
    assert verify_login_token_signature(token.replace(".", ""), LINK_KEY) is False
    assert verify_login_token_signature("", LINK_KEY) is False


def test_signature_prefix_binds_the_token_version():
    """R3: la firma cubre `login-link:v1:` y no otro prefijo."""
    import hashlib
    import hmac

    token = sign_login_token(LINK_KEY)
    nonce = token.split(".", 1)[0]
    expected = hmac.new(
        LINK_KEY.encode(), f"{LINK_PREFIX}{nonce}".encode(), hashlib.sha256
    ).hexdigest()
    assert token.endswith(expected)


# --- R45 ------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("valid_from", "valid_until", "revoked_at", "expected"),
    [
        (NOW - timedelta(days=1), NOW + timedelta(days=30), None, "vigente"),
        (NOW - timedelta(days=1), NOW + timedelta(days=3), None, "por_vencer"),
        (NOW - timedelta(days=30), NOW, None, "vencida"),
        (NOW + timedelta(days=1), NOW + timedelta(days=30), None, "no_iniciada"),
        (
            NOW - timedelta(days=1),
            NOW + timedelta(days=30),
            NOW - timedelta(hours=1),
            "revocada",
        ),
    ],
)
def test_credential_status_five_states(valid_from, valid_until, revoked_at, expected):
    """R45: los cinco estados se calculan con reloj fijo."""
    assert credential_status(valid_from, valid_until, revoked_at, NOW, 5) == expected


def test_credential_status_boundaries():
    """R45: `valid_until == now` ya está vencida; el aviso usa `<=`."""
    assert (
        credential_status(NOW, NOW, None, NOW, 5) == "vencida"
    )
    assert (
        credential_status(NOW, NOW + timedelta(days=5), None, NOW, 5)
        == "por_vencer"
    )
    assert (
        credential_status(NOW, NOW + timedelta(days=6), None, NOW, 5)
        == "vigente"
    )


def test_only_valid_and_expiring_allow_access():
    """R34, R36: solo vigente y por_vencer habilitan."""
    assert credential_allows_access("vigente")
    assert credential_allows_access("por_vencer")
    for status in ("vencida", "revocada", "no_iniciada"):
        assert not credential_allows_access(status)


def test_days_remaining_never_negative():
    """R45: días completos desde las fechas, mínimo 0."""
    assert days_remaining(NOW + timedelta(days=9, hours=1), NOW) == 9
    assert days_remaining(NOW - timedelta(days=4), NOW) == 0


# --- R29, R49 -------------------------------------------------------------------


def test_logout_commands_match_normalized_exact_text():
    """R29: mayúsculas/espacios coinciden; un comando de asesor no."""
    commands = ("/salir", "cerrar sesion", "cerrar sesión")
    assert is_logout_command("  /SALIR ", commands)
    assert is_logout_command("Cerrar   Sesión", commands)
    assert not is_logout_command("/cerrar 12", commands)
    assert not is_logout_command("/salir ahora", commands)


def test_identity_policy_valid_override_wins():
    """R49: una clave válida de `app_settings` sustituye al entorno."""
    settings = Settings(identity_link_ttl_minutes=15, credential_validity_days=30)
    policy = resolve_identity_policy(
        settings, {"identity.link_ttl_minutes": "45", "identity.validity_days": "10"}
    )
    assert policy.link_ttl_minutes == 45
    assert policy.validity_days == 10


@pytest.mark.parametrize("value", ["abc", "0", "1441", "12.5", ""])
def test_identity_policy_invalid_override_is_discarded(value, caplog):
    """R49: un valor inválido o fuera de rango se descarta con log."""
    caplog.set_level(logging.WARNING)
    settings = Settings(identity_link_ttl_minutes=15)
    policy = resolve_identity_policy(
        settings, {"identity.link_ttl_minutes": value}
    )
    assert policy.link_ttl_minutes == 15
    assert "identity_setting_invalid" in caplog.text
