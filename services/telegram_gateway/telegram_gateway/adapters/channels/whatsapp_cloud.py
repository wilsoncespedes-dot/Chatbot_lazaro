"""Adaptador de puerto para WhatsApp Cloud API.

Fase 2: el webhook `/whatsapp/webhook` entra por el `WebhookService` común. El
adaptador verifica la firma `X-Hub-Signature-256`, registra la ventana de 24 h
y los estados de entrega, y devuelve los mensajes normalizados del lote.
"""
from __future__ import annotations

import json
import logging
from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import TYPE_CHECKING, Any, Callable, ClassVar

from lazaro_contracts import ChannelCapabilities, DeliveryStatus, NormalizedMessage, ResponseBlock
from pydantic import ValidationError

from ...adapters.whatsapp import ChannelAdapter
from ...domain import ChannelNotConfigured, ChannelRecord, ChannelSecrets
from ...registry import CHANNEL_REGISTRY, ChannelContext
from ...whatsapp_cloud import (
    SIGNATURE_HEADER,
    parse_webhook,
    to_delivery_status,
    verify_signature,
    whatsapp_capabilities,
)

if TYPE_CHECKING:
    from ...adapters.whatsapp_window import WhatsAppWindowStore

logger = logging.getLogger(__name__)

WEBHOOK_OBJECT = "whatsapp_business_account"


@CHANNEL_REGISTRY.register("whatsapp_cloud")
class WhatsAppCloudChannel:
    managed_by_environment: ClassVar[bool] = True
    webhook_propio: ClassVar[bool] = True

    def __init__(
        self,
        client: ChannelAdapter | None,
        clock: Callable[[], datetime],
        *,
        app_secret: str = "",
        phone_number_id: str = "",
        window: "WhatsAppWindowStore | None" = None,
    ) -> None:
        self._client = client
        self._clock = clock
        self._app_secret = app_secret
        self._phone_number_id = phone_number_id
        self._window = window

    @classmethod
    def default_capabilities(
        cls, config: Mapping[str, Any] | None = None
    ) -> ChannelCapabilities:
        return ChannelCapabilities(**whatsapp_capabilities(window_open=False))

    @classmethod
    def is_available(cls, context: ChannelContext) -> bool:
        return context.adapters.whatsapp is not None or context.settings.whatsapp_enabled

    @classmethod
    def build(
        cls,
        record: ChannelRecord,
        context: ChannelContext,
        secrets: ChannelSecrets | None,
    ) -> "WhatsAppCloudChannel":
        if not cls.is_available(context):
            raise ChannelNotConfigured("El canal no está configurado en este servicio.")
        settings = context.settings
        return cls(
            context.adapters.whatsapp,
            context.adapters.clock,
            app_secret=settings.whatsapp_app_secret.get_secret_value(),
            phone_number_id=settings.whatsapp_phone_number_id,
            window=context.adapters.whatsapp_window,
        )

    def _require_client(self) -> ChannelAdapter:
        if self._client is None:
            raise ChannelNotConfigured("El canal no está configurado en este servicio.")
        return self._client

    def verificar_webhook(self, headers: Mapping[str, str], body: bytes) -> bool:
        return verify_signature(self._app_secret, body, headers.get(SIGNATURE_HEADER))

    def eventos(self, body: bytes) -> list[NormalizedMessage]:
        """R14: un cuerpo ajeno o no JSON se ignora (200) para que Meta no reintente."""
        try:
            payload = json.loads(body)
        except (json.JSONDecodeError, UnicodeDecodeError):
            return []
        if not isinstance(payload, dict) or payload.get("object") != WEBHOOK_OBJECT:
            return []
        received_at = self._clock()
        parsed = parse_webhook(payload, self._phone_number_id, received_at)
        if self._window is not None:
            for wa_id in parsed.inbound_wa_ids:
                try:
                    self._window.record_inbound(wa_id, received_at)
                except Exception as exc:  # noqa: BLE001 - R27 no debe romper el lote
                    logger.warning(
                        "No se pudo registrar la ventana de WhatsApp (%s)",
                        type(exc).__name__,
                    )
        for status in parsed.statuses:
            logger.info(
                "whatsapp_status wamid=%s status=%s codes=%s",
                status.wamid,
                to_delivery_status(status.status),
                list(status.error_codes),
            )
        return list(parsed.messages)

    def recibir_mensaje(
        self, payload: Mapping[str, Any]
    ) -> NormalizedMessage | None:
        try:
            return self._require_client().normalize_incoming(dict(payload), self._clock())
        except (KeyError, TypeError, ValueError, ValidationError, ChannelNotConfigured):
            return None

    def enviar_mensaje(
        self, destino: str, bloques: Sequence[ResponseBlock]
    ) -> DeliveryStatus:
        return self._require_client().send(destino, bloques)

    def identificar_usuario(self, payload: Mapping[str, Any]) -> str | None:
        value = payload.get("from")
        if isinstance(value, bool) or value is None:
            return None
        if isinstance(value, (str, int)):
            text = str(value)
            return text if text.strip() else None
        return None

    def capacidades(self, destino: str | None = None) -> ChannelCapabilities:
        client = self._require_client()
        capabilities_for = getattr(client, "capabilities_for", None)
        if destino is not None and callable(capabilities_for):
            return capabilities_for(destino)
        return client.capabilities()
