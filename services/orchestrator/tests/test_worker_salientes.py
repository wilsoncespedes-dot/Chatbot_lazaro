"""Worker de salida `enviar_salientes` (#64, R22-R28)."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import pytest
from lazaro_contracts import TextBlock

from orchestrator.domain import (
    OutboxEntry,
    compute_backoff,
    destination_key,
)
from orchestrator.queue import run_outbox_once
from migrations.testing import database_url_for_tests, migrated_database

FIXED = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)


def _enqueue(env, destination: str = "100", text: str = "Hola", kind: str = "notice") -> int:
    entry = OutboxEntry(
        contact_id=None,
        destination_key=destination_key("telegram", destination),
        channel="telegram",
        destination=destination,
        kind=kind,
        blocks=[TextBlock(type="text", text=text)],
    )
    return env.repo.enqueue_outbound(entry)


def test_delivers_and_marks_sent(env):
    """R22: entrega con send_channel_blocks y vacía los bloques."""
    row_id = _enqueue(env)
    assert run_outbox_once(env.settings, env.adapters)
    row = env.repo.outbox[row_id]
    assert row["status"] == "sent"
    assert row["blocks"] == []
    assert env.gateway.blocks_sent[-1][0:2] == ("telegram", "100")


def test_backoff_is_exponential_with_jitter_and_cap():
    """R23: min(tope, base*2^(n-1)) con jitter multiplicativo."""
    assert compute_backoff(1, 2, 300, 0.5, rng=lambda: 0.5) == 2
    assert compute_backoff(3, 2, 300, 0.5, rng=lambda: 0.5) == 8
    assert compute_backoff(20, 2, 300, 0.5, rng=lambda: 0.5) == 300
    assert compute_backoff(1, 2, 300, 0.5, rng=lambda: 0.0) == 1
    assert compute_backoff(1, 2, 300, 0.5, rng=lambda: 1.0) == 3


def test_transient_failure_returns_pending(env):
    """R23: un fallo transitorio vuelve a pending con next_attempt_at."""
    row_id = _enqueue(env)
    env.gateway.fail = True
    assert run_outbox_once(env.settings, env.adapters)
    row = env.repo.outbox[row_id]
    assert row["status"] == "pending"
    assert row["last_error"] == "ServiceUnavailable"
    assert row["next_attempt_at"] > env.adapters.clock()


def test_failed_after_max_attempts(env):
    """R24: al agotar intentos queda failed con el nombre de la excepción."""
    env.settings.outbox_max_attempts = 1
    row_id = _enqueue(env)
    env.gateway.fail = True
    assert run_outbox_once(env.settings, env.adapters)
    row = env.repo.outbox[row_id]
    assert row["status"] == "failed"
    assert row["last_error"] == "ServiceUnavailable"


def test_channel_rejected_is_not_retried(env):
    """R25: un 422 del canal marca failed sin reintentar."""
    row_id = _enqueue(env)
    env.gateway.reject_channel = True
    assert run_outbox_once(env.settings, env.adapters)
    row = env.repo.outbox[row_id]
    assert row["status"] == "failed"
    assert row["last_error"] == "ChannelRejected"
    assert row["attempts"] == 1


def test_window_closed_is_left_fuera_de_ventana_and_logged(env, caplog):
    """Fase 7: 422 channel_window_closed deja la fila en fuera_de_ventana, sin reintento."""
    row_id = _enqueue(env)
    env.gateway.window_closed = True
    with caplog.at_level("WARNING", logger="orchestrator.queue"):
        assert run_outbox_once(env.settings, env.adapters)
    row = env.repo.outbox[row_id]
    assert row["status"] == "fuera_de_ventana"
    assert row["last_error"] == "ChannelOutOfWindow"
    assert row["attempts"] == 1
    assert row["locked_until"] is None
    assert f"outbox_fuera_de_ventana id={row_id} channel=telegram" in caplog.text
    # No vuelve a reclamarse ni aparece como envío fallido del panel.
    env.gateway.window_closed = False
    assert not run_outbox_once(env.settings, env.adapters)
    assert env.repo.list_failed_outbound(10) == []


def test_order_by_destination(env):
    """R26: una fila anterior no terminal bloquea a las posteriores del destino."""
    first = _enqueue(env, text="uno")
    second = _enqueue(env, text="dos")
    env.gateway.fail = True
    assert run_outbox_once(env.settings, env.adapters)
    assert env.repo.outbox[first]["status"] == "pending"
    assert run_outbox_once(env.settings, env.adapters) is False
    assert env.repo.outbox[second]["status"] == "pending"

    env.gateway.fail = False
    env.repo.fail_outbound(first, env.adapters.clock(), "ServiceUnavailable")
    assert run_outbox_once(env.settings, env.adapters)
    assert env.repo.outbox[second]["status"] == "sent"


def test_concurrent_workers_deliver_each_row_once(env):
    """R27: varias instancias no entregan dos veces la misma fila."""
    for index in range(20):
        _enqueue(env, destination=f"sala-{index}")

    def drain() -> int:
        delivered = 0
        while run_outbox_once(env.settings, env.adapters):
            delivered += 1
        return delivered

    with ThreadPoolExecutor(max_workers=8) as executor:
        total = sum(executor.map(lambda _: drain(), range(8)))

    assert total == 20
    assert len(env.gateway.blocks_sent) == 20
    assert all(row["status"] == "sent" for row in env.repo.outbox.values())


def test_expired_sending_lease_is_redelivered(env):
    """R28: una fila sending con concesión vencida se reenvía."""
    row_id = _enqueue(env)
    now = [FIXED]
    env.adapters.clock = lambda: now[0]
    claimed = env.repo.claim_outbound(now[0], 5)
    assert claimed is not None and claimed.id == row_id
    now[0] = now[0] + timedelta(seconds=10)
    assert run_outbox_once(env.settings, env.adapters)
    row = env.repo.outbox[row_id]
    assert row["status"] == "sent"
    assert row["attempts"] == 2


# ── Postgres real (TEST_DATABASE_URL) ───────────────────────────────────────


@pytest.mark.integration
@pytest.mark.skipif(
    not database_url_for_tests(),
    reason="requiere TEST_DATABASE_URL con un Postgres local desechable",
)
def test_postgres_fail_outbound_can_leave_row_fuera_de_ventana():
    """Fase 7: el estado se guarda en Postgres y la fila no vuelve a reclamarse."""
    from orchestrator.adapters.repository import PostgresRepository

    with migrated_database() as url:
        repo = PostgresRepository(url)
        now = datetime.now(timezone.utc)
        row_id = repo.enqueue_outbound(
            OutboxEntry(
                contact_id=None,
                destination_key=destination_key("facebook", "psid-1"),
                channel="facebook",
                destination="psid-1",
                kind="reply",
                blocks=[TextBlock(type="text", text="Hola")],
            )
        )
        claimed = repo.claim_outbound(now + timedelta(seconds=1), 60)
        assert claimed is not None and claimed.id == row_id
        repo.fail_outbound(
            row_id, now, "ChannelOutOfWindow", status="fuera_de_ventana"
        )
        assert repo.claim_outbound(now + timedelta(minutes=5), 60) is None
        assert repo.list_failed_outbound(10) == []
        rows = repo._run(
            "SELECT status, last_error FROM outbox WHERE id = %s", (row_id,), fetch=True
        )
        assert [tuple(row) for row in rows] == [("fuera_de_ventana", "ChannelOutOfWindow")]
