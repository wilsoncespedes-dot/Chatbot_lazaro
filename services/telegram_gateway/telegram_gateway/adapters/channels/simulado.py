"""Adaptador SIMULADO del canal: no usa red; deja las respuestas en un buzón."""
from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any, Callable, ClassVar

from lazaro_contracts import (
    MAX_TEXT_LENGTH,
    ChannelCapabilities,
    DeliveryStatus,
    NormalizedMessage,
    ResponseBlock,
)
from pydantic import ValidationError

from ...adapters.mailbox import MailboxRepository
from ...adapters.telegram import render_blocks
from ...domain import ChannelNotConfigured, ChannelRecord, ChannelSecrets, InvalidChannelConfig
from ...registry import CHANNEL_REGISTRY, ChannelContext

logger = logging.getLogger(__name__)

CHANNEL_TYPE = "simulado"
MAX_REASON_LENGTH = 200

_BOOL_KEYS = (
    "free_text_allowed",
    "supports_buttons",
    "supports_links",
    "supports_images",
    "supports_files",
    "supports_audio",
    "requires_template",
)
_INT_KEYS = ("max_options", "min_list_options", "max_list_options")
_DEFAULTS: dict[str, Any] = {
    "free_text_allowed": True,
    "max_options": 0,
    "min_list_options": 0,
    "max_list_options": 0,
    "supports_links": False,
    "requires_template": False,
    "supports_buttons": False,
    "supports_images": False,
    "supports_files": False,
    "supports_audio": False,
}


def _split_text(text: str, limit: int) -> list[str]:
    return [text[index : index + limit] for index in range(0, len(text), limit)]


def _capabilities_from_config(raw: Mapping[str, Any]) -> ChannelCapabilities:
    unknown = set(raw) - set(_DEFAULTS)
    if unknown:
        raise ValueError("capabilities contiene claves desconocidas")
    for key in _BOOL_KEYS:
        if key in raw and not isinstance(raw[key], bool):
            raise ValueError(f"capabilities.{key} debe ser booleano")
    for key in _INT_KEYS:
        value = raw.get(key)
        if key in raw and (isinstance(value, bool) or not isinstance(value, int)):
            raise ValueError(f"capabilities.{key} debe ser entero")
    values = {key: raw.get(key, default) for key, default in _DEFAULTS.items()}
    try:
        return ChannelCapabilities(**values)
    except ValidationError as exc:
        raise ValueError("capabilities no válidas") from exc


@CHANNEL_REGISTRY.register(CHANNEL_TYPE)
class SimuladoChannel:
    """SIMULADO: canal de pruebas que se hace pasar por cualquier plataforma.

    Nunca abre sockets ni llama a la red: las respuestas salientes quedan en el
    buzón del gateway y el panel las muestra como si fueran del bot o del asesor.
    """

    managed_by_environment: ClassVar[bool] = False
    has_mailbox: ClassVar[bool] = True

    def __init__(
        self,
        channel_id: str,
        capabilities: ChannelCapabilities,
        mailbox: MailboxRepository,
        clock: Callable[[], datetime],
    ) -> None:
        self._channel_id = channel_id
        self._capabilities = capabilities
        self._mailbox = mailbox
        self._clock = clock

    @classmethod
    def default_capabilities(
        cls, config: Mapping[str, Any] | None = None
    ) -> ChannelCapabilities:
        raw = (config or {}).get("capabilities", {})
        if isinstance(raw, Mapping):
            try:
                return _capabilities_from_config(raw)
            except ValueError:
                pass
        return ChannelCapabilities(**_DEFAULTS)

    @classmethod
    def is_available(cls, context: ChannelContext) -> bool:
        return True

    @classmethod
    def build(
        cls,
        record: ChannelRecord,
        context: ChannelContext,
        secrets: ChannelSecrets | None,
    ) -> "SimuladoChannel":
        mailbox = context.adapters.mailbox
        if mailbox is None:
            raise ChannelNotConfigured("El buzón del canal simulado no está disponible.")
        raw = record.config.get("capabilities", {})
        if not isinstance(raw, Mapping):
            raise InvalidChannelConfig(
                "config.capabilities del canal simulado no es válido."
            )
        try:
            capabilities = _capabilities_from_config(raw)
        except ValueError:
            raise InvalidChannelConfig(
                "config.capabilities del canal simulado no es válido."
            ) from None
        return cls(record.id, capabilities, mailbox, context.adapters.clock)

    @classmethod
    def validate_config(
        cls, config: Mapping[str, Any], context: ChannelContext
    ) -> None:
        unknown = set(config) - {"capabilities"}
        if unknown:
            raise InvalidChannelConfig(
                "config del canal simulado solo admite capabilities."
            )
        raw = config.get("capabilities", {})
        if not isinstance(raw, Mapping):
            raise InvalidChannelConfig("config.capabilities debe ser un objeto.")
        try:
            _capabilities_from_config(raw)
        except ValueError:
            raise InvalidChannelConfig(
                "config.capabilities del canal simulado no es válido."
            ) from None

    def recibir_mensaje(
        self, payload: Mapping[str, Any]
    ) -> NormalizedMessage | None:
        try:
            message = NormalizedMessage.model_validate(dict(payload))
        except (TypeError, ValueError, ValidationError):
            return None
        if message.direction != "inbound":
            return None
        return message

    def identificar_usuario(self, payload: Mapping[str, Any]) -> str | None:
        try:
            message = NormalizedMessage.model_validate(dict(payload))
        except (TypeError, ValueError, ValidationError):
            return None
        if message.direction != "inbound":
            return None
        return message.external_user_id

    def capacidades(self, destino: str | None = None) -> ChannelCapabilities:
        return self._capabilities

    def enviar_mensaje(
        self, destino: str, bloques: Sequence[ResponseBlock]
    ) -> DeliveryStatus:
        text = "\n".join(render_blocks([block]) for block in bloques)
        try:
            for chunk in _split_text(text, MAX_TEXT_LENGTH):
                self._mailbox.append(
                    self._channel_id, destino, "reply", chunk, self._clock()
                )
        except Exception as exc:  # noqa: BLE001 - R10 solo el tipo
            logger.warning(
                "simulado_mailbox_error channel_id=%s code=%s",
                self._channel_id,
                type(exc).__name__,
            )
            return "failed"
        return "sent"

    def registrar_entrada(self, message: NormalizedMessage) -> None:
        self._mailbox.append(
            self._channel_id,
            message.external_user_id,
            "client",
            message.text or message.kind,
            self._clock(),
        )

    def registrar_rechazo(self, message: NormalizedMessage, reason: str) -> None:
        text = (reason or "El orquestador no procesó el mensaje.")[:MAX_REASON_LENGTH]
        self._mailbox.append(
            self._channel_id,
            message.external_user_id,
            "rejected",
            text,
            self._clock(),
        )
