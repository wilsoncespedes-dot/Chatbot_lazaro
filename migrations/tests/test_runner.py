"""Runner de migraciones sin Postgres: orden, lock, checksum, rollback y variables."""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from migrations import MIGRATIONS_DIR, schema_sql, section
from migrations.runner import (
    MIGRATION_LOCK_KEY,
    MigrationError,
    load_migrations,
    main,
    render,
    resolve_variables,
    run_migrations,
    sync_role_passwords,
)


class FakeCursor:
    def __init__(self, conn: "FakeConn") -> None:
        self.conn = conn
        self._rows: list[tuple] = []

    def execute(self, sql: str, params: tuple = ()) -> None:
        self.conn.log.append((sql, params))
        if self.conn.fail_on and self.conn.fail_on in sql:
            raise RuntimeError("boom")
        if sql.startswith("SELECT version, sha256 FROM schema_migrations"):
            self._rows = list(self.conn.applied.items())
        elif sql.startswith("INSERT INTO schema_migrations"):
            self.conn.pending_inserts.append((params[0], params[2]))
        elif sql.startswith("SELECT 1 FROM pg_roles"):
            self._rows = [(1,)] if params[0] in self.conn.roles else []
        else:
            self._rows = []

    def fetchall(self) -> list[tuple]:
        return self._rows


class FakeConn:
    def __init__(self, applied: dict[str, str] | None = None, fail_on: str = "") -> None:
        self.log: list[tuple[str, tuple]] = []
        self.applied = dict(applied or {})
        self.pending_inserts: list[tuple[str, str]] = []
        self.commits = 0
        self.rollbacks = 0
        self.fail_on = fail_on
        self.roles = {"bot_lectura"}

    def cursor(self) -> FakeCursor:
        return FakeCursor(self)

    def commit(self) -> None:
        self.commits += 1
        for version, sha in self.pending_inserts:
            self.applied[version] = sha
        self.pending_inserts.clear()

    def rollback(self) -> None:
        self.rollbacks += 1
        self.pending_inserts.clear()


def _write(tmp_path: Path, name: str, sql: str) -> None:
    (tmp_path / name).write_text(sql, encoding="utf-8")


def test_files_load_in_version_order_with_checksum(tmp_path):
    _write(tmp_path, "0002_b.sql", "SELECT 2;")
    _write(tmp_path, "0001_a.sql", "SELECT 1;")
    migrations = load_migrations(tmp_path)
    assert [m.version for m in migrations] == ["0001", "0002"]
    assert all(len(m.sha256) == 64 for m in migrations)


def test_checksum_ignores_line_endings(tmp_path):
    (tmp_path / "0001_a.sql").write_bytes(b"SELECT 1;\nSELECT 2;\n")
    lf = load_migrations(tmp_path)[0].sha256
    (tmp_path / "0001_a.sql").write_bytes(b"SELECT 1;\r\nSELECT 2;\r\n")
    assert load_migrations(tmp_path)[0].sha256 == lf


@pytest.mark.parametrize("name", ["1_a.sql", "0001-a.sql", "0001_A.sql"])
def test_bad_file_names_are_rejected(tmp_path, name):
    _write(tmp_path, name, "SELECT 1;")
    with pytest.raises(MigrationError):
        load_migrations(tmp_path)


def test_duplicate_versions_are_rejected(tmp_path):
    _write(tmp_path, "0001_a.sql", "SELECT 1;")
    _write(tmp_path, "0001_b.sql", "SELECT 1;")
    with pytest.raises(MigrationError, match="repetida"):
        load_migrations(tmp_path)


def test_runner_takes_session_lock_and_applies_each_file_in_its_own_transaction(tmp_path):
    _write(tmp_path, "0001_a.sql", "CREATE TABLE a (id int);")
    _write(tmp_path, "0002_b.sql", "CREATE TABLE b (id int);")
    conn = FakeConn()

    applied = run_migrations(conn, load_migrations(tmp_path), {})

    assert applied == ["0001", "0002"]
    assert conn.log[0] == ("SELECT pg_advisory_lock(%s)", (MIGRATION_LOCK_KEY,))
    assert conn.log[-1] == ("SELECT pg_advisory_unlock(%s)", (MIGRATION_LOCK_KEY,))
    executed = [sql for sql, _ in conn.log]
    # archivo + su fila de control, uno detrás de otro, y commit entre medias
    first = executed.index("CREATE TABLE a (id int);")
    assert executed[first + 1].startswith("INSERT INTO schema_migrations")
    assert set(conn.applied) == {"0001", "0002"}


def test_second_run_applies_nothing(tmp_path):
    _write(tmp_path, "0001_a.sql", "CREATE TABLE a (id int);")
    migrations = load_migrations(tmp_path)
    conn = FakeConn()
    run_migrations(conn, migrations, {})
    conn.log.clear()

    assert run_migrations(conn, migrations, {}) == []
    assert not any(sql.startswith("CREATE TABLE a") for sql, _ in conn.log)


def test_failed_file_rolls_back_and_stops(tmp_path):
    _write(tmp_path, "0001_a.sql", "CREATE TABLE a (id int);")
    _write(tmp_path, "0002_b.sql", "CREATE TABLE roto (id int);")
    _write(tmp_path, "0003_c.sql", "CREATE TABLE c (id int);")
    conn = FakeConn(fail_on="roto")

    with pytest.raises(MigrationError, match="0002_b.sql"):
        run_migrations(conn, load_migrations(tmp_path), {})

    assert set(conn.applied) == {"0001"}
    assert conn.rollbacks == 1
    assert not any("TABLE c" in sql for sql, _ in conn.log)
    # el lock se libera aunque falle
    assert conn.log[-1][0] == "SELECT pg_advisory_unlock(%s)"


def test_changed_applied_migration_aborts(tmp_path):
    _write(tmp_path, "0001_a.sql", "CREATE TABLE a (id int);")
    conn = FakeConn(applied={"0001": "otro-hash"})
    with pytest.raises(MigrationError, match="cambió"):
        run_migrations(conn, load_migrations(tmp_path), {})


def test_placeholders_only_accept_known_validated_variables():
    variables = resolve_variables({"EMBEDDINGS_DIM": "768"})
    assert render("vector({{EMBEDDINGS_DIM}})", variables) == "vector(768)"
    assert resolve_variables({})["EMBEDDINGS_DIM"] == "1536"
    with pytest.raises(MigrationError):
        resolve_variables({"EMBEDDINGS_DIM": "1; DROP TABLE x"})
    with pytest.raises(MigrationError, match="no permitida"):
        render("{{OTRA}}", variables)


def test_role_password_is_enabled_only_from_env_and_validated():
    conn = FakeConn()
    assert sync_role_passwords(conn, {}) == []
    assert not any("ALTER ROLE" in sql for sql, _ in conn.log)

    assert sync_role_passwords(conn, {"BOT_LECTURA_PASSWORD": "A" * 24}) == ["bot_lectura"]
    assert any(sql.startswith("ALTER ROLE bot_lectura WITH LOGIN") for sql, _ in conn.log)

    with pytest.raises(MigrationError):
        sync_role_passwords(FakeConn(), {"BOT_LECTURA_PASSWORD": "corta"})
    with pytest.raises(MigrationError):
        sync_role_passwords(FakeConn(), {"BOT_LECTURA_PASSWORD": "x' OR '1'='1" * 3})


def test_main_without_database_url_fails():
    assert main([], env={}) == 2


def test_repository_migrations_are_well_formed():
    """Los archivos reales cargan, y 0001 conserva todo el esquema de los servicios."""
    migrations = load_migrations(MIGRATIONS_DIR)
    assert migrations[0].path.name == "0001_esquema_inicial.sql"
    sql = schema_sql()
    for table in (
        "contacts", "messages", "inbox", "outbox", "profiles", "client_memory",
        "handover_cases", "canales", "buzon_simulado", "manuals", "chunks",
        "demo_ofertas", "mcp_auditoria",
    ):
        assert f"CREATE TABLE IF NOT EXISTS {table} " in sql or (
            f"CREATE TABLE IF NOT EXISTS {table} (" in sql
        ), table
    # 0001 es idempotente: todo CREATE lleva IF NOT EXISTS
    body = migrations[0].sql
    for statement in re.findall(r"CREATE (?:UNIQUE )?(?:TABLE|INDEX|EXTENSION) \S+ \S+ \S+", body):
        assert "IF NOT EXISTS" in statement, statement
    assert section("orchestrator: tablas")
