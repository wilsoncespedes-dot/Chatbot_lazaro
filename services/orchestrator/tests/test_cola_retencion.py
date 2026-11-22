"""Retención y supresión de las colas (#64, R38-R39)."""
from __future__ import annotations

from datetime import timedelta

from lazaro_contracts import TextBlock

from orchestrator.domain import (
    InboundEntry,
    OutboxEntry,
    conversation_key,
    destination_key,
)


def _inbound(env, conversation: str = "telegram:10") -> int:
    channel, external = conversation.split(":", 1)
    env.repo.enqueue_inbound(
        InboundEntry(
            conversation_key=conversation,
            channel=channel,
            external_user_id=external,
            payload_kind="legacy",
            payload={"update_id": 1},
        ),
        None,
    )
    return max(env.repo.inbox)


def _outbox(env, destination: str = "100", contact_id: str | None = None) -> int:
    return env.repo.enqueue_outbound(
        OutboxEntry(
            contact_id=contact_id,
            destination_key=destination_key("telegram", destination),
            channel="telegram",
            destination=destination,
            kind="notice",
            blocks=[TextBlock(type="text", text="hola")],
        )
    )


def test_purge_deletes_old_queue_rows_and_reports_counts(env):
    """R38: la purga borra inbox/outbox por antigüedad y reporta sus claves."""
    now = env.adapters.clock()
    cutoff = now - timedelta(days=30)
    inbox_id = _inbound(env)
    outbox_id = _outbox(env)
    env.repo.inbox[inbox_id]["created_at"] = now - timedelta(days=40)
    env.repo.outbox[outbox_id]["created_at"] = now - timedelta(days=40)
    fresh_inbox = _inbound(env, "telegram:20")
    fresh_outbox = _outbox(env, "200")

    deleted = env.repo.purge_personal_data(cutoff, now)

    assert deleted["inbox"] == 1
    assert deleted["outbox"] == 1
    assert inbox_id not in env.repo.inbox
    assert outbox_id not in env.repo.outbox
    assert fresh_inbox in env.repo.inbox
    assert fresh_outbox in env.repo.outbox


def test_delete_contact_content_removes_queues_by_key_contact_and_destination(env):
    """R39: la supresión borra inbox por conversación y outbox por contacto/destino."""
    now = env.adapters.clock()
    contact = env.repo.get_or_create_channel_contact("telegram", "10", "100", now)
    inbox_id = _inbound(env, conversation_key("telegram", "10"))
    other_inbox = _inbound(env, conversation_key("telegram", "20"))
    outbox_id = _outbox(env, "100", contact.id)
    other_outbox = _outbox(env, "200")

    env.repo.delete_contact_content("telegram", "10")

    assert inbox_id not in env.repo.inbox
    assert outbox_id not in env.repo.outbox
    assert other_inbox in env.repo.inbox
    assert other_outbox in env.repo.outbox
