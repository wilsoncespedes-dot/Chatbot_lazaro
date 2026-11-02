"""Tests de los adaptadores de buffer de mensajes (#30)."""
from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone

import pytest

from telegram_gateway.adapters.message_buffer import (
    BUF_PREFIX,
    DUE_KEY,
    INFLIGHT_PREFIX,
    LEASES_KEY,
    FakeMessageBuffer,
    MessageBuffer,
    RedisMessageBuffer,
)
from telegram_gateway.domain import BufferedMessage, ClaimedGroup

NOW = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)


class FakeClock:
    def __init__(self) -> None:
        self.now = NOW

    def __call__(self) -> datetime:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += timedelta(seconds=seconds)


def message(update_id: int, text: str = "hola", received_at: datetime = NOW) -> BufferedMessage:
    return BufferedMessage(update_id, 55, text, received_at)


def test_fake_buffer_satisfies_protocol():
    """R29: el fake cumple el Protocol MessageBuffer."""
    assert isinstance(FakeMessageBuffer(), MessageBuffer)


def test_append_is_idempotent_for_same_update_id():
    """R12: añadir dos veces el mismo update_id deja una sola copia."""
    clock = FakeClock()
    buffer = FakeMessageBuffer(clock=clock)
    assert buffer.append(1, message(1), 2, 8, 300) is True
    assert buffer.append(1, message(1), 2, 8, 300) is False
    assert [m.update_id for m in buffer.pending(1)] == [1]


def test_claim_moves_buffer_and_blocks_a_second_claim():
    """R19: un grupo reclamado no se vuelve a reclamar antes del ack."""
    clock = FakeClock()
    buffer = FakeMessageBuffer(clock=clock)
    buffer.append(1, message(1), 2, 8, 300)
    clock.advance(2)
    claimed = buffer.claim_due(clock.now, 30, 300, 10)
    assert len(claimed) == 1 and claimed[0].attempts == 1
    assert buffer.pending(1) == []
    assert buffer.claim_due(clock.now, 30, 300, 10) == []
    assert buffer.claim_chat(1, clock.now, 30, 300) is None


def test_ack_removes_group_and_release_allows_retry():
    """R21, R23: release conserva intentos y ack elimina el grupo."""
    clock = FakeClock()
    buffer = FakeMessageBuffer(clock=clock)
    buffer.append(1, message(1), 2, 8, 300)
    clock.advance(2)
    claimed = buffer.claim_due(clock.now, 30, 300, 10)[0]
    buffer.release(claimed, clock.now)
    retried = buffer.claim_due(clock.now, 30, 300, 10)
    assert len(retried) == 1 and retried[0].attempts == 2
    assert [m.text for m in retried[0].messages] == ["hola"]
    buffer.ack(retried[0])
    assert buffer.claim_due(clock.now, 30, 300, 10) == []


def test_ack_with_stale_claim_id_does_not_remove_group():
    """R18: un ack de un reclamo anterior no confirma el grupo vigente."""
    clock = FakeClock()
    buffer = FakeMessageBuffer(clock=clock)
    buffer.append(1, message(1), 2, 8, 300)
    clock.advance(2)
    first = buffer.claim_due(clock.now, 30, 300, 10)[0]
    clock.advance(31)
    second = buffer.claim_due(clock.now, 30, 300, 10)[0]
    buffer.ack(first)
    clock.advance(31)
    third = buffer.claim_due(clock.now, 30, 300, 10)
    assert len(third) == 1
    assert third[0].claim_id != second.claim_id
    assert third[0].attempts == 3


def test_lease_expiry_reclaims_with_incremented_attempts():
    """R23: al vencer el lease se vuelve a reclamar sumando un intento."""
    clock = FakeClock()
    buffer = FakeMessageBuffer(clock=clock)
    buffer.append(1, message(1), 2, 8, 300)
    clock.advance(2)
    assert buffer.claim_due(clock.now, 30, 300, 10)[0].attempts == 1
    clock.advance(30)
    assert buffer.claim_due(clock.now, 30, 300, 10)[0].attempts == 2
    clock.advance(30)
    assert buffer.claim_due(clock.now, 30, 300, 10)[0].attempts == 3


def test_ttl_expires_buffer_and_inflight_group():
    """R24: buffer y grupo caducan pasados BUFFER_TTL_SECONDS."""
    clock = FakeClock()
    buffer = FakeMessageBuffer(clock=clock)
    buffer.append(1, message(1), 2, 8, 300)
    clock.advance(301)
    assert buffer.pending(1) == []
    assert buffer.claim_due(clock.now, 30, 300, 10) == []

    buffer.append(1, message(2), 2, 8, 300)
    clock.advance(2)
    assert len(buffer.claim_due(clock.now, 30, 300, 10)) == 1
    clock.advance(301)
    assert buffer.claim_due(clock.now, 30, 300, 10) == []


def test_fake_buffer_fail_raises_connection_error():
    """R29: fail=True lanza ConnectionError en todas las operaciones."""
    buffer = FakeMessageBuffer(fail=True)
    with pytest.raises(ConnectionError):
        buffer.append(1, message(1), 2, 8, 300)
    with pytest.raises(ConnectionError):
        buffer.pending(1)
    with pytest.raises(ConnectionError):
        buffer.claim_chat(1, NOW, 30, 300)
    with pytest.raises(ConnectionError):
        buffer.claim_due(NOW, 30, 300, 10)


class ScriptStub:
    def __init__(self, result=None) -> None:
        self.calls = []
        self.result = result

    def register_script(self, script):
        def call(keys=None, args=None, client=None):
            self.calls.append((keys, args))
            return self.result

        return call


def test_redis_append_passes_ttl_and_keys():
    """R24: RedisMessageBuffer crea buffer y vencimiento con TTL."""
    buffer = RedisMessageBuffer("redis://localhost:6379/0")
    stub = ScriptStub(result=1)
    buffer._client = stub
    assert buffer.append(9, message(4), 2, 8, 300) is True
    keys, args = stub.calls[0]
    assert keys == [f"{BUF_PREFIX}9", DUE_KEY]
    assert args[-1] == 300
    assert args[0] == "4"


def test_redis_claim_chat_passes_ttl():
    """R24: el reclamo renueva el TTL del grupo reclamado."""
    buffer = RedisMessageBuffer("redis://localhost:6379/0")
    stub = ScriptStub(result=None)
    buffer._client = stub
    assert buffer.claim_chat(9, NOW, 30, 300) is None
    keys, args = stub.calls[0]
    assert keys[0] == f"{BUF_PREFIX}9"
    assert args[-1] == 300


def _redis_messages_json(*messages: BufferedMessage) -> str:
    """Misma forma que el `messages_json` que construyen los scripts Lua."""
    return json.dumps(
        [
            {
                "update_id": message.update_id,
                "user_id": message.user_id,
                "text": message.text,
                "received_at": message.received_at.isoformat(),
            }
            for message in messages
        ]
    )


def test_redis_claim_chat_parses_lua_payload():
    """R13: claim_chat interpreta [claim_id, intentos, mensajes] como lo devuelve el Lua."""
    buffer = RedisMessageBuffer("redis://localhost:6379/0")
    messages_json = _redis_messages_json(message(1, "uno"), message(2, "dos"))
    payload = json.dumps(["9:7", 1, messages_json]).encode()
    buffer._client = ScriptStub(result=payload)

    group = buffer.claim_chat(9, NOW, 30, 300)

    assert group is not None
    assert group.chat_id == 9
    assert group.claim_id == "9:7"
    assert group.attempts == 1
    assert [m.update_id for m in group.messages] == [1, 2]
    assert [m.text for m in group.messages] == ["uno", "dos"]


def test_redis_claim_due_parses_lua_payload_for_a_due_buffer():
    """R6, R18: claim_due interpreta [chat, claim_id, intentos, mensajes] del Lua."""
    buffer = RedisMessageBuffer("redis://localhost:6379/0")
    messages_json = _redis_messages_json(message(1, "uno"), message(2, "dos"))
    payload = json.dumps([["9", "9:7", 1, messages_json]]).encode()
    stub = ScriptStub(result=payload)
    buffer._client = stub

    groups = buffer.claim_due(NOW, 30, 300, 100)

    assert len(groups) == 1
    group = groups[0]
    assert group.chat_id == 9
    assert group.claim_id == "9:7"
    assert group.attempts == 1
    assert [m.update_id for m in group.messages] == [1, 2]
    assert [m.text for m in group.messages] == ["uno", "dos"]
    keys, args = stub.calls[0]
    assert keys == [DUE_KEY, LEASES_KEY]
    assert args[:4] == [NOW.timestamp(), 30, 300, 100]


def test_redis_claim_due_parses_expired_lease_with_incremented_attempts():
    """R23: un lease vencido se reclama con el contador de intentos incrementado."""
    buffer = RedisMessageBuffer("redis://localhost:6379/0")
    messages_json = _redis_messages_json(message(3, "texto"), message(4, "más"))
    payload = json.dumps([["10", "10:8", 2, messages_json]])
    buffer._client = ScriptStub(result=payload)

    groups = buffer.claim_due(NOW, 30, 300, 100)

    assert len(groups) == 1
    group = groups[0]
    assert group.chat_id == 10
    assert group.claim_id == "10:8"
    assert group.attempts == 2
    assert [m.update_id for m in group.messages] == [3, 4]
    assert [m.text for m in group.messages] == ["texto", "más"]


def test_redis_claim_due_returns_nothing_for_empty_lua_result():
    """R18: sin grupos reclamados, el Lua devuelve una lista vacía."""
    buffer = RedisMessageBuffer("redis://localhost:6379/0")
    buffer._client = ScriptStub(result=b"[]")

    assert buffer.claim_due(NOW, 30, 300, 100) == []


def test_redis_ack_uses_claim_id_and_keys():
    """R18: ack confirma el grupo vigente con su claim_id e inflight del chat."""
    buffer = RedisMessageBuffer("redis://localhost:6379/0")
    stub = ScriptStub(result=1)
    buffer._client = stub
    group = ClaimedGroup(chat_id=9, claim_id="9:7", attempts=1, messages=(message(1),))

    buffer.ack(group)

    keys, args = stub.calls[0]
    assert keys == [f"{INFLIGHT_PREFIX}9", LEASES_KEY]
    assert args == ["9", "9:7"]


def test_redis_release_keeps_claim_and_reschedules_lease():
    """R21: release reprograma el lease del mismo claim para reintentar."""
    buffer = RedisMessageBuffer("redis://localhost:6379/0")
    stub = ScriptStub(result=1)
    buffer._client = stub
    group = ClaimedGroup(chat_id=9, claim_id="9:7", attempts=1, messages=(message(1),))

    buffer.release(group, NOW)

    keys, args = stub.calls[0]
    assert keys == [f"{INFLIGHT_PREFIX}9", LEASES_KEY]
    assert args == ["9", "9:7", NOW.timestamp()]


@pytest.mark.integration
@pytest.mark.skipif(
    not os.environ.get("REDIS_TEST_URL"),
    reason="T18 opcional: requiere REDIS_TEST_URL apuntando a un Redis real",
)
def test_redis_message_buffer_against_real_redis():
    """R18, R23 (T18 opcional): reclamo atómico y lease con Redis real."""
    redis = pytest.importorskip("redis")
    client = redis.Redis.from_url(os.environ["REDIS_TEST_URL"])
    client.flushdb()
    buffer = RedisMessageBuffer(os.environ["REDIS_TEST_URL"])
    try:
        assert buffer.append(1, message(1, "a"), 2, 8, 300) is True
        assert buffer.append(1, message(2, "b"), 2, 8, 300) is True
        assert buffer.append(1, message(2, "b"), 2, 8, 300) is False
        due = NOW + timedelta(seconds=2)
        claimed = buffer.claim_due(due, 30, 300, 10)
        assert len(claimed) == 1
        assert [m.text for m in claimed[0].messages] == ["a", "b"]
        assert buffer.claim_due(due, 30, 300, 10) == []
        buffer.ack(claimed[0])
        assert buffer.claim_due(due, 30, 300, 10) == []
    finally:
        client.flushdb()
