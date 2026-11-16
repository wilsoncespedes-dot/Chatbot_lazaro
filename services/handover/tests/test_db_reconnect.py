"""Reconexión a Postgres tras reiniciar la base (conexión guardada rota)."""
from __future__ import annotations

import pytest

from handover.adapters import repository as repo_module
from handover.adapters.repository import PostgresCaseRepository, is_connection_error


class _Cursor:
    def __init__(self, conn):
        self.conn = conn

    def execute(self, sql, params=()):
        if self.conn.broken:
            raise BrokenPipeError(32, "Broken pipe")
        self.conn.executed.append(sql)

    def fetchall(self):
        return []

    def fetchone(self):
        return None


class _Conn:
    def __init__(self):
        self.broken = False
        self.closed = False
        self.executed: list[str] = []

    def cursor(self):
        return _Cursor(self)

    def commit(self):
        if self.broken:
            raise BrokenPipeError(32, "Broken pipe")

    def rollback(self):
        if self.broken:
            raise BrokenPipeError(32, "Broken pipe")

    def close(self):
        self.closed = True


@pytest.fixture
def connections():
    return []


@pytest.fixture
def repo(connections):
    def connect():
        conn = _Conn()
        connections.append(conn)
        return conn

    return PostgresCaseRepository("postgresql://x", connect=connect)


def test_connection_error_classification():
    assert is_connection_error(BrokenPipeError())
    assert is_connection_error(ConnectionResetError())
    assert not is_connection_error(ValueError("sql"))


def test_broken_connection_is_discarded_and_next_call_reconnects(repo, connections):
    repo._run("SELECT 1", ())
    connections[0].broken = True
    with pytest.raises(BrokenPipeError):
        repo._run("SELECT 2", ())
    assert connections[0].closed
    repo._run("SELECT 3", ())
    assert len(connections) == 2
    assert "SELECT 3" in connections[1].executed


def test_idle_connection_is_probed_and_replaced_when_dead(repo, connections, monkeypatch):
    now = [1000.0]
    monkeypatch.setattr(repo_module.time, "monotonic", lambda: now[0])
    repo._run("SELECT 1", ())
    connections[0].broken = True
    now[0] += repo_module.IDLE_PROBE_SECONDS + 1
    repo._run("SELECT 2", ())
    assert len(connections) == 2
    assert "SELECT 2" in connections[1].executed


def test_recent_connection_is_not_probed(repo, connections, monkeypatch):
    now = [1000.0]
    monkeypatch.setattr(repo_module.time, "monotonic", lambda: now[0])
    repo._run("SELECT 1", ())
    before = list(connections[0].executed)
    now[0] += 1
    repo._run("SELECT 2", ())
    assert connections[0].executed == before + ["SELECT 2"]


def test_sql_errors_keep_the_connection(repo, connections):
    repo._run("SELECT 1", ())

    def failing_execute(sql, params=()):
        raise ValueError("error de SQL")

    original = _Cursor.execute
    _Cursor.execute = lambda self, sql, params=(): failing_execute(sql, params)
    try:
        with pytest.raises(ValueError):
            repo._run("SELECT mal", ())
    finally:
        _Cursor.execute = original
    assert not connections[0].closed
    repo._run("SELECT 2", ())
    assert len(connections) == 1
