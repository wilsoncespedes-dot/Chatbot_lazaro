"""Fase 4: consultas a la base listas para producción.

- Un cliente nunca ve filas de otro, aunque su SQL no tenga WHERE (RLS).
- DROP/UPDATE se rechazan en la validación y, además, por permisos del rol.
- Una consulta lenta se corta por `statement_timeout`.
- Usar el usuario principal en DB_QUERY/CLIENT_DATA impide arrancar.
- Toda consulta lleva LIMIT y devuelve un resultado estructurado.
"""
from __future__ import annotations

import json
import time
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from urllib.parse import urlparse, urlunparse

import pytest
from pydantic import ValidationError

from orchestrator.adapters.db_query import FakeDbQuery, PostgresReadOnlyQuery
from orchestrator.adapters.llm import ScriptedLLM
from orchestrator.config import Settings
from orchestrator.db_query import (
    DbQueryRejected,
    DbQueryUnavailable,
    QueryResult,
    ValidatedQuery,
    validate_sql,
)
from orchestrator.domain import query_staff_data
from migrations.runner import ROLE_PASSWORD_ENV
from migrations.testing import database_url_for_tests, migrated_database

ROOT = Path(__file__).resolve().parents[3]
NOW = datetime(2026, 11, 23, 10, 0, tzinfo=timezone.utc)
CASOS = {"consultas.v_casos": ("caso", "estado", "motivo", "canal", "creado", "asignado", "cerrado")}


def _env_example_value(name: str) -> str:
    for line in (ROOT / ".env.example").read_text(encoding="utf-8").splitlines():
        if line.startswith(f"{name}="):
            return line.split("=", 1)[1]
    raise AssertionError(f"{name} no está en .env.example")


def _allowlist(name: str) -> dict[str, tuple[str, ...]]:
    return {view: tuple(cols) for view, cols in json.loads(_env_example_value(name)).items()}


# ── validación: LIMIT obligatorio y sentencias de escritura ─────────────────


def test_limit_is_added_when_missing():
    validated = validate_sql(
        "SELECT estado FROM consultas.v_casos", CASOS, "consultas", 1, max_rows=50
    )
    assert validated.sql == "SELECT estado FROM consultas.v_casos LIMIT 51"


def test_existing_top_level_limit_is_kept_and_must_be_an_integer():
    kept = validate_sql(
        "SELECT estado FROM consultas.v_casos LIMIT 5;", CASOS, "consultas", 1, max_rows=50
    )
    assert kept.sql == "SELECT estado FROM consultas.v_casos LIMIT 5"
    for sql in (
        "SELECT estado FROM consultas.v_casos LIMIT 1.5",
        "SELECT estado FROM consultas.v_casos LIMIT caso",
        "SELECT estado FROM consultas.v_casos LIMIT 5 LIMIT 6",
        "SELECT estado FROM consultas.v_casos LIMIT",
    ):
        with pytest.raises(DbQueryRejected):
            validate_sql(sql, CASOS, "consultas", 1, max_rows=50)


def test_without_max_rows_the_sql_is_unchanged():
    """Compatibilidad: quien no pide LIMIT obligatorio recibe el SQL tal cual."""
    validated = validate_sql("SELECT estado FROM consultas.v_casos", CASOS, "consultas", 1)
    assert validated.sql == "SELECT estado FROM consultas.v_casos"


@pytest.mark.parametrize(
    "sql",
    [
        "DROP VIEW consultas.v_casos",
        "UPDATE consultas.v_casos SET estado = 'cerrado'",
        "DELETE FROM consultas.v_casos",
        "SELECT estado FROM consultas.v_casos; DROP VIEW consultas.v_casos",
        "INSERT INTO consultas.v_casos (caso) VALUES ('x')",
    ],
)
def test_write_statements_are_rejected_by_validation(sql):
    with pytest.raises(DbQueryRejected):
        validate_sql(sql, CASOS, "consultas", 1, max_rows=50)


# ── configuración: nunca el usuario principal ──────────────────────────────


def _base(**overrides) -> dict:
    values = {
        "database_url": "postgresql://lazaro:principal@postgres:5432/lazaro",
        "db_query_allowlist": json.dumps({k: list(v) for k, v in CASOS.items()}),
    }
    values.update(overrides)
    return values


def test_db_query_with_the_main_user_refuses_to_start():
    with pytest.raises(ValidationError, match="usuario principal"):
        Settings(
            **_base(
                db_query_enabled=True,
                # otra clave y otro host, pero el mismo usuario
                db_query_database_url="postgresql://lazaro:otra@db:5432/lazaro",
            )
        )


def test_client_data_with_the_main_or_staff_user_refuses_to_start():
    allowlist = json.dumps({"mis_datos.v_mis_casos": ["caso", "estado"]})
    with pytest.raises(ValidationError, match="usuario principal"):
        Settings(
            **_base(
                client_data_enabled=True,
                client_data_allowlist=allowlist,
                client_data_database_url="postgresql://lazaro:x@postgres:5432/lazaro",
            )
        )
    with pytest.raises(ValidationError):
        Settings(
            **_base(
                db_query_enabled=True,
                db_query_database_url="postgresql://bot_consultas:a@postgres/lazaro",
                client_data_enabled=True,
                client_data_allowlist=allowlist,
                client_data_database_url="postgresql://bot_consultas:b@postgres/lazaro",
            )
        )


def test_read_roles_are_accepted():
    settings = Settings(
        **_base(
            db_query_enabled=True,
            db_query_database_url="postgresql://bot_consultas:c@postgres:5432/lazaro",
            client_data_enabled=True,
            client_data_allowlist=_env_example_value("CLIENT_DATA_ALLOWLIST"),
            client_data_database_url="postgresql://bot_lectura:l@postgres:5432/lazaro",
            db_query_allowlist=_env_example_value("DB_QUERY_ALLOWLIST"),
        )
    )
    assert settings.db_query_enabled and settings.client_data_enabled


def test_env_example_documents_roles_and_switches():
    for name in (
        "BOT_LECTURA_PASSWORD",
        "BOT_CONSULTAS_PASSWORD",
        "DB_QUERY_ENABLED",
        "CLIENT_DATA_ENABLED",
        "MCP_ENABLED",
        "DB_QUERY_ALLOWLIST",
        "CLIENT_DATA_ALLOWLIST",
    ):
        _env_example_value(name)
    assert ROLE_PASSWORD_ENV == {
        "bot_lectura": "BOT_LECTURA_PASSWORD",
        "bot_consultas": "BOT_CONSULTAS_PASSWORD",
    }


# ── adaptador y resultado estructurado ─────────────────────────────────────


class _RoleCursor:
    def __init__(self, superuser: bool) -> None:
        self.superuser = superuser
        self.executed: list[str] = []
        self.description = None

    def execute(self, sql, params=()):
        self.executed.append(sql)

    def fetchall(self):
        if self.executed[-1].startswith("SELECT rolsuper"):
            return [(self.superuser, False)]
        return []


class _RoleConn:
    def __init__(self, cursor) -> None:
        self._cursor = cursor

    def cursor(self):
        return self._cursor

    def close(self):
        pass


def test_staff_adapter_refuses_a_superuser_role():
    cursor = _RoleCursor(superuser=True)
    adapter = PostgresReadOnlyQuery("postgresql://x", CASOS, connect=lambda: _RoleConn(cursor))
    with pytest.raises(DbQueryUnavailable):
        adapter.run(ValidatedQuery("SELECT estado FROM consultas.v_casos", ()), 5, 1000)
    assert not any("FROM (SELECT estado" in sql for sql in cursor.executed)


def test_query_result_is_structured_and_json_safe():
    result = QueryResult(
        columns=["dia", "total", "precio"],
        rows=[(date(2026, 11, 1), 3, Decimal("10.50")), (None, 0, None)],
        truncated=True,
    )
    data = result.as_dict()
    assert data == {
        "columns": ["dia", "total", "precio"],
        "rows": [["2026-11-01", 3, 10.5], [None, 0, None]],
        "truncated": True,
    }
    json.dumps(data)


def test_staff_query_returns_columns_and_rows(env_factory):
    env = env_factory(
        database_url="postgresql://lazaro:principal@postgres/lazaro",
        db_query_enabled=True,
        db_query_database_url="postgresql://bot_consultas:c@postgres/lazaro",
        db_query_allowlist=json.dumps({k: list(v) for k, v in CASOS.items()}),
    )
    env.adapters.db_query = FakeDbQuery(
        QueryResult(columns=["estado", "total"], rows=[("abierto", 2)], truncated=False)
    )
    env.adapters.llm = ScriptedLLM(
        [json.dumps({"sql": "SELECT estado, count(*) AS total FROM consultas.v_casos GROUP BY estado"})]
    )

    outcome = query_staff_data("¿cuántos casos por estado?", env.settings, env.adapters)

    assert outcome.status == "ok"
    assert outcome.result.columns == ["estado", "total"]
    assert outcome.result.rows == [("abierto", 2)]
    executed = env.adapters.db_query.calls[0][0]
    assert executed.sql.endswith(f"LIMIT {env.settings.db_query_max_rows + 1}")


# ── Postgres real (TEST_DATABASE_URL) ──────────────────────────────────────

LECTURA_PASSWORD = "prueba_bot_lectura_1234"
CONSULTAS_PASSWORD = "prueba_bot_consultas_1234"


def _as_role(url: str, role: str, password: str) -> str:
    parsed = urlparse(url)
    netloc = f"{role}:{password}@{parsed.hostname}:{parsed.port or 5432}"
    return urlunparse(parsed._replace(netloc=netloc))


def _seed(url: str) -> None:
    import pg8000.dbapi

    from migrations.runner import connect, sync_role_passwords

    conn = connect(url)
    sync_role_passwords(
        conn,
        {"BOT_LECTURA_PASSWORD": LECTURA_PASSWORD, "BOT_CONSULTAS_PASSWORD": CONSULTAS_PASSWORD},
    )
    cur = conn.cursor()
    for profile, contact, case in (("pA", "cA", "caseA"), ("pB", "cB", "caseB")):
        cur.execute(
            "INSERT INTO profiles (id, username, role, password_hash, created_at, public_id, email) "
            "VALUES (%s, %s, 'cliente', 'h', %s, %s, %s)",
            (profile, f"user_{profile}", NOW, f"PUB-{profile}", f"{profile}@example.com"),
        )
        cur.execute(
            "INSERT INTO client_credentials (profile_id, valid_from, valid_until, created_at, updated_at) "
            "VALUES (%s, %s, %s, %s, %s)",
            (profile, NOW - timedelta(days=1), NOW + timedelta(days=30), NOW, NOW),
        )
        cur.execute(
            "INSERT INTO contacts (id, channel, external_user_id, external_chat_id, created_at) "
            "VALUES (%s, 'whatsapp', %s, %s, %s)",
            (contact, contact, contact, NOW),
        )
        cur.execute(
            "INSERT INTO client_sessions (id, profile_id, contact_id, started_at, last_activity_at) "
            "VALUES (%s, %s, %s, %s, %s)",
            (f"s-{profile}", profile, contact, NOW, NOW),
        )
        cur.execute(
            "INSERT INTO case_links (case_id, contact_id, created_at, profile_id) "
            "VALUES (%s, %s, %s, %s)",
            (case, contact, NOW, profile),
        )
        cur.execute(
            "INSERT INTO handover_cases (case_id, contact_id, chat_id, reason, status, "
            "last_messages, created_at) VALUES (%s, %s, 0, 'user_request', 'open', '[]', %s)",
            (case, contact, NOW),
        )
        cur.execute(
            "INSERT INTO messages (contact_id, role, text, at) VALUES (%s, 'user', 'hola', %s)",
            (contact, NOW),
        )
    conn.commit()
    conn.close()
    assert pg8000  # el driver está instalado


requires_pg = pytest.mark.skipif(
    not database_url_for_tests(),
    reason="requiere TEST_DATABASE_URL con un Postgres local desechable",
)


@pytest.mark.integration
@requires_pg
def test_postgres_client_never_sees_rows_of_another_client():
    from orchestrator.adapters.client_data import PostgresClientDataQuery

    with migrated_database() as url:
        _seed(url)
        allowlist = _allowlist("CLIENT_DATA_ALLOWLIST")
        adapter = PostgresClientDataQuery(
            _as_role(url, "bot_lectura", LECTURA_PASSWORD), allowlist, "lazaro.cliente_id"
        )
        casos = adapter.run(
            ValidatedQuery("SELECT caso, estado FROM mis_datos.v_mis_casos", ()), "pA", 20, 5000
        )
        assert casos.columns == ["caso", "estado"]
        assert casos.rows == [["caseA", "open"]] or casos.rows == [("caseA", "open")]
        cuenta = adapter.run(
            ValidatedQuery("SELECT usuario, correo FROM mis_datos.v_mi_cuenta", ()), "pB", 20, 5000
        )
        assert [tuple(row) for row in cuenta.rows] == [("user_pB", "pB@example.com")]
        sesiones = adapter.run(
            ValidatedQuery("SELECT canal FROM mis_datos.v_mis_sesiones", ()), "nadie", 20, 5000
        )
        assert sesiones.rows == []


@pytest.mark.integration
@requires_pg
def test_postgres_write_statements_fail_by_permissions_too():
    from migrations.runner import connect

    with migrated_database() as url:
        _seed(url)
        for role, password, view in (
            ("bot_lectura", LECTURA_PASSWORD, "mis_datos.v_mis_casos"),
            ("bot_consultas", CONSULTAS_PASSWORD, "consultas.v_casos"),
        ):
            conn = connect(_as_role(url, role, password))
            cur = conn.cursor()
            for sql in (
                # v_ofertas es una vista simple (actualizable): solo frena el permiso
                "UPDATE consultas.v_ofertas SET precio_cop = 0",
                f"DROP VIEW {view}",
                "DELETE FROM profiles",
                "UPDATE profiles SET role = 'admin'",
                "SELECT * FROM profiles",
                "SELECT * FROM messages",
                "CREATE TABLE public.intruso (id int)",
            ):
                # sin el READ ONLY del rol: la barrera es el permiso
                cur.execute("SET TRANSACTION READ WRITE")
                with pytest.raises(Exception) as excinfo:
                    cur.execute(sql)
                assert "permission denied" in str(excinfo.value) or "must be owner" in str(
                    excinfo.value
                ), (role, sql, excinfo.value)
                conn.rollback()
            cur.execute("SHOW statement_timeout")
            assert cur.fetchall()[0][0] == "5s"
            cur.execute("SHOW default_transaction_read_only")
            assert cur.fetchall()[0][0] == "on"
            conn.rollback()
            conn.close()

        # el personal no lee las vistas de clientes, y el cliente no lee las del personal
        conn = connect(_as_role(url, "bot_consultas", CONSULTAS_PASSWORD))
        with pytest.raises(Exception, match="permission denied"):
            conn.cursor().execute("SELECT * FROM mis_datos.v_mis_casos")
        conn.close()
        conn = connect(_as_role(url, "bot_lectura", LECTURA_PASSWORD))
        with pytest.raises(Exception, match="permission denied"):
            conn.cursor().execute("SELECT * FROM consultas.v_casos")
        conn.close()


@pytest.mark.integration
@requires_pg
def test_postgres_staff_views_and_timeout():
    with migrated_database() as url:
        _seed(url)
        allowlist = _allowlist("DB_QUERY_ALLOWLIST")
        adapter = PostgresReadOnlyQuery(
            _as_role(url, "bot_consultas", CONSULTAS_PASSWORD), allowlist
        )
        result = adapter.run(
            ValidatedQuery(
                "SELECT estado, count(*) AS total FROM consultas.v_casos GROUP BY estado", ()
            ),
            50,
            5000,
        )
        assert result.columns == ["estado", "total"]
        assert [tuple(row) for row in result.rows] == [("open", 2)]
        diarios = adapter.run(
            ValidatedQuery("SELECT canal, mensajes FROM consultas.v_mensajes_diarios", ()), 50, 5000
        )
        assert [tuple(row) for row in diarios.rows] == [("whatsapp", 2)]

        started = time.monotonic()
        with pytest.raises(DbQueryUnavailable):
            adapter.run(ValidatedQuery("SELECT pg_sleep(3) AS espera", ()), 1, 300)
        assert time.monotonic() - started < 2.5


@pytest.mark.integration
@requires_pg
def test_postgres_main_user_keeps_full_access_with_forced_rls():
    from orchestrator.adapters.repository import PostgresRepository

    with migrated_database() as url:
        _seed(url)
        repo = PostgresRepository(url)
        assert repo.get_profile("pA") is not None
        assert repo.get_profile("pB") is not None
        assert repo.get_client_credential("pA") is not None
