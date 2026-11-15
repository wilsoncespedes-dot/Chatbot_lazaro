"""Lógica pura del segundo factor del panel: TOTP, cifrado y códigos de recuperación."""
from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import struct
from datetime import datetime
from urllib.parse import quote

TOTP_DIGITS = 6
TOTP_PERIOD_SECONDS = 30
SECRET_BYTES = 20
RECOVERY_BYTES = 10
RECOVERY_ALPHABET = frozenset("abcdefghijklmnopqrstuvwxyz234567")


def generate_secret() -> bytes:
    """R5: 160 bits aleatorios para el secreto TOTP."""
    return secrets.token_bytes(SECRET_BYTES)


def totp_at(secret: bytes, step: int, digits: int = TOTP_DIGITS) -> str:
    """R1: código RFC 6238 (HMAC-SHA1, contador de 30 s)."""
    counter = struct.pack(">Q", step)
    digest = hmac.new(secret, counter, hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    value = struct.unpack(">I", digest[offset:offset + 4])[0] & 0x7FFFFFFF
    return str(value % (10 ** digits)).zfill(digits)


def _step_at(now: datetime) -> int:
    return int(now.timestamp()) // TOTP_PERIOD_SECONDS


def verify_totp(
    secret: bytes, code: str, now: datetime, window: int
) -> int | None:
    """R2, R3, R4: devuelve el paso coincidente dentro de ±window o None."""
    if not isinstance(code, str):
        return None
    candidate = code.strip()
    if len(candidate) != TOTP_DIGITS or not candidate.isascii() or not candidate.isdigit():
        return None
    base = _step_at(now)
    offsets = [0]
    for distance in range(1, window + 1):
        offsets.extend((-distance, distance))
    for offset in offsets:
        step = base + offset
        if step < 0:
            continue
        if hmac.compare_digest(totp_at(secret, step), candidate):
            return step
    return None


def secret_base32(secret: bytes) -> str:
    return base64.b32encode(secret).decode("ascii").rstrip("=")


def provisioning_uri(secret: bytes, account: str, issuer: str) -> str:
    """R5: URI `otpauth://totp/` con emisor y cuenta escapados."""
    label = f"{quote(issuer, safe='')}:{quote(account, safe='')}"
    query = f"secret={secret_base32(secret)}&issuer={quote(issuer, safe='')}"
    return f"otpauth://totp/{label}?{query}"


def encrypt_secret(secret: bytes, key: str) -> str:
    """R27: cifra con Fernet; la clave es la única fuente de confianza."""
    from cryptography.fernet import Fernet

    from .domain import TwoFactorUnavailable

    try:
        token = Fernet(key.strip().encode("ascii")).encrypt(secret)
    except Exception:
        raise TwoFactorUnavailable("El segundo factor no está disponible.") from None
    return token.decode("ascii")


def decrypt_secret(ciphertext: str, key: str) -> bytes:
    """R27: descifra o falla cerrado sin revelar la clave ni el contenido."""
    from cryptography.fernet import Fernet

    from .domain import TwoFactorUnavailable

    if not key.strip():
        raise TwoFactorUnavailable("El segundo factor no está disponible.")
    try:
        return Fernet(key.strip().encode("ascii")).decrypt(
            ciphertext.encode("ascii")
        )
    except Exception:
        raise TwoFactorUnavailable("El segundo factor no está disponible.") from None


def generate_recovery_codes(count: int) -> list[str]:
    """R31: `count` códigos de 80 bits con formato `xxxx-xxxx-xxxx-xxxx`."""
    codes: list[str] = []
    while len(codes) < count:
        raw = base64.b32encode(secrets.token_bytes(RECOVERY_BYTES))
        text = raw.decode("ascii").rstrip("=").lower()
        if len(text) != 16:
            continue
        code = "-".join(text[index:index + 4] for index in range(0, 16, 4))
        if code not in codes:
            codes.append(code)
    return codes


def normalize_recovery_code(raw: str) -> str:
    """R34: ignora mayúsculas, espacios y guiones."""
    if not isinstance(raw, str):
        return ""
    return "".join(
        character
        for character in raw.lower()
        if not character.isspace() and character != "-"
    )


def hash_recovery_code(raw: str) -> str:
    """R31: guarda solo el SHA-256 hexadecimal del código normalizado."""
    return hashlib.sha256(normalize_recovery_code(raw).encode("ascii")).hexdigest()


def looks_like_recovery_code(raw: str) -> bool:
    normalized = normalize_recovery_code(raw)
    return len(normalized) == 16 and set(normalized) <= RECOVERY_ALPHABET
