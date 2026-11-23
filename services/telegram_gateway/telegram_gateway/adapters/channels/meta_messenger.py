"""Fase 7: Facebook Messenger e Instagram Messaging (Send API de Meta).

- Webhook compartido `GET/POST /webhooks/messenger`: el GET es el handshake
  `hub.challenge` y el POST se verifica con `X-Hub-Signature-256` (las mismas
  funciones que WhatsApp Cloud). El canal sale de `object` (`page` → `facebook`,
  `instagram` → `instagram`).
- Salida por el Send API con texto e imágenes (`supports_images=True`).
- El Page Access Token vive cifrado (Fernet, `CHANNEL_SECRETS_KEY`) en
  `canales.config_secreta`; `META_PAGE_ACCESS_TOKEN` solo lo siembra o lo rota.
- Política de 24 h: si el último mensaje del cliente es más antiguo, el envío
  se rechaza con `ChannelWindowClosed` (422 `channel_window_closed`) y el
  orquestador deja la fila de la outbox en `fuera_de_ventana`.
"""
from __future__ import annotations

import json
import logging
from collections.abc import Iterator, Mapping, Sequence
from datetime import datetime, timedelta
from typing import Any, Callable, ClassVar

from lazaro_contracts import (
    ChannelCapabilities,
    DeliveryStatus,
    ImageBlock,
    NormalizedMessage,
    ResponseBlock,
)

from ...adapters.meta_messaging import MetaMessagingApi, MetaMessagingApiError
from ...adapters.meta_window import MetaMessageWindowStore
from ...adapters.telegram import render_blocks
from ...domain import (
    ChannelNotConfigured,
    ChannelRecord,
    ChannelSecrets,
    ChannelWindowClosed,
)
from ...meta_messaging import (
    META_FACEBOOK_CHANNEL,
    META_INSTAGRAM_CHANNEL,
    META_SIGNATURE_HEADER,
    MetaChannel,
    parse_meta_webhook,
)
from ...registry import CHANNEL_REGISTRY, ChannelContext
from ...secret_cipher import SecretCipher
from ...whatsapp_cloud import verify_signature
from ..channel_repository import ChannelRepository

logger = logging.getLogger(__name__)

PAGE_TOKEN_CREDENTIAL = "page_access_token"

META_CAPABILITIES = ChannelCapabilities(
    free_text_allowed=True,
    max_options=0,
    min_list_options=0,
    max_list_options=0,
    supports_links=True,
    requires_template=False,
    supports_buttons=False,
    supports_images=True,
    supports_files=False,
    supports_audio=False,
)


class MetaPageTokenStore:
    """Page Access Token cifrado en `config_secreta` del canal."""

    def __init__(
        self, repository: ChannelRepository, cipher: SecretCipher, channel_id: str
    ) -> None:
        self._repository = repository
        self._cipher = cipher
        self._channel_id = channel_id

    def _secrets(self) -> ChannelSecrets | None:
        encrypted = self._repository.get_encrypted_secrets(self._channel_id)
        if encrypted is None:
            return None
        return self._cipher.decrypt(encrypted)

    def load(self) -> str | None:
        secrets = self._secrets()
        if secrets is None:
            return None
        return secrets.credentials.get(PAGE_TOKEN_CREDENTIAL) or None

    def save(self, token: str) -> None:
        current = self._secrets() or ChannelSecrets()
        credentials = {**dict(current.credentials), PAGE_TOKEN_CREDENTIAL: token}
        encrypted = self._cipher.encrypt(
            ChannelSecrets(secret=current.secret, credentials=credentials)
        )
        if not self._repository.set_encrypted_secrets(self._channel_id, encrypted):
            raise ChannelNotConfigured("El canal Meta no existe en la tabla de canales.")


def _segments(blocks: Sequence[ResponseBlock]) -> Iterator[str | ImageBlock]:
    """Agrupa bloques de texto consecutivos y deja cada imagen en su sitio."""
    pending: list[ResponseBlock] = []
    for block in blocks:
        if isinstance(block, ImageBlock):
            if pending:
                text = render_blocks(pending)
                if text.strip():
                    yield text
                pending = []
            yield block
        else:
            pending.append(block)
    if pending:
        text = render_blocks(pending)
        if text.strip():
            yield text


class _MetaMessagingChannel:
    managed_by_environment: ClassVar[bool] = True
    webhook_propio: ClassVar[bool] = True
    channel_id: ClassVar[MetaChannel]
    enabled_setting: ClassVar[str]

    def __init__(
        self,
        api: MetaMessagingApi | None,
        clock: Callable[[], datetime],
        *,
        app_secret: str,
        page_id: str,
        instagram_account_id: str,
        page_token: str = "",
        token_store: MetaPageTokenStore | None = None,
        window: MetaMessageWindowStore | None = None,
        window_hours: int = 24,
    ) -> None:
        self._api = api
        self._clock = clock
        self._app_secret = app_secret
        self._page_id = page_id
        self._instagram_account_id = instagram_account_id
        self._bootstrap_page_token = page_token
        self._token_store = token_store
        self._window = window
        self._window_hours = window_hours

    @classmethod
    def is_available(cls, context: ChannelContext) -> bool:
        return bool(
            getattr(context.settings, cls.enabled_setting)
            and context.adapters.meta is not None
        )

    @classmethod
    def default_capabilities(
        cls, config: Mapping[str, Any] | None = None
    ) -> ChannelCapabilities:
        return META_CAPABILITIES

    @classmethod
    def build(
        cls,
        record: ChannelRecord,
        context: ChannelContext,
        secrets: ChannelSecrets | None,
    ) -> "_MetaMessagingChannel":
        if not cls.is_available(context):
            raise ChannelNotConfigured("El canal Meta no está configurado.")
        settings = context.settings
        token_store = None
        cipher = SecretCipher(settings.channel_secrets_key.get_secret_value())
        if context.adapters.channels is not None and cipher.available:
            token_store = MetaPageTokenStore(context.adapters.channels, cipher, record.id)
        return cls(
            context.adapters.meta,
            context.adapters.clock,
            app_secret=settings.meta_app_secret.get_secret_value(),
            page_id=settings.meta_page_id,
            instagram_account_id=settings.meta_instagram_account_id,
            page_token=settings.meta_page_access_token.get_secret_value(),
            token_store=token_store,
            window=context.adapters.meta_window,
            window_hours=settings.meta_messaging_window_hours,
        )

    # ── entrada ────────────────────────────────────────────────────────────

    def verificar_webhook(self, headers: Mapping[str, str], body: bytes) -> bool:
        signature = next(
            (
                value
                for key, value in headers.items()
                if key.lower() == META_SIGNATURE_HEADER.lower()
            ),
            None,
        )
        return verify_signature(self._app_secret, body, signature)

    def eventos(self, body: bytes) -> list[NormalizedMessage]:
        try:
            payload = json.loads(body)
        except (json.JSONDecodeError, UnicodeDecodeError):
            return []
        return parse_meta_webhook(
            payload,
            self.channel_id,
            self._page_id,
            self._instagram_account_id,
            self._clock(),
        )

    def recibir_mensaje(
        self, payload: Mapping[str, Any]
    ) -> NormalizedMessage | None:
        messages = parse_meta_webhook(
            dict(payload),
            self.channel_id,
            self._page_id,
            self._instagram_account_id,
            self._clock(),
        )
        return messages[0] if messages else None

    def registrar_entrada(self, message: NormalizedMessage) -> None:
        if self._window is not None:
            self._window.record_inbound(
                self.channel_id, message.external_chat_id, message.received_at
            )

    def identificar_usuario(self, payload: Mapping[str, Any]) -> str | None:
        message = self.recibir_mensaje(payload)
        return message.external_user_id if message is not None else None

    def capacidades(self, destino: str | None = None) -> ChannelCapabilities:
        return META_CAPABILITIES

    # ── salida ─────────────────────────────────────────────────────────────

    def _check_window(self, destino: str) -> None:
        if self._window is None:
            return
        try:
            last_inbound = self._window.last_inbound(self.channel_id, destino)
        except Exception as exc:  # noqa: BLE001 - falla cerrada para la política de Meta
            logger.warning(
                "meta_window_unavailable channel=%s type=%s",
                self.channel_id,
                type(exc).__name__,
            )
            raise ChannelWindowClosed(
                "No se pudo comprobar la ventana de atención de Meta."
            ) from None
        if last_inbound is None or self._clock() - last_inbound >= timedelta(
            hours=self._window_hours
        ):
            # Sin el id del cliente: solo canal (R41 de logs sin datos personales).
            logger.warning("meta_fuera_de_ventana channel=%s", self.channel_id)
            raise ChannelWindowClosed("La ventana de atención de Meta está cerrada.")

    def _page_token(self) -> str:
        """El token del entorno, si existe, se guarda cifrado; si no, el cifrado."""
        bootstrap = self._bootstrap_page_token
        if self._token_store is not None:
            stored = self._token_store.load()
            if bootstrap and stored != bootstrap:
                self._token_store.save(bootstrap)
                logger.info("meta_page_token_stored channel=%s", self.channel_id)
                return bootstrap
            if stored:
                return stored
        if bootstrap:
            return bootstrap
        raise ChannelNotConfigured("El canal Meta no tiene Page Access Token.")

    def enviar_mensaje(
        self, destino: str, bloques: Sequence[ResponseBlock]
    ) -> DeliveryStatus:
        if self._api is None:
            raise ChannelNotConfigured("El cliente de Meta no está configurado.")
        self._check_window(destino)
        token = self._page_token()
        try:
            for segment in _segments(bloques):
                if isinstance(segment, ImageBlock):
                    self._api.send_image(self.channel_id, destino, segment.url, token)
                else:
                    self._api.send_message(self.channel_id, destino, segment, token)
        except MetaMessagingApiError as exc:
            logger.warning(
                "meta_channel_send_failed channel=%s type=%s",
                self.channel_id,
                type(exc).__name__,
            )
            return "failed"
        return "sent"


@CHANNEL_REGISTRY.register("meta_messenger")
class FacebookMessengerChannel(_MetaMessagingChannel):
    channel_id = META_FACEBOOK_CHANNEL
    enabled_setting = "meta_messenger_enabled"


@CHANNEL_REGISTRY.register("meta_instagram")
class InstagramMessagingChannel(_MetaMessagingChannel):
    channel_id = META_INSTAGRAM_CHANNEL
    enabled_setting = "meta_instagram_enabled"
