"""Entrega de mensajes entrantes al orquestador sin perderlos (fase 2).

Orden: `post_message` → si el orquestador falla de forma transitoria, el mensaje
se guarda en la cola de reintento y se responde `ok` al canal → si tampoco se
puede guardar, `InboundUnavailable` (503) para que el canal lo reenvíe.
Un worker reenvía la cola con espera creciente hasta que el orquestador lo
acepta o el mensaje caduca.
"""
from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from datetime import timedelta

from lazaro_contracts import NormalizedMessage
from pydantic import ValidationError

from .config import Settings
from .domain import Adapters, InboundUnavailable, OrchestratorError

logger = logging.getLogger(__name__)

MAX_REASON_LENGTH = 200


@dataclass(frozen=True)
class ForwardResult:
    forwarded: bool
    queued: bool = False
    reason: str | None = None


def retry_delay_seconds(failures: int, settings: Settings) -> float:
    """Espera antes del siguiente intento: base · 2^fallos, con tope."""
    exponent = min(max(failures, 0), 30)
    return min(
        settings.inbound_retry_base_seconds * (2**exponent),
        settings.inbound_retry_max_delay_seconds,
    )


def queue_for_retry(
    message: NormalizedMessage, reason: str, settings: Settings, adapters: Adapters
) -> None:
    """Guarda el mensaje para reenviarlo; lanza `InboundUnavailable` si no puede."""
    store = adapters.inbound_retry
    now = adapters.clock()
    try:
        if store is None:
            raise RuntimeError("cola de reintento no configurada")
        store.save(
            message,
            reason,
            now,
            now + timedelta(seconds=retry_delay_seconds(0, settings)),
        )
    except Exception as exc:  # noqa: BLE001 - cualquier fallo deja el mensaje sin guardar
        logger.error(
            "inbound_retry_save_failed channel=%s message_id=%s code=%s",
            message.channel,
            message.external_message_id,
            type(exc).__name__,
        )
        raise InboundUnavailable(
            "No se pudo recibir el mensaje; el canal debe reenviarlo."
        ) from None
    logger.warning(
        "inbound_queued channel=%s message_id=%s reason=%s",
        message.channel,
        message.external_message_id,
        reason,
    )


class InboundForwarder:
    def __init__(self, settings: Settings, adapters: Adapters) -> None:
        self._settings = settings
        self._adapters = adapters

    def forward(self, message: NormalizedMessage) -> ForwardResult:
        try:
            self._adapters.orchestrator.post_message(message)
        except ValidationError:
            logger.error(
                "inbound_rejected channel=%s message_id=%s reason=validation_error",
                message.channel,
                message.external_message_id,
            )
            return ForwardResult(forwarded=False, reason="validation_error")
        except OrchestratorError as exc:
            reason = (str(exc) or type(exc).__name__)[:MAX_REASON_LENGTH]
            if not exc.retryable:
                logger.error(
                    "inbound_rejected channel=%s message_id=%s reason=%s",
                    message.channel,
                    message.external_message_id,
                    reason,
                )
                return ForwardResult(forwarded=False, reason=reason)
            queue_for_retry(message, reason, self._settings, self._adapters)
            return ForwardResult(forwarded=False, queued=True, reason=reason)
        return ForwardResult(forwarded=True)


def process_due_retries(settings: Settings, adapters: Adapters) -> int:
    """Una pasada del worker: reenvía los mensajes vencidos. Devuelve cuántos tomó."""
    store = adapters.inbound_retry
    if store is None:
        return 0
    now = adapters.clock()
    rows = store.claim_due(
        now, settings.inbound_retry_lease_seconds, settings.inbound_retry_batch_size
    )
    for row in rows:
        message = row.message
        try:
            adapters.orchestrator.post_message(message)
        except ValidationError:
            store.delete(row.id)
            logger.error(
                "inbound_retry_discarded channel=%s message_id=%s reason=validation_error",
                message.channel,
                message.external_message_id,
            )
            continue
        except OrchestratorError as exc:
            reason = (str(exc) or type(exc).__name__)[:MAX_REASON_LENGTH]
            age = (now - row.created_at).total_seconds()
            if not exc.retryable or age >= settings.inbound_retry_max_age_seconds:
                store.delete(row.id)
                logger.error(
                    "inbound_retry_discarded channel=%s message_id=%s attempts=%d "
                    "reason=%s",
                    message.channel,
                    message.external_message_id,
                    row.attempts,
                    "expired" if exc.retryable else reason,
                )
                continue
            delay = retry_delay_seconds(row.attempts, settings)
            store.reschedule(row.id, now + timedelta(seconds=delay), reason)
            logger.warning(
                "inbound_retry_failed channel=%s message_id=%s attempts=%d next_in=%.0fs",
                message.channel,
                message.external_message_id,
                row.attempts,
                delay,
            )
            continue
        store.delete(row.id)
        logger.info(
            "inbound_retry_delivered channel=%s message_id=%s attempts=%d",
            message.channel,
            message.external_message_id,
            row.attempts,
        )
    return len(rows)


class InboundRetryWorker:
    """Hilo daemon que vacía la cola de reintento cada `INBOUND_RETRY_POLL_SECONDS`."""

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
            target=self._run, name="inbound-retry", daemon=True
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
                process_due_retries(self._settings, self._adapters)
            except Exception as exc:  # noqa: BLE001 - el worker no muere por un fallo
                logger.error("inbound_retry_worker_error code=%s", type(exc).__name__)
            self._stopped.wait(self._settings.inbound_retry_poll_seconds)
