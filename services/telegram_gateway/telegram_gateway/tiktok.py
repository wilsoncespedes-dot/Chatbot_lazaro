"""Fase 6: lógica pura del canal TikTok Business Messaging.

La cabecera, firma, eventos, formato del webhook, OAuth y envío siguen la
documentación oficial de TikTok API for Business. El evento europeo
`im_receive_msg_eu` no incluye datos suficientes para identificar ni responder
al remitente; se ignora de forma segura.

Forma asumida del webhook (POST con JSON):

    {"client_key": "...", "event": "im_receive_msg", "create_time": 1700000000,
     "user_openid": "<cuenta de empresa>",
     "content": "{\"message_id\": \"m1\", \"conversation_id\": \"c1\",
                  \"from_user_id\": \"u1\", \"message_type\": \"text\",
                  \"text\": \"Hola\"}"}
"""
from __future__ import annotations

import hashlib
import hmac
import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from lazaro_contracts import MAX_TEXT_LENGTH, ChannelCapabilities, NormalizedMessage
from pydantic import ValidationError

CHANNEL_ID = "tiktok"
SIGNATURE_HEADER = "TikTok-Signature"
SIGNATURE_TOLERANCE_SECONDS = 300
# `im_receive_msg_eu` no incluye remitente, id ni contenido en el esquema público;
# no se puede normalizar de forma segura y se ignora.
MESSAGE_EVENTS: frozenset[str] = frozenset({"im_receive_msg"})
MAX_TIKTOK_TEXT = 6000

TIKTOK_CAPABILITIES = ChannelCapabilities(
    free_text_allowed=True,
    max_options=0,
    min_list_options=0,
    max_list_options=0,
    supports_links=True,
    requires_template=False,
    supports_buttons=False,
    supports_images=False,
    supports_files=False,
    supports_audio=False,
)


def header_value(headers: Mapping[str, str], name: str) -> str | None:
    """Cabecera sin distinguir mayúsculas (los dobles de test usan `dict`)."""
    value = headers.get(name)
    if value is not None:
        return value
    lowered = name.lower()
    for key, candidate in headers.items():
        if key.lower() == lowered:
            return candidate
    return None


def tiktok_signature(secret: str, timestamp: int, body: bytes) -> str:
    message = f"{int(timestamp)}.".encode("utf-8") + body
    return hmac.new(secret.encode("utf-8"), message, hashlib.sha256).hexdigest()


def verify_tiktok_signature(
    secret: str,
    body: bytes,
    header: str | None,
    now: datetime,
    tolerance_seconds: int = SIGNATURE_TOLERANCE_SECONDS,
) -> bool:
    """HMAC-SHA256 de `<t>.<cuerpo>` con el secreto, en ventana anti-repetición.

    PENDIENTE: confirmar con la doc oficial de TikTok Business Messaging el nombre
    exacto de la cabecera (`TikTok-Signature`), el formato `t=<unix>,s=<hex>`, el
    mensaje firmado (`<t>.<cuerpo crudo>`) y qué secreto firma (se asume el
    `client_secret` de la app, configurado como `TIKTOK_WEBHOOK_SECRET`). No se ha
    probado contra TikTok real. Sin secreto se rechaza todo.
    """
    if not secret or not header:
        return False
    parts: dict[str, str] = {}
    for item in header.split(","):
        key, sep, value = item.strip().partition("=")
        if not sep or key in parts:
            return False
        parts[key] = value
    timestamp_raw = parts.get("t", "")
    received = parts.get("s", "").lower()
    if not timestamp_raw.isdigit() or len(timestamp_raw) > 12 or not received:
        return False
    timestamp = int(timestamp_raw)
    if abs(now.timestamp() - timestamp) > tolerance_seconds:
        return False
    expected = tiktok_signature(secret, timestamp, body)
    return hmac.compare_digest(received, expected)


def _as_id(value: Any) -> str | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (str, int)):
        text = str(value).strip()
        return text or None
    return None


def _content(payload: Mapping[str, Any]) -> dict | None:
    raw = payload.get("content")
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            return None
    return raw if isinstance(raw, dict) else None


def _text(content: Mapping[str, Any]) -> str | None:
    value = content.get("text")
    if isinstance(value, Mapping):
        value = value.get("body")
    if isinstance(value, str) and value.strip() and len(value) <= MAX_TEXT_LENGTH:
        return value
    return None


def parse_tiktok_webhook(
    payload: Mapping[str, Any], business_id: str, received_at: datetime
) -> list[NormalizedMessage]:
    """R2-R4: evento de mensaje entrante oficial → `NormalizedMessage`."""
    if payload.get("event") not in MESSAGE_EVENTS:
        return []
    if payload.get("user_openid") != business_id:
        return []
    content = _content(payload)
    if content is None:
        return []
    message_id = _as_id(content.get("message_id"))
    sender = _as_id(content.get("unique_identifier"))
    sender_info = content.get("from_user")
    if isinstance(sender_info, Mapping):
        if sender_info.get("role") == "business_account":
            return []
        sender = sender or _as_id(sender_info.get("id"))
    if message_id is None or sender is None:
        return []
    if content.get("is_echo") is True or sender == business_id:
        return []
    chat = _as_id(content.get("conversation_id")) or sender
    message_type = str(content.get("type") or content.get("message_type") or "text").lower()
    text = _text(content) if message_type == "text" else None
    try:
        if text is not None:
            message = NormalizedMessage(
                channel=CHANNEL_ID,
                external_user_id=sender,
                external_chat_id=chat,
                external_message_id=message_id,
                kind="text",
                text=text,
                received_at=received_at,
            )
        else:
            message = NormalizedMessage(
                channel=CHANNEL_ID,
                external_user_id=sender,
                external_chat_id=chat,
                external_message_id=message_id,
                kind="unsupported",
                received_at=received_at,
            )
    except ValidationError:
        return []
    return [message]


def build_text_payload(business_id: str, destination: str, text: str) -> dict:
    """Cuerpo oficial de envío de texto al conversation_id."""
    return {
        "business_id": business_id,
        "recipient_type": "CONVERSATION",
        "recipient": destination,
        "message_type": "TEXT",
        "text": {"body": text},
    }


def split_text(text: str, limit: int = MAX_TIKTOK_TEXT) -> list[str]:
    stripped = text.strip()
    if not stripped:
        return []
    return [stripped[index : index + limit] for index in range(0, len(stripped), limit)]


# ── tokens OAuth ───────────────────────────────────────────────────────────

_ACCESS = "access_token"
_REFRESH = "refresh_token"
_ACCESS_EXPIRES = "access_expires_at"
_REFRESH_EXPIRES = "refresh_expires_at"


@dataclass(frozen=True)
class TikTokTokens:
    access_token: str
    refresh_token: str
    access_expires_at: datetime
    refresh_expires_at: datetime | None = None

    def __repr__(self) -> str:  # nunca los valores en logs
        return f"TikTokTokens(access_expires_at={self.access_expires_at.isoformat()})"

    def expires_soon(self, now: datetime, margin_seconds: int) -> bool:
        return self.access_expires_at - timedelta(seconds=margin_seconds) <= now

    def as_credentials(self) -> dict[str, str]:
        values = {
            _ACCESS: self.access_token,
            _REFRESH: self.refresh_token,
            _ACCESS_EXPIRES: str(int(self.access_expires_at.timestamp())),
        }
        if self.refresh_expires_at is not None:
            values[_REFRESH_EXPIRES] = str(int(self.refresh_expires_at.timestamp()))
        return values

    @classmethod
    def from_credentials(cls, credentials: Mapping[str, str]) -> "TikTokTokens | None":
        access = credentials.get(_ACCESS, "")
        refresh = credentials.get(_REFRESH, "")
        expires = credentials.get(_ACCESS_EXPIRES, "")
        if not access or not refresh or not expires.isdigit():
            return None
        refresh_expires = credentials.get(_REFRESH_EXPIRES, "")
        return cls(
            access_token=access,
            refresh_token=refresh,
            access_expires_at=datetime.fromtimestamp(int(expires), timezone.utc),
            refresh_expires_at=(
                datetime.fromtimestamp(int(refresh_expires), timezone.utc)
                if refresh_expires.isdigit()
                else None
            ),
        )


class TikTokTokenInvalid(ValueError):
    """La respuesta de refresco no trae los campos esperados."""


def tokens_from_refresh(
    body: Mapping[str, Any], previous_refresh_token: str, now: datetime
) -> TikTokTokens:
    """Respuesta de `/tt_user/oauth2/refresh_token/` → tokens rotados."""
    code = body.get("code")
    if isinstance(code, int) and not isinstance(code, bool) and code != 0:
        raise TikTokTokenInvalid("TikTok rechazó el refresh token")
    data = body.get("data") if isinstance(body.get("data"), Mapping) else body
    access = data.get("access_token")
    expires_in = data.get("expires_in")
    if not isinstance(access, str) or not access:
        raise TikTokTokenInvalid("falta access_token")
    if isinstance(expires_in, bool) or not isinstance(expires_in, int) or expires_in <= 0:
        raise TikTokTokenInvalid("expires_in no es válido")
    refresh = data.get("refresh_token")
    refresh_in = data.get("refresh_token_expires_in")
    return TikTokTokens(
        access_token=access,
        refresh_token=refresh if isinstance(refresh, str) and refresh else previous_refresh_token,
        access_expires_at=now + timedelta(seconds=expires_in),
        refresh_expires_at=(
            now + timedelta(seconds=refresh_in)
            if (
                isinstance(refresh_in, int)
                and not isinstance(refresh_in, bool)
                and refresh_in > 0
            )
            else None
        ),
    )
