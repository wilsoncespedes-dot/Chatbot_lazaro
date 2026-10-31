"""Tests de los adaptadores reales con conexión y transporte falsos (sin Postgres ni red)."""
from __future__ import annotations

import importlib
import json
import re
from datetime import datetime, timezone

import httpx
import pytest
from lazaro_contracts import LastMessage

from handover.adapters.gateway import HttpGatewayClient
from handover.adapters.repository import PostgresCaseRepository
from handover.domain import Case, ServiceUnavailable

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

    schema = [sql for sql, params in conn.log if sql.startswith("CREATE TABLE")]
    assert any("handover_cases" in sql for sql in schema)
    assert any("handover_notifications" in sql for sql in schema)
    statements = [(sql, params) for sql, params in conn.log if not sql.startswith("CREATE")]
    assert len(statements) == 6
    for sql, params in statements:
        assert SECRET not in sql
        assert "case-1" not in sql and "contact-1" not in sql
        assert sql.count("%s") == len(params), sql
        assert params
    assert any(SECRET in str(params) for _, params in statements)
    assert all(not re.search(r"'[^']*'", sql) for sql, _ in statements)


def test_postgres_repository_connects_lazily_and_once():
    """R26: la conexión se abre en el primer uso y el esquema se crea una sola vez."""
    calls = []
    conn = _FakeConn()
    repo = PostgresCaseRepository("postgresql://x", connect=lambda: calls.append(1) or conn)
    assert calls == []
    repo.get_case("a")
    repo.get_case("b")
    assert calls == [1]
    assert sum(sql.startswith("CREATE TABLE") for sql, _ in conn.log) == 2


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
