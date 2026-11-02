"""Tests del candado de la conexión compartida de PostgresRepository (sin Postgres)."""
from __future__ import annotations

import threading
import time
from datetime import datetime, timezone

import pytest

from orchestrator.adapters.repository import _SCHEMA, PostgresRepository

NOW = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)


def test_postgres_repository_serializes_statements_across_threads():
    """R1, R2: dos hilos nunca usan la conexión a la vez y el candado está tomado."""
    state = {"inside": 0, "max": 0, "locked": [], "errors": []}
    repo_holder: dict[str, PostgresRepository] = {}

    class Cursor:
        def __init__(self) -> None:
            self.sql = ""

        def execute(self, sql, params=()):
            self.sql = sql
            state["inside"] += 1
            state["max"] = max(state["max"], state["inside"])
            state["locked"].append(repo_holder["repo"]._lock.locked())
            time.sleep(0.002)
            state["inside"] -= 1

        def fetchall(self):
            if "FROM messages" in self.sql:
                return [("user", "hola", NOW)]
            return [("c1", 10, 100)]

    class Conn:
        def cursor(self):
            return Cursor()

        def commit(self):
            pass

        def rollback(self):
            pass

    repo = PostgresRepository("postgresql://x", connect=lambda: Conn(), new_id=lambda: "nuevo")
    repo_holder["repo"] = repo
    barrier = threading.Barrier(2)

    def worker():
        try:
            barrier.wait(timeout=5)
            for _ in range(5):
                repo.add_event("c1", "rag_answer", "chunks_found", NOW)
                repo.last_messages("c1", 10)
                repo.mark_update_if_new(1)
                repo.get_or_create_contact(10, 100, NOW)
        except Exception as exc:  # pragma: no cover - solo falla el test
            state["errors"].append(exc)

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=5)

    assert state["errors"] == []
    assert all(not thread.is_alive() for thread in threads)
    assert state["max"] == 1
    assert state["locked"] and all(state["locked"])


def test_postgres_repository_connects_once_with_concurrent_first_use():
    """R3: el primer uso concurrente abre una sola conexión y crea el esquema una vez."""
    calls = []
    statements: list[str] = []
    errors = []

    class Cursor:
        def execute(self, sql, params=()):
            statements.append(sql)

        def fetchall(self):
            return [("c1", 10, 100)]

    class Conn:
        def cursor(self):
            return Cursor()

        def commit(self):
            pass

        def rollback(self):
            pass

    conn = Conn()

    def connect():
        calls.append(1)
        time.sleep(0.01)
        return conn

    repo = PostgresRepository("postgresql://x", connect=connect)
    barrier = threading.Barrier(2)

    def worker():
        try:
            barrier.wait(timeout=5)
            repo.get_or_create_contact(10, 100, NOW)
        except Exception as exc:  # pragma: no cover - solo falla el test
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=5)

    assert errors == []
    assert all(not thread.is_alive() for thread in threads)
    assert calls == [1]
    assert sum(sql.startswith("CREATE TABLE") for sql in statements) == len(_SCHEMA)


def test_postgres_repository_releases_lock_after_error():
    """R4: el error hace rollback, se propaga y el candado queda libre para otro hilo."""
    rollbacks = []
    fail = {"pending": True}

    class Cursor:
        def execute(self, sql, params=()):
            if sql.startswith("INSERT INTO events") and fail["pending"]:
                fail["pending"] = False
                raise RuntimeError("boom")

        def fetchall(self):
            return [("user", "hola", NOW)]

    class Conn:
        def cursor(self):
            return Cursor()

        def commit(self):
            pass

        def rollback(self):
            rollbacks.append(1)

    repo = PostgresRepository("postgresql://x", connect=lambda: Conn())

    with pytest.raises(RuntimeError):
        repo.add_event("c1", "rag_answer", "chunks_found", NOW)

    assert rollbacks == [1]
    assert repo._lock.locked() is False

    finished = []

    def worker():
        repo.last_messages("c1", 10)
        finished.append(1)

    thread = threading.Thread(target=worker)
    thread.start()
    thread.join(timeout=5)
    assert not thread.is_alive()
    assert finished == [1]
