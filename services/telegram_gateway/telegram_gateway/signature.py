"""Firma HMAC-SHA256 de los webhooks genéricos (módulo puro, sin IO)."""
from __future__ import annotations

import hashlib
import hmac
import re
from datetime import datetime, timezone

SIGNATURE_HEX_LENGTH = 64
_TIMESTAMP_PATTERN = re.compile(r"^[0-9]+$")


def sign_payload(secret: str, timestamp: int | str, body: bytes) -> str:
    """R3: HMAC-SHA256 hex de `<timestamp>.<cuerpo>` con la clave en UTF-8."""
    message = f"{timestamp}.".encode("utf-8") + body
    return hmac.new(secret.encode("utf-8"), message, hashlib.sha256).hexdigest()


def _now_timestamp(now: datetime) -> int:
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    return int(now.timestamp())


def verify_signature(
    secret: str,
    timestamp_header: str | None,
    signature_header: str | None,
    body: bytes,
    now: datetime,
    window_seconds: int,
) -> bool:
    """R4, R5: firma en tiempo constante dentro de la ventana anti-repetición."""
    if timestamp_header is None or signature_header is None:
        return False
    if len(signature_header) != SIGNATURE_HEX_LENGTH:
        return False
    if _TIMESTAMP_PATTERN.fullmatch(timestamp_header) is None:
        return False
    expected = sign_payload(secret, timestamp_header, body)
    try:
        matches = hmac.compare_digest(signature_header, expected)
    except TypeError:
        return False
    if not matches:
        return False
    return abs(_now_timestamp(now) - int(timestamp_header)) <= window_seconds
