"""Lógica pura de identidad: firma de enlaces, estados de credencial y política (R3, R45, R49)."""
from __future__ import annotations

import hashlib
import hmac
import logging
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal

from .classifier import normalize_text
from .config import Settings

logger = logging.getLogger(__name__)

LINK_PREFIX = "login-link:v1:"

CredentialStatus = Literal["vigente", "por_vencer", "vencida", "revocada", "no_iniciada"]


def sign_login_token(key: str) -> str:
    """R3: `<nonce>.<hmac_sha256>` con nonce de `secrets.token_urlsafe(32)`."""
    nonce = secrets.token_urlsafe(32)
    signature = hmac.new(
        key.encode("utf-8"), f"{LINK_PREFIX}{nonce}".encode("utf-8"), hashlib.sha256
    ).hexdigest()
    return f"{nonce}.{signature}"


def verify_login_token_signature(token: str, key: str) -> bool:
    """R13: comprobación barata de la firma antes de tocar el repositorio."""
    if not token or not key or "." not in token:
        return False
    nonce, signature = token.rsplit(".", 1)
    if not nonce or not signature:
        return False
    expected = hmac.new(
        key.encode("utf-8"), f"{LINK_PREFIX}{nonce}".encode("utf-8"), hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(signature, expected)


def credential_status(
    valid_from: datetime,
    valid_until: datetime,
    revoked_at: datetime | None,
    now: datetime,
    notice_days: int,
) -> CredentialStatus:
    """R45: estado calculado, nunca almacenado como contador."""
    if revoked_at is not None:
        return "revocada"
    if now < valid_from:
        return "no_iniciada"
    if now >= valid_until:
        return "vencida"
    if valid_until - now <= timedelta(days=notice_days):
        return "por_vencer"
    return "vigente"


def credential_allows_access(status: CredentialStatus) -> bool:
    """R34, R36: solo vigente y por_vencer habilitan el acceso."""
    return status in ("vigente", "por_vencer")


def days_remaining(valid_until: datetime, now: datetime) -> int:
    """R45: días naturales restantes, nunca negativos."""
    return max(0, (valid_until.date() - now.date()).days)


def is_logout_command(text: str, commands: tuple[str, ...]) -> bool:
    """R29: igualdad exacta normalizada; `/cerrar 12` no es un cierre de sesión."""
    normalized = normalize_text(text)
    return any(normalized == normalize_text(command) for command in commands if command)


@dataclass(frozen=True)
class IdentityPolicy:
    link_ttl_minutes: int
    session_idle_minutes: int
    login_max_attempts: int
    lockout_minutes: int
    validity_days: int
    expiry_notice_days: int


POLICY_FIELDS: dict[str, tuple[str, int, int]] = {
    "identity.link_ttl_minutes": ("link_ttl_minutes", 1, 1440),
    "identity.session_idle_minutes": ("session_idle_minutes", 5, 1440),
    "identity.login_max_attempts": ("login_max_attempts", 1, 100),
    "identity.lockout_minutes": ("lockout_minutes", 1, 1440),
    "identity.validity_days": ("validity_days", 1, 366),
    "identity.expiry_notice_days": ("expiry_notice_days", 0, 60),
}

# Alias privado conservado por compatibilidad con #38.
_POLICY_FIELDS = POLICY_FIELDS


def _default_policy(settings: Settings) -> dict[str, int]:
    return {
        "link_ttl_minutes": settings.identity_link_ttl_minutes,
        "session_idle_minutes": settings.identity_session_idle_minutes,
        "login_max_attempts": settings.identity_login_max_attempts,
        "lockout_minutes": settings.identity_lockout_minutes,
        "validity_days": settings.credential_validity_days,
        "expiry_notice_days": settings.credential_expiry_notice_days,
    }


def resolve_identity_policy(
    settings: Settings, overrides: dict[str, str]
) -> IdentityPolicy:
    """R49: `app_settings` válido gana; un valor inválido se descarta y se registra."""
    values = _default_policy(settings)
    for key, raw in overrides.items():
        spec = POLICY_FIELDS.get(key)
        if spec is None:
            continue
        field, minimum, maximum = spec
        try:
            parsed = int(raw)
        except (TypeError, ValueError):
            logger.warning("identity_setting_invalid key=%s", key)
            continue
        if parsed < minimum or parsed > maximum:
            logger.warning("identity_setting_invalid key=%s", key)
            continue
        values[field] = parsed
    return IdentityPolicy(**values)
