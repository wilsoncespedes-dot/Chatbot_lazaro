"""Pruebas puras del TOTP, el cifrado y los códigos de recuperación (#54)."""
from __future__ import annotations

import base64
from datetime import datetime, timezone

import pytest

from orchestrator.two_factor import (
    decrypt_secret,
    encrypt_secret,
    generate_recovery_codes,
    generate_secret,
    hash_recovery_code,
    normalize_recovery_code,
    provisioning_uri,
    secret_base32,
    totp_at,
    verify_totp,
)

RFC_SECRET = b"12345678901234567890"
KEY = base64.urlsafe_b64encode(b"k" * 32).decode("ascii")


def _at(epoch: int) -> datetime:
    return datetime.fromtimestamp(epoch, tz=timezone.utc)


@pytest.mark.parametrize(
    ("epoch", "expected"),
    [
        (59, "94287082"),
        (1111111109, "07081804"),
        (1111111111, "14050471"),
        (1234567890, "89005924"),
        (2000000000, "69279037"),
        (20000000000, "65353130"),
    ],
)
def test_rfc6238_appendix_b_vectors(epoch, expected):
    """R1: los vectores del Apéndice B de RFC 6238 coinciden."""
    assert totp_at(RFC_SECRET, epoch // 30, digits=8) == expected


def test_window_accepts_previous_and_next_step():
    """R2: ±1 paso se acepta con la ventana por defecto."""
    now = _at(1_700_000_000)
    step = int(now.timestamp()) // 30
    assert verify_totp(RFC_SECRET, totp_at(RFC_SECRET, step - 1), now, 1) == step - 1
    assert verify_totp(RFC_SECRET, totp_at(RFC_SECRET, step + 1), now, 1) == step + 1


def test_outside_window_is_rejected():
    """R3: un paso fuera de la ventana no coincide."""
    now = _at(1_700_000_000)
    step = int(now.timestamp()) // 30
    assert verify_totp(RFC_SECRET, totp_at(RFC_SECRET, step - 2), now, 1) is None
    assert verify_totp(RFC_SECRET, totp_at(RFC_SECRET, step + 2), now, 1) is None


@pytest.mark.parametrize("code", ["", "12345", "1234567", "abcdef", "１２３４５６"])
def test_non_six_ascii_digits_are_rejected_without_exception(code):
    """R4: longitudes o caracteres no ASCII no lanzan excepción."""
    now = _at(1_700_000_000)
    assert verify_totp(RFC_SECRET, code, now, 1) is None


def test_encrypt_round_trip_and_ciphertext_hides_secret():
    """R27: Fernet descifra el mismo secreto y el texto cifrado no lo contiene."""
    secret = generate_secret()
    ciphertext = encrypt_secret(secret, KEY)
    assert decrypt_secret(ciphertext, KEY) == secret
    assert secret_base32(secret) not in ciphertext
    assert secret.hex() not in ciphertext


def test_recovery_codes_format_uniqueness_and_normalization():
    """R31, R34: formato, unicidad y comparación sin mayúsculas, espacios ni guiones."""
    codes = generate_recovery_codes(8)
    assert len(codes) == len(set(codes)) == 8
    for code in codes:
        groups = code.split("-")
        assert len(groups) == 4
        assert all(len(group) == 4 for group in groups)
        assert set("".join(groups)) <= set("abcdefghijklmnopqrstuvwxyz234567")
    first = codes[0]
    varied = f"  {first.upper()[:4]} {first[5:9]}-{first[10:]} "
    assert normalize_recovery_code(varied) == normalize_recovery_code(first)
    assert hash_recovery_code(varied) == hash_recovery_code(first)


def test_provisioning_uri_contains_issuer_and_secret():
    """R5: la URI otpauth lleva emisor, cuenta y secreto base32."""
    uri = provisioning_uri(RFC_SECRET, "ana", "Lazaro Software")
    assert uri.startswith("otpauth://totp/")
    assert "secret=" + secret_base32(RFC_SECRET) in uri
    assert "issuer=Lazaro%20Software" in uri
