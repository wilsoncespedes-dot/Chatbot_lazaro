"""Fase 2: un solo flujo de entrada y ninguna respuesta doble.

- Un mismo mensaje del canal reenviado (Redis caído en el gateway) produce una
  sola respuesta: la barrera es el índice único (canal, id externo) del inbox.
- El contrato histórico de Telegram entra al mismo flujo que los demás canales.
- Si el proceso directo del consentimiento falla, la reserva se borra y el
  reintento del gateway se procesa.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from lazaro_contracts import NormalizedMessage

import orchestrator.domain as domain
from orchestrator.domain import DedupKey, InboundEntry
from migrations.testing import database_url_for_tests, migrated_database

HEADERS = {"X-Service-Token": "svc-token"}
NOW = datetime(2026, 11, 23, 10, 0, tzinfo=timezone.utc)


def _canonical(text: str, message_id: str, user: str = "10", channel: str = "telegram"):
    return {
        "channel": channel,
        "external_user_id": user,
        "external_chat_id": "100" if channel == "telegram" else user,
        "external_message_id": message_id,
        "kind": "text",
        "text": text,
        "received_at": "2026-01-02T03:04:00+00:00",
    }


def _replies(env) -> int:
    return len(env.gateway.sent) + len(env.gateway.channel_sent) + len(env.gateway.blocks_sent)


def test_legacy_flow_was_removed():
    assert not hasattr(domain, "process_message")
    assert not hasattr(domain, "_legacy_consent_gate")


def test_same_message_twice_with_consent_answers_once(env):
    first = env.post(text="¿Cómo instalo el módulo?", update_id=7)
    replies = _replies(env)
    second = env.post(text="¿Cómo instalo el módulo?", update_id=7)
    assert first.json() == {"status": "accepted"}
    assert second.json() == {"status": "duplicate"}
    assert _replies(env) == replies
    assert len(env.llm.calls) == 1


@pytest.mark.parametrize("channel", ["telegram", "whatsapp"])
def test_same_message_twice_before_consent_sends_one_notice(env, channel):
    """Sin clave de dedup (R7) el índice del inbox sigue frenando la copia."""
    from fakes import drain_queues

    counts = []
    for _ in range(2):
        env.client.post(
            "/messages",
            json=_canonical("Hola", "dup-1", user="57300", channel=channel),
            headers=HEADERS,
        )
        drain_queues(env.settings, env.adapters)
        counts.append(_replies(env))
    assert counts[0] >= 1
    assert counts[1] == counts[0]


def test_legacy_and_canonical_copies_of_the_same_update_are_one_message(env):
    """`MessageRequest(update_id=5)` y el canónico ("telegram", "5") son el mismo."""
    env.post(text="hola", update_id=5)
    response = env.client.post(
        "/messages", json=_canonical("hola", "5"), headers=HEADERS
    )
    assert response.json() == {"status": "duplicate"}


def test_failed_direct_consent_is_released_for_the_gateway_retry(env, monkeypatch):
    env.present()
    accept = _canonical(env.settings.consent_accept_phrase, "accept-1")
    real = domain.process_channel_message
    calls = {"n": 0}

    def flaky(message, settings, adapters):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("fallo al guardar la evidencia")
        return real(message, settings, adapters)

    import orchestrator.main as main_module

    monkeypatch.setattr(main_module, "process_channel_message", flaky)
    client = TestClient(env.client.app, raise_server_exceptions=False)
    first = client.post("/messages", json=accept, headers=HEADERS)
    assert first.status_code == 500
    assert not any(
        row.get("external_message_id") == "accept-1" for row in env.repo.inbox.values()
    )
    second = client.post("/messages", json=accept, headers=HEADERS)
    assert second.json() == {"status": "accepted"}
    assert len(env.repo.privacy_consents) == 1


# ── Postgres real (TEST_DATABASE_URL) ───────────────────────────────────────


@pytest.mark.integration
@pytest.mark.skipif(
    not database_url_for_tests(),
    reason="requiere TEST_DATABASE_URL con un Postgres local desechable",
)
def test_postgres_inbox_unique_index_blocks_copies_and_release_allows_retry():
    from orchestrator.adapters.repository import PostgresRepository

    message = NormalizedMessage(
        channel="whatsapp",
        external_user_id="57300",
        external_chat_id="57300",
        external_message_id="wamid.1",
        kind="text",
        text="hola",
        received_at=NOW,
    )

    def entry(msg_id: str) -> InboundEntry:
        return InboundEntry(
            conversation_key="whatsapp:57300",
            channel="whatsapp",
            external_user_id="57300",
            payload_kind="channel",
            payload=message.model_copy(update={"external_message_id": msg_id}).model_dump(
                mode="json"
            ),
            external_message_id=msg_id,
        )

    with migrated_database() as url:
        repo = PostgresRepository(url)
        # Sin clave de dedup (antes del consentimiento): el índice manda.
        assert repo.enqueue_inbound(entry("wamid.1"), None) is True
        assert repo.enqueue_inbound(entry("wamid.1"), None) is False
        # Con clave de dedup: la marca se revierte si el índice rechaza.
        dedup = DedupKey(kind="message", channel="whatsapp", external_message_id="wamid.1")
        assert repo.enqueue_inbound(entry("wamid.1"), dedup) is False
        assert repo.mark_message_if_new("whatsapp", "wamid.1") is True

        dedup2 = DedupKey(kind="message", channel="whatsapp", external_message_id="wamid.2")
        row_id = repo.begin_direct_inbound(entry("wamid.2"), dedup2, NOW, 60)
        assert row_id is not None
        assert repo.begin_direct_inbound(entry("wamid.2"), dedup2, NOW, 60) is None
        repo.abandon_inbound(row_id, dedup2)
        again = repo.begin_direct_inbound(entry("wamid.2"), dedup2, NOW, 60)
        assert again is not None
        repo.finish_inbound(again, NOW)
        # El worker no vuelve a tomar la fila directa ya terminada.
        later = datetime.now(timezone.utc) + timedelta(minutes=1)
        claimed = repo.claim_inbound(later, 60)
        assert claimed is not None and claimed.payload["external_message_id"] == "wamid.1"
        repo.finish_inbound(claimed.id, later)
        assert repo.claim_inbound(later, 60) is None
