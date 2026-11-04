"""Utilidades puras de cuentas: hash de contraseña, tokens de vínculo y /start."""
from __future__ import annotations

import hashlib
import hmac
import re
import secrets

PASSWORD_SCHEME = "pbkdf2_sha256"
SCRYPT_SCHEME = "scrypt"
SALT_BYTES = 16
SCRYPT_KEY_BYTES = 32
SCRYPT_MAXMEM = 64 * 1024 * 1024
ROLES = ("admin", "asesor", "cliente")
USERNAME_PATTERN = re.compile(r"^[a-z0-9_.-]{3,64}$")


def hash_password(password: str, iterations: int, salt: bytes | None = None) -> str:
    """PBKDF2-SHA256 con sal aleatoria; formato pbkdf2_sha256$<iter>$<sal>$<hash>."""
    raw_salt = secrets.token_bytes(SALT_BYTES) if salt is None else salt
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), raw_salt, iterations)
    return f"{PASSWORD_SCHEME}${iterations}${raw_salt.hex()}${digest.hex()}"


def hash_password_scrypt(
    password: str,
    n: int,
    r: int = 8,
    p: int = 1,
    salt: bytes | None = None,
) -> str:
    """R19: scrypt memory-hard con sal de 16 bytes y prefijo versionable."""
    raw_salt = secrets.token_bytes(SALT_BYTES) if salt is None else salt
    digest = hashlib.scrypt(
        password.encode("utf-8"),
        salt=raw_salt,
        n=n,
        r=r,
        p=p,
        maxmem=SCRYPT_MAXMEM,
        dklen=SCRYPT_KEY_BYTES,
    )
    return f"{SCRYPT_SCHEME}${n}${r}${p}${raw_salt.hex()}${digest.hex()}"


def _verify_scrypt(password: str, stored: str) -> bool:
    try:
        scheme, n_raw, r_raw, p_raw, salt_hex, digest_hex = stored.split("$")
        if scheme != SCRYPT_SCHEME:
            return False
        n, r, p = int(n_raw), int(r_raw), int(p_raw)
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(digest_hex)
    except (AttributeError, TypeError, ValueError):
        return False
    if n <= 0 or r <= 0 or p <= 0:
        return False
    try:
        digest = hashlib.scrypt(
            password.encode("utf-8"),
            salt=salt,
            n=n,
            r=r,
            p=p,
            maxmem=SCRYPT_MAXMEM,
            dklen=len(expected),
        )
    except (ValueError, OverflowError):
        return False
    return hmac.compare_digest(digest, expected)


def _verify_pbkdf2(password: str, stored: str) -> bool:
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


def verify_password(password: str, stored: str) -> bool:
    """R20: despacha por prefijo; los hashes PBKDF2 de #20 siguen válidos."""
    if not isinstance(stored, str):
        return False
    if stored.startswith(f"{SCRYPT_SCHEME}$"):
        return _verify_scrypt(password, stored)
    if stored.startswith(f"{PASSWORD_SCHEME}$"):
        return _verify_pbkdf2(password, stored)
    return False


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
