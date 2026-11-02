"""Utilidades puras de cuentas: hash de contraseña, tokens de vínculo y /start."""
from __future__ import annotations

import hashlib
import hmac
import re
import secrets

PASSWORD_SCHEME = "pbkdf2_sha256"
SALT_BYTES = 16
ROLES = ("admin", "asesor", "cliente")
USERNAME_PATTERN = re.compile(r"^[a-z0-9_.-]{3,64}$")


def hash_password(password: str, iterations: int, salt: bytes | None = None) -> str:
    """PBKDF2-SHA256 con sal aleatoria; formato pbkdf2_sha256$<iter>$<sal>$<hash>."""
    raw_salt = secrets.token_bytes(SALT_BYTES) if salt is None else salt
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), raw_salt, iterations)
    return f"{PASSWORD_SCHEME}${iterations}${raw_salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, iterations, salt_hex, digest_hex = stored.split("$")
        if scheme != PASSWORD_SCHEME:
            return False
        rounds = int(iterations)
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(digest_hex)
    except (AttributeError, TypeError, ValueError):
        return False
    if rounds <= 0:
        return False
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, rounds)
    return hmac.compare_digest(digest, expected)


def new_link_token() -> str:
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def parse_start_token(text: str) -> str | None:
    """Pura: "/start <token>" → token; cualquier otra forma → None."""
    parts = text.split()
    if len(parts) == 2 and parts[0] == "/start":
        return parts[1]
    return None
