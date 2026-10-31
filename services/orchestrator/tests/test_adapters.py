"""Tests de los adaptadores reales con transporte falso (sin red ni Postgres)."""
from __future__ import annotations

import json
from datetime import datetime, timezone

import httpx
import pytest
from lazaro_contracts import HandoverRequest

from orchestrator.adapters import gateway, handover, llm, rag
from orchestrator.adapters.repository import PostgresRepository
from orchestrator.domain import ServiceUnavailable

NOW = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)


@pytest.fixture()
def captured(monkeypatch):
    """Sustituye httpx.post por un MockTransport y guarda las peticiones."""
    requests: list[tuple[httpx.Request, float]] = []
    responses: dict[str, httpx.Response] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        return responses[request.url.path]

    real_post = httpx.post

    def fake_post(url, *, timeout=None, **kwargs):
        with httpx.Client(transport=httpx.MockTransport(handler)) as client:
            req = client.build_request("POST", url, **kwargs)
            requests.append((req, timeout))
            return client.send(req)

    monkeypatch.setattr(httpx, "post", fake_post)
    assert real_post is not fake_post
    return requests, responses


def test_http_clients_send_service_token_url_and_timeout(captured):
    """R32"""
    requests, responses = captured
    responses["/search"] = httpx.Response(
        200, json=[{"chunk_id": "c", "manual": "M", "text": "t", "score": 0.5}]
    )
    responses["/send"] = httpx.Response(200, json={"sent": True})
    responses["/handover"] = httpx.Response(200, json={"status": "notified", "case_id": "k"})

    results = rag.HttpRagClient("http://rag:8000/", "tok", 3).search("hola", 5)
    gateway.HttpGatewayClient("http://gw:8000", "tok", 3).send(9, "texto")
    req = HandoverRequest(case_id="k", contact_id="c", chat_id=9, reason="user_request",
                          last_messages=[])
    resp = handover.HttpHandoverClient("http://ho:8000", "tok", 3).request(req)

    assert results[0].chunk_id == "c" and resp.status == "notified"
    assert [str(r.url) for r, _ in requests] == [
        "http://rag:8000/search", "http://gw:8000/send", "http://ho:8000/handover",
    ]
    for request, timeout in requests:
        assert request.headers["X-Service-Token"] == "tok"
        assert timeout == 3
    assert json.loads(requests[0][0].content) == {"query": "hola", "top_k": 5}
    assert json.loads(requests[1][0].content) == {"chat_id": 9, "text": "texto"}


def test_http_clients_raise_service_unavailable_on_errors(captured):
    requests, responses = captured
    responses["/search"] = httpx.Response(500)
    responses["/send"] = httpx.Response(502)
    responses["/handover"] = httpx.Response(200, json={"raro": 1})
    responses["/chat/completions"] = httpx.Response(200, json={"choices": []})
    with pytest.raises(ServiceUnavailable):
        rag.HttpRagClient("http://rag", "t").search("q", 1)
    with pytest.raises(ServiceUnavailable):
        gateway.HttpGatewayClient("http://gw", "t").send(1, "x")
    req = HandoverRequest(case_id="k", contact_id="c", chat_id=9, reason="user_request",
                          last_messages=[])
    with pytest.raises(ServiceUnavailable):
        handover.HttpHandoverClient("http://ho", "t").request(req)
    with pytest.raises(ServiceUnavailable):
        llm.HttpLLMClient("http://llm", "k", "m").complete("s", "u")


def test_http_llm_client_sends_only_system_and_user(captured):
    """R28, R32"""
    requests, responses = captured
    responses["/v1/chat/completions"] = httpx.Response(
        200, json={"choices": [{"message": {"content": "hola"}}]}
    )
    out = llm.HttpLLMClient("http://llm/v1", "key", "modelo", 4).complete("SYS", "USR")
    assert out == "hola"
    request, timeout = requests[0]
    body = json.loads(request.content)
    assert body["messages"] == [
        {"role": "system", "content": "SYS"},
        {"role": "user", "content": "USR"},
    ]
    assert "tools" not in body and "functions" not in body
    assert request.headers["Authorization"] == "Bearer key" and timeout == 4


class _FakeCursor:
    def __init__(self, log):
        self.log = log

    def execute(self, sql, params=()):
        self.log.append((sql, tuple(params)))

    def fetchall(self):
        sql = self.log[-1][0]
        if "FROM messages" in sql:
            return [("user", "hola", NOW)]
        return [("c1", 10, 100)]


class _FakeConn:
    def __init__(self):
        self.log: list = []

    def cursor(self):
        return _FakeCursor(self.log)

    def commit(self):
        pass

    def rollback(self):
        pass


def test_postgres_repository_uses_parameters_only():
    """R41, R31"""
    conn = _FakeConn()
    repo = PostgresRepository("postgresql://x", connect=lambda: conn, new_id=lambda: "nuevo")
    secret = "'; DROP TABLE messages; -- TEXTO-CLIENTE"
    repo.mark_update_if_new(1)
    repo.get_or_create_contact(10, 100, NOW)
    repo.add_message("c1", "user", secret, NOW)
    repo.last_messages("c1", 10)
    repo.add_event("c1", "rag_answer", "chunks_found", NOW)
    assert any(secret in params for _, params in conn.log)
    for sql, _ in conn.log:
        assert "TEXTO-CLIENTE" not in sql and "DROP TABLE messages" not in sql
        assert "'" not in sql
    dml = [sql for sql, _ in conn.log if not sql.startswith("CREATE")]
    assert dml and all("%s" in sql for sql in dml)


def test_postgres_repository_connects_lazily():
    """R34"""
    calls = []
    repo = PostgresRepository("postgresql://x", connect=lambda: calls.append(1) or _FakeConn())
    assert calls == []
    repo.add_event("c", "t", "r", NOW)
    assert calls == [1]
