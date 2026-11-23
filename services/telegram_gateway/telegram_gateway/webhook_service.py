"""Caso de uso del webhook común de canales (sin HTTP ni IO directa).

Todos los canales entran por aquí: Telegram y WhatsApp (con su verificación
propia y sus URLs históricas) y los canales con firma genérica `/webhooks/<id>`.
Adaptador → `NormalizedMessage` → dedup → orquestador (o cola de reintento).
"""
from __future__ import annotations

import json
import logging
from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal

from lazaro_contracts import LAZARO_SIGNATURE_HEADER, LAZARO_TIMESTAMP_HEADER

from . import grouping
from .channel_service import ChannelService
from .config import Settings
from .domain import (
    Adapters,
    IncomingUpdate,
    InboundUnavailable,
    InvalidWebhookPayload,
    PayloadTooLarge,
    WebhookUnauthorized,
)
from .inbound import InboundForwarder
from .signature import verify_signature

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from lazaro_contracts import NormalizedMessage

    from .ports.canal import Canal


@dataclass(frozen=True)
class WebhookResult:
    status: Literal["accepted", "duplicate"]


@dataclass(frozen=True)
class DeliveryResult:
    status: Literal["accepted", "duplicate"]
    forwarded: bool
    reason: str | None = None
    queued: bool = False


def _load_object(body: bytes) -> dict:
    try:
        payload = json.loads(body.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise InvalidWebhookPayload("El cuerpo de la petición no es válido.") from None
    if not isinstance(payload, dict):
        raise InvalidWebhookPayload("El cuerpo de la petición no es válido.")
    return payload


def _telegram_update(message: "NormalizedMessage") -> IncomingUpdate | None:
    """Update entero que exige el buffer de agrupación; None si no aplica."""
    if message.kind != "text" or message.text is None:
        return None
    try:
        return IncomingUpdate(
            update_id=int(message.external_message_id),
            chat_id=int(message.external_chat_id),
            user_id=int(message.external_user_id),
            text=message.text,
        )
    except ValueError:
        return None


class WebhookService:
    def __init__(
        self, channels: ChannelService, settings: Settings, adapters: Adapters
    ) -> None:
        self._channels = channels
        self._settings = settings
        self._adapters = adapters
        self._forwarder = InboundForwarder(settings, adapters)

    def receive(
        self,
        channel_id: str,
        headers: Mapping[str, str],
        body: bytes,
        *,
        own_route: bool = False,
    ) -> WebhookResult:
        """R7-R28 de #62: 404 → 413 → 401 → 422 → dedup → entrega.

        `own_route=True` solo desde las URLs históricas de Telegram/WhatsApp.
        """
        canal, secret = self._channels.resolve_for_webhook(
            channel_id, own_route=own_route
        )
        if len(body) > self._settings.webhook_max_body_bytes:
            raise PayloadTooLarge("El cuerpo del webhook supera el tamaño máximo.")
        if secret is None:
            messages = self._own_webhook_messages(canal, headers, body)
        else:
            if not verify_signature(
                secret,
                headers.get(LAZARO_TIMESTAMP_HEADER),
                headers.get(LAZARO_SIGNATURE_HEADER),
                body,
                self._adapters.clock(),
                self._settings.webhook_signature_window_seconds,
            ):
                raise WebhookUnauthorized("Firma del webhook ausente o no válida.")
            message = canal.recibir_mensaje(_load_object(body))
            if message is None:
                raise InvalidWebhookPayload("El cuerpo de la petición no es válido.")
            messages = [message]
        for message in messages:
            if message.channel != channel_id:
                raise InvalidWebhookPayload("El mensaje pertenece a otro canal.")
            if message.direction != "inbound":
                raise InvalidWebhookPayload("El mensaje no es de entrada.")
        results = [self._deliver(channel_id, canal, message) for message in messages]
        if results and all(result.status == "duplicate" for result in results):
            return WebhookResult(status="duplicate")
        return WebhookResult(status="accepted")

    def _own_webhook_messages(
        self, canal: "Canal", headers: Mapping[str, str], body: bytes
    ) -> list["NormalizedMessage"]:
        verify = getattr(canal, "verificar_webhook", None)
        extract = getattr(canal, "eventos", None)
        if not callable(verify) or not callable(extract):
            raise WebhookUnauthorized("Firma del webhook ausente o no válida.")
        if not verify(headers, body):
            raise WebhookUnauthorized("Firma del webhook ausente o no válida.")
        messages = extract(body)
        if messages is None:
            raise InvalidWebhookPayload("El cuerpo de la petición no es válido.")
        return list(messages)

    def inject(
        self, channel_id: str, canal: "Canal", message: "NormalizedMessage"
    ) -> DeliveryResult:
        """R20 de #63: entrega un mensaje ya autorizado por el token de servicio."""
        return self._deliver(channel_id, canal, message)

    def _call_hook(
        self, channel_id: str, canal: "Canal", name: str, *args: Any
    ) -> None:
        hook = getattr(canal, name, None)
        if not callable(hook):
            return
        try:
            hook(*args)
        except Exception as exc:  # noqa: BLE001 - R26 no rompe la entrega
            logger.error(
                "%s_failed channel_id=%s code=%s", name, channel_id, type(exc).__name__
            )

    def _forget(self, channel_id: str, external_message_id: str) -> None:
        """Sin entrega ni cola, se quita la marca para que el reenvío del canal entre."""
        forget = getattr(self._adapters.dedup, "forget_message", None)
        if not callable(forget):
            return
        try:
            forget(channel_id, external_message_id)
        except Exception as exc:  # noqa: BLE001 - el orquestador deduplica igualmente
            logger.warning(
                "dedup_forget_failed channel_id=%s code=%s",
                channel_id,
                type(exc).__name__,
            )

    def _deliver(
        self, channel_id: str, canal: "Canal", message: "NormalizedMessage"
    ) -> DeliveryResult:
        try:
            is_new = self._adapters.dedup.mark_message_if_new(
                channel_id,
                message.external_message_id,
                self._settings.dedup_ttl_seconds,
            )
        except Exception as exc:  # noqa: BLE001 - R26 se trata como nuevo
            # Sin Redis, la barrera es el índice único (canal, id externo) del
            # inbox del orquestador: un reenvío responde `duplicate`.
            logger.error(
                "Fallo de Redis al deduplicar webhook channel_id=%s (%s); "
                "se trata como nuevo",
                channel_id,
                type(exc).__name__,
            )
            is_new = True
        if not is_new:
            return DeliveryResult(status="duplicate", forwarded=False)
        self._call_hook(channel_id, canal, "registrar_entrada", message)
        try:
            if getattr(canal, "agrupa_mensajes", False) is True and self._groups(message):
                return DeliveryResult(status="accepted", forwarded=True)
            result = self._forwarder.forward(message)
        except InboundUnavailable:
            self._forget(channel_id, message.external_message_id)
            raise
        if not result.forwarded and not result.queued:
            self._call_hook(
                channel_id, canal, "registrar_rechazo", message, result.reason or ""
            )
        return DeliveryResult(
            status="accepted",
            forwarded=result.forwarded,
            reason=result.reason,
            queued=result.queued,
        )

    def _groups(self, message: "NormalizedMessage") -> bool:
        """#30: los textos de un canal que agrupa pasan por el buffer de Redis."""
        if not self._settings.message_grouping_enabled or self._adapters.buffer is None:
            return False
        incoming = _telegram_update(message)
        if incoming is None:
            return False
        grouping.enqueue_text(
            incoming, self._settings, self._adapters, self._forwarder.forward
        )
        return True
