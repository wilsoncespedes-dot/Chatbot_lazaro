"""Fase 6: adaptador de puerto para TikTok Business Messaging.

- Webhook propio en `/webhooks/tiktok`, verificado con HMAC-SHA256 y
  `TIKTOK_WEBHOOK_SECRET`; sin ese secreto se rechaza todo (401).
- Los tokens OAuth viven cifrados (Fernet, `CHANNEL_SECRETS_KEY`) en
  `canales.config_secreta` y se refrescan antes de vencer. Si TikTok responde que
  el token no vale, se refresca una vez y se reintenta el envío.
- `supports_images=False`: el núcleo manda los gráficos como enlace.
"""
from __future__ import annotations

import json
import logging
import threading
from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any, Callable, ClassVar

from lazaro_contracts import ChannelCapabilities, DeliveryStatus, NormalizedMessage, ResponseBlock

from ...adapters.telegram import render_blocks
from ...domain import (
    ChannelNotConfigured,
    ChannelRecord,
    ChannelSecrets,
    ChannelWindowClosed,
)
from ...registry import CHANNEL_REGISTRY, ChannelContext
from ...secret_cipher import SecretCipher
from ...tiktok import (
    CHANNEL_ID,
    SIGNATURE_HEADER,
    TIKTOK_CAPABILITIES,
    TikTokTokenInvalid,
    TikTokTokens,
    build_text_payload,
    header_value,
    parse_tiktok_webhook,
    split_text,
    tokens_from_refresh,
    verify_tiktok_signature,
)
from ..channel_repository import ChannelRepository
from ..tiktok_api import TikTokApi, TikTokApiError, TikTokAuthError
from ..tiktok_quota import TIKTOK_MESSAGES_PER_WINDOW, TikTokMessageQuotaStore

logger = logging.getLogger(__name__)

# Un refresco a la vez por proceso: TikTok rota el refresh token y dos refrescos
# simultáneos invalidarían el que se guarde primero.
_REFRESH_LOCK = threading.Lock()


class ChannelTokenStore:
    """Tokens OAuth cifrados dentro de `config_secreta` del canal."""

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

    def load(self) -> TikTokTokens | None:
        secrets = self._secrets()
        if secrets is None:
            return None
        return TikTokTokens.from_credentials(secrets.credentials)

    def save(self, tokens: TikTokTokens) -> None:
        current = self._secrets() or ChannelSecrets()
        credentials = {**dict(current.credentials), **tokens.as_credentials()}
        encrypted = self._cipher.encrypt(
            ChannelSecrets(secret=current.secret, credentials=credentials)
        )
        if not self._repository.set_encrypted_secrets(self._channel_id, encrypted):
            raise ChannelNotConfigured("El canal TikTok no existe en la tabla de canales.")


@CHANNEL_REGISTRY.register("tiktok")
class TikTokChannel:
    managed_by_environment: ClassVar[bool] = True
    webhook_propio: ClassVar[bool] = True

    def __init__(
        self,
        api: TikTokApi | None,
        store: ChannelTokenStore | None,
        clock: Callable[[], datetime],
        *,
        client_key: str = "",
        client_secret: str = "",
        webhook_secret: str = "",
        business_id: str = "",
        bootstrap_refresh_token: str = "",
        quota: TikTokMessageQuotaStore | None = None,
        refresh_margin_seconds: int = 300,
        signature_tolerance_seconds: int = 300,
    ) -> None:
        self._api = api
        self._store = store
        self._clock = clock
        self._client_key = client_key
        self._client_secret = client_secret
        self._webhook_secret = webhook_secret
        self._business_id = business_id
        self._bootstrap_refresh_token = bootstrap_refresh_token
        self._quota = quota
        self._refresh_margin_seconds = refresh_margin_seconds
        self._signature_tolerance_seconds = signature_tolerance_seconds

    # ── fábrica ────────────────────────────────────────────────────────────

    @classmethod
    def default_capabilities(
        cls, config: Mapping[str, Any] | None = None
    ) -> ChannelCapabilities:
        return TIKTOK_CAPABILITIES

    @classmethod
    def is_available(cls, context: ChannelContext) -> bool:
        return context.adapters.tiktok is not None or context.settings.tiktok_enabled

    @classmethod
    def build(
        cls,
        record: ChannelRecord,
        context: ChannelContext,
        secrets: ChannelSecrets | None,
    ) -> "TikTokChannel":
        if not cls.is_available(context):
            raise ChannelNotConfigured("El canal no está configurado en este servicio.")
        settings = context.settings
        store = None
        cipher = SecretCipher(settings.channel_secrets_key.get_secret_value())
        if context.adapters.channels is not None and cipher.available:
            store = ChannelTokenStore(context.adapters.channels, cipher, record.id)
        return cls(
            context.adapters.tiktok,
            store,
            context.adapters.clock,
            client_key=settings.tiktok_client_key,
            client_secret=settings.tiktok_client_secret.get_secret_value(),
            webhook_secret=settings.tiktok_webhook_secret.get_secret_value(),
            business_id=settings.tiktok_business_id,
            bootstrap_refresh_token=settings.tiktok_refresh_token.get_secret_value(),
            quota=context.adapters.tiktok_quota,
            refresh_margin_seconds=settings.tiktok_token_refresh_margin_seconds,
            signature_tolerance_seconds=settings.tiktok_signature_tolerance_seconds,
        )

    # ── entrada ────────────────────────────────────────────────────────────

    def verificar_webhook(self, headers: Mapping[str, str], body: bytes) -> bool:
        # Sin TIKTOK_WEBHOOK_SECRET `verify_tiktok_signature` devuelve False: 401.
        return verify_tiktok_signature(
            self._webhook_secret,
            body,
            header_value(headers, SIGNATURE_HEADER),
            self._clock(),
            self._signature_tolerance_seconds,
        )

    def eventos(self, body: bytes) -> list[NormalizedMessage]:
        """Un cuerpo ajeno o no JSON se ignora (200) para que TikTok no reintente."""
        try:
            payload = json.loads(body)
        except (json.JSONDecodeError, UnicodeDecodeError):
            return []
        if not isinstance(payload, dict):
            return []
        if self._client_key and payload.get("client_key") != self._client_key:
            return []
        return parse_tiktok_webhook(payload, self._business_id, self._clock())

    def recibir_mensaje(self, payload: Mapping[str, Any]) -> NormalizedMessage | None:
        messages = parse_tiktok_webhook(dict(payload), self._business_id, self._clock())
        return messages[0] if messages else None

    def identificar_usuario(self, payload: Mapping[str, Any]) -> str | None:
        message = self.recibir_mensaje(payload)
        return message.external_user_id if message is not None else None

    def capacidades(self, destino: str | None = None) -> ChannelCapabilities:
        return TIKTOK_CAPABILITIES

    # ── tokens ─────────────────────────────────────────────────────────────

    def _require(self) -> tuple[TikTokApi, ChannelTokenStore]:
        if self._api is None or self._store is None:
            raise ChannelNotConfigured("El canal TikTok no está configurado.")
        return self._api, self._store

    def _refresh(self, stale_access_token: str | None) -> TikTokTokens:
        api, store = self._require()
        with _REFRESH_LOCK:
            current = store.load()
            now = self._clock()
            # Otro envío ya refrescó mientras esperábamos el candado.
            if current is not None and (
                stale_access_token is None
                and not current.expires_soon(now, self._refresh_margin_seconds)
                or stale_access_token is not None
                and current.access_token != stale_access_token
            ):
                return current
            refresh_token = (
                current.refresh_token if current is not None else self._bootstrap_refresh_token
            )
            if not refresh_token:
                raise ChannelNotConfigured("El canal TikTok no tiene refresh token.")
            body = api.refresh_token(self._client_key, self._client_secret, refresh_token)
            try:
                tokens = tokens_from_refresh(body, refresh_token, now)
            except TikTokTokenInvalid:
                logger.warning("tiktok_refresh_invalid_response")
                raise TikTokApiError("refresh_invalid") from None
            store.save(tokens)
            logger.info("tiktok_token_refreshed")
            return tokens

    def _valid_tokens(self) -> TikTokTokens:
        _, store = self._require()
        current = store.load()
        if current is None or current.expires_soon(
            self._clock(), self._refresh_margin_seconds
        ):
            return self._refresh(None)
        return current

    # ── salida ─────────────────────────────────────────────────────────────

    def _send_with_retry(self, payload: Mapping[str, Any]) -> None:
        api, _ = self._require()
        tokens = self._valid_tokens()
        if self._quota is not None:
            try:
                allowed = self._quota.reserve_send(
                    str(payload["recipient"]), TIKTOK_MESSAGES_PER_WINDOW
                )
            except Exception as exc:  # noqa: BLE001 - fallo cerrado ante cuota no comprobable
                logger.warning("tiktok_quota_unavailable type=%s", type(exc).__name__)
                raise ChannelWindowClosed(
                    "No se pudo comprobar el límite de mensajes de TikTok."
                ) from None
            if not allowed:
                raise ChannelWindowClosed(
                    "Se alcanzó el límite de mensajes de TikTok para esta conversación."
                )
        try:
            api.send_message(tokens.access_token, payload)
        except TikTokAuthError:
            tokens = self._refresh(tokens.access_token)
            api.send_message(tokens.access_token, payload)

    def enviar_mensaje(
        self, destino: str, bloques: Sequence[ResponseBlock]
    ) -> DeliveryStatus:
        text = render_blocks(list(bloques))
        try:
            for chunk in split_text(text):
                self._send_with_retry(
                    build_text_payload(self._business_id, destino, chunk)
                )
        except TikTokApiError as exc:
            logger.warning("tiktok_send_failed code=%s", type(exc).__name__)
            return "failed"
        return "sent"

    def registrar_entrada(self, message: NormalizedMessage) -> None:
        if self._quota is not None:
            self._quota.record_inbound(message.external_chat_id)
