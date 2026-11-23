"""Esquema Postgres (#36): declarado en `migrations/0001_esquema_inicial.sql`.

El backfill real de contactos y consentimientos se prueba contra Postgres en
`migrations/tests/test_runner_integracion.py`.
"""
from __future__ import annotations

import inspect
from datetime import datetime, timezone

from migrations import section
from orchestrator.adapters.repository import PostgresRepository

_SCHEMA = section("orchestrator: tablas")
_INDEXES = section("orchestrator: índices")
_MIGRATIONS = section("orchestrator: migraciones aditivas previas")

NOW = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)


def test_two_factor_schema_is_additive_and_idempotent():
    """R17, R23, R35: tablas nuevas, columna enroll_only y migración idempotente."""
    schema = " ".join(_SCHEMA)
    indexes = " ".join(_INDEXES)
    migrations = " ".join(_MIGRATIONS)
    assert "CREATE TABLE IF NOT EXISTS staff_two_factor" in schema
    assert "CREATE TABLE IF NOT EXISTS staff_recovery_codes" in schema
    assert "enroll_only BOOLEAN NOT NULL DEFAULT FALSE" in schema
    assert "staff_recovery_codes_profile" in indexes
    assert "ALTER TABLE admin_sessions ADD COLUMN IF NOT EXISTS enroll_only" in migrations


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


def test_schema_declares_case_notes_and_tags():
    """R39: las tablas de notas y etiquetas se crean de forma idempotente."""
    schema = " ".join(_SCHEMA)
    assert "CREATE TABLE IF NOT EXISTS case_notes" in schema
    assert "author_profile_id TEXT NOT NULL" in schema
    assert "CREATE TABLE IF NOT EXISTS case_tags" in schema
    assert "name_key TEXT NOT NULL UNIQUE" in schema
    assert "CREATE TABLE IF NOT EXISTS case_tag_assignments" in schema
    assert "PRIMARY KEY (case_id, tag_id)" in schema
    indexes = " ".join(_INDEXES)
    assert "case_notes_case" in indexes
    assert "case_notes_contact" in indexes
    assert "case_tag_assignments_tag" in indexes
    assert "case_tag_assignments_contact" in indexes
    assert all("IF NOT EXISTS" in statement for statement in _SCHEMA)


def test_schema_declares_saved_replies_outside_personal_data():
    """R24: tabla idempotente, sin `contact_id` y fuera de supresión y purga."""
    schema = " ".join(_SCHEMA)
    assert "CREATE TABLE IF NOT EXISTS saved_replies" in schema
    table = next(statement for statement in _SCHEMA if "saved_replies" in statement)
    assert "id TEXT PRIMARY KEY" in table
    assert "title TEXT NOT NULL" in table
    assert "body TEXT NOT NULL" in table
    assert "active BOOLEAN NOT NULL" in table
    assert "contact_id" not in table
    assert "saved_replies" not in " ".join(_MIGRATIONS)
    for method in (
        PostgresRepository.execute_suppression,
        PostgresRepository.purge_personal_data,
    ):
        assert "saved_replies" not in inspect.getsource(method)


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


def test_connection_never_runs_ddl():
    """Fase 1: el servicio ya no crea tablas al conectar (deadlock de 5d1a398);
    el esquema lo aplica una sola vez `migrations/runner.py` en el despliegue."""
    log: list = []
    repo = PostgresRepository("postgresql://x", connect=lambda: _ContactConn(log))
    repo.get_case_contact("case-1")
    assert log, "la consulta debe ejecutarse"
    assert all(
        not sql.lstrip().upper().startswith(("CREATE", "ALTER", "SELECT PG_ADVISORY"))
        for sql, _ in log
    )


def test_no_service_bootstraps_schema_on_connect():
    """Ningún repositorio conserva DDL de arranque ni el turno global de esquema."""
    from pathlib import Path

    root = Path(__file__).resolve().parents[3]
    for module in (
        "services/orchestrator/orchestrator/adapters/repository.py",
        "services/handover/handover/adapters/repository.py",
        "services/telegram_gateway/telegram_gateway/adapters/channel_repository.py",
        "services/telegram_gateway/telegram_gateway/adapters/mailbox.py",
        "services/rag/rag/adapters/repository.py",
        "services/mcp_lectura/mcp_lectura/schema.py",
    ):
        text = (root / module).read_text(encoding="utf-8")
        assert "SCHEMA_LOCK_SQL" not in text, module
        assert "CREATE TABLE" not in text, module


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
