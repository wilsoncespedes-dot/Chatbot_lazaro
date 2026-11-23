"""Runner contra un Postgres real (pgvector). Requiere TEST_DATABASE_URL.

TEST_DATABASE_URL debe apuntar a un Postgres local desechable con un usuario que
pueda crear bases y roles (p. ej. el contenedor `pgvector/pgvector:pg16`). Cada
test crea su propia base y la borra al terminar; nunca usa la de producción.
"""
from __future__ import annotations

import os
import threading
import uuid
from urllib.parse import urlparse, urlunparse

import pytest

from migrations.runner import (
    connect,
    load_migrations,
    render,
    resolve_variables,
    run_migrations,
)

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not os.environ.get("TEST_DATABASE_URL"),
        reason="requiere TEST_DATABASE_URL con un Postgres local desechable",
    ),
]


def _with_db(url: str, name: str) -> str:
    parsed = urlparse(url)
    return urlunparse(parsed._replace(path=f"/{name}"))


@pytest.fixture
def fresh_db():
    admin_url = os.environ["TEST_DATABASE_URL"]
    name = f"mig_{uuid.uuid4().hex[:12]}"
    admin = connect(admin_url)
    admin.autocommit = True
    admin.cursor().execute(f"CREATE DATABASE {name}")
    try:
        yield _with_db(admin_url, name)
    finally:
        cursor = admin.cursor()
        cursor.execute(
            "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = %s",
            (name,),
        )
        cursor.execute(f"DROP DATABASE IF EXISTS {name}")
        admin.close()


def _snapshot(url: str) -> dict:
    conn = connect(url)
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT table_name, column_name, data_type, is_nullable, column_default "
            "FROM information_schema.columns WHERE table_schema NOT IN "
            "('pg_catalog', 'information_schema') ORDER BY 1, 2"
        )
        columns = cur.fetchall()
        cur.execute(
            "SELECT schemaname, indexname, indexdef FROM pg_indexes "
            "WHERE schemaname NOT IN ('pg_catalog') ORDER BY 1, 2"
        )
        indexes = cur.fetchall()
        cur.execute(
            "SELECT conrelid::regclass::text, conname, pg_get_constraintdef(oid) "
            "FROM pg_constraint WHERE connamespace = 'public'::regnamespace ORDER BY 1, 2"
        )
        constraints = cur.fetchall()
        cur.execute("SELECT count(*) FROM schema_migrations")
        migrations = cur.fetchone()[0]
        return {
            "columns": columns,
            "indexes": indexes,
            "constraints": constraints,
            "migrations": migrations,
        }
    finally:
        conn.close()


def _run(url: str) -> list[str]:
    conn = connect(url)
    try:
        return run_migrations(conn, load_migrations(), resolve_variables({}))
    finally:
        conn.close()


def _tables(url: str) -> set[str]:
    conn = connect(url)
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'public' AND table_type = 'BASE TABLE'"
        )
        return {row[0] for row in cur.fetchall()}
    finally:
        conn.close()


EXPECTED_TABLES = {
    "schema_migrations", "contacts", "messages", "events", "tool_calls", "inbox",
    "outbox", "profiles", "client_memory", "conversation_summaries", "canales",
    "buzon_simulado", "handover_cases", "handover_requests", "manuals", "chunks",
    "demo_ofertas", "mcp_auditoria",
}


def test_empty_database_gets_full_schema(fresh_db):
    applied = _run(fresh_db)
    assert applied[0] == "0001"
    assert applied == [m.version for m in load_migrations()]
    assert EXPECTED_TABLES <= _tables(fresh_db)


def test_running_twice_changes_nothing(fresh_db):
    _run(fresh_db)
    before = _snapshot(fresh_db)
    assert _run(fresh_db) == []
    assert _snapshot(fresh_db) == before


def test_existing_database_created_by_old_services_is_adopted_without_changes(fresh_db):
    """Producción ya tiene las tablas (creadas al arrancar): 0001 no cambia nada."""
    first = load_migrations()[0]
    conn = connect(fresh_db)
    cur = conn.cursor()
    cur.execute(render(first.sql, resolve_variables({})))
    cur.execute(
        "INSERT INTO contacts (id, channel, external_user_id, external_chat_id, "
        "created_at) VALUES ('c1', 'whatsapp', '573', '573', now())"
    )
    conn.commit()
    conn.close()
    tables_before = _tables(fresh_db)

    _run(fresh_db)

    assert tables_before | {"schema_migrations"} <= _tables(fresh_db)
    conn = connect(fresh_db)
    cur = conn.cursor()
    cur.execute("SELECT id, channel, external_user_id FROM contacts")
    assert [list(row) for row in cur.fetchall()] == [["c1", "whatsapp", "573"]]
    conn.close()


def test_legacy_telegram_rows_are_backfilled_preserving_ids(fresh_db):
    """Antes de #36 contacts solo tenía ids de Telegram: 0001 los rellena."""
    conn = connect(fresh_db)
    cur = conn.cursor()
    cur.execute(
        "CREATE TABLE contacts (id TEXT PRIMARY KEY, telegram_user_id BIGINT UNIQUE "
        "NOT NULL, chat_id BIGINT NOT NULL, created_at TIMESTAMPTZ NOT NULL)"
    )
    cur.execute(
        "CREATE TABLE privacy_consents (id BIGSERIAL PRIMARY KEY, telegram_user_id "
        "BIGINT NOT NULL, notice_version TEXT NOT NULL, notice_sha256 TEXT NOT NULL, "
        "accepted_at TIMESTAMPTZ NOT NULL)"
    )
    cur.execute("INSERT INTO contacts VALUES ('c1', 10, 100, now()), ('c2', 11, 101, now())")
    cur.execute(
        "INSERT INTO privacy_consents (telegram_user_id, notice_version, notice_sha256, "
        "accepted_at) VALUES (10, 'v1', 'hash-10', '2026-01-02T03:04:05Z')"
    )
    conn.commit()
    conn.close()

    _run(fresh_db)

    conn = connect(fresh_db)
    cur = conn.cursor()
    cur.execute(
        "SELECT id, channel, external_user_id, external_chat_id, canal_id "
        "FROM contacts ORDER BY id"
    )
    assert [list(row) for row in cur.fetchall()] == [
        ["c1", "telegram", "10", "100", "telegram"],
        ["c2", "telegram", "11", "101", "telegram"],
    ]
    cur.execute(
        "SELECT channel, external_user_id, notice_version, notice_sha256, result, "
        "evidence_type FROM privacy_consents"
    )
    assert [list(row) for row in cur.fetchall()] == [["telegram", "10", "v1", "hash-10", "accepted", "legacy"]]
    conn.close()


def test_concurrent_runners_apply_each_migration_once(fresh_db):
    results: list[list[str]] = []
    errors: list[BaseException] = []
    barrier = threading.Barrier(2)

    def worker() -> None:
        try:
            barrier.wait(timeout=10)
            results.append(_run(fresh_db))
        except BaseException as exc:  # pragma: no cover - solo falla el test
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=60)

    assert errors == []
    assert sorted(len(r) for r in results) == [0, len(load_migrations())]
