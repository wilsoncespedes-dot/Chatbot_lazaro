"""Caso de uso del webhook genérico firmado (sin HTTP ni IO directa)."""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal

from pydantic import ValidationError

from .channel_service import ChannelService
from .config import Settings
from .domain import (
    Adapters,
    InvalidWebhookPayload,
    OrchestratorError,
    PayloadTooLarge,
    WebhookUnauthorized,
)
from .signature import verify_signature

logger = logging.getLogger(__name__)
MAX_REASON_LENGTH = 200

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


def _load_object(body: bytes) -> dict:
    try:
        payload = json.loads(body.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise InvalidWebhookPayload("El cuerpo de la petición no es válido.") from None
    if not isinstance(payload, dict):
        raise InvalidWebhookPayload("El cuerpo de la petición no es válido.")
    return payload


class WebhookService:
    def __init__(
        self, channels: ChannelService, settings: Settings, adapters: Adapters
    ) -> None:
        self._channels = channels
        self._settings = settings
        self._adapters = adapters

    def receive(
        self,
        channel_id: str,
        timestamp: str | None,
        signature: str | None,
        body: bytes,
    ) -> WebhookResult:
        """R7-R28 de #62: 404 → 413 → 401 → 422 → dedup → entrega."""
        canal, secret = self._channels.resolve_for_webhook(channel_id)
        if len(body) > self._settings.webhook_max_body_bytes:
            raise PayloadTooLarge("El cuerpo del webhook supera el tamaño máximo.")
        now = self._adapters.clock()
        if not verify_signature(
            secret,
            timestamp,
            signature,
            body,
            now,
            self._settings.webhook_signature_window_seconds,
        ):
            raise WebhookUnauthorized("Firma del webhook ausente o no válida.")
        message = canal.recibir_mensaje(_load_object(body))
        if message is None:
            raise InvalidWebhookPayload("El cuerpo de la petición no es válido.")
        if message.channel != channel_id:
            raise InvalidWebhookPayload("El mensaje pertenece a otro canal.")
        if message.direction != "inbound":
            raise InvalidWebhookPayload("El mensaje no es de entrada.")
        result = self._deliver(channel_id, canal, message)
        return WebhookResult(status=result.status)

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
            self._adapters.orchestrator.post_message(message)
        except (OrchestratorError, ValidationError) as exc:
            reason = (
                str(exc) if isinstance(exc, OrchestratorError) else "validation_error"
            )[:MAX_REASON_LENGTH]
            logger.error(
                "webhook_forward_failed channel_id=%s reason=%s", channel_id, reason
            )
            self._call_hook(channel_id, canal, "registrar_rechazo", message, reason)
            return DeliveryResult(status="accepted", forwarded=False, reason=reason)
        return DeliveryResult(status="accepted", forwarded=True)
