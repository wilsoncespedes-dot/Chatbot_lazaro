"""R27–R31: persistencia parametrizada, reconexión, healthcheck y siembra."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from telegram_gateway.adapters.channel_repository import (
    IDLE_PROBE_SECONDS,
    ChannelChanges,
    FakeChannelRepository,
    PostgresChannelRepository,
)
from telegram_gateway.domain import ChannelRecord, ChannelSeed

NOW = datetime(2026, 11, 21, 15, 0, tzinfo=timezone.utc)
SEED = ChannelSeed("telegram", "Telegram", "telegram", "telegram", "#1B6FA8")
ROW = (
    "telegram",
    "Telegram",
    "telegram",
    "telegram",
    "#1B6FA8",
    {"region": "demo"},
    True,
    NOW,
    True,
    True,
)


class _Cursor:
    def __init__(self, conn: "_Connection") -> None:
        self.conn = conn
        self.rows: list[tuple] = []

    def execute(self, sql, params=()):
        if self.conn.broken:
            raise BrokenPipeError("connection lost")
        values = tuple(params or ())
        self.conn.log.append((sql, values))
        if sql == "SELECT 1":
            self.rows = [(1,)]
        elif "SELECT config_secreta FROM canales" in sql:
            self.rows = [(self.conn.secret,)] if self.conn.secret is not None else []
        elif "AS has_secrets" in sql:
            self.rows = list(self.conn.record_rows)
        elif "RETURNING id" in sql:
            self.rows = [(values[0] if "INSERT INTO" in sql else values[-1],)]
        else:
            self.rows = []

    def fetchall(self):
        return self.rows

    def fetchone(self):
        return self.rows[0] if self.rows else None


class _Connection:
    def __init__(self) -> None:
        self.log: list[tuple[str, tuple]] = []
        self.record_rows: list[tuple] = [ROW]
        self.secret: str | None = "encrypted-token"
        self.broken = False
        self.closed = False
        self.commits = 0
        self.rollbacks = 0

    def cursor(self) -> _Cursor:
        return _Cursor(self)

    def commit(self) -> None:
        if self.broken:
            raise BrokenPipeError("connection lost")
        self.commits += 1

    def rollback(self) -> None:
        self.rollbacks += 1

    def close(self) -> None:
        self.closed = True


def _repo(connections: list[_Connection], *, clock=None) -> PostgresChannelRepository:
    def connect() -> _Connection:
        conn = _Connection()
        connections.append(conn)
        return conn

    return PostgresChannelRepository("postgresql://test", connect=connect, clock=clock)


def _record(**changes) -> ChannelRecord:
    values = {
        "id": "canal-demo",
        "name": "Canal demo",
        "adapter_type": "simulado",
        "icon": "chat",
        "color": "#1B6FA8",
        "config": {"publico": "si"},
        "active": True,
        "created_at": NOW,
        "has_secrets": True,
        "active_follows_environment": False,
    }
    values.update(changes)
    return ChannelRecord(**values)


def test_postgres_repository_creates_schema_and_migration_columns_on_connect():
    """R27: la primera conexión crea canales y añade columnas idempotentemente."""
    connections: list[_Connection] = []
    repo = _repo(connections)
    assert repo.list_channels() == [
        ChannelRecord(
            id="telegram",
            name="Telegram",
            adapter_type="telegram",
            icon="telegram",
            color="#1B6FA8",
            config={"region": "demo"},
            active=True,
            created_at=NOW,
            has_secrets=True,
            active_follows_environment=True,
        )
    ]
    statements = [sql for sql, _ in connections[0].log]
    assert any(sql.startswith("CREATE TABLE IF NOT EXISTS canales") for sql in statements)
    assert any(
        "ADD COLUMN IF NOT EXISTS config_secreta" in sql for sql in statements
    )
    assert any(
        "ADD COLUMN IF NOT EXISTS activo_segun_entorno" in sql for sql in statements
    )
    assert len([sql for sql in statements if sql.startswith("CREATE TABLE")]) == 1


def test_postgres_channel_queries_keep_values_in_parameters_and_hide_secret_column():
    """R27: CRUD parametriza valores y list/get solo consultan si hay secretos."""
    connections: list[_Connection] = []
    repo = _repo(connections)
    malicious = "'; DROP TABLE canales; --"
    assert repo.list_channels()
    assert repo.get("telegram") is not None
    assert repo.get_encrypted_secrets("telegram") == "encrypted-token"
    assert repo.create(_record(config={"public": malicious}), "ciphertext") is True
    assert repo.update("telegram", ChannelChanges(name=malicious)) is not None
    assert repo.set_active("telegram", False) is not None
    assert repo.set_encrypted_secrets("telegram", "new-ciphertext") is True

    statements = [
        (sql, params)
        for sql, params in connections[0].log
        if not sql.startswith(("CREATE", "ALTER", "SELECT 1"))
    ]
    assert any("ON CONFLICT (id) DO NOTHING" in sql for sql, _ in statements)
    assert any("IS NOT NULL) AS has_secrets" in sql for sql, _ in statements)
    assert not any("SELECT config_secreta FROM canales" in sql for sql, _ in statements[:-5])
    for sql, params in statements:
        assert sql.count("%s") == len(params), sql
        assert malicious not in sql
    assert any(malicious in str(params) for _, params in statements)


def test_seed_inserts_missing_rows_and_resynchronizes_only_environment_rows():
    """R29–R31: seed usa ON CONFLICT y UPDATE condicionado por la marca de entorno."""
    connections: list[_Connection] = []
    repo = _repo(connections)
    repo.seed([(SEED, False)])
    operations = [sql for sql, _ in connections[0].log]
    insert = next(sql for sql in operations if sql.startswith("INSERT INTO canales"))
    update = next(sql for sql in operations if sql.startswith("UPDATE canales SET activo"))
    assert "ON CONFLICT (id) DO NOTHING" in insert
    assert "activo_segun_entorno" in insert
    assert "AND activo_segun_entorno" in update
    assert "IS DISTINCT FROM %s" in update
    assert connections[0].commits >= 2


def test_postgres_repository_discards_connection_error_and_reconnects_next_call():
    """R28: un error OSError descarta la conexión y la siguiente operación reconecta."""
    connections: list[_Connection] = []
    repo = _repo(connections)
    repo._run("SELECT 1")
    connections[0].broken = True
    with pytest.raises(BrokenPipeError):
        repo._run("SELECT 2")
    assert connections[0].closed
    repo._run("SELECT 3")
    assert len(connections) == 2
    assert "SELECT 3" in [sql for sql, _ in connections[1].log]


def test_idle_failed_probe_discards_connection_before_next_query():
    """R28: tras diez segundos, un SELECT 1 fallido fuerza una conexión nueva."""
    now = [100.0]
    connections: list[_Connection] = []
    repo = _repo(connections, clock=lambda: now[0])
    repo._run("SELECT 1")
    connections[0].broken = True
    now[0] += IDLE_PROBE_SECONDS + 1
    repo._run("SELECT 2")
    assert len(connections) == 2
    assert connections[0].closed
    assert "SELECT 2" in [sql for sql, _ in connections[1].log]


def test_health_check_uses_independent_connection_and_timeout():
    """R28: health_check consulta SELECT 1 en otra conexión y la cierra."""
    main = _Connection()
    health = _Connection()
    timeouts: list[float] = []
    repo = PostgresChannelRepository(
        "postgresql://test",
        connect=lambda: main,
        connect_health=lambda timeout: (timeouts.append(timeout) or health),
    )
    repo.health_check(1.25)
    assert repo._conn is None
    assert timeouts == [1.25]
    assert [sql for sql, _ in health.log] == ["SELECT 1"]
    assert health.closed


def test_fake_repository_seed_semantics_are_idempotent_and_environment_aware():
    """R29–R31: el fake crea faltantes, sincroniza activación y respeta cambios manuales."""
    now = [NOW]
    repository = FakeChannelRepository(clock=lambda: now[0])
    repository.seed([(SEED, False)])
    initial = repository.get(SEED.id)
    assert initial is not None and initial.active is False
    assert initial.active_follows_environment is True

    now[0] = NOW.replace(minute=1)
    repository.seed([(SEED, True)])
    active = repository.get(SEED.id)
    assert active is not None and active.active is True
    assert active.created_at == NOW
    repository.set_active(SEED.id, False)
    manual = repository.get(SEED.id)
    assert manual is not None and manual.active_follows_environment is False
    repository.seed([(SEED, True)])
    assert repository.get(SEED.id) == manual
    assert len(repository.list_channels()) == 1


def test_fake_repository_keeps_secrets_separate_from_channel_records():
    """R27: el fake guarda el token por separado y los records solo reflejan has_secrets."""
    repository = FakeChannelRepository()
    assert repository.create(_record(has_secrets=False), None)
    assert repository.set_encrypted_secrets("canal-demo", "ciphertext")
    assert repository.get_encrypted_secrets("canal-demo") == "ciphertext"
    record = repository.get("canal-demo")
    assert record is not None and record.has_secrets is True
    assert "ciphertext" not in repr(repository)
    assert "ciphertext" not in repr(record)


def test_fake_repository_can_simulate_store_and_health_failures():
    """R28: el fake permite fallos de consultas y de health_check."""
    repository = FakeChannelRepository(fail=True)
    with pytest.raises(OSError):
        repository.list_channels()
    unhealthy = FakeChannelRepository(health_ok=False)
    with pytest.raises(OSError):
        unhealthy.health_check(1.0)
