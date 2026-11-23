"""Errores y lógica pura del servicio telegram_gateway (sin IO)."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any, Callable, Mapping, Sequence

from lazaro_contracts import (
    MAX_TEXT_LENGTH,
    ChannelCapabilities,
    DeliveryStatus,
    ImageBlock,
    LinkBlock,
    ListBlock,
    MessageRequest,
    NormalizedMessage,
    OptionsBlock,
    ResponseBlock,
    TemplateBlock,
    TextBlock,
)

if TYPE_CHECKING:
    from .adapters.callback import CallbackClient
    from .adapters.dedup import DedupStore
    from .adapters.message_buffer import MessageBuffer
    from .adapters.orchestrator import OrchestratorClient
    from .adapters.telegram import TelegramClient
    from .adapters.whatsapp import ChannelAdapter
    from .adapters.whatsapp_window import WhatsAppWindowStore
    from .adapters.channel_repository import ChannelRepository
    from .adapters.mailbox import MailboxRepository
    from .adapters.inbound_retry import InboundRetryStore
    from .registry import ChannelRegistry
    from .ports.canal import Canal


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


class UnknownChannel(DomainError):
    """Canal que no está registrado en este gateway."""

    code = "validation_error"
    status_code = 422


class ChannelNotFound(DomainError):
    """No existe una fila de canal para el id solicitado."""

    code = "not_found"
    status_code = 404


class ChannelInactive(DomainError):
    code = "channel_inactive"
    status_code = 422


class ChannelAlreadyExists(DomainError):
    code = "channel_exists"
    status_code = 409


class ChannelManagedByEnvironment(DomainError):
    code = "channel_managed_by_environment"
    status_code = 409


class ChannelSecretsUnavailable(DomainError):
    code = "channel_secrets_unavailable"
    status_code = 503


class ChannelStoreUnavailable(DomainError):
    code = "channel_store_unavailable"
    status_code = 503


class UnsupportedBlock(DomainError):
    """#60: bloque que el canal no admite; #61 lo sustituye por degradación."""

    code = "validation_error"
    status_code = 422


class PayloadTooLarge(DomainError):
    """#62: el cuerpo del webhook supera el límite configurado."""

    code = "payload_too_large"
    status_code = 413


class WebhookUnauthorized(DomainError):
    """#62: firma ausente/incorrecta o timestamp fuera de la ventana."""

    code = "unauthorized"
    status_code = 401


class InvalidWebhookPayload(DomainError):
    """#62: el cuerpo del webhook no cumple el contrato del canal."""

    code = "validation_error"
    status_code = 422


class InvalidChannelConfig(DomainError):
    """#62: la configuración del canal no es válida y no se persiste."""

    code = "validation_error"
    status_code = 422


class OrchestratorError(Exception):
    """Fallo al llamar al orquestador; el webhook la captura y no llega al cliente.

    `retryable=False` indica que el orquestador rechazó el contenido (400/413/422):
    reenviarlo no cambiaría el resultado, así que no va a la cola de reintento.
    """

    def __init__(self, message: str = "", *, retryable: bool = True) -> None:
        super().__init__(message)
        self.retryable = retryable


class InboundUnavailable(DomainError):
    """Fase 2: ni el orquestador ni la cola de reintento aceptaron el mensaje.

    El webhook responde 503 para que el canal lo reenvíe más tarde.
    """

    code = "service_unavailable"
    status_code = 503


class CallbackNetworkError(Exception):
    """#62: fallo de red o de tiempo de espera en el callback saliente."""


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


@dataclass(frozen=True)
class ChannelRecord:
    id: str
    name: str
    adapter_type: str
    icon: str
    color: str
    config: Mapping[str, Any]
    active: bool
    created_at: datetime
    has_secrets: bool
    active_follows_environment: bool
    # #66: pista pública de cada credencial (`…` + últimos 4); nunca el valor.
    credential_hints: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class ChannelSecrets:
    secret: str | None = field(default=None, repr=False)
    credentials: Mapping[str, str] = field(default_factory=dict, repr=False)


@dataclass(frozen=True)
class ChannelSeed:
    id: str
    name: str
    adapter_type: str
    icon: str
    color: str
    config: Mapping[str, Any] = field(default_factory=dict)


BUILTIN_CHANNEL_SEEDS: tuple[ChannelSeed, ...] = (
    ChannelSeed(
        "telegram", "Telegram", "telegram", "telegram", "#1B6FA8",
        {"consent_mode": "texto"},
    ),
    ChannelSeed(
        "whatsapp", "WhatsApp", "whatsapp_cloud", "whatsapp", "#0E7A5F",
        {"consent_mode": "boton"},
    ),
)


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
    channels: "ChannelRepository | None" = None
    channel_registry: "ChannelRegistry | None" = None
    callback: "CallbackClient | None" = None
    mailbox: "MailboxRepository | None" = None
    inbound_retry: "InboundRetryStore | None" = None


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


def is_immediate(text: str, accept_phrase: str, reject_phrase: str = "") -> bool:
    """R13, R14, R46 R31: comandos y frases de decisión no se agrupan."""
    if text.strip().startswith("/"):
        return True
    normalized = _normalize_text(text)
    for phrase in (accept_phrase, reject_phrase):
        if phrase.strip() and normalized == _normalize_text(phrase):
            return True
    return False


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


def extract_callback_query_id(update: dict) -> str | None:
    """R7: id real de `callback_query` para confirmarlo; nunca uno sintético."""
    callback = update.get("callback_query")
    if not isinstance(callback, dict):
        return None
    callback_query_id = callback.get("id")
    if not isinstance(callback_query_id, str) or not callback_query_id.strip():
        return None
    return callback_query_id


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
    """Degrada según capacidades y luego envía por el adaptador legado."""
    capabilities_for = getattr(adapter, "capabilities_for", None)
    capabilities = (
        capabilities_for(destination)
        if callable(capabilities_for)
        else adapter.capabilities()
    )
    prepared = prepare_blocks(blocks, capabilities)
    return adapter.send(destination, prepared)


def degrade_blocks(
    blocks: Sequence[ResponseBlock], capabilities: ChannelCapabilities
) -> list[ResponseBlock]:
    """Adapta bloques que el canal no puede representar, sin IO ni mutación."""
    degraded: list[ResponseBlock] = []
    for block in blocks:
        if isinstance(block, OptionsBlock) and (
            not capabilities.supports_buttons
            or len(block.options) > capabilities.max_options
        ):
            text = "\n".join(
                f"{index}. {option}"
                for index, option in enumerate(block.options, start=1)
            )
            degraded.append(TextBlock(type="text", text=text))
        elif isinstance(block, ListBlock) and (
            len(block.options) < capabilities.min_list_options
            or len(block.options) > capabilities.max_list_options
        ):
            text = "\n".join(
                f"{index}. {option}"
                for index, option in enumerate(block.options, start=1)
            )
            degraded.append(TextBlock(type="text", text=text))
        elif isinstance(block, ImageBlock) and not capabilities.supports_images:
            if capabilities.supports_links:
                degraded.append(
                    LinkBlock(type="link", text=block.alt_text, url=block.url)
                )
            else:
                degraded.append(
                    TextBlock(type="text", text=f"{block.alt_text}: {block.url}")
                )
        elif isinstance(block, LinkBlock) and not capabilities.supports_links:
            combined = f"{block.text}: {block.url}"
            if len(combined) <= MAX_TEXT_LENGTH:
                degraded.append(TextBlock(type="text", text=combined))
            else:
                degraded.extend(
                    (
                        TextBlock(type="text", text=block.text),
                        TextBlock(type="text", text=block.url),
                    )
                )
        else:
            degraded.append(block)
    return degraded


def prepare_blocks(
    blocks: Sequence[ResponseBlock], capabilities: ChannelCapabilities
) -> list[ResponseBlock]:
    """Degrada primero y después aplica las restricciones de ventana/plantilla."""
    block_list = degrade_blocks(blocks, capabilities)
    if not block_list:
        raise ValueError("la respuesta no tiene bloques")
    has_free_text = any(not isinstance(block, TemplateBlock) for block in block_list)
    if has_free_text and not capabilities.free_text_allowed:
        raise ChannelWindowClosed(
            "La ventana de atención está cerrada; solo se pueden enviar plantillas."
        )
    if capabilities.requires_template and has_free_text:
        raise ChannelWindowClosed(
            "Este canal exige una plantilla y la respuesta usa texto libre."
        )
    return block_list


def send_through_channel(
    channel: "Canal",
    destination: str,
    blocks: Sequence[ResponseBlock],
) -> DeliveryStatus:
    """Degrada y envía por el puerto de canal."""
    prepared = prepare_blocks(blocks, channel.capacidades(destination))
    return channel.enviar_mensaje(destination, prepared)
