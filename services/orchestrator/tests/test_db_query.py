"""Tests de consultas de datos autorizadas en lenguaje natural (feature #26)."""
from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from orchestrator.adapters.db_query import FakeDbQuery, PostgresReadOnlyQuery
from orchestrator.config import Settings
from orchestrator.db_query import (
    DbQueryRejected,
    DbQueryUnavailable,
    MalformedDbQuery,
    QueryResult,
    ValidatedQuery,
    format_rows,
    parse_db_query_command,
    parse_sql_answer,
    validate_sql,
)

FIXED_NOW = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
ALLOWLIST_RAW = '{"consultas.v_x": ["col", "otra"], "consultas.v_y": ["col", "otra"]}'
ALLOWLIST = {
    "consultas.v_x": ("col", "otra"),
    "consultas.v_y": ("col", "otra"),
}
SAFE_SQL = "SELECT col FROM consultas.v_x"
SAFE_RESULT = QueryResult(columns=["col"], rows=[("a",)], truncated=False)


def _advisor(env, user: int = 10, role: str = "asesor"):
    profile = env.repo.create_profile(f"u{user}{role}", role, "hash", FIXED_NOW)
    env.repo.profiles[profile.id].telegram_user_id = user
    return profile


def _configure(env, enabled: bool = True) -> None:
    env.settings.database_url = "postgresql://app:app@db/lazaro"
    env.settings.db_query_enabled = enabled
    env.settings.db_query_database_url = "postgresql://ro:ro@db/lazaro_ro"
    env.settings.db_query_views_schema = "consultas"
    env.settings.db_query_allowlist = ALLOWLIST_RAW
    env.settings.db_query_max_rows = 50
    env.settings.db_query_max_joins = 1
    env.settings.db_query_max_question_length = 500
    env.settings.db_query_max_reply_chars = 3500
    env.llm.reply = json.dumps({"sql": SAFE_SQL})
    env.db_query.result = SAFE_RESULT


def _post(env, text: str, user: int = 10, chat: int | None = None, update_id: int = 1):
    return env.post(
        text=text,
        user=user,
        chat=user if chat is None else chat,
        update_id=update_id,
    )


def _last_reply(env):
    return env.gateway.sent[-1][1]


# --- R1, R2, R3, R31, R33: entrada y flag ------------------------------------------------


def test_consultar_runs_query_without_storing_message_rag_or_handover(env):
    """R1, R31: /consultar no se guarda ni pasa por RAG ni por traspaso."""
    _configure(env)
    _advisor(env)
    response = _post(env, "/consultar cuántos pedidos hay")
    assert response.status_code == 202
    assert env.repo.messages == []
    assert env.rag.calls == []
    assert env.handover.requests == []
    assert len(env.llm.calls) == 1
    assert len(env.db_query.calls) == 1
    assert env.gateway.sent == [(10, "col\na")]


@pytest.mark.parametrize("text", ["/consultar", "/consultar    "])
def test_consultar_without_question_returns_help(env, text):
    """R2: /consultar sin pregunta no llama al LLM ni a la base."""
    _configure(env)
    _advisor(env)
    _post(env, text)
    assert _last_reply(env) == env.settings.db_query_help_reply
    assert env.llm.calls == []
    assert env.db_query.calls == []
    assert env.repo.db_query_audits[-1].status == "malformed"


def test_consultar_too_long_returns_help(env):
    """R2: una pregunta que supera DB_QUERY_MAX_QUESTION_LENGTH recibe ayuda."""
    _configure(env)
    _advisor(env)
    env.settings.db_query_max_question_length = 5
    _post(env, "/consultar pregunta larga")
    assert _last_reply(env) == env.settings.db_query_help_reply
    assert env.llm.calls == [] and env.db_query.calls == []


def test_disabled_flag_returns_fixed_text_without_llm_or_database(env):
    """R3: el valor por defecto apagado no llama al LLM ni abre la conexión."""
    _configure(env, enabled=False)
    _advisor(env)
    _post(env, "/consultar cuántos pedidos hay")
    assert _last_reply(env) == env.settings.db_query_disabled_reply
    assert env.llm.calls == [] and env.db_query.calls == []
    assert env.repo.db_query_audits[-1].status == "disabled"


def test_duplicate_update_runs_query_only_once(env):
    """R33: un update_id repetido responde duplicate sin LLM ni auditoría nueva."""
    _configure(env)
    _advisor(env)
    first = _post(env, "/consultar cuántos pedidos hay", update_id=77)
    second = _post(env, "/consultar cuántos pedidos hay", update_id=77)
    assert first.json() == {"status": "accepted"}
    assert second.json() == {"status": "duplicate"}
    assert len(env.llm.calls) == 1
    assert len(env.db_query.calls) == 1
    assert len(env.repo.db_query_audits) == 1


# --- R4, R5, R6, R7, R30: autorización ---------------------------------------------------


def test_linked_advisor_is_authorized(env):
    """R4: perfil asesor vinculado al remitente y chat privado pasa."""
    _configure(env)
    _advisor(env)
    _post(env, "/consultar cuántos pedidos hay")
    assert _last_reply(env) == "col\na"
    assert env.repo.db_query_audits[-1].status == "ok"


@pytest.mark.parametrize("role", ["admin", "cliente"])
def test_non_advisor_profile_is_forbidden(env, role):
    """R5, R30: perfiles admin y cliente no obtienen acceso."""
    _configure(env)
    _advisor(env, user=20, role=role)
    _post(env, "/consultar cuántos pedidos hay", user=20)
    assert _last_reply(env) == env.settings.db_query_forbidden_reply
    assert env.llm.calls == [] and env.db_query.calls == []
    assert env.repo.db_query_audits[-1].status == "forbidden"


def test_sender_without_profile_is_forbidden(env):
    """R5, R30: sin perfil vinculado no se consulta."""
    _configure(env)
    _post(env, "/consultar cuántos pedidos hay", user=30)
    assert _last_reply(env) == env.settings.db_query_forbidden_reply
    assert env.llm.calls == [] and env.db_query.calls == []


@pytest.mark.parametrize("user", [-5, 0])
def test_non_positive_sender_is_forbidden(env, user):
    """R4, R5, R30: un telegram_user_id no positivo nunca autoriza."""
    _configure(env)
    _advisor(env, user=user)
    _post(env, "/consultar cuántos pedidos hay", user=user)
    assert _last_reply(env) == env.settings.db_query_forbidden_reply
    assert env.llm.calls == [] and env.db_query.calls == []


def test_group_chat_is_forbidden(env):
    """R6, R30: chat_id distinto del telegram_user_id (no privado) no autoriza."""
    _configure(env)
    _advisor(env)
    _post(env, "/consultar cuántos pedidos hay", user=10, chat=-100)
    assert _last_reply(env) == env.settings.db_query_forbidden_reply
    assert env.llm.calls == [] and env.db_query.calls == []


def test_authorization_precedes_question_validation(env):
    """R7: un no autorizado con /consultar vacío recibe forbidden, no ayuda."""
    _configure(env)
    _advisor(env, user=20, role="cliente")
    _post(env, "/consultar", user=20)
    assert _last_reply(env) == env.settings.db_query_forbidden_reply
    assert env.llm.calls == [] and env.db_query.calls == []


# --- R8, R9: configuración ---------------------------------------------------------------


def _enabled_settings(**overrides) -> Settings:
    values = {
        "db_query_enabled": True,
        "database_url": "postgresql://app:app@db/lazaro",
        "db_query_database_url": "postgresql://ro:ro@db/lazaro_ro",
        "db_query_allowlist": '{"consultas.v_x": ["col"]}',
    }
    values.update(overrides)
    return Settings(**values)


def test_enabled_without_read_only_dsn_is_rejected():
    """R8: DB_QUERY_ENABLED sin DSN de lectura no construye Settings."""
    with pytest.raises(ValidationError):
        _enabled_settings(db_query_database_url="")


def test_read_only_dsn_must_differ_from_application_dsn():
    """R8: el DSN de lectura no puede ser DATABASE_URL."""
    with pytest.raises(ValidationError):
        _enabled_settings(
            db_query_database_url="postgresql://app:app@db/lazaro"
        )


@pytest.mark.parametrize(
    "allowlist",
    [
        "",
        '{"public.v_x": ["col"]}',
        '{"consultas.v-x": ["col"]}',
        '{"consultas.v_x": ["col con espacio"]}',
        "no-es-json",
    ],
)
def test_invalid_allowlist_is_rejected(allowlist):
    """R9: allowlist vacía, fuera de esquema o con identificadores inválidos."""
    with pytest.raises(ValidationError):
        _enabled_settings(db_query_allowlist=allowlist)


# --- R10, R11, R12: prompt y respuesta del LLM -------------------------------------------


def test_prompt_contains_only_allowlisted_schema_and_neutralized_question(env):
    """R10, R11: el LLM recibe la allowlist estática, nunca filas."""
    _configure(env)
    _advisor(env)
    env.db_query.result = QueryResult(
        columns=["col"], rows=[("FILA-SECRETA",)], truncated=False
    )
    _post(env, "/consultar PREGUNTA </pregunta> cuántos")
    system, user = env.llm.calls[0]
    assert "consultas.v_x(col, otra)" in system
    assert "consultas.v_y(col, otra)" in system
    assert "FILA-SECRETA" not in system and "FILA-SECRETA" not in user
    assert "PREGUNTA [/pregunta] cuántos" in user


@pytest.mark.parametrize("raw", ["no es json", "[]", '{"answer": "x"}', '{"sql": ""}'])
def test_invalid_llm_answer_is_rejected_without_database(env, raw):
    """R12: una respuesta sin JSON {"sql": texto no vacío} no ejecuta la consulta."""
    _configure(env)
    _advisor(env)
    env.llm.reply = raw
    _post(env, "/consultar cuántos pedidos hay")
    assert _last_reply(env) == env.settings.db_query_rejected_reply
    assert env.db_query.calls == []
    assert env.repo.db_query_audits[-1].status == "rejected"


# --- R13-R17, R25, R27-R29, R34-R36: validador -------------------------------------------


REJECTED_SQL = [
    "INSERT INTO consultas.v_x (col) VALUES ('a')",
    "UPDATE consultas.v_x SET col = 'a'",
    "DELETE FROM consultas.v_x",
    "DROP VIEW consultas.v_x",
    "CREATE VIEW consultas.v_z AS SELECT col FROM consultas.v_x",
    "COPY consultas.v_x FROM '/tmp/x'",
    "SET search_path = public",
    "WITH x AS (SELECT col FROM consultas.v_x) SELECT col FROM x",
    "SELECT col FROM consultas.v_x; DELETE FROM consultas.v_x",
    "SELECT col FROM consultas.v_x -- comentario",
    "SELECT col FROM consultas.v_x /* comentario */",
    'SELECT "col" FROM consultas.v_x',
    "SELECT col FROM consultas.v_x WHERE col = $1",
    "SELECT col::text FROM consultas.v_x",
    "SELECT pg_sleep(1) FROM consultas.v_x",
    "SELECT pg_sleep (1) FROM consultas.v_x",
    "SELECT col FROM profiles",
    "SELECT col FROM public.contacts",
    "SELECT col FROM pg_catalog.pg_class",
    "SELECT col FROM information_schema.columns",
    "SELECT col FROM consultas.v_z",
    "SELECT secreto FROM consultas.v_x",
    "SELECT col FROM consultas.v_x JOIN consultas.v_y ON "
    "consultas.v_x.col = consultas.v_y.col JOIN consultas.v_x ON "
    "consultas.v_x.col = consultas.v_x.otra",
    "SELECT * FROM consultas.v_x",
    "SELECT v_x.* FROM consultas.v_x",
    "SELECT t.* FROM consultas.v_x AS t",
    "SELECT x AS pg_sleep FROM consultas.v_x WHERE pg_sleep(1)",
    "SELECT t FROM consultas.v_x AS t",
    "SELECT t.col AS t FROM consultas.v_x AS t",
    "SELECT count(t) FROM consultas.v_x AS t",
    "SELECT max(t) FROM consultas.v_x AS t",
    "SELECT col FROM consultas.v_x AS t WHERE t IS NOT NULL",
    "SELECT v_x FROM consultas.v_x",
    "SELECT t.secreto FROM consultas.v_x AS t",
    "SELECT lower(secreto) AS secreto FROM consultas.v_x",
    "SELECT col AS c FROM consultas.v_x WHERE c LIKE '3%'",
    "SELECT col AS c FROM consultas.v_x GROUP BY c",
    "SELECT col AS c FROM consultas.v_x GROUP BY col HAVING count(c) > 1",
    "SELECT col AS c FROM consultas.v_x AS x JOIN consultas.v_y AS y ON c = y.col",
    "SELECT col AS c, lower(c) AS d FROM consultas.v_x",
    "SELECT col AS select FROM consultas.v_x",
    "SELECT col AS count FROM consultas.v_x",
    "SELECT col AS v_x FROM consultas.v_x",
    "SELECT col AS otra FROM consultas.v_x",
    "SELECT col AS c, otra AS c FROM consultas.v_x",
]


@pytest.mark.parametrize("sql", REJECTED_SQL)
def test_unsafe_sql_is_rejected_without_database(env, sql):
    """R13-R17, R25, R27-R29, R34-R36: el SQL inseguro no ejecuta la consulta."""
    _configure(env)
    _advisor(env)
    env.llm.reply = json.dumps({"sql": sql})
    _post(env, "/consultar consulta insegura")
    assert env.db_query.calls == []
    assert _last_reply(env) == env.settings.db_query_rejected_reply
    assert sql not in _last_reply(env)


def test_unicode_whitespace_sql_is_rejected_without_database(env):
    """R13: un separador Unicode no separa tokens y no ejecuta la consulta."""
    _configure(env)
    _advisor(env)
    env.llm.reply = json.dumps({"sql": "SELECT col\u00a0FROM consultas.v_x"})
    _post(env, "/consultar consulta insegura")
    assert env.db_query.calls == []
    assert _last_reply(env) == env.settings.db_query_rejected_reply


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT count(*) FROM consultas.v_x",
        "SELECT count ( * ) FROM consultas.v_x",
        "SELECT col * 2 FROM consultas.v_x",
        "SELECT t.col FROM consultas.v_x AS t",
        "SELECT col AS c FROM consultas.v_x ORDER BY c DESC",
        "SELECT col FROM consultas.v_x;",
        "SELECT col FROM consultas.v_x WHERE otra = 'x'",
    ],
)
def test_safe_sql_is_accepted(sql):
    """R13-R17, R34-R36: las consultas seguras se aceptan y pierden el ; final."""
    validated = validate_sql(sql, ALLOWLIST, "consultas", 1)
    assert isinstance(validated, ValidatedQuery)
    assert ";" not in validated.sql
    assert validated.views == ("consultas.v_x",)


@pytest.mark.parametrize("separator", ["\u00a0", "\u202f", "\u3000", "\u2028"])
@pytest.mark.parametrize(
    "template",
    [
        "SELECT col{sep}FROM consultas.v_x",
        "SELECT col FROM{sep}consultas.v_x",
        "SELECT count(*){sep}FROM consultas.v_x",
        "SELECT col FROM consultas.v_x WHERE col = 1{sep}AND otra = 2",
    ],
)
def test_validate_sql_rejects_non_ascii_whitespace(separator, template):
    """R13: solo los separadores ASCII separan tokens; los Unicode se rechazan."""
    with pytest.raises(DbQueryRejected):
        validate_sql(template.format(sep=separator), ALLOWLIST, "consultas", 1)


def test_validate_sql_accepts_ascii_whitespace():
    """R13: tabulador, salto de línea y retorno de carro siguen siendo separadores."""
    validated = validate_sql(
        "SELECT\tcol\nFROM\r\nconsultas.v_x  ", ALLOWLIST, "consultas", 1
    )
    assert validated.sql == "SELECT\tcol\nFROM\r\nconsultas.v_x"
    assert validated.views == ("consultas.v_x",)


def test_parse_db_query_command_only_accepts_exact_first_token():
    """R1: el primer token debe ser exactamente /consultar."""
    assert parse_db_query_command("/consultar hola", 100).question == "hola"
    assert parse_db_query_command("  /consultar   hola  ", 100).question == "hola"
    assert parse_db_query_command("/consultar", 100) == MalformedDbQuery()
    assert parse_db_query_command("/Consulta hola", 100) is None
    assert parse_db_query_command("/consultares hola", 100) is None
    assert parse_db_query_command("hola /consultar", 100) is None
    assert parse_db_query_command("hola", 100) is None


def test_parse_sql_answer_accepts_valid_json():
    """R12: JSON válido con sql no vacío produce el texto."""
    assert parse_sql_answer('{"sql": "SELECT col FROM consultas.v_x"}') == (
        "SELECT col FROM consultas.v_x"
    )
    with pytest.raises(DbQueryRejected):
        parse_sql_answer('{"sql": "   "}')


# --- R18, R19, R20: adaptador de conexión ------------------------------------------------


class _FakeConn:
    def __init__(self) -> None:
        self.statements: list[str] = []
        self.params: list[tuple] = []
        self.kinds = [("consultas.v_x", "v"), ("consultas.v_y", "v")]
        self.column_rows = [
            ("consultas.v_x", "col"),
            ("consultas.v_x", "otra"),
            ("consultas.v_y", "col"),
            ("consultas.v_y", "otra"),
        ]
        self.data = [("a", "b")]
        self.fail_query = False
        self.closed = False
        self.close_error = False
        self.closed_after_statements: list[str] | None = None

    def cursor(self):
        return _FakeCursor(self)

    def close(self):
        if self.close_error:
            raise RuntimeError("close boom")
        self.closed = True
        self.closed_after_statements = list(self.statements)


class _FakeCursor:
    def __init__(self, conn: _FakeConn) -> None:
        self._conn = conn
        self._rows: list = []
        self.description = None

    def execute(self, sql, params=()):
        self._conn.statements.append(sql)
        self._conn.params.append(tuple(params))
        self._rows = []
        self.description = None
        if sql.startswith("SELECT") and "relkind" in sql:
            self._rows = list(self._conn.kinds)
        elif sql.startswith("SELECT") and "pg_attribute" in sql:
            self._rows = list(self._conn.column_rows)
        elif sql.startswith("SELECT * FROM ("):
            if self._conn.fail_query:
                raise RuntimeError("boom")
            self._rows = list(self._conn.data)
            self.description = [("col",), ("otra",)]

    def fetchall(self):
        return list(self._rows)


def _adapter(conn: _FakeConn) -> PostgresReadOnlyQuery:
    return PostgresReadOnlyQuery(
        "postgresql://x", ALLOWLIST, connect=lambda: conn
    )


def test_adapter_uses_read_only_transaction_timeout_limit_and_rollback():
    """R18, R19: READ ONLY, statement_timeout, LIMIT max+1, ROLLBACK y cierre."""
    conn = _FakeConn()
    adapter = _adapter(conn)
    result = adapter.run(ValidatedQuery(SAFE_SQL, ("consultas.v_x",)), 10, 1234)
    assert conn.statements[0] == "SET TRANSACTION READ ONLY"
    assert conn.statements[1] == "SET LOCAL statement_timeout = 1234"
    assert conn.statements[-2] == (
        "SELECT * FROM (SELECT col FROM consultas.v_x) AS q LIMIT 11"
    )
    assert conn.statements[-1] == "ROLLBACK"
    assert result.rows == [("a", "b")] and result.truncated is False
    assert conn.closed is True
    assert conn.closed_after_statements[-1] == "ROLLBACK"


def test_adapter_rolls_back_and_closes_after_execution_error():
    """R18, R24: un error de ejecución siempre termina con ROLLBACK y cierre."""
    conn = _FakeConn()
    conn.fail_query = True
    adapter = _adapter(conn)
    with pytest.raises(DbQueryUnavailable):
        adapter.run(ValidatedQuery(SAFE_SQL, ("consultas.v_x",)), 10, 1000)
    assert conn.statements[-1] == "ROLLBACK"
    assert conn.closed is True
    assert conn.closed_after_statements[-1] == "ROLLBACK"


def test_adapter_close_failure_does_not_replace_query_result(caplog):
    """R18: un fallo al cerrar se registra y no oculta el resultado de la consulta."""
    caplog.set_level(logging.DEBUG)
    conn = _FakeConn()
    conn.close_error = True
    adapter = _adapter(conn)
    result = adapter.run(ValidatedQuery(SAFE_SQL, ("consultas.v_x",)), 10, 1000)
    assert result.rows == [("a", "b")]
    assert conn.statements[-1] == "ROLLBACK"
    assert "db_query_close_failed" in caplog.text
    assert "boom" not in caplog.text


def test_adapter_rejects_non_view_object_without_running_sql():
    """R20: un objeto que no es vista impide ejecutar el SQL validado."""
    conn = _FakeConn()
    conn.kinds = [("consultas.v_x", "r"), ("consultas.v_y", "v")]
    adapter = _adapter(conn)
    with pytest.raises(DbQueryUnavailable) as excinfo:
        adapter.run(ValidatedQuery(SAFE_SQL, ("consultas.v_x",)), 10, 1000)
    assert all(not sql.startswith("SELECT * FROM (") for sql in conn.statements)
    assert "v_x" not in str(excinfo.value)
    assert conn.closed is True


@pytest.mark.parametrize(
    "column_rows",
    [
        [
            ("consultas.v_x", "col"),
            ("consultas.v_x", "otra"),
            ("consultas.v_x", "secreto"),
            ("consultas.v_y", "col"),
            ("consultas.v_y", "otra"),
        ],
        [
            ("consultas.v_x", "col"),
            ("consultas.v_y", "col"),
            ("consultas.v_y", "otra"),
        ],
    ],
)
def test_adapter_requires_exact_columns_without_leaking_names(column_rows, caplog):
    """R20: una columna de más o de menos responde unavailable sin nombres."""
    caplog.set_level(logging.DEBUG)
    conn = _FakeConn()
    conn.column_rows = column_rows
    adapter = _adapter(conn)
    with pytest.raises(DbQueryUnavailable) as excinfo:
        adapter.run(ValidatedQuery(SAFE_SQL, ("consultas.v_x",)), 10, 1000)
    assert all(not sql.startswith("SELECT * FROM (") for sql in conn.statements)
    assert "secreto" not in str(excinfo.value)
    assert "secreto" not in caplog.text


def test_adapter_memoizes_successful_catalog_check():
    """R20: tras verificar columnas exactas no repite la comprobación."""
    conn = _FakeConn()
    adapter = _adapter(conn)
    query = ValidatedQuery(SAFE_SQL, ("consultas.v_x",))
    adapter.run(query, 10, 1000)
    adapter.run(query, 10, 1000)
    kinds = [sql for sql in conn.statements if "relkind" in sql]
    columns = [sql for sql in conn.statements if "pg_attribute" in sql]
    assert len(kinds) == 1 and len(columns) == 1


def test_adapter_rechecks_catalog_after_a_failure():
    """R20: un fallo de catálogo no se memoriza y se reintenta."""
    conn = _FakeConn()
    conn.column_rows = [("consultas.v_x", "col")]
    adapter = _adapter(conn)
    query = ValidatedQuery(SAFE_SQL, ("consultas.v_x",))
    with pytest.raises(DbQueryUnavailable):
        adapter.run(query, 10, 1000)
    conn.column_rows = [
        ("consultas.v_x", "col"),
        ("consultas.v_x", "otra"),
        ("consultas.v_y", "col"),
        ("consultas.v_y", "otra"),
    ]
    adapter.run(query, 10, 1000)
    columns = [sql for sql in conn.statements if "pg_attribute" in sql]
    assert len(columns) == 2


def test_adapter_truncates_to_max_rows_and_requests_one_more():
    """R19: con max_rows+1 filas devuelve max_rows y marca el truncado."""
    conn = _FakeConn()
    conn.data = [("a", "b"), ("c", "d"), ("e", "f")]
    adapter = _adapter(conn)
    result = adapter.run(ValidatedQuery(SAFE_SQL, ("consultas.v_x",)), 2, 1000)
    assert "LIMIT 3" in conn.statements[-2]
    assert result.rows == [("a", "b"), ("c", "d")] and result.truncated is True


# --- R19, R26: formato -------------------------------------------------------------------


def test_format_rows_caps_length_and_keeps_truncated_note():
    """R19, R26: el texto se recorta a max_chars y conserva la nota."""
    result = QueryResult(
        columns=["col"], rows=[("x" * 500,)], truncated=True
    )
    text = format_rows(result, 200, "Hay más filas.")
    assert len(text) <= 200
    assert text.endswith("Hay más filas.")


def test_truncated_query_reply_is_capped(env):
    """R19, R26: la respuesta final respeta DB_QUERY_MAX_REPLY_CHARS."""
    _configure(env)
    _advisor(env)
    env.settings.db_query_max_reply_chars = 200
    env.db_query.result = QueryResult(
        columns=["col"], rows=[("x" * 100,), ("y" * 100,)], truncated=True
    )
    _post(env, "/consultar cuántos pedidos hay")
    reply = _last_reply(env)
    assert len(reply) <= 200
    assert reply.endswith(env.settings.db_query_truncated_note)


# --- R21, R22, R23, R24, R32: auditoría y errores ----------------------------------------


def test_ok_query_writes_audit_with_expected_fields(env):
    """R21: una consulta correcta deja perfil, vistas, filas y hash del SQL."""
    _configure(env)
    profile = _advisor(env)
    env.db_query.result = QueryResult(columns=["col"], rows=[("a",)], truncated=False)
    _post(env, "/consultar cuántos pedidos hay")
    audit = env.repo.db_query_audits[-1]
    assert audit.profile_id == profile.id
    assert audit.telegram_user_id == 10
    assert audit.status == "ok"
    assert audit.views == "consultas.v_x"
    assert audit.row_count == 1
    assert audit.sql_sha256 == hashlib.sha256(SAFE_SQL.encode()).hexdigest()
    assert audit.at == FIXED_NOW


@pytest.mark.parametrize(
    ("setup", "expected_status"),
    [
        ("forbidden", "forbidden"),
        ("malformed", "malformed"),
        ("disabled", "disabled"),
        ("rejected", "rejected"),
        ("unavailable", "unavailable"),
    ],
)
def test_audit_is_written_for_every_outcome(env, setup, expected_status):
    """R21: también se audita cada solicitud denegada o fallida."""
    _configure(env, enabled=setup != "disabled")
    if setup == "forbidden":
        _advisor(env, user=20, role="cliente")
        _post(env, "/consultar hola", user=20)
    else:
        _advisor(env)
        if setup == "malformed":
            _post(env, "/consultar")
        elif setup == "disabled":
            _post(env, "/consultar hola")
        elif setup == "rejected":
            env.llm.reply = "no es json"
            _post(env, "/consultar hola")
        else:
            env.db_query.fail = True
            _post(env, "/consultar hola")
    assert env.repo.db_query_audits[-1].status == expected_status


def test_audit_and_logs_never_store_question_sql_rows_or_dsn(env, caplog):
    """R22: ni la pregunta, ni el SQL, ni las filas, ni el DSN quedan en rastro."""
    caplog.set_level(logging.DEBUG)
    _configure(env)
    _advisor(env)
    env.settings.db_query_database_url = (
        "postgresql://usuario:CLAVE-SECRETA@db/lazaro_ro"
    )
    question = "PREGUNTA-SECRETA-999"
    sql = "SELECT col FROM consultas.v_x WHERE otra = 'SQL-SECRETO-777'"
    row = "FILA-SECRETA-555"
    env.llm.reply = json.dumps({"sql": sql})
    env.db_query.result = QueryResult(columns=["col"], rows=[(row,)], truncated=False)
    _post(env, f"/consultar {question}")

    audit = env.repo.db_query_audits[-1]
    recorded = " ".join(
        [
            str(audit.profile_id),
            str(audit.telegram_user_id),
            audit.status,
            audit.views,
            str(audit.row_count),
            audit.sql_sha256,
        ]
    )
    for secret in (question, "SQL-SECRETO", row, "CLAVE-SECRETA"):
        assert secret not in recorded
        assert secret not in caplog.text


def test_audit_failure_returns_unavailable_without_sending_rows(env):
    """R23, R32: si falla la auditoría no se envían los resultados."""
    _configure(env)
    _advisor(env)
    env.repo.fail_db_query_audit = True
    env.db_query.result = QueryResult(
        columns=["col"], rows=[("RESULTADO-SECRETO",)], truncated=False
    )
    _post(env, "/consultar cuántos pedidos hay")
    assert env.gateway.sent == [(10, env.settings.db_query_unavailable_reply)]
    assert "RESULTADO-SECRETO" not in _last_reply(env)
    assert len(env.db_query.calls) == 1


def test_database_error_returns_fixed_text_without_internal_details(env, caplog):
    """R24: el fallo de ejecución responde unavailable sin SQL ni nombres."""
    caplog.set_level(logging.DEBUG)
    _configure(env)
    _advisor(env)
    env.db_query.error = DbQueryUnavailable(
        "error en consultas.v_x columna secreto"
    )
    _post(env, "/consultar cuántos pedidos hay")
    reply = _last_reply(env)
    assert reply == env.settings.db_query_unavailable_reply
    for fragment in ("consultas.v_x", "secreto", "SELECT"):
        assert fragment not in reply
        assert fragment not in caplog.text
    assert env.repo.db_query_audits[-1].status == "unavailable"


def test_fake_db_query_records_calls():
    """R18: la versión falsa registra cada llamada para poder verificarla."""
    fake = FakeDbQuery(result=SAFE_RESULT)
    query = ValidatedQuery(SAFE_SQL, ("consultas.v_x",))
    assert fake.run(query, 5, 1000) is SAFE_RESULT
    assert fake.calls == [(query, 5, 1000)]
