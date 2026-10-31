"""Errores y lógica pura del servicio telegram_gateway (sin IO)."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Callable

from lazaro_contracts import MessageRequest

if TYPE_CHECKING:
    from .adapters.dedup import DedupStore
    from .adapters.orchestrator import OrchestratorClient
    from .adapters.telegram import TelegramClient


class DomainError(Exception):
    """Base de los errores de negocio; cada subclase fija su código y su HTTP status."""

    code = "domain_error"
    status_code = 400


class TelegramError(DomainError):
    code = "telegram_error"
    status_code = 502


class OrchestratorError(Exception):
    """Fallo al llamar al orquestador; el webhook la captura y no llega al cliente."""


@dataclass(frozen=True)
class IncomingUpdate:
    update_id: int
    chat_id: int
    user_id: int
    text: str | None


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class Adapters:
    telegram: "TelegramClient"
    dedup: "DedupStore"
    orchestrator: "OrchestratorClient"
    clock: Callable[[], datetime] = field(default=_utcnow)


def _as_int(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def extract_incoming(update: dict) -> IncomingUpdate | None:
    """Devuelve None si el update no trae `message`. `text` vacío o en blanco -> None."""
    message = update.get("message")
    if not isinstance(message, dict):
        return None
    chat = message.get("chat") if isinstance(message.get("chat"), dict) else {}
    sender = message.get("from") if isinstance(message.get("from"), dict) else {}
    chat_id = _as_int(chat.get("id"))
    if chat_id is None:
        return None
    user_id = _as_int(sender.get("id"))
    text = message.get("text")
    if not isinstance(text, str) or not text.strip():
        text = None
    return IncomingUpdate(
        update_id=update["update_id"],
        chat_id=chat_id,
        user_id=user_id if user_id is not None else chat_id,
        text=text,
    )


def build_message_request(incoming: IncomingUpdate, now: datetime) -> MessageRequest:
    return MessageRequest(
        update_id=incoming.update_id,
        telegram_user_id=incoming.user_id,
        chat_id=incoming.chat_id,
        text=incoming.text or "",
        received_at=now,
    )
