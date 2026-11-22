"""Worker de entrada `procesar_entrantes` (#64, R9-R16)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from orchestrator.adapters.repository import PostgresRepository
from orchestrator.domain import (
    InboundEntry,
    conversation_key,
)
from orchestrator.privacy import notice_sha256
from orchestrator.queue import run_inbox_once

FIXED = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
RECEIVED_AT = "2026-01-02T03:04:00+00:00"


def _legacy(update_id: int = 1, user: int = 10, chat: int = 100) -> dict:
    return {
        "update_id": update_id,
        "telegram_user_id": user,
        "chat_id": chat,
        "text": "Hola",
        "received_at": RECEIVED_AT,
    }


def _channel(message_id: str = "m1") -> dict:
    return {
        "channel": "whatsapp",
        "external_user_id": "57300",
        "external_chat_id": "57300",
        "external_message_id": message_id,
        "kind": "text",
        "text": "Hola",
        "received_at": RECEIVED_AT,
    }


def _enqueue(env, payload: dict, kind: str = "legacy") -> int:
    channel = "telegram" if kind == "legacy" else payload["channel"]
    external = (
        str(payload.get("telegram_user_id", "10"))
        if kind == "legacy"
        else payload["external_user_id"]
    )
    entry = InboundEntry(
        conversation_key=conversation_key(channel, external),
        channel=channel,
        external_user_id=external,
        payload_kind=kind,
        payload=payload,
    )
    assert env.repo.enqueue_inbound(entry, None)
    return max(env.repo.inbox)


def _consent(env, channel: str = "telegram", user: str = "10") -> None:
    env.repo.add_channel_privacy_consent(
        channel,
        user,
        env.settings.privacy_notice_version,
        notice_sha256(env.settings.privacy_notice_text),
        env.adapters.clock(),
    )


def test_claim_sql_is_atomic_and_skips_locked():
    """R9: el reclamo usa FOR UPDATE SKIP LOCKED y una sola sentencia."""
    statements: list[tuple[str, tuple]] = []

    class _Cursor:
        def execute(self, sql, params=()):
            statements.append((sql, tuple(params)))

        def fetchall(self):
            return []

    class _Conn:
        def cursor(self):
            return _Cursor()

        def commit(self):
            pass

        def rollback(self):
            pass

    repo = PostgresRepository("postgresql://x", connect=lambda: _Conn())
    assert repo.claim_inbound(FIXED, 120) is None
    claim_sql = next(sql for sql, _ in statements if sql.startswith("UPDATE inbox"))
    assert "FOR UPDATE SKIP LOCKED" in claim_sql
    assert "NOT EXISTS" in claim_sql
    assert "conversation_key" in claim_sql


def test_order_by_conversation_and_done_clears_payload(env):
    """R10, R12: la cabeza de la conversación va primero; done vacía la carga."""
    _consent(env)
    first = _enqueue(env, _legacy(update_id=1))
    second = _enqueue(env, _legacy(update_id=2))

    row = env.repo.claim_inbound(env.adapters.clock(), 120)
    assert row is not None and row.id == first
    assert env.repo.claim_inbound(env.adapters.clock(), 120) is None

    env.repo.finish_inbound(first, env.adapters.clock())
    assert env.repo.inbox[first]["payload"] == {}
    row2 = env.repo.claim_inbound(env.adapters.clock(), 120)
    assert row2 is not None and row2.id == second


def test_dispatches_legacy_and_channel(env):
    """R11: legacy y channel se enrutan al flujo correspondiente."""
    _consent(env)
    _consent(env, "whatsapp", "57300")
    _enqueue(env, _legacy())
    assert run_inbox_once(env.settings, env.adapters)
    assert env.rag.calls == [("Hola", env.settings.rag_top_k)]
    assert env.repo.inbox[1]["status"] == "done"

    _enqueue(env, _channel("m1"), kind="channel")
    assert run_inbox_once(env.settings, env.adapters)
    assert any(message.role == "user" for message in env.repo.messages)


def test_exception_retries_with_backoff(env):
    """R13: un fallo vuelve a pending con backoff y el código de la excepción."""
    _enqueue(env, {"update_id": 1})
    assert run_inbox_once(env.settings, env.adapters)
    row = env.repo.inbox[1]
    assert row["status"] == "pending"
    assert row["last_error"] == "ValidationError"
    assert row["next_attempt_at"] > env.adapters.clock()


def test_failed_after_max_attempts_clears_payload(env):
    """R14: al agotar intentos queda failed con motivo y sin carga."""
    env.settings.inbox_max_attempts = 1
    _enqueue(env, {"update_id": 1})
    assert run_inbox_once(env.settings, env.adapters)
    row = env.repo.inbox[1]
    assert row["status"] == "failed"
    assert row["last_error"] == "ValidationError"
    assert row["payload"] == {}


def test_expired_lease_is_reclaimed(env):
    """R15: una fila processing con la concesión vencida se reclama y cuenta intento."""
    _consent(env)
    _enqueue(env, _legacy())
    now = [FIXED]
    env.adapters.clock = lambda: now[0]
    claimed = env.repo.claim_inbound(now[0], 5)
    assert claimed is not None and claimed.attempts == 1
    now[0] = now[0] + timedelta(seconds=10)
    assert run_inbox_once(env.settings, env.adapters)
    row = env.repo.inbox[1]
    assert row["status"] == "done"
    assert row["attempts"] == 2


def test_other_conversations_keep_flowing_while_one_retries(env):
    """R16: el reintento de una conversación no bloquea a las demás."""
    _consent(env, "telegram", "10")
    _consent(env, "telegram", "20")
    _enqueue(env, {"update_id": 1})
    good = InboundEntry(
        conversation_key=conversation_key("telegram", "20"),
        channel="telegram",
        external_user_id="20",
        payload_kind="legacy",
        payload=_legacy(update_id=2, user=20, chat=200),
    )
    env.repo.enqueue_inbound(good, None)
    second = max(env.repo.inbox)

    assert run_inbox_once(env.settings, env.adapters)
    assert run_inbox_once(env.settings, env.adapters)
    assert env.repo.inbox[1]["status"] == "pending"
    assert env.repo.inbox[second]["status"] == "done"
