"""Cola de entrada y outbox en Postgres: procesar entrantes y enviar salientes (#64)."""
from __future__ import annotations

import logging
from datetime import timedelta

from lazaro_contracts import (
    MessageRequest,
    NormalizedMessage,
    ResponseBlock,
    normalize_legacy_message,
)
from pydantic import TypeAdapter

from .config import Settings
from .domain import (
    Adapters,
    OUTBOX_OUT_OF_WINDOW,
    ChannelOutOfWindow,
    ChannelRejected,
    InboundQueueRow,
    ServiceUnavailable,
    compute_backoff,
    process_channel_message,
)

logger = logging.getLogger(__name__)

_BLOCK_ADAPTER = TypeAdapter(ResponseBlock)


def process_inbound(
    row: InboundQueueRow, settings: Settings, adapters: Adapters
) -> None:
    """R11: despacha la carga guardada al flujo único (fase 2).

    Las filas `legacy` encoladas antes del despliegue se convierten al mensaje
    canónico con la misma identidad de Telegram.
    """
    if row.payload_kind == "legacy":
        message = normalize_legacy_message(MessageRequest.model_validate(row.payload))
    else:
        message = NormalizedMessage.model_validate(row.payload)
    process_channel_message(message, settings, adapters)


def run_inbox_once(settings: Settings, adapters: Adapters) -> bool:
    """Reclama y procesa una fila; nunca deja salir la excepción del bucle."""
    repository = adapters.repository
    row = repository.claim_inbound(adapters.clock(), settings.worker_lease_seconds)
    if row is None:
        return False
    try:
        process_inbound(row, settings, adapters)
    except Exception as exc:  # noqa: BLE001 - un fallo no debe parar el worker
        code = type(exc).__name__
        now = adapters.clock()
        if row.attempts >= settings.inbox_max_attempts:
            repository.fail_inbound(row.id, now, code)
        else:
            delay = compute_backoff(
                row.attempts,
                settings.inbox_backoff_base_seconds,
                settings.outbox_backoff_max_seconds,
                settings.outbox_backoff_jitter,
            )
            repository.retry_inbound(
                row.id, now + timedelta(seconds=delay), code
            )
        # R41: solo id de fila, canal y nombre de la excepción.
        logger.error("inbox_failed id=%s channel=%s code=%s", row.id, row.channel, code)
        return True
    repository.finish_inbound(row.id, adapters.clock())
    return True


def run_outbox_once(settings: Settings, adapters: Adapters) -> bool:
    """Reclama una fila y la entrega al gateway; nunca deja salir la excepción."""
    repository = adapters.repository
    row = repository.claim_outbound(adapters.clock(), settings.worker_lease_seconds)
    if row is None:
        return False
    try:
        blocks = [_BLOCK_ADAPTER.validate_python(block) for block in row.blocks]
        adapters.gateway.send_channel_blocks(row.channel, row.destination, blocks)
    except ChannelOutOfWindow:
        # Fase 7: no se reintenta ni cuenta como fallo del canal; queda a la vista
        # con su propio estado para reenviarla por plantilla o por un asesor.
        repository.fail_outbound(
            row.id, adapters.clock(), "ChannelOutOfWindow", status=OUTBOX_OUT_OF_WINDOW
        )
        logger.warning("outbox_fuera_de_ventana id=%s channel=%s", row.id, row.channel)
        return True
    except ChannelRejected:
        repository.fail_outbound(row.id, adapters.clock(), "ChannelRejected")
        logger.error("outbox_failed id=%s channel=%s code=ChannelRejected", row.id, row.channel)
        return True
    except ServiceUnavailable as exc:
        code = type(exc).__name__
        now = adapters.clock()
        if row.attempts >= settings.outbox_max_attempts:
            repository.fail_outbound(row.id, now, code)
        else:
            delay = compute_backoff(
                row.attempts,
                settings.outbox_backoff_base_seconds,
                settings.outbox_backoff_max_seconds,
                settings.outbox_backoff_jitter,
            )
            repository.retry_outbound(row.id, now + timedelta(seconds=delay), code)
        logger.error("outbox_failed id=%s channel=%s code=%s", row.id, row.channel, code)
        return True
    except Exception as exc:  # noqa: BLE001 - una fila corrupta no para el worker
        code = type(exc).__name__
        repository.fail_outbound(row.id, adapters.clock(), code)
        logger.error("outbox_failed id=%s channel=%s code=%s", row.id, row.channel, code)
        return True
    repository.finish_outbound(row.id, adapters.clock())
    return True
