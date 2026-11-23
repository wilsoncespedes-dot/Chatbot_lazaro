"""Fase 2: cola de reintento del gateway contra Postgres real (TEST_DATABASE_URL)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from lazaro_contracts import NormalizedMessage

from migrations.testing import migrated_database, database_url_for_tests
from telegram_gateway.adapters.inbound_retry import PostgresInboundRetryStore

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not database_url_for_tests(),
        reason="requiere TEST_DATABASE_URL con un Postgres local desechable",
    ),
]

NOW = datetime(2026, 11, 23, 10, 0, tzinfo=timezone.utc)


def _message(message_id: str = "10", text: str = "hola") -> NormalizedMessage:
    return NormalizedMessage(
        channel="telegram",
        external_user_id="55",
        external_chat_id="77",
        external_message_id=message_id,
        kind="text",
        text=text,
        received_at=NOW,
    )


@pytest.fixture
def store():
    with migrated_database() as url:
        yield PostgresInboundRetryStore(url)


def test_save_is_idempotent_and_claim_respects_schedule_and_lease(store):
    store.save(_message(), "caído", NOW, NOW + timedelta(seconds=2))
    store.save(_message(text="copia"), "caído", NOW, NOW + timedelta(seconds=2))

    assert store.claim_due(NOW, 60, 10) == []
    later = NOW + timedelta(seconds=2)
    [row] = store.claim_due(later, 60, 10)
    assert (row.message.text, row.attempts) == ("hola", 1)
    # Reclamado con lease: otro worker no lo toma mientras dure.
    assert store.claim_due(later, 60, 10) == []

    store.reschedule(row.id, later + timedelta(seconds=4), "sigue caído")
    assert store.claim_due(later + timedelta(seconds=3), 60, 10) == []
    [again] = store.claim_due(later + timedelta(seconds=4), 60, 10)
    assert again.attempts == 2

    store.delete(again.id)
    assert store.claim_due(later + timedelta(days=1), 60, 10) == []
