"""R31–R35 (#65): `canal_id` en contactos y mensajes, y su migración idempotente."""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone

from orchestrator.adapters.repository import FakeRepository, PostgresRepository
from migrations import section

_SCHEMA = section("orchestrator: tablas")
_INDEXES = section("orchestrator: índices")
_MIGRATIONS = section("orchestrator: migraciones aditivas previas")

NOW = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
CANAL_ID_STATEMENTS = [statement for statement in _MIGRATIONS if "canal_id" in statement]


def test_fake_contact_and_message_store_canal_id():
    """R31, R32: alta de contacto y mensaje con canal_id igual al canal del contacto."""
    repo = FakeRepository()
    simulado = repo.get_or_create_channel_contact("simulado", "u-1", "d-1", NOW)
    legacy = repo.get_or_create_contact(10, 100, NOW)
    repo.add_message(simulado.id, "user", "hola", NOW)
    repo.add_message(legacy.id, "user", "hola", NOW)
    assert repo.contact_canal_ids[simulado.id] == "simulado"
    assert [m.canal_id for m in repo.messages] == ["simulado", "telegram"]


class _Cursor:
    def __init__(self, log: list) -> None:
        self.log = log
        self.rows: list[tuple] = []

    def execute(self, sql, params=()):
        self.log.append((sql, tuple(params or ())))
        if sql.startswith("SELECT id, channel"):
            self.rows = [("c1", params[0], params[1], "d-1", None, None)]
        elif sql.startswith("SELECT id, telegram_user_id"):
            self.rows = [("c1", params[0], 100)]
        else:
            self.rows = []

    def fetchall(self):
        return self.rows

    def fetchone(self):
        return self.rows[0] if self.rows else None


class _Conn:
    def __init__(self, log: list) -> None:
        self.log = log

    def cursor(self):
        return _Cursor(self.log)

    def commit(self):
        pass

    def rollback(self):
        pass

    def close(self):
        pass


def _postgres(log: list) -> PostgresRepository:
    return PostgresRepository(
        "postgresql://x", connect=lambda: _Conn(log), new_id=lambda: "c1"
    )


def test_postgres_inserts_write_canal_id():
    """R31, R32: los INSERT de contactos y mensajes escriben canal_id."""
    log: list = []
    repo = _postgres(log)
    repo.get_or_create_channel_contact("simulado", "u-1", "d-1", NOW)
    repo.get_or_create_contact(10, 100, NOW)
    repo.add_message("c1", "user", "hola", NOW)
    repo.add_message("c1", "advisor", "hola", NOW)
    contacts = [(sql, p) for sql, p in log if sql.startswith("INSERT INTO contacts")]
    assert len(contacts) == 2
    assert all("canal_id" in sql for sql, _ in contacts)
    assert contacts[0][1][-1] == "simulado"
    assert contacts[1][1][-1] == "telegram"
    messages = [(sql, p) for sql, p in log if sql.startswith("INSERT INTO messages")]
    assert len(messages) == 2
    for sql, params in messages:
        assert "canal_id" in sql
        assert "(SELECT channel FROM contacts WHERE id = %s)" in sql
        assert params[-1] == "c1"


class _MigrationState:
    """Simula las sentencias de canal_id sobre filas en memoria."""

    def __init__(self) -> None:
        self.columns = {"contacts": set(), "messages": set()}
        self.indexes: set[str] = set()
        self.contacts = {
            "c-tg": {"id": "c-tg", "channel": "telegram", "telegram_user_id": 10, "chat_id": 100},
            "c-wa": {"id": "c-wa", "channel": "whatsapp", "telegram_user_id": None, "chat_id": None},
        }
        self.messages = [
            {"id": 1, "contact_id": "c-tg", "role": "user", "text": "hola", "at": NOW},
            {"id": 2, "contact_id": "c-wa", "role": "bot", "text": "buenas", "at": NOW},
        ]
        self.updated_rows = 0

    def execute(self, sql: str) -> None:
        if sql.startswith("ALTER TABLE contacts ADD COLUMN IF NOT EXISTS canal_id"):
            if "canal_id" not in self.columns["contacts"]:
                self.columns["contacts"].add("canal_id")
                for row in self.contacts.values():
                    row["canal_id"] = None
        elif sql.startswith("ALTER TABLE messages ADD COLUMN IF NOT EXISTS canal_id"):
            if "canal_id" not in self.columns["messages"]:
                self.columns["messages"].add("canal_id")
                for row in self.messages:
                    row["canal_id"] = None
        elif sql.startswith("UPDATE contacts SET canal_id = channel WHERE canal_id IS NULL"):
            for row in self.contacts.values():
                if row["canal_id"] is None:
                    row["canal_id"] = row["channel"]
                    self.updated_rows += 1
        elif sql.startswith("UPDATE messages SET canal_id = c.channel FROM contacts c"):
            assert "messages.canal_id IS NULL" in sql
            for row in self.messages:
                if row["canal_id"] is None:
                    row["canal_id"] = self.contacts[row["contact_id"]]["channel"]
                    self.updated_rows += 1
        elif sql.startswith("CREATE INDEX IF NOT EXISTS messages_canal_id"):
            self.indexes.add("messages_canal_id")
        else:  # pragma: no cover - el filtro solo deja sentencias de canal_id
            raise AssertionError(sql)


def test_migration_backfills_canal_id_from_contact_channel():
    """R33, R35: rellena canal_id sin tocar otras columnas ni el número de filas."""
    state = _MigrationState()
    before_contacts = deepcopy(state.contacts)
    before_messages = deepcopy(state.messages)
    for statement in CANAL_ID_STATEMENTS:
        state.execute(statement)
    assert {k: v["canal_id"] for k, v in state.contacts.items()} == {
        "c-tg": "telegram",
        "c-wa": "whatsapp",
    }
    assert [m["canal_id"] for m in state.messages] == ["telegram", "whatsapp"]
    assert len(state.contacts) == len(before_contacts)
    assert len(state.messages) == len(before_messages)
    for key, row in state.contacts.items():
        assert {k: v for k, v in row.items() if k != "canal_id"} == before_contacts[key]
    for row, before in zip(state.messages, before_messages):
        assert {k: v for k, v in row.items() if k != "canal_id"} == before
    assert "messages_canal_id" in state.indexes


def test_second_migration_run_changes_nothing():
    """R34: la segunda ejecución no modifica filas ni falla."""
    state = _MigrationState()
    for statement in CANAL_ID_STATEMENTS:
        state.execute(statement)
    snapshot = (deepcopy(state.contacts), deepcopy(state.messages))
    state.updated_rows = 0
    for statement in CANAL_ID_STATEMENTS:
        state.execute(statement)
    assert state.updated_rows == 0
    assert (state.contacts, state.messages) == snapshot


def test_canal_id_statements_are_additive_and_last():
    """R33: solo ADD COLUMN IF NOT EXISTS, UPDATE de NULL e índice IF NOT EXISTS, al final."""
    assert len(CANAL_ID_STATEMENTS) == 5
    assert list(_MIGRATIONS[-5:]) == CANAL_ID_STATEMENTS
    for statement in CANAL_ID_STATEMENTS:
        assert "DROP" not in statement and "DELETE" not in statement
        if statement.startswith("UPDATE"):
            assert "canal_id IS NULL" in statement
