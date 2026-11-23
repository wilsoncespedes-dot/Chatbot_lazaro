"""Agrupación de mensajes consecutivos: webhook, envío de grupos y worker."""
from __future__ import annotations

import logging
import threading

from collections.abc import Callable

from lazaro_contracts import MAX_TEXT_LENGTH, NormalizedMessage, normalize_legacy_message
from pydantic import ValidationError

from .config import Settings
from .domain import (
    Adapters,
    BufferedMessage,
    ClaimedGroup,
    IncomingUpdate,
    OrchestratorError,
    build_group_request,
    is_immediate,
    must_flush_before,
    normalize_incoming,
)
from .inbound import queue_for_retry

Forward = Callable[[NormalizedMessage], object]

logger = logging.getLogger(__name__)

DUE_BATCH_LIMIT = 100


def _update_ids(group: ClaimedGroup) -> str:
    return ",".join(str(message.update_id) for message in group.messages)


def _post_single(incoming: IncomingUpdate, adapters: Adapters, forward: Forward) -> None:
    """Reenvía un mensaje suelto; `forward` lo guarda para reintento si hace falta.

    Un `InboundUnavailable` de `forward` se propaga: el webhook responde 503.
    """
    try:
        message = normalize_incoming(incoming, adapters.clock())
    except ValidationError:
        logger.error(
            "Mensaje fuera de contrato descartado update_id=%s", incoming.update_id
        )
        return
    forward(message)


def _queue_group(
    message: NormalizedMessage, reason: str, settings: Settings, adapters: Adapters
) -> bool:
    """Fase 2: el grupo pasa a la cola persistente en vez de esperar en Redis."""
    if adapters.inbound_retry is None:
        return False
    try:
        queue_for_retry(message, reason, settings, adapters)
    except Exception:  # noqa: BLE001 - se conserva el reintento del buffer
        return False
    return True


def _send_group(group: ClaimedGroup, settings: Settings, adapters: Adapters) -> None:
    buffer = adapters.buffer
    if buffer is None:  # pragma: no cover - el llamador exige buffer
        return
    try:
        message = normalize_legacy_message(
            build_group_request(group.chat_id, group.messages)
        )
    except ValidationError:
        buffer.ack(group)
        logger.error(
            "grouping_discarded reason=validation chat_id=%s update_ids=%s messages=%d",
            group.chat_id,
            _update_ids(group),
            len(group.messages),
        )
        return
    try:
        adapters.orchestrator.post_message(message)
    except OrchestratorError as exc:
        if exc.retryable and _queue_group(message, str(exc), settings, adapters):
            buffer.ack(group)
            logger.warning(
                "grouping_queued chat_id=%s update_ids=%s messages=%d",
                group.chat_id,
                _update_ids(group),
                len(group.messages),
            )
            return
        if group.attempts < settings.message_grouping_max_attempts:
            buffer.release(group, adapters.clock())
            logger.warning(
                "grouping_retry chat_id=%s attempts=%d messages=%d type=%s",
                group.chat_id,
                group.attempts,
                len(group.messages),
                type(exc).__name__,
            )
        else:
            buffer.ack(group)
            logger.error(
                "grouping_discarded reason=max_attempts chat_id=%s update_ids=%s "
                "messages=%d attempts=%d",
                group.chat_id,
                _update_ids(group),
                len(group.messages),
                group.attempts,
            )
        return
    buffer.ack(group)


def _flush_webhook(
    chat_id: int, update_id: int, settings: Settings, adapters: Adapters
) -> bool:
    """Reclama y envía el buffer del chat; False si hay un grupo en vuelo (R20)."""
    buffer = adapters.buffer
    if buffer is None:  # pragma: no cover - el llamador exige buffer
        return True
    if not buffer.pending(chat_id):
        return True
    group = buffer.claim_chat(
        chat_id,
        adapters.clock(),
        settings.message_grouping_lease_seconds,
        settings.message_grouping_buffer_ttl_seconds,
    )
    if group is None:
        logger.warning("grouping_inflight_race update_id=%s", update_id)
        return False
    _send_group(group, settings, adapters)
    return True


def flush_chat(chat_id: int, settings: Settings, adapters: Adapters) -> None:
    """Envía el buffer pendiente del chat si no está reclamado por otro proceso."""
    buffer = adapters.buffer
    if buffer is None:
        return
    if not buffer.pending(chat_id):
        return
    group = buffer.claim_chat(
        chat_id,
        adapters.clock(),
        settings.message_grouping_lease_seconds,
        settings.message_grouping_buffer_ttl_seconds,
    )
    if group is not None:
        _send_group(group, settings, adapters)


def enqueue_text(
    incoming: IncomingUpdate, settings: Settings, adapters: Adapters, forward: Forward
) -> None:
    """Rama de texto del webhook cuando la agrupación está activa.

    El reenvío individual queda fuera del `try`: si no se puede entregar ni
    guardar, el error llega al webhook (503) en vez de reenviarse dos veces.
    """
    buffer = adapters.buffer
    text = incoming.text or ""
    if buffer is None or len(text) > MAX_TEXT_LENGTH:
        _post_single(incoming, adapters, forward)
        return
    new = BufferedMessage(
        update_id=incoming.update_id,
        user_id=incoming.user_id,
        text=text,
        received_at=adapters.clock(),
    )
    try:
        if is_immediate(
            text,
            settings.message_grouping_accept_phrase,
            settings.message_grouping_reject_phrase,
        ):
            _flush_webhook(incoming.chat_id, incoming.update_id, settings, adapters)
        else:
            pending = buffer.pending(incoming.chat_id)
            if not must_flush_before(
                pending, new, settings.message_grouping_max_messages
            ) or _flush_webhook(incoming.chat_id, incoming.update_id, settings, adapters):
                buffer.append(
                    incoming.chat_id,
                    new,
                    settings.message_grouping_window_seconds,
                    settings.message_grouping_max_wait_seconds,
                    settings.message_grouping_buffer_ttl_seconds,
                )
                return
    except Exception as exc:
        logger.error(
            "grouping_redis_error update_id=%s (%s)",
            incoming.update_id,
            type(exc).__name__,
        )
    _post_single(incoming, adapters, forward)


def flush_due(settings: Settings, adapters: Adapters) -> int:
    """Una iteración del worker: reclama y envía los grupos vencidos o con lease caducada."""
    buffer = adapters.buffer
    if buffer is None:
        return 0
    groups = buffer.claim_due(
        adapters.clock(),
        settings.message_grouping_lease_seconds,
        settings.message_grouping_buffer_ttl_seconds,
        DUE_BATCH_LIMIT,
    )
    for group in groups:
        if group.attempts > settings.message_grouping_max_attempts:
            buffer.ack(group)
            logger.error(
                "grouping_discarded reason=max_attempts chat_id=%s update_ids=%s "
                "messages=%d attempts=%d",
                group.chat_id,
                _update_ids(group),
                len(group.messages),
                group.attempts,
            )
            continue
        _send_group(group, settings, adapters)
    return len(groups)


class GroupingWorker:
    """Hilo daemon que vacía los buffers vencidos cada `POLL_SECONDS`."""

    def __init__(self, settings: Settings, adapters: Adapters) -> None:
        self._settings = settings
        self._adapters = adapters
        self._stopped = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stopped.clear()
        self._thread = threading.Thread(
            target=self._run, name="message-grouping", daemon=True
        )
        self._thread.start()

    def stop(self, timeout: float = 5) -> None:
        self._stopped.set()
        thread = self._thread
        if thread is not None:
            thread.join(timeout)
        self._thread = None

    def _run(self) -> None:
        while not self._stopped.is_set():
            try:
                flush_due(self._settings, self._adapters)
            except Exception as exc:
                logger.error("grouping_worker_error type=%s", type(exc).__name__)
            self._stopped.wait(self._settings.message_grouping_poll_seconds)
