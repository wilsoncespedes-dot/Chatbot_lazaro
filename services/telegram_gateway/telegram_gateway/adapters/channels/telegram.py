"""Adaptador de puerto para el canal Telegram.

Fase 2: el webhook `/telegram/webhook` entra por el `WebhookService` común. El
adaptador verifica el secreto de Telegram, confirma los `callback_query` y
traduce el update a `NormalizedMessage`.
"""
from __future__ import annotations

import hmac
import json
import logging
from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any, Callable, ClassVar

from lazaro_contracts import ChannelCapabilities, DeliveryStatus, NormalizedMessage, ResponseBlock
from pydantic import ValidationError

from ...adapters.telegram import TelegramChannelAdapter, TelegramClient, telegram_capabilities
from ...domain import (
    ChannelRecord,
    ChannelSecrets,
    extract_callback,
    extract_callback_query_id,
    extract_incoming,
    normalize_callback,
    normalize_incoming,
)
from ...registry import CHANNEL_REGISTRY, ChannelContext

logger = logging.getLogger(__name__)

WEBHOOK_SECRET_HEADER = "X-Telegram-Bot-Api-Secret-Token"


def _valid_update(payload: Mapping[str, Any]) -> dict[str, Any] | None:
    update = dict(payload)
    update_id = update.get("update_id")
    if isinstance(update_id, bool) or not isinstance(update_id, int):
        return None
    return update


@CHANNEL_REGISTRY.register("telegram")
class TelegramChannel:
    managed_by_environment: ClassVar[bool] = True
    # Verifica su propio webhook (secreto de Telegram) en vez de la firma genérica.
    webhook_propio: ClassVar[bool] = True
    # Los textos seguidos se agrupan antes de llegar al orquestador (#30).
    agrupa_mensajes: ClassVar[bool] = True

    def __init__(
        self,
        client: TelegramClient,
        clock: Callable[[], datetime],
        webhook_secret: str = "",
    ) -> None:
        self._client = client
        self._adapter = TelegramChannelAdapter(client)
        self._clock = clock
        self._webhook_secret = webhook_secret

    @classmethod
    def is_available(cls, context: ChannelContext) -> bool:
        return True

    @classmethod
    def default_capabilities(
        cls, config: Mapping[str, Any] | None = None
    ) -> ChannelCapabilities:
        return telegram_capabilities()

    @classmethod
    def build(
        cls,
        record: ChannelRecord,
        context: ChannelContext,
        secrets: ChannelSecrets | None,
    ) -> "TelegramChannel":
        return cls(
            context.adapters.telegram,
            context.adapters.clock,
            context.settings.telegram_webhook_secret,
        )

    def verificar_webhook(self, headers: Mapping[str, str], body: bytes) -> bool:
        received = headers.get(WEBHOOK_SECRET_HEADER)
        expected = self._webhook_secret
        return (
            bool(expected)
            and received is not None
            and hmac.compare_digest(received.encode(), expected.encode())
        )

    def _answer_callback(self, update: Mapping[str, Any]) -> None:
        """#44: se confirma siempre (también duplicados o inválidos) con el id real."""
        callback_query_id = extract_callback_query_id(dict(update))
        if callback_query_id is None:
            return
        try:
            self._client.answer_callback_query(callback_query_id)
        except Exception as exc:  # noqa: BLE001 - R4: nunca rompe el webhook
            logger.warning(
                "Fallo al confirmar callback update_id=%s (%s)",
                update.get("update_id"),
                type(exc).__name__,
            )

    def eventos(self, body: bytes) -> list[NormalizedMessage] | None:
        """Mensajes del update; `None` si el cuerpo no es un update de Telegram."""
        try:
            payload = json.loads(body.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            return None
        update = _valid_update(payload) if isinstance(payload, dict) else None
        if update is None:
            return None
        self._answer_callback(update)
        callback = extract_callback(update)
        if callback is not None:
            try:
                return [normalize_callback(callback, self._clock())]
            except ValidationError:
                logger.error("callback_invalido update_id=%s", callback.update_id)
                return []
        incoming = extract_incoming(update)
        if incoming is None:
            return []
        try:
            return [normalize_incoming(incoming, self._clock())]
        except ValidationError:
            logger.error("update_fuera_de_contrato update_id=%s", incoming.update_id)
            return []

    def recibir_mensaje(
        self, payload: Mapping[str, Any]
    ) -> NormalizedMessage | None:
        update = _valid_update(payload)
        if update is None:
            return None
        try:
            if "callback_query" in update:
                callback = extract_callback(update)
                return (
                    normalize_callback(callback, self._clock())
                    if callback is not None
                    else None
                )
            incoming = extract_incoming(update)
            return normalize_incoming(incoming, self._clock()) if incoming else None
        except (KeyError, TypeError, ValueError, ValidationError):
            return None

    def enviar_mensaje(
        self, destino: str, bloques: Sequence[ResponseBlock]
    ) -> DeliveryStatus:
        return self._adapter.send(destino, bloques)

    def identificar_usuario(self, payload: Mapping[str, Any]) -> str | None:
        update = _valid_update(payload)
        if update is None:
            return None
        try:
            if "callback_query" in update:
                callback = extract_callback(update)
                return str(callback.user_id) if callback is not None else None
            incoming = extract_incoming(update)
            return str(incoming.user_id) if incoming is not None else None
        except (KeyError, TypeError, ValueError):
            return None

    def capacidades(self, destino: str | None = None) -> ChannelCapabilities:
        return self._adapter.capabilities()
