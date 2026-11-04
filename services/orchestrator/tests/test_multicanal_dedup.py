"""Deduplicación multicanal del orquestador: clave (canal, mensaje externo) (#36)."""
from __future__ import annotations

import threading
from datetime import datetime, timezone

from orchestrator.adapters.repository import FakeRepository, PostgresRepository
from orchestrator.privacy import notice_sha256

SERVICE_TOKEN = "svc-token"
HEADERS = {"X-Service-Token": SERVICE_TOKEN}
RECEIVED_AT = "2026-11-03T16:05:12Z"
FIXED_NOW = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)


def _consent(env, channel: str, external_user_id: str) -> None:
    env.repo.add_channel_privacy_consent(
        channel,
        external_user_id,
        env.settings.privacy_notice_version,
        notice_sha256(env.settings.privacy_notice_text),
        FIXED_NOW,
    )


# ── R5, R6: repositorio ─────────────────────────────────────────────────────


def test_same_channel_same_external_id_is_duplicate():
    """R5: el mismo par (canal, mensaje externo) se procesa una sola vez."""
    repo = FakeRepository()
    assert repo.mark_message_if_new("whatsapp", "m1") is True
    assert repo.mark_message_if_new("whatsapp", "m1") is False


def test_same_external_id_in_two_channels_is_not_duplicate():
    """R6: el identificador solo es único dentro de su canal."""
    repo = FakeRepository()
    assert repo.mark_message_if_new("telegram", "1") is True
    assert repo.mark_message_if_new("whatsapp", "1") is True
    assert repo.mark_message_if_new("telegram", "1") is False
    assert repo.mark_message_if_new("whatsapp", "1") is False


def test_legacy_update_id_uses_telegram_channel_key():
    """R5: el payload histórico sigue usando update_id como clave Telegram."""
    repo = FakeRepository()
    assert repo.mark_update_if_new(7) is True
    assert repo.mark_message_if_new("telegram", "7") is False
    assert repo.mark_message_if_new("whatsapp", "7") is True
    assert repo.processed == {7}


def test_dedup_is_atomic_under_concurrency():
    """R5: dos hilos con la misma clave no procesan dos veces."""
    repo = FakeRepository()
    results: list[bool] = []
    barrier = threading.Barrier(2)

    def worker():
        barrier.wait(timeout=5)
        results.append(repo.mark_message_if_new("whatsapp", "concurrente"))

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=5)

    assert sorted(results) == [False, True]


def test_postgres_dedup_uses_composite_parameters():
    """R5, R6: el SQL persiste el canal y el id externo de forma parametrizada."""
    class Cursor:
        def __init__(self, log):
            self.log = log

        def execute(self, sql, params=()):
            self.log.append((sql, tuple(params)))

        def fetchall(self):
            return [("external_message_id",)]

    class Conn:
        def __init__(self):
            self.log: list = []

        def cursor(self):
            return Cursor(self.log)

        def commit(self):
            pass

        def rollback(self):
            pass

    conn = Conn()
    repo = PostgresRepository("postgresql://x", connect=lambda: conn)
    assert repo.mark_message_if_new("whatsapp", "m1") is True
    assert any(
        "processed_messages" in sql and params == ("whatsapp", "m1")
        for sql, params in conn.log
    )
    assert "m1" not in " ".join(sql for sql, _ in conn.log)


def test_postgres_honors_legacy_processed_updates():
    """R5: las filas históricas de `processed_updates` siguen descartando repetidos."""
    class Cursor:
        def __init__(self, state):
            self.state = state
            self._rows: list = []

        def execute(self, sql, params=()):
            self._rows = []
            if "INSERT INTO processed_messages" in sql and "processed_updates" in sql:
                key = (params[0], params[1])
                if params[2] in self.state["legacy"] or key in self.state["processed"]:
                    return
                self.state["processed"].add(key)
                self._rows = [(params[1],)]
            elif "INSERT INTO processed_messages" in sql and "VALUES" in sql:
                key = tuple(params)
                if key in self.state["processed"]:
                    self._rows = []
                else:
                    self.state["processed"].add(key)
                    self._rows = [(params[1],)]

        def fetchall(self):
            return self._rows

    class Conn:
        def __init__(self):
            self.state = {"legacy": {5, 6}, "processed": set()}

        def cursor(self):
            return Cursor(self.state)

        def commit(self):
            pass

        def rollback(self):
            pass

    conn = Conn()
    repo = PostgresRepository("postgresql://x", connect=lambda: conn)
    assert repo.mark_message_if_new("telegram", "5") is False
    assert repo.mark_message_if_new("telegram", "6") is False
    assert repo.mark_message_if_new("telegram", "7") is True
    assert repo.mark_message_if_new("whatsapp", "5") is True
    assert conn.state["legacy"] == {5, 6}


def test_postgres_legacy_update_writes_only_processed_updates():
    """R22: el payload legacy no escribe `processed_messages` ni identidad."""
    class Cursor:
        def __init__(self, state):
            self.state = state
            self._rows: list = []

        def execute(self, sql, params=()):
            self._rows = []
            self.state["sql"].append((sql, tuple(params)))
            if not sql.startswith("INSERT INTO processed_updates"):
                return
            update_id = params[0]
            if (
                update_id in self.state["updates"]
                or (params[1], params[2]) in self.state["messages"]
            ):
                return
            self.state["updates"].add(update_id)
            self._rows = [(update_id,)]

        def fetchall(self):
            return self._rows

    class Conn:
        def __init__(self, state):
            self.state = state

        def cursor(self):
            return Cursor(self.state)

        def commit(self):
            pass

        def rollback(self):
            pass

    state = {"updates": set(), "messages": set(), "sql": []}
    repo = PostgresRepository("postgresql://x", connect=lambda: Conn(state))

    assert repo.mark_update_if_new(9) is True
    assert repo.mark_update_if_new(9) is False

    statements = [sql for sql, _ in state["sql"]]
    legacy_sql = next(
        sql for sql in statements if sql.startswith("INSERT INTO processed_updates")
    )
    assert state["updates"] == {9}
    assert not any(sql.startswith("INSERT INTO processed_messages") for sql in statements)
    assert "9" not in legacy_sql

    state["messages"].add(("telegram", "10"))
    assert repo.mark_update_if_new(10) is False


# ── R5, R6: ruta POST /messages ─────────────────────────────────────────────


def _canonical(channel: str, external_id: str = "77", **changes):
    data = {
        "channel": channel,
        "external_user_id": "10" if channel == "telegram" else "57300",
        "external_chat_id": "100" if channel == "telegram" else "57300",
        "external_message_id": external_id,
        "kind": "text",
        "text": "hola",
        "received_at": RECEIVED_AT,
    }
    data.update(changes)
    return data


def test_messages_accepts_canonical_and_detects_duplicate(env):
    """R5: POST /messages acepta NormalizedMessage y descarta el duplicado."""
    _consent(env, "whatsapp", "57300")
    first = env.client.post("/messages", json=_canonical("whatsapp"), headers=HEADERS)
    second = env.client.post("/messages", json=_canonical("whatsapp"), headers=HEADERS)
    assert first.status_code == 202 and first.json() == {"status": "accepted"}
    assert second.status_code == 202 and second.json() == {"status": "duplicate"}
    assert ("whatsapp", "77") in env.repo.processed_messages


def test_messages_processes_same_id_once_per_channel(env):
    """R6: el mismo id externo por dos canales se procesa una vez en cada uno."""
    _consent(env, "telegram", "10")
    _consent(env, "whatsapp", "57300")
    telegram = env.client.post("/messages", json=_canonical("telegram"), headers=HEADERS)
    whatsapp = env.client.post("/messages", json=_canonical("whatsapp"), headers=HEADERS)
    assert telegram.json() == {"status": "accepted"}
    assert whatsapp.json() == {"status": "accepted"}
    assert ("telegram", "77") in env.repo.processed_messages
    assert ("whatsapp", "77") in env.repo.processed_messages


def test_legacy_payload_still_deduplicates_by_update_id(env):
    """R5: el payload histórico conserva su comportamiento de idempotencia."""
    first = env.post(update_id=9)
    second = env.post(update_id=9)
    assert first.json() == {"status": "accepted"}
    assert second.json() == {"status": "duplicate"}
