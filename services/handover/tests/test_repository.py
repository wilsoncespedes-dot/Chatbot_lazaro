"""Tests de los adaptadores reales con conexión y transporte falsos (sin Postgres ni red)."""
from __future__ import annotations

import importlib
import json
import re
import threading
import time
from datetime import datetime, timezone

import httpx
import pytest
from lazaro_contracts import LastMessage

from handover.adapters.gateway import HttpGatewayClient
from handover.adapters.repository import FakeCaseRepository, PostgresCaseRepository
from handover.domain import Case, Denial, HandoverRequestRecord, ServiceUnavailable

NOW = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
SECRET = "'; DROP TABLE handover_cases; -- TEXTO-CLIENTE"


class _FakeCursor:
    def __init__(self, conn: "_FakeConn") -> None:
        self.conn = conn

    def execute(self, sql, params=()):
        self.conn.log.append((sql, tuple(params)))

    def fetchall(self):
        return self.conn.rows


class _FakeConn:
    def __init__(self, rows: list | None = None) -> None:
        self.log: list[tuple[str, tuple]] = []
        self.rows = rows or []
        self.commits = 0

    def cursor(self):
        return _FakeCursor(self)

    def commit(self):
        self.commits += 1

    def rollback(self):
        pass


def _case() -> Case:
    return Case(
        case_id="case-1",
        contact_id="contact-1",
        chat_id=900,
        reason="user_request",
        status="open",
        last_messages=[LastMessage(role="user", text=SECRET, at=NOW)],
        created_at=NOW,
    )


def test_postgres_repository_uses_parameters_only():
    """R26: toda sentencia usa %s y los valores (también texto de clientes) son parámetros."""
    conn = _FakeConn()
    repo = PostgresCaseRepository("postgresql://x", connect=lambda: conn)
    case = _case()
    repo.create_case(case)
    repo.update_case(case.model_copy(update={"status": "assigned", "advisor_id": "111"}))
    repo.find_active_case("contact-1")
    repo.get_case("case-1")
    repo.list_open_cases()
    repo.add_notification("case-1", "111", "user_request", NOW, False)
    repo.claim_timeout("case-1", NOW, NOW)
    repo.release_timeout_claim("case-1")
    repo.mark_timed_out("case-1")
    repo.update_last_messages("case-1", case.last_messages)

    schema = [sql for sql, params in conn.log if sql.startswith("CREATE TABLE")]
    assert any("handover_cases" in sql for sql in schema)
    assert any("handover_notifications" in sql for sql in schema)
    statements = [
        (sql, params)
        for sql, params in conn.log
        if not sql.startswith(("CREATE", "ALTER"))
    ]
    assert len(statements) == 10
    for sql, params in statements:
        assert SECRET not in sql
        assert "case-1" not in sql and "contact-1" not in sql
        assert sql.count("%s") == len(params), sql
        assert params
    assert any(SECRET in str(params) for _, params in statements)
    assert all(not re.search(r"'[^']*'", sql) for sql, _ in statements)


def test_postgres_conditional_updates_filter_status_in_where():
    """R27: reclamar, liberar y marcar usan un UPDATE con la condición en el WHERE."""
    conn = _FakeConn(rows=[("case-1",)])
    repo = PostgresCaseRepository("postgresql://x", connect=lambda: conn)

    before = len(_statements(conn))
    assert repo.claim_timeout("case-1", NOW, NOW) is True
    statements = _statements(conn)
    assert len(statements) == before + 1
    sql, params = statements[-1]
    assert sql.startswith("UPDATE handover_cases SET timeout_claimed_at = %s")
    assert "status = %s" in sql and "timeout_claimed_at IS NULL" in sql
    assert "timeout_claimed_at <= %s" in sql
    assert "RETURNING case_id" in sql
    assert "open" not in sql and "open" in params
    assert sql.count("%s") == len(params)
    assert not re.search(r"'[^']*'", sql)

    before = len(statements)
    assert repo.release_timeout_claim("case-1") is None
    statements = _statements(conn)
    assert len(statements) == before + 1
    sql, params = statements[-1]
    assert sql.startswith("UPDATE handover_cases SET timeout_claimed_at = NULL")
    assert "WHERE case_id = %s AND status = %s" in sql
    assert "open" not in sql and "open" in params
    assert "RETURNING" not in sql
    assert sql.count("%s") == len(params)
    assert not re.search(r"'[^']*'", sql)

    before = len(statements)
    assert repo.mark_timed_out("case-1") is True
    statements = _statements(conn)
    assert len(statements) == before + 1
    sql, params = statements[-1]
    assert sql.startswith("UPDATE handover_cases SET status = %s, timeout_claimed_at = NULL")
    assert "WHERE case_id = %s AND status = %s" in sql
    assert "RETURNING case_id" in sql
    assert "timed_out" not in sql and "timed_out" in params
    assert "open" not in sql and "open" in params
    assert sql.count("%s") == len(params)
    assert not re.search(r"'[^']*'", sql)

    conn.rows = []
    assert repo.claim_timeout("case-1", NOW, NOW) is False
    assert repo.mark_timed_out("case-1") is False


def test_postgres_update_last_messages_writes_only_last_messages():
    """R25: la reutilización escribe solo last_messages, sin estado ni asesor."""
    conn = _FakeConn()
    repo = PostgresCaseRepository("postgresql://x", connect=lambda: conn)
    repo.update_last_messages("case-1", _case().last_messages)

    sql, params = _statements(conn)[-1]
    assert sql.startswith("UPDATE handover_cases SET last_messages = CAST(%s AS JSONB)")
    assert "WHERE case_id = %s" in sql
    for field in ("status", "advisor_id", "assigned_at", "closed_at", "closed_by"):
        assert field not in sql
    assert "case-1" not in sql and SECRET not in sql
    assert sql.count("%s") == len(params)
    assert SECRET in params[0]
    assert not re.search(r"'[^']*'", sql)


def test_postgres_schema_adds_claim_column_if_not_exists():
    """R28: el ALTER de la reclamación se ejecuta una vez, tras los CREATE TABLE."""
    conn = _FakeConn()
    repo = PostgresCaseRepository("postgresql://x", connect=lambda: conn)
    repo.get_case("a")
    repo.get_case("b")

    creates = [index for index, (sql, _) in enumerate(conn.log) if sql.startswith("CREATE TABLE")]
    alters = [index for index, (sql, _) in enumerate(conn.log) if sql.startswith("ALTER TABLE")]
    assert len(creates) == 5
    assert len(alters) == 1
    sql = conn.log[alters[0]][0]
    assert sql == (
        "ALTER TABLE handover_cases ADD COLUMN IF NOT EXISTS "
        "timeout_claimed_at TIMESTAMPTZ NULL"
    )
    assert alters[0] > max(creates)


def test_postgres_repository_connects_lazily_and_once():
    """R26: la conexión se abre en el primer uso y el esquema se crea una sola vez."""
    calls = []
    conn = _FakeConn()
    repo = PostgresCaseRepository("postgresql://x", connect=lambda: calls.append(1) or conn)
    assert calls == []
    repo.get_case("a")
    repo.get_case("b")
    assert calls == [1]
    assert sum(sql.startswith("CREATE TABLE") for sql, _ in conn.log) == 5


def test_postgres_repository_reads_cases_from_rows():
    """R26: las filas se convierten en Case (last_messages desde JSONB)."""
    messages = [{"role": "user", "text": "hola", "at": "2026-01-02T03:04:05Z"}]
    row = ("case-1", "contact-1", 900, "user_request", "assigned", "111", messages,
           NOW, NOW, None, None)
    conn = _FakeConn(rows=[row])
    repo = PostgresCaseRepository("postgresql://x", connect=lambda: conn)
    case = repo.get_case("case-1")
    assert case is not None
    assert (case.status, case.advisor_id, case.chat_id) == ("assigned", "111", 900)
    assert case.last_messages[0].text == "hola"
    conn.rows = [row[:6] + (json.dumps(messages),) + row[7:]]
    assert repo.list_open_cases()[0].last_messages[0].role == "user"


def test_import_main_does_not_connect(monkeypatch):
    """R26: importar main no abre la conexión a Postgres."""
    import pg8000.dbapi

    def boom(*args, **kwargs):
        raise AssertionError("no debe conectar")

    monkeypatch.setattr(pg8000.dbapi, "connect", boom)
    module = importlib.import_module("handover.main")
    importlib.reload(module)
    assert module.app is not None


@pytest.fixture()
def captured(monkeypatch):
    """Sustituye httpx.post por un MockTransport y guarda las peticiones."""
    requests: list[tuple[httpx.Request, float]] = []
    status = {"code": 200}

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status["code"], json={"sent": True})

    def fake_post(url, *, timeout=None, **kwargs):
        with httpx.Client(transport=httpx.MockTransport(handler)) as client:
            req = client.build_request("POST", url, **kwargs)
            requests.append((req, timeout))
            return client.send(req)

    monkeypatch.setattr(httpx, "post", fake_post)
    return requests, status


def test_http_gateway_client_posts_send_with_token(captured):
    """R3, R17: el cliente real llama a POST /send con token, cuerpo SendRequest y timeout."""
    requests, _ = captured
    HttpGatewayClient("http://gw:8000/", "tok", 3).send(111, "aviso")
    request, timeout = requests[0]
    assert str(request.url) == "http://gw:8000/send"
    assert request.headers["X-Service-Token"] == "tok"
    assert json.loads(request.content) == {"chat_id": 111, "text": "aviso"}
    assert timeout == 3


def test_http_gateway_client_raises_service_unavailable_on_error(captured):
    """R6, R19: un error del gateway se convierte en ServiceUnavailable."""
    _, status = captured
    status["code"] = 502
    with pytest.raises(ServiceUnavailable):
        HttpGatewayClient("http://gw", "tok").send(111, "aviso")


# --- Handover: denegaciones y escrituras condicionales (#14) ------------------------------


def _statements(conn: _FakeConn) -> list[tuple[str, tuple]]:
    return [
        (sql, params)
        for sql, params in conn.log
        if not sql.startswith(("CREATE", "ALTER"))
    ]


def test_postgres_repository_add_denial_uses_parameters_only():
    """autorizacion_asesores R21: add_denial usa SQL parametrizado y crea su tabla."""
    conn = _FakeConn()
    repo = PostgresCaseRepository("postgresql://x", connect=lambda: conn)
    evil = "'; DROP TABLE x; --"
    repo.add_denial(Denial(case_id=evil, advisor_id="111", action="reply", at=NOW))
    assert any(
        sql.startswith("CREATE TABLE IF NOT EXISTS handover_denials") for sql, _ in conn.log
    )
    statements = _statements(conn)
    assert len(statements) == 1
    sql, params = statements[0]
    assert evil not in sql
    assert sql.count("%s") == len(params)
    assert params == (evil, "111", "reply", NOW)
    assert not re.search(r"'[^']*'", sql)


def test_fake_repository_add_denial_stores_copy():
    """autorizacion_asesores R21: el repositorio falso guarda una copia de la denegación."""
    repo = FakeCaseRepository()
    denial = Denial(case_id="case-1", advisor_id="111", action="close", at=NOW)
    repo.add_denial(denial)
    assert repo.denials == [denial]
    assert repo.denials[0] is not denial


def test_postgres_conditional_writes_use_parameters_only():
    """autorizacion_asesores R43, R37: assign condicional con una sola sentencia parametrizada."""
    evil = "'; DROP TABLE x; --"
    conn = _FakeConn(rows=[("case-1",)])
    repo = PostgresCaseRepository("postgresql://x", connect=lambda: conn)
    assert repo.assign_if_unassigned(evil, "111", NOW) is True
    sql, params = _statements(conn)[-1]
    assert sql.startswith("UPDATE handover_cases SET status = %s, advisor_id = %s")
    assert "RETURNING case_id" in sql
    assert "status IN (%s, %s)" in sql
    assert evil not in sql
    assert sql.count("%s") == len(params)
    assert not re.search(r"'[^']*'", sql)
    assert params == ("assigned", "111", NOW, evil, "open", "timed_out")

    conn.rows = []
    assert repo.assign_if_unassigned(evil, "111", NOW) is False


def test_postgres_count_assigned_by_advisor_uses_parameters():
    """autorizacion_asesores R49: el recuento filtra por estado con parámetro."""
    conn = _FakeConn(rows=[("111", 2), ("999", 1), (None, 1)])
    repo = PostgresCaseRepository("postgresql://x", connect=lambda: conn)
    assert repo.count_assigned_by_advisor() == {"111": 2, "999": 1, None: 1}
    sql, params = _statements(conn)[-1]
    assert "SELECT advisor_id, COUNT(*) FROM handover_cases" in sql
    assert "GROUP BY advisor_id" in sql
    assert "assigned" not in sql
    assert params == ("assigned",)

    fake = FakeCaseRepository()
    fake.create_case(_case())
    fake.create_case(
        _case().model_copy(update={"case_id": "case-2", "status": "assigned", "advisor_id": "111"})
    )
    fake.create_case(
        _case().model_copy(update={"case_id": "case-3", "status": "closed", "advisor_id": "111"})
    )
    assert fake.count_assigned_by_advisor() == {"111": 1}


def test_postgres_repository_serializes_statements_across_threads():
    """autorizacion_asesores R44: dos hilos nunca usan la conexión a la vez."""
    state = {"inside": 0, "max": 0, "locked": [], "errors": []}
    repo_holder: dict[str, PostgresCaseRepository] = {}

    class Cursor:
        def __init__(self, conn):
            self.conn = conn

        def execute(self, sql, params=()):
            state["inside"] += 1
            state["max"] = max(state["max"], state["inside"])
            state["locked"].append(repo_holder["repo"]._lock.locked())
            time.sleep(0.002)
            state["inside"] -= 1

        def fetchall(self):
            return []

    class Conn:
        def cursor(self):
            return Cursor(self)

        def commit(self):
            pass

        def rollback(self):
            pass

    repo = PostgresCaseRepository("postgresql://x", connect=lambda: Conn())
    repo_holder["repo"] = repo
    barrier = threading.Barrier(2)

    def worker():
        try:
            barrier.wait(timeout=5)
            for _ in range(5):
                repo.get_case("case-1")
        except Exception as exc:  # pragma: no cover - solo falla el test
            state["errors"].append(exc)

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=5)
    assert state["errors"] == []
    assert state["max"] == 1
    assert state["locked"] and all(state["locked"])


def test_postgres_repository_connects_once_with_concurrent_first_use():
    """autorizacion_asesores R45: el primer uso concurrente abre una sola conexión."""
    calls = []
    conn = _FakeConn()

    def connect():
        calls.append(1)
        time.sleep(0.01)
        return conn

    repo = PostgresCaseRepository("postgresql://x", connect=connect)
    barrier = threading.Barrier(2)

    def worker():
        barrier.wait(timeout=5)
        repo.get_case("case-1")

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=5)
    assert calls == [1]
    assert sum(sql.startswith("CREATE TABLE") for sql, _ in conn.log) == 5


def test_fake_close_if_still_allowed_checks_state_and_assignee():
    """autorizacion_asesores R41, R54, R43: el cierre falso comprueba y escribe solo sus campos."""
    allowed_cases = [
        ("open", None, None),
        ("timed_out", None, "111"),
        ("assigned", "111", "111"),
        ("assigned", "999", "999"),
        ("assigned", None, None),
    ]
    for status, advisor, allowed_assignee in allowed_cases:
        repo = FakeCaseRepository()
        original = _case().model_copy(update={"status": status, "advisor_id": advisor})
        repo.create_case(original)
        assert repo.close_if_still_allowed("case-1", "111", allowed_assignee, NOW) is True
        current = repo.cases["case-1"]
        assert (current.status, current.closed_by, current.closed_at) == ("closed", "111", NOW)
        assert (current.advisor_id, current.assigned_at) == (
            original.advisor_id,
            original.assigned_at,
        )
        assert current.last_messages == original.last_messages

    rejected_cases = [
        ("assigned", "222", "111"),
        ("assigned", "999", None),
        ("assigned", None, "999"),
        ("closed", "111", "111"),
    ]
    for status, advisor, allowed_assignee in rejected_cases:
        repo = FakeCaseRepository()
        original = _case().model_copy(update={"status": status, "advisor_id": advisor})
        repo.create_case(original)
        before = repo.cases["case-1"].model_copy(deep=True)
        assert repo.close_if_still_allowed("case-1", "111", allowed_assignee, NOW) is False
        assert repo.cases["case-1"] == before


def test_postgres_close_if_still_allowed_uses_parameters_only():
    """autorizacion_asesores R43, R41, R54: las dos variantes del cierre condicional."""
    evil = "'; DROP TABLE x; --"
    conn = _FakeConn(rows=[("case-1",)])
    repo = PostgresCaseRepository("postgresql://x", connect=lambda: conn)
    assert repo.close_if_still_allowed(evil, "111", "111", NOW) is True
    sql, params = _statements(conn)[-1]
    assert sql.startswith("UPDATE handover_cases SET status = %s, closed_by = %s")
    assert "RETURNING case_id" in sql
    assert "status IN (%s, %s)" in sql
    assert "advisor_id = %s" in sql
    assert evil not in sql
    assert "<>" not in sql
    assert sql.count("%s") == len(params)
    assert not re.search(r"'[^']*'", sql)
    assert {"open", "timed_out", "assigned"} <= set(params)
    assert params[-1] == "111"

    assert repo.close_if_still_allowed(evil, "111", None, NOW) is True
    sql, params = _statements(conn)[-1]
    assert "advisor_id IS NULL" in sql
    assert "advisor_id = %s" not in sql
    assert evil not in sql
    assert "<>" not in sql
    assert sql.count("%s") == len(params)
    assert not re.search(r"'[^']*'", sql)
    assert {"open", "timed_out", "assigned"} <= set(params)

    conn.rows = []
    assert repo.close_if_still_allowed(evil, "111", "111", NOW) is False


# --- Registro de solicitudes (#11) --------------------------------------------------------


def test_postgres_creates_requests_table_if_not_exists():
    """R16, R2, R19: cuarta tabla con las 10 columnas y sin texto de mensajes."""
    conn = _FakeConn()
    repo = PostgresCaseRepository("postgresql://x", connect=lambda: conn)
    repo.get_case("case-1")

    statements = [sql for sql, _ in conn.log if sql.startswith("CREATE TABLE")]
    assert len(statements) == 5
    table = next(sql for sql in statements if "handover_requests" in sql)
    assert table.startswith("CREATE TABLE IF NOT EXISTS handover_requests")
    for column in (
        "id BIGSERIAL PRIMARY KEY",
        "requested_case_id TEXT NOT NULL",
        "case_id TEXT NULL",
        "contact_id TEXT NOT NULL",
        "reason TEXT NOT NULL",
        "received_at TIMESTAMPTZ NOT NULL",
        "result TEXT NOT NULL",
        "advisors_configured INTEGER NOT NULL",
        "notices_delivered INTEGER NOT NULL",
        "messages_count INTEGER NOT NULL",
    ):
        assert column in table
    assert table.count(",") == 9
    assert "last_messages" not in table and "message_text" not in table


def test_postgres_request_methods_use_parameters_only():
    """R17: add_request y complete_request usan una sola sentencia parametrizada cada uno."""
    record = HandoverRequestRecord(
        requested_case_id="case-1",
        contact_id="contact-1",
        reason="user_request",
        received_at=NOW,
        result="received",
        advisors_configured=3,
        notices_delivered=0,
        messages_count=2,
    )
    conn = _FakeConn(rows=[(7,)])
    repo = PostgresCaseRepository("postgresql://x", connect=lambda: conn)
    assert repo.add_request(record) == 7

    statements = _statements(conn)
    assert len(statements) == 1
    sql, params = statements[0]
    assert sql.startswith("INSERT INTO handover_requests")
    assert "RETURNING id" in sql
    assert "case-1" not in sql and "contact-1" not in sql and "user_request" not in sql
    assert sql.count("%s") == len(params) == 9
    assert not re.search(r"'[^']*'", sql)
    assert params == ("case-1", None, "contact-1", "user_request", NOW, "received", 3, 0, 2)

    repo.complete_request(7, "case-1", "notified", 2)
    statements = _statements(conn)
    assert len(statements) == 2
    sql, params = statements[-1]
    assert sql.startswith("UPDATE handover_requests SET case_id = %s, result = %s")
    assert "WHERE id = %s" in sql
    assert "case-1" not in sql and "notified" not in sql
    assert sql.count("%s") == len(params) == 4
    assert not re.search(r"'[^']*'", sql)
    assert params == ("case-1", "notified", 2, 7)


# --- Listado de casos de un asesor (#33) --------------------------------------------------


def test_postgres_list_cases_for_advisor_is_parameterized_and_ordered():
    """contrato_listar_casos_asesor R13-R16: filtro, orden y límite con parámetros."""
    evil = "'; DROP TABLE x; --"
    conn = _FakeConn(rows=[])
    repo = PostgresCaseRepository("postgresql://x", connect=lambda: conn)
    assert repo.list_cases_for_advisor(evil, ["111", "222"], 7) == []

    sql, params = _statements(conn)[-1]
    assert sql.startswith("SELECT case_id, contact_id, chat_id")
    assert "status IN (%s, %s)" in sql
    assert "advisor_id = %s" in sql
    assert "advisor_id IS NULL" in sql
    assert "NOT (advisor_id = ANY(%s))" in sql
    assert "ORDER BY created_at ASC, case_id ASC LIMIT %s" in sql
    assert evil not in sql
    assert sql.count("%s") == len(params) == 7
    assert params == ("open", "timed_out", "assigned", evil, "assigned", ["111", "222"], 7)
    assert not re.search(r"'[^']*'", sql)


def test_fake_repository_request_ids_are_incremental_and_copies():
    """R1, R6, R8: el fake asigna ids incrementales y no comparte estado."""
    record = HandoverRequestRecord(
        requested_case_id="case-1",
        contact_id="contact-1",
        reason="user_request",
        received_at=NOW,
        result="received",
        advisors_configured=3,
        notices_delivered=0,
        messages_count=1,
    )
    repo = FakeCaseRepository()
    first = repo.add_request(record)
    second = repo.add_request(record)
    assert (first, second) == (1, 2)
    assert [r.request_id for r in repo.requests] == [1, 2]
    assert repo.requests[0] is not record

    repo.complete_request(2, "case-1", "notified", 3)
    assert repo.requests[0].result == "received"
    assert repo.requests[1] == record.model_copy(
        update={
            "request_id": 2,
            "case_id": "case-1",
            "result": "notified",
            "notices_delivered": 3,
        }
    )

