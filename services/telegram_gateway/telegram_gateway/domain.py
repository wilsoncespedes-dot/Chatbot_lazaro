"""Errores y lógica pura del servicio telegram_gateway (sin IO)."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any, Callable, Sequence

from lazaro_contracts import (
    MAX_TEXT_LENGTH,
    DeliveryStatus,
    MessageRequest,
    NormalizedMessage,
    ResponseBlock,
    TemplateBlock,
)

if TYPE_CHECKING:
    from .adapters.dedup import DedupStore
    from .adapters.message_buffer import MessageBuffer
    from .adapters.orchestrator import OrchestratorClient
    from .adapters.telegram import TelegramClient
    from .adapters.whatsapp import ChannelAdapter
    from .adapters.whatsapp_window import WhatsAppWindowStore


class DomainError(Exception):
    """Base de los errores de negocio; cada subclase fija su código y su HTTP status."""

    code = "domain_error"
    status_code = 400


class TelegramError(DomainError):
    code = "telegram_error"
    status_code = 502


class ChannelWindowClosed(DomainError):
    code = "validation_error"
    status_code = 422


class TemplateNotApproved(DomainError):
    code = "validation_error"
    status_code = 422


class ChannelSendFailed(DomainError):
    code = "upstream_error"
    status_code = 502


class ChannelNotConfigured(DomainError):
    code = "upstream_error"
    status_code = 502


class WebhookForbidden(DomainError):
    code = "forbidden"
    status_code = 403


class OrchestratorError(Exception):
    """Fallo al llamar al orquestador; el webhook la captura y no llega al cliente."""


@dataclass(frozen=True)
class IncomingUpdate:
    update_id: int
    chat_id: int
    user_id: int
    text: str | None


@dataclass(frozen=True)
class IncomingCallback:
    """`callback_query` de Telegram ya extraído, sin IO (R38)."""

    update_id: int
    chat_id: int
    user_id: int
    callback_id: str
    button_id: str
    button_proof: str | None


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class Adapters:
    telegram: "TelegramClient"
    dedup: "DedupStore"
    orchestrator: "OrchestratorClient"
    clock: Callable[[], datetime] = field(default=_utcnow)
    buffer: "MessageBuffer | None" = None
    whatsapp: "ChannelAdapter | None" = None
    whatsapp_window: "WhatsAppWindowStore | None" = None


@dataclass(frozen=True)
class BufferedMessage:
    update_id: int
    user_id: int
    text: str
    received_at: datetime


@dataclass(frozen=True)
class ClaimedGroup:
    chat_id: int
    claim_id: str
    attempts: int
    messages: tuple[BufferedMessage, ...]


def _normalize_text(text: str) -> str:
    return " ".join(text.split()).casefold()


def is_immediate(text: str, accept_phrase: str) -> bool:
    """R13, R14: comandos y la frase de aceptación no se agrupan."""
    if text.strip().startswith("/"):
        return True
    if not accept_phrase.strip():
        return False
    return _normalize_text(text) == _normalize_text(accept_phrase)


def compute_due(
    first: datetime, last: datetime, window: float, max_wait: float
) -> datetime:
    """R5: vence al cerrar la ventana, sin superar el tope desde el primer mensaje."""
    return min(last + timedelta(seconds=window), first + timedelta(seconds=max_wait))


def must_flush_before(
    pending: Sequence[BufferedMessage], new: BufferedMessage, max_messages: int
) -> bool:
    """R9: otro usuario o desborde de tamaño obliga a enviar el buffer pendiente."""
    if not pending:
        return False
    if any(message.user_id != new.user_id for message in pending):
        return True
    if len(pending) >= max_messages:
        return True
    texts = [message.text for message in pending] + [new.text]
    return len("\n".join(texts)) > MAX_TEXT_LENGTH


def build_group_request(chat_id: int, messages: Sequence[BufferedMessage]) -> MessageRequest:
    """R6, R7: un único mensaje con los textos ordenados por update_id."""
    ordered = sorted(messages, key=lambda message: message.update_id)
    return MessageRequest(
        update_id=ordered[0].update_id,
        telegram_user_id=ordered[0].user_id,
        chat_id=chat_id,
        text="\n".join(message.text for message in ordered),
        received_at=ordered[-1].received_at,
    )


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


def extract_callback(update: dict) -> IncomingCallback | None:
    """R38: acepta `callback_query` con datos canónicos y prueba del aviso.

    Devuelve None para cualquier callback sin `data`, sin chat o sin receptor;
    el webhook responde 200 sin reenviarlo.
    """
    callback = update.get("callback_query")
    if not isinstance(callback, dict):
        return None
    data = callback.get("data")
    if not isinstance(data, str) or not data.strip():
        return None
    button_id, separator, proof = data.partition(":")
    if not button_id.strip():
        return None
    message = callback.get("message") if isinstance(callback.get("message"), dict) else {}
    chat = message.get("chat") if isinstance(message.get("chat"), dict) else {}
    sender = callback.get("from") if isinstance(callback.get("from"), dict) else {}
    chat_id = _as_int(chat.get("id"))
    user_id = _as_int(sender.get("id"))
    if chat_id is None and user_id is None:
        return None
    if chat_id is None:
        chat_id = user_id
    if user_id is None:
        user_id = chat_id
    callback_id = callback.get("id")
    if not isinstance(callback_id, str) or not callback_id.strip():
        callback_id = str(update["update_id"])
    return IncomingCallback(
        update_id=update["update_id"],
        chat_id=chat_id,
        user_id=user_id,
        callback_id=callback_id,
        button_id=button_id.strip(),
        button_proof=proof.strip() if separator and proof.strip() else None,
    )


def normalize_callback(
    callback: IncomingCallback, received_at: datetime
) -> NormalizedMessage:
    """R38: convierte el callback en el botón canónico del modelo común."""
    return NormalizedMessage(
        channel="telegram",
        external_user_id=str(callback.user_id),
        external_chat_id=str(callback.chat_id),
        external_message_id=callback.callback_id,
        kind="button",
        button_id=callback.button_id,
        button_proof=callback.button_proof,
        received_at=received_at,
    )


def build_message_request(incoming: IncomingUpdate, now: datetime) -> MessageRequest:
    return MessageRequest(
        update_id=incoming.update_id,
        telegram_user_id=incoming.user_id,
        chat_id=incoming.chat_id,
        text=incoming.text or "",
        received_at=now,
    )


def normalize_incoming(
    incoming: IncomingUpdate, received_at: datetime
) -> NormalizedMessage:
    """R1, R3: traduce el update Telegram al mensaje común sin perder el payload legacy."""
    return NormalizedMessage(
        channel="telegram",
        external_user_id=str(incoming.user_id),
        external_chat_id=str(incoming.chat_id),
        external_message_id=str(incoming.update_id),
        kind="text" if incoming.text is not None else "unsupported",
        text=incoming.text,
        received_at=received_at,
    )


def send_response(
    adapter: "ChannelAdapter",
    destination: str,
    blocks: Sequence[ResponseBlock],
) -> DeliveryStatus:
    """R7-R9: consulta las capacidades del canal antes de enviar y falla cerrado."""
    block_list = list(blocks)
    if not block_list:
        raise ValueError("la respuesta no tiene bloques")
    capabilities_for = getattr(adapter, "capabilities_for", None)
    capabilities = (
        capabilities_for(destination)
        if callable(capabilities_for)
        else adapter.capabilities()
    )
    has_free_text = any(not isinstance(block, TemplateBlock) for block in block_list)
    if has_free_text and not capabilities.free_text_allowed:
        raise ChannelWindowClosed(
            "La ventana de atención está cerrada; solo se pueden enviar plantillas."
        )
    if capabilities.requires_template and has_free_text:
        raise ChannelWindowClosed(
            "Este canal exige una plantilla y la respuesta usa texto libre."
        )
    return adapter.send(destination, block_list)
