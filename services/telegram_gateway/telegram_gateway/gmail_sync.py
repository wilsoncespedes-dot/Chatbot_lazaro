"""Sincronización incremental de Gmail hacia el inbox durable del orquestador."""
from __future__ import annotations

import logging
import threading
from dataclasses import dataclass

from .adapters.gmail_api import GmailApiError, added_message_ids
from .adapters.gmail_history import GmailHistoryRepository
from .adapters.orchestrator import OrchestratorClient
from .adapters.channels.gmail import GmailChannel
from .channel_service import ChannelService
from .domain import ChannelNotConfigured, DomainError, OrchestratorError

logger = logging.getLogger(__name__)
_LOCKS_GUARD = threading.Lock()
_CHANNEL_LOCKS: dict[str, threading.Lock] = {}


class GmailHistoryExpired(DomainError):
    code = "gmail_history_expired"
    status_code = 409


class GmailSyncFailed(DomainError):
    code = "gmail_sync_failed"
    status_code = 502


@dataclass(frozen=True)
class GmailSyncResult:
    initialized: bool
    processed: int
    history_id: str


def _channel_lock(channel_id: str) -> threading.Lock:
    with _LOCKS_GUARD:
        return _CHANNEL_LOCKS.setdefault(channel_id, threading.Lock())


class GmailSyncService:
    def __init__(
        self,
        channels: ChannelService,
        history: GmailHistoryRepository,
        orchestrator: OrchestratorClient,
    ) -> None:
        self._channels = channels
        self._history = history
        self._orchestrator = orchestrator

    def _gmail_channel(self, channel_id: str) -> GmailChannel:
        try:
            channel = self._channels.resolve(channel_id)
        except DomainError:
            raise
        if not isinstance(channel, GmailChannel):
            raise ChannelNotConfigured("El canal no es un adaptador Gmail API.")
        return channel

    def _check_mailbox(self, channel: GmailChannel) -> str:
        try:
            profile = channel.client.profile()
        except GmailApiError as exc:
            logger.warning(
                "gmail_profile_failed status=%s code=%s", exc.status_code, exc.code
            )
            raise GmailSyncFailed("No se pudo consultar el buzón Gmail.") from None
        actual = profile.get("emailAddress")
        history_id = profile.get("historyId")
        if (
            not isinstance(actual, str)
            or actual.casefold() != channel.email_address.casefold()
            or not isinstance(history_id, str)
        ):
            raise ChannelNotConfigured(
                "La cuenta OAuth no coincide con config.email_address del canal Gmail."
            )
        return history_id

    def initialize(self, channel_id: str) -> GmailSyncResult:
        """Fija el punto de inicio actual; deliberadamente no hace backfill."""
        with _channel_lock(channel_id):
            channel = self._gmail_channel(channel_id)
            history_id = self._check_mailbox(channel)
            self._history.reset_cursor(channel_id, history_id)
            return GmailSyncResult(True, 0, history_id)

    def sync(self, channel_id: str) -> GmailSyncResult:
        with _channel_lock(channel_id):
            channel = self._gmail_channel(channel_id)
            cursor = self._history.get_cursor(channel_id)
            profile_history_id = self._check_mailbox(channel)
            if cursor is None:
                self._history.set_cursor(channel_id, profile_history_id)
                return GmailSyncResult(True, 0, profile_history_id)

            page_token: str | None = None
            final_history_id = cursor
            processed = 0
            try:
                while True:
                    try:
                        response = channel.client.history(cursor, page_token)
                    except GmailApiError as exc:
                        if exc.status_code == 404:
                            raise GmailHistoryExpired(
                                "El cursor Gmail expiró; reinícialo desde la administración."
                            ) from None
                        logger.warning(
                            "gmail_history_failed channel_id=%s status=%s code=%s",
                            channel_id,
                            exc.status_code,
                            exc.code,
                        )
                        raise GmailSyncFailed(
                            "Falló la consulta del historial Gmail."
                        ) from None
                    response_history_id = response.get("historyId")
                    if isinstance(response_history_id, str):
                        final_history_id = response_history_id
                    for message_id in added_message_ids(response):
                        try:
                            message_data = channel.client.get_message(message_id)
                        except GmailApiError as exc:
                            logger.warning(
                                "gmail_message_read_failed channel_id=%s status=%s code=%s",
                                channel_id,
                                exc.status_code,
                                exc.code,
                            )
                            raise GmailSyncFailed(
                                "No se pudo leer un mensaje Gmail recibido."
                            ) from None
                        labels = message_data.get("labelIds", [])
                        if not isinstance(labels, list) or "INBOX" not in labels:
                            continue
                        normalized = channel.recibir_mensaje(message_data)
                        if normalized is None:
                            continue
                        self._orchestrator.post_message(normalized)
                        processed += 1
                    page_token = response.get("nextPageToken")
                    if not isinstance(page_token, str) or not page_token:
                        break
            except (OrchestratorError, ValueError) as exc:
                logger.warning(
                    "gmail_sync_delivery_failed channel_id=%s code=%s",
                    channel_id,
                    type(exc).__name__,
                )
                raise GmailSyncFailed(
                    "El orquestador no aceptó todos los mensajes Gmail."
                ) from None

            self._history.set_cursor(channel_id, final_history_id)
            logger.info(
                "gmail_sync_completed channel_id=%s processed=%s",
                channel_id,
                processed,
            )
            return GmailSyncResult(False, processed, final_history_id)
