"""R12–R18, R39: buzón del canal simulado (falso y PostgreSQL)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from telegram_gateway.adapters.mailbox import (
    FakeMailboxRepository,
    PostgresMailboxRepository,
)
from telegram_gateway.adapters.dedup import FakeDedupStore
from telegram_gateway.adapters.orchestrator import FakeOrchestratorClient
from telegram_gateway.adapters.telegram import FakeTelegramClient
from telegram_gateway.config import Settings
from telegram_gateway.domain import Adapters
from telegram_gateway.main import build_default_adapters, create_app

NOW = datetime(2026, 11, 21, 15, 0, tzinfo=timezone.utc)
CHANNEL = "tiktok-simulado"
OTHER_CHANNEL = "otro-simulado"


class _Cursor:
    def __init__(self, conn: "_Connection") -> None:
        self.conn = conn
        self.rows: list[tuple] = []

    def execute(self, sql, params=()):
        if self.conn.broken:
            raise BrokenPipeError("connection lost")
        values = tuple(params or ())
        self.conn.log.append((sql, values))
        normalized = " ".join(sql.split())
        if normalized.startswith(("CREATE TABLE", "CREATE INDEX")) or (
            "pg_advisory_xact_lock" in normalized
        ):
            self.rows = []
        elif normalized.startswith("INSERT INTO buzon_simulado"):
            self.conn.next_id += 1
            channel_id, destination, kind, text, created_at = values
            self.conn.rows.append(
                (self.conn.next_id, channel_id, destination, kind, text, created_at)
            )
            self.rows = [(self.conn.next_id,)]
        elif normalized.startswith("DELETE FROM buzon_simulado WHERE canal_id") and (
            "creado_en <" in normalized
        ):
            channel_id, cutoff = values
            self.conn.rows = [
                row
                for row in self.conn.rows
                if not (row[1] == channel_id and row[5] < cutoff)
            ]
            self.rows = []
        elif normalized.startswith("DELETE FROM buzon_simulado WHERE canal_id") and (
            "OFFSET" in normalized
        ):
            channel_id, _, max_entries = values
            channel_rows = [row for row in self.conn.rows if row[1] == channel_id]
            excess = len(channel_rows) - int(max_entries)
            keep = {row[0] for row in channel_rows[excess:]}
            self.conn.rows = [
                row
                for row in self.conn.rows
                if row[1] != channel_id or row[0] in keep
            ]
            self.rows = []
        elif normalized.startswith("SELECT"):
            channel_id, after_id, cutoff = values[0], values[1], values[2]
            destination = values[3] if len(values) == 5 else None
            limit = values[-1]
            rows = [
                row
                for row in self.conn.rows
                if row[1] == channel_id
                and row[0] > after_id
                and row[5] >= cutoff
                and (destination is None or row[2] == destination)
            ]
            self.rows = sorted(rows)[: int(limit)]
        else:
            self.rows = []

    def fetchall(self):
        return self.rows

    def fetchone(self):
        return self.rows[0] if self.rows else None


class _Connection:
    def __init__(self) -> None:
        self.log: list[tuple[str, tuple]] = []
        self.rows: list[tuple] = []
        self.next_id = 0
        self.broken = False
        self.closed = False

    def cursor(self) -> _Cursor:
        return _Cursor(self)

    def commit(self) -> None:
        if self.broken:
            raise BrokenPipeError("connection lost")

    def rollback(self) -> None:
        pass

    def close(self) -> None:
        self.closed = True


def _postgres(
    connections: list[_Connection],
    *,
    retention: int = 3600,
    max_entries: int = 500,
) -> PostgresMailboxRepository:
    def connect() -> _Connection:
        conn = _Connection()
        connections.append(conn)
        return conn

    return PostgresMailboxRepository(
        "postgresql://test",
        retention,
        max_entries,
        connect=connect,
        clock=lambda: 100.0,
    )


def _append_all(repo, now=NOW) -> None:
    repo.append(CHANNEL, "cliente-demo", "client", "uno", now)
    repo.append(CHANNEL, "cliente-otro", "reply", "dos", now)
    repo.append(OTHER_CHANNEL, "cliente-demo", "client", "tres", now)


def test_fake_mailbox_orders_filters_and_isolates_channels():
    """R12: ids crecientes, `after`, filtro por destino y aislamiento por canal."""
    repo = FakeMailboxRepository()
    _append_all(repo)
    all_entries = repo.list(CHANNEL, None, 0, 100, NOW)
    assert [entry.id for entry in all_entries] == [1, 2]
    assert [entry.text for entry in all_entries] == ["uno", "dos"]
    assert [entry.kind for entry in all_entries] == ["client", "reply"]
    assert [entry.id for entry in repo.list(CHANNEL, None, 1, 100, NOW)] == [2]
    filtered = repo.list(CHANNEL, "cliente-demo", 0, 100, NOW)
    assert [entry.text for entry in filtered] == ["uno"]
    assert [entry.channel for entry in all_entries] == [CHANNEL, CHANNEL]
    assert [entry.text for entry in repo.list(OTHER_CHANNEL, None, 0, 100, NOW)] == [
        "tres"
    ]


def test_fake_mailbox_retention_uses_the_controlled_clock():
    """R13: una entrada de 3600 s se conserva y una de 3601 s ya no se devuelve."""
    repo = FakeMailboxRepository(retention_seconds=3600)
    repo.append(CHANNEL, "cliente-demo", "client", "antigua", NOW)
    fresh = NOW + timedelta(seconds=3600)
    repo.append(CHANNEL, "cliente-demo", "reply", "viva", fresh)
    assert [entry.text for entry in repo.list(CHANNEL, None, 0, 100, NOW)] == [
        "antigua",
        "viva",
    ]
    assert [
        entry.text
        for entry in repo.list(CHANNEL, None, 0, 100, NOW + timedelta(seconds=3600))
    ] == ["antigua", "viva"]
    assert [
        entry.text
        for entry in repo.list(CHANNEL, None, 0, 100, NOW + timedelta(seconds=3601))
    ] == ["viva"]


def test_fake_mailbox_keeps_at_most_max_entries_per_channel():
    """R14: al superar el tope se eliminan las entradas más antiguas del canal."""
    repo = FakeMailboxRepository(max_entries=10)
    for index in range(12):
        repo.append(CHANNEL, "cliente-demo", "reply", f"m{index}", NOW)
    repo.append(OTHER_CHANNEL, "cliente-demo", "reply", "otro", NOW)
    texts = [entry.text for entry in repo.list(CHANNEL, None, 0, 100, NOW)]
    assert texts == [f"m{index}" for index in range(2, 12)]
    assert [entry.text for entry in repo.list(OTHER_CHANNEL, None, 0, 100, NOW)] == [
        "otro"
    ]


def test_postgres_mailbox_creates_schema_reconnects_and_parameterizes_sql():
    """R15, R17: sin DDL al conectar (lo crea el runner), parámetros %s y reconexión."""
    connections: list[_Connection] = []
    repo = _postgres(connections)
    _append_all(repo)
    assert [entry.text for entry in repo.list(CHANNEL, None, 0, 100, NOW)] == [
        "uno",
        "dos",
    ]
    from migrations import section

    statements = [sql for sql, _ in connections[0].log]
    assert not any(sql.startswith(("CREATE", "ALTER")) for sql in statements)
    ddl = section("telegram_gateway: buzón simulado")
    assert any(sql.startswith("CREATE TABLE IF NOT EXISTS buzon_simulado") for sql in ddl)
    assert any("CREATE INDEX IF NOT EXISTS buzon_simulado_canal_id" in sql for sql in ddl)
    operations = [
        (sql, params)
        for sql, params in connections[0].log
        if not sql.startswith(("CREATE", "SELECT 1"))
    ]
    for sql, params in operations:
        assert sql.count("%s") == len(params), sql
        assert "cliente-demo" not in sql
    inserts = [sql for sql, _ in operations if sql.startswith("INSERT INTO buzon_simulado")]
    assert inserts
    for sql in inserts:
        assert "secreto" not in sql.lower()
        assert "firma" not in sql.lower()
        assert "encabezado" not in sql.lower()
    assert all(
        set(("canal_id", "destino", "tipo", "texto", "creado_en")).issubset(
            set(column.strip() for column in sql.split("(")[1].split(")")[0].split(","))
        )
        for sql in inserts
    )

    connections[0].broken = True
    with pytest.raises(BrokenPipeError):
        repo.append(CHANNEL, "cliente-demo", "reply", "fallo", NOW)
    assert connections[0].closed
    repo.append(CHANNEL, "cliente-demo", "reply", "nueva", NOW)
    assert len(connections) == 2


def test_fake_and_postgres_mailbox_behave_the_same():
    """R12: el falso en memoria reproduce el comportamiento del PostgreSQL."""
    connections: list[_Connection] = []
    fake = FakeMailboxRepository()
    postgres = _postgres(connections)
    for repo in (fake, postgres):
        _append_all(repo)
    for arguments in (
        (CHANNEL, None, 0, 100),
        (CHANNEL, "cliente-demo", 0, 100),
        (CHANNEL, None, 1, 100),
    ):
        assert fake.list(*arguments, NOW) == postgres.list(*arguments, NOW)


def test_fake_mailbox_can_simulate_failures():
    """R10: el falso permite simular un fallo del almacén."""
    repo = FakeMailboxRepository(fail=True)
    with pytest.raises(OSError):
        repo.append(CHANNEL, "cliente-demo", "client", "hola", NOW)
    with pytest.raises(OSError):
        repo.list(CHANNEL, None, 0, 100, NOW)


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("simulated_mailbox_retention_seconds", 59),
        ("simulated_mailbox_retention_seconds", 86401),
        ("simulated_mailbox_max_entries", 9),
        ("simulated_mailbox_max_entries", 5001),
    ],
)
def test_settings_reject_mailbox_values_outside_their_range(name, value):
    """R18: los dos ajustes validan su rango al construir Settings."""
    with pytest.raises(ValidationError):
        Settings(**{name: value})


def test_env_example_declares_mailbox_settings_with_test_only_note():
    """R39: .env.example declara los dos ajustes y avisa que es solo de pruebas."""
    from pathlib import Path

    text = (Path(__file__).resolve().parents[3] / ".env.example").read_text(
        encoding="utf-8"
    )
    assert "SIMULATED_MAILBOX_RETENTION_SECONDS=3600" in text
    assert "SIMULATED_MAILBOX_MAX_ENTRIES=500" in text
    assert "solo pruebas" in text.lower()


def test_default_composition_uses_postgres_and_tests_fall_back_to_fake():
    """R16: producción usa Postgres y create_app inyecta el falso si falta."""
    assert isinstance(
        build_default_adapters(Settings()).mailbox, PostgresMailboxRepository
    )
    adapters = Adapters(
        telegram=FakeTelegramClient(),
        dedup=FakeDedupStore(),
        orchestrator=FakeOrchestratorClient(),
        clock=lambda: NOW,
        mailbox=None,
    )
    create_app(
        Settings(
            service_token="token",
            telegram_webhook_secret="webhook-secret",
            telegram_bot_token="123456:BOT",
        ),
        adapters,
    )
    assert isinstance(adapters.mailbox, FakeMailboxRepository)
