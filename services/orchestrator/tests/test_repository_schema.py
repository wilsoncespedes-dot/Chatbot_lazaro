"""Esquema Postgres y migración idempotente de identidad por canal (#36)."""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone

from orchestrator.adapters.repository import (
    PostgresRepository,
    _INDEXES,
    _MIGRATIONS,
    _SCHEMA,
)

NOW = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)


class _MigrationCursor:
    def __init__(self, state: dict) -> None:
        self.state = state

    def execute(self, sql: str, params=()) -> None:
        self.state["statements"].append(sql)
        if sql.startswith("ALTER TABLE contacts ALTER COLUMN telegram_user_id DROP NOT NULL"):
            self.state["nullable_contacts"] = True
        elif sql.startswith("ALTER TABLE contacts ALTER COLUMN chat_id DROP NOT NULL"):
            self.state["nullable_chat"] = True
        elif sql.startswith("UPDATE contacts SET channel = 'telegram'"):
            for row in self.state["contacts"].values():
                if row["channel"] is None:
                    row["channel"] = "telegram"
        elif sql.startswith("UPDATE contacts SET external_user_id"):
            for row in self.state["contacts"].values():
                if row["external_user_id"] is None and row["telegram_user_id"] is not None:
                    row["external_user_id"] = str(row["telegram_user_id"])
        elif sql.startswith("UPDATE contacts SET external_chat_id"):
            for row in self.state["contacts"].values():
                if row["external_chat_id"] is None and row["chat_id"] is not None:
                    row["external_chat_id"] = str(row["chat_id"])
        elif sql.startswith("ALTER TABLE privacy_consents ALTER COLUMN telegram_user_id"):
            self.state["nullable_consent"] = True
        elif sql.startswith("UPDATE privacy_consents SET channel = 'telegram'"):
            for row in self.state["consents"]:
                if row["channel"] is None:
                    row["channel"] = "telegram"
        elif sql.startswith("UPDATE privacy_consents SET external_user_id"):
            for row in self.state["consents"]:
                if row["external_user_id"] is None and row["telegram_user_id"] is not None:
                    row["external_user_id"] = str(row["telegram_user_id"])
        elif "contacts_channel_external_user" in sql:
            self.state["contact_index"] = True
        elif "privacy_consents_channel_user_version" in sql:
            self.state["consent_index"] = True

    def fetchall(self):
        return []


class _MigrationConn:
    def __init__(self, state: dict) -> None:
        self.state = state

    def cursor(self):
        return _MigrationCursor(self.state)

    def commit(self) -> None:
        pass

    def rollback(self) -> None:
        pass


def _legacy_state() -> dict:
    return {
        "contacts": {
            "c1": {
                "id": "c1",
                "telegram_user_id": 10,
                "chat_id": 100,
                "channel": None,
                "external_user_id": None,
                "external_chat_id": None,
            },
            "c2": {
                "id": "c2",
                "telegram_user_id": 11,
                "chat_id": 101,
                "channel": None,
                "external_user_id": None,
                "external_chat_id": None,
            },
        },
        "messages": [
            {
                "id": 1,
                "contact_id": "c1",
                "role": "user",
                "text": "Hola",
                "at": NOW,
            },
            {
                "id": 2,
                "contact_id": "c1",
                "role": "bot",
                "text": "Respuesta",
                "at": NOW,
            },
        ],
        "case_links": [
            {"case_id": "case-1", "contact_id": "c1", "created_at": NOW}
        ],
        "consents": [
            {
                "telegram_user_id": 10,
                "channel": None,
                "external_user_id": None,
                "notice_version": "v1",
                "notice_sha256": "hash-10",
                "accepted_at": NOW,
            }
        ],
        "statements": [],
    }


def _migrate(state: dict) -> None:
    repo = PostgresRepository(
        "postgresql://x", connect=lambda: _MigrationConn(state), run_migrations=True
    )
    repo.ensure_schema()


def test_legacy_contacts_are_backfilled_preserving_ids_and_relations():
    """R17: el backfill asigna canal y ids externos sin cambiar ids de contacto."""
    state = _legacy_state()
    messages_before = deepcopy(state["messages"])
    links_before = deepcopy(state["case_links"])

    _migrate(state)

    assert state["contacts"]["c1"]["id"] == "c1"
    assert state["contacts"]["c1"]["channel"] == "telegram"
    assert state["contacts"]["c1"]["external_user_id"] == "10"
    assert state["contacts"]["c1"]["external_chat_id"] == "100"
    assert state["contacts"]["c2"]["external_user_id"] == "11"
    assert state["nullable_contacts"] is True
    assert state["nullable_chat"] is True
    assert state["contact_index"] is True
    assert state["messages"] == messages_before
    assert state["case_links"] == links_before
    assert {
        message["contact_id"] for message in state["messages"]
    } <= set(state["contacts"])
    assert {
        link["contact_id"] for link in state["case_links"]
    } <= set(state["contacts"])


def test_legacy_consents_are_backfilled_without_losing_version_hash_or_date():
    """R18: el consentimiento histórico conserva versión, hash y fecha."""
    state = _legacy_state()

    _migrate(state)

    [consent] = state["consents"]
    assert (consent["channel"], consent["external_user_id"]) == ("telegram", "10")
    assert consent["notice_version"] == "v1"
    assert consent["notice_sha256"] == "hash-10"
    assert consent["accepted_at"] == NOW
    assert state["nullable_consent"] is True
    assert state["consent_index"] is True


def test_migration_is_idempotent_when_run_more_than_once():
    """R17, R18: ejecutar el backfill otra vez no duplica ni reescribe datos."""
    state = _legacy_state()

    _migrate(state)
    first_contacts = deepcopy(state["contacts"])
    first_consents = deepcopy(state["consents"])
    first_messages = deepcopy(state["messages"])
    first_links = deepcopy(state["case_links"])

    _migrate(state)

    assert state["contacts"] == first_contacts
    assert state["consents"] == first_consents
    assert state["messages"] == first_messages
    assert state["case_links"] == first_links
    assert len(state["contacts"]) == 2
    assert len(state["consents"]) == 1
    assert len(state["messages"]) == 2
    assert len(state["case_links"]) == 1


def test_schema_declares_channel_identity_columns():
    """R13, R16: el esquema nuevo guarda canal e ids externos como texto."""
    schema = " ".join(_SCHEMA)
    assert "channel TEXT" in schema
    assert "external_user_id TEXT" in schema
    assert "external_chat_id TEXT" in schema


def test_schema_declares_conversation_states_and_button_evidence():
    """#37 R4, R5, R24, R26: estado por contacto y evidencia de botón."""
    schema = " ".join(_SCHEMA)
    assert "CREATE TABLE IF NOT EXISTS conversation_states" in schema
    assert "result TEXT" in schema
    assert "evidence_type TEXT" in schema
    assert "external_message_id TEXT" in schema
    assert "button_id TEXT" in schema
    assert "occurred_at TIMESTAMPTZ" in schema


def test_schema_declares_tool_calls_and_suppression_requests():
    """#39 R7, R36: tablas nuevas con sus columnas y protección de un pendiente."""
    schema = " ".join(_SCHEMA)
    assert "CREATE TABLE IF NOT EXISTS tool_calls" in schema
    assert "args_sha256 TEXT NOT NULL" in schema
    assert "detail TEXT NOT NULL" in schema
    assert "CREATE TABLE IF NOT EXISTS suppression_requests" in schema
    assert "status TEXT NOT NULL" in schema
    indexes = " ".join(_INDEXES)
    assert "tool_calls_at_idx" in indexes
    assert "tool_calls_contact_idx" in indexes
    assert "suppression_requests_one_pending" in " ".join(_MIGRATIONS)


def test_migrations_add_button_evidence_without_rewriting_history():
    """#37 R4, R5, R34: migración aditiva que conserva lo aceptado previamente."""
    migrations = " ".join(_MIGRATIONS)
    assert "ALTER COLUMN accepted_at DROP NOT NULL" in migrations
    assert "ADD COLUMN IF NOT EXISTS result TEXT" in migrations
    assert "ADD COLUMN IF NOT EXISTS evidence_type TEXT" in migrations
    assert "evidence_type = 'legacy'" in migrations
    assert "DELETE" not in migrations.upper()
    assert "DROP TABLE" not in migrations.upper()


def test_schema_declares_panel_audit_and_presence():
    """R55, R56, R62: tablas, columnas e índices nuevos."""
    schema = " ".join(_SCHEMA)
    assert "CREATE TABLE IF NOT EXISTS panel_audit" in schema
    assert "actor_profile_id TEXT NOT NULL" in schema
    assert "request_id TEXT" in schema
    assert "CREATE TABLE IF NOT EXISTS advisor_presence" in schema
    assert "last_seen_at TIMESTAMPTZ NOT NULL" in schema
    indexes = " ".join(_INDEXES)
    assert "panel_audit_at" in indexes
    assert "suppression_requests_status_created" in indexes
    migrations = " ".join(_MIGRATIONS)
    assert "result_note TEXT" in migrations
    assert "notification_result TEXT" in migrations


def test_schema_declares_administration_tables_and_indexes():
    """R16, R25, R53: tablas nuevas idempotentes con sus índices."""
    schema = " ".join(_SCHEMA)
    assert "CREATE TABLE IF NOT EXISTS text_versions" in schema
    assert "UNIQUE (field, version)" in schema
    assert "CREATE TABLE IF NOT EXISTS whatsapp_templates" in schema
    assert "CREATE TABLE IF NOT EXISTS credential_expiry_notices" in schema
    assert "PRIMARY KEY (profile_id, valid_until)" in schema
    indexes = " ".join(_INDEXES)
    assert "whatsapp_templates_purpose" in indexes
    assert "events_type_at" in indexes
    assert "case_links_created" in indexes
    assert all("IF NOT EXISTS" in statement for statement in _SCHEMA)


class _ContactCursor:
    def __init__(self, log: list) -> None:
        self.log = log

    def execute(self, sql: str, params=()) -> None:
        self.log.append((sql, tuple(params)))

    def fetchall(self):
        return [("c1", "whatsapp", "57300", "57301", None, None)]


class _ContactConn:
    def __init__(self, log: list) -> None:
        self.log = log

    def cursor(self):
        return _ContactCursor(self.log)

    def commit(self) -> None:
        pass

    def rollback(self) -> None:
        pass


def test_get_case_contact_selects_all_six_columns():
    """R13: el contacto del caso conserva canal y destino de WhatsApp."""
    log: list = []
    repo = PostgresRepository("postgresql://x", connect=lambda: _ContactConn(log))
    contact = repo.get_case_contact("case-1")
    sql = next(sql for sql, _ in log if sql.startswith("SELECT c.id"))
    for column in (
        "c.id",
        "c.channel",
        "c.external_user_id",
        "c.external_chat_id",
        "c.telegram_user_id",
        "c.chat_id",
    ):
        assert column in sql
    assert (contact.channel, contact.external_chat_id) == ("whatsapp", "57301")


class _RecordingCursor:
    def __init__(self, log: list) -> None:
        self.log = log

    def execute(self, sql: str, params=()) -> None:
        self.log.append((sql, tuple(params)))

    def fetchall(self):
        return [("c1", "whatsapp", "57300", "57300", None, None)]


class _RecordingConn:
    def __init__(self, log: list) -> None:
        self.log = log

    def cursor(self):
        return _RecordingCursor(self.log)

    def commit(self) -> None:
        pass

    def rollback(self) -> None:
        pass


class _ParamCursor:
    def __init__(self, log: list) -> None:
        self.log = log
        self._rows: list = []

    def execute(self, sql: str, params=()) -> None:
        self.log.append((sql, tuple(params)))
        self._rows = [("req-1",)] if "RETURNING id" in sql else []

    def fetchall(self):
        return self._rows


class _ParamConn:
    def __init__(self, log: list) -> None:
        self.log = log

    def cursor(self):
        return _ParamCursor(self.log)

    def commit(self) -> None:
        pass

    def rollback(self) -> None:
        pass


def test_postgres_tool_calls_and_suppression_use_parameters():
    """#39 R7, R36, R37: SQL nuevo parametrizado y sin valores interpolados."""
    log: list = []
    repo = PostgresRepository(
        "postgresql://x", connect=lambda: _ParamConn(log), new_id=lambda: "nuevo"
    )

    repo.add_tool_call(
        "c1", "p1", "active", "buscar_base_conocimiento", "rule", "allowed",
        "ok", "sha", "", NOW,
    )
    request_id, created = repo.create_or_get_pending_suppression(
        "req-1", "p1", "c1", "telegram", NOW
    )
    repo.set_suppression_case("req-1", "case-1")

    assert (request_id, created) == ("req-1", True)
    dml = [
        (sql, params) for sql, params in log if not sql.startswith("CREATE")
    ]
    assert any(sql.startswith("INSERT INTO tool_calls") for sql, _ in dml)
    assert any(
        sql.startswith("INSERT INTO suppression_requests") for sql, _ in dml
    )
    for sql, params in dml:
        assert "req-1" not in sql and "case-1" not in sql
        assert sql.count("%s") == len(params)


def test_whatsapp_postgres_identity_keeps_telegram_columns_null():
    """R16, R20: WhatsApp no escribe su id en `telegram_user_id` ni `chat_id`."""
    log: list = []
    repo = PostgresRepository("postgresql://x", connect=lambda: _RecordingConn(log))

    contact = repo.get_or_create_channel_contact(
        "whatsapp", "57300", "57300", NOW
    )
    repo.add_channel_privacy_consent("whatsapp", "57300", "v1", "sha", NOW)

    assert (contact.channel, contact.external_user_id) == ("whatsapp", "57300")
    assert contact.telegram_user_id is None and contact.chat_id is None

    insert_contact = next(
        params for sql, params in log if sql.startswith("INSERT INTO contacts")
    )
    assert insert_contact[1] == "whatsapp"
    assert insert_contact[4] is None and insert_contact[5] is None
    select_contact = next(
        sql for sql, _ in log if sql.startswith("SELECT id, channel")
    )
    assert "channel = %s AND external_user_id = %s" in select_contact
    insert_consent = next(
        params for sql, params in log if sql.startswith("INSERT INTO privacy_consents")
    )
    assert insert_consent[0] == "whatsapp" and insert_consent[2] is None
