"""Tests del traspaso en el orquestador: aviso sin asesores, vínculo caso-contacto y
POST /cases/{id}/reply."""
from __future__ import annotations

import json
from datetime import datetime, timezone

import httpx
import pytest
from lazaro_contracts import CaseReplyResponse, ErrorResponse, HandoverResponse

from orchestrator.adapters.handover import HttpHandoverClient
from orchestrator.adapters.repository import PostgresRepository
from orchestrator.domain import Contact, ServiceUnavailable

HEADERS = {"X-Service-Token": "svc-token"}
FIXED_NOW = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)


def _reply(env, case_id: str = "case-1", advisor_id: str = "555", text: str = "Hola, soy tu asesor",
           headers: dict | None = None, body: dict | None = None):
    payload = {"advisor_id": advisor_id, "text": text} if body is None else body
    return env.client.post(f"/cases/{case_id}/reply", json=payload,
                           headers=HEADERS if headers is None else headers)


def _open_case(env) -> Contact:
    """Crea el caso case-1 del contacto (telegram 10, chat 100) con un traspaso notificado."""
    env.post(text="quiero un asesor", update_id=1)
    return env.repo.contacts[10]


def _snapshot(env) -> tuple:
    return (len(env.repo.messages), len(env.repo.events), list(env.gateway.sent),
            list(env.handover.assigned))


# --- _handover: no_advisors y vínculo caso-contacto ---------------------------------------


def test_no_advisors_sends_fixed_reply_to_client(env):
    """R29, R30: con no_advisors se registra el evento, se envía NO_ADVISORS_REPLY y se guarda."""
    env.handover.status = "no_advisors"
    env.post(text="quiero un asesor", update_id=1)
    reply = env.settings.no_advisors_reply
    assert env.gateway.sent == [(100, reply)]
    assert ("handover_failed", "no_advisors") in env.events()
    bot = [m for m in env.repo.messages if m.role == "bot"]
    assert [(m.text, m.at) for m in bot] == [(reply, FIXED_NOW)]


def test_no_advisors_after_no_relevant_chunks_also_informs_client(env):
    """R30: el cliente nunca queda sin respuesta, también con motivo no_relevant_chunks."""
    env.handover.status = "no_advisors"
    env.rag.results = []
    env.post(update_id=1)
    assert env.gateway.sent == [
        (100, env.settings.no_answer_reply), (100, env.settings.no_advisors_reply)
    ]


def test_case_is_linked_to_contact_after_handover(env):
    """R28: el case_id devuelto por handover queda vinculado al contacto con cualquier status."""
    contact = _open_case(env)
    assert env.repo.get_case_contact("case-1") == contact
    env.handover.status = "no_advisors"
    env.post(text="quiero un asesor", update_id=2)
    assert env.repo.get_case_contact("case-2") == contact
    assert env.repo.get_case_contact("otro") is None


def test_case_link_uses_effective_case_id(env):
    """R28: se vincula el case_id efectivo que devuelve handover, no el propuesto."""
    env.handover.request = lambda req: HandoverResponse(status="notified", case_id="reused-9")
    contact = _open_case(env)
    assert env.repo.get_case_contact("reused-9") == contact
    assert env.repo.get_case_contact("case-1") is None


def test_handover_unavailable_creates_no_link(env):
    """R28: si handover no responde, no hay caso que vincular (comportamiento previo intacto)."""
    env.handover.fail = True
    env.post(text="quiero un asesor", update_id=1)
    assert env.repo.case_links == {}
    assert env.gateway.sent == []


# --- POST /cases/{id}/reply ---------------------------------------------------------------


def test_reply_sends_text_stores_advisor_message_and_event(env):
    """R31, R32: envía el texto al chat del contacto, lo guarda como advisor y registra evento."""
    contact = _open_case(env)
    env.gateway.sent.clear()
    response = _reply(env, "case-1", "555", "Hola, soy tu asesor")
    assert response.status_code == 200
    assert response.json() == {"sent": True}
    CaseReplyResponse.model_validate(response.json())
    assert env.gateway.sent == [(100, "Hola, soy tu asesor")]
    advisor = [m for m in env.repo.messages if m.role == "advisor"]
    assert [(m.contact_id, m.text, m.at) for m in advisor] == [
        (contact.id, "Hola, soy tu asesor", FIXED_NOW)
    ]
    assert ("advisor_reply", "advisor:555") in env.events()


def test_reply_assigns_case_in_handover(env):
    """R33: tras enviar con éxito se llama a POST /cases/{id}/assign con el advisor_id."""
    _open_case(env)
    _reply(env, "case-1", "555")
    assert env.handover.assigned == [("case-1", "555")]


def test_reply_assign_failure_still_returns_sent(env):
    """R34: si assign falla se registra assign_failed y se responde 200 sent=true."""
    _open_case(env)
    env.handover.fail_assign = True
    response = _reply(env, "case-1", "555")
    assert response.status_code == 200
    assert response.json() == {"sent": True}
    assert ("assign_failed", "case-1") in env.events()
    assert [m.role for m in env.repo.messages].count("advisor") == 1


def test_reply_unknown_case_returns_404_without_sending(env):
    """R35: un caso que el orquestador no conoce -> 404 not_found sin POST /send."""
    _open_case(env)
    before = _snapshot(env)
    response = _reply(env, "no-existe")
    assert response.status_code == 404
    ErrorResponse.model_validate(response.json())
    assert response.json()["error"] == "not_found"
    assert _snapshot(env) == before


def test_reply_send_failure_returns_502_and_stores_nothing(env):
    """R36: si POST /send falla -> 502 upstream_error, sin guardar ni llamar a assign."""
    _open_case(env)
    env.gateway.fail = True
    before = _snapshot(env)
    response = _reply(env, "case-1")
    assert response.status_code == 502
    ErrorResponse.model_validate(response.json())
    assert response.json()["error"] == "upstream_error"
    assert _snapshot(env) == before


@pytest.mark.parametrize("headers", [{}, {"X-Service-Token": "otro"}])
def test_reply_without_token_returns_401(env, headers):
    """R37: sin X-Service-Token válido -> 401 unauthorized sin enviar nada."""
    _open_case(env)
    before = _snapshot(env)
    response = _reply(env, "case-1", headers=headers)
    assert response.status_code == 401
    assert response.json()["error"] == "unauthorized"
    assert _snapshot(env) == before


@pytest.mark.parametrize(
    "body",
    [{}, {"advisor_id": "555"}, {"advisor_id": "", "text": "x"}, {"advisor_id": "5", "text": ""},
     {"advisor_id": "5", "text": "x", "extra": 1}, {"advisor_id": "5", "text": "x" * 4097}],
)
def test_reply_invalid_body_returns_422(env, body):
    """R38: cuerpo que no valida contra CaseReplyRequest -> 422 validation_error."""
    _open_case(env)
    before = _snapshot(env)
    response = _reply(env, "case-1", body=body)
    assert response.status_code == 422
    ErrorResponse.model_validate(response.json())
    assert response.json()["error"] == "validation_error"
    assert _snapshot(env) == before


# --- Adaptadores reales con transporte / conexión falsos ----------------------------------


@pytest.fixture()
def captured(monkeypatch):
    requests: list[tuple[httpx.Request, float]] = []
    reply = {"response": httpx.Response(200, json={"status": "assigned", "case_id": "a b"})}

    def handler(request: httpx.Request) -> httpx.Response:
        return reply["response"]

    def fake_post(url, *, timeout=None, **kwargs):
        with httpx.Client(transport=httpx.MockTransport(handler)) as client:
            req = client.build_request("POST", url, **kwargs)
            requests.append((req, timeout))
            return client.send(req)

    monkeypatch.setattr(httpx, "post", fake_post)
    return requests, reply


def test_http_handover_client_assign_posts_to_assign_route(captured):
    """R33: assign llama a POST /cases/{id}/assign con token, advisor_id y timeout."""
    requests, _ = captured
    resp = HttpHandoverClient("http://ho:8000/", "tok", 3).assign("a b", "555")
    assert resp.status == "assigned"
    request, timeout = requests[0]
    assert request.url.raw_path == b"/cases/a%20b/assign"
    assert request.headers["X-Service-Token"] == "tok" and timeout == 3
    assert json.loads(request.content) == {"advisor_id": "555"}


@pytest.mark.parametrize("status", [403, 404, 409, 500])
def test_http_handover_client_assign_raises_on_error_status(captured, status):
    """R34: un 4xx/5xx de assign se convierte en ServiceUnavailable."""
    _, reply = captured
    reply["response"] = httpx.Response(status, json={"error": "x", "message": "y"})
    with pytest.raises(ServiceUnavailable):
        HttpHandoverClient("http://ho", "tok").assign("case-1", "555")


class _Cursor:
    def __init__(self, log):
        self.log = log

    def execute(self, sql, params=()):
        self.log.append((sql, tuple(params)))

    def fetchall(self):
        return [("c1", 10, 100)]


class _Conn:
    def __init__(self):
        self.log: list = []

    def cursor(self):
        return _Cursor(self.log)

    def commit(self):
        pass

    def rollback(self):
        pass


def test_postgres_case_links_use_parameters_only():
    """R28, R31: case_links se crea y se consulta con SQL parametrizado."""
    conn = _Conn()
    repo = PostgresRepository("postgresql://x", connect=lambda: conn)
    secret = "'; DROP TABLE case_links; --"
    repo.link_case(secret, "c1", FIXED_NOW)
    contact = repo.get_case_contact(secret)
    assert contact == Contact(id="c1", telegram_user_id=10, chat_id=100)
    assert any("CREATE TABLE IF NOT EXISTS case_links" in sql for sql, _ in conn.log)
    statements = [(sql, p) for sql, p in conn.log if not sql.startswith("CREATE")]
    assert len(statements) == 2
    for sql, params in statements:
        assert secret not in sql and sql.count("%s") == len(params)
        assert secret in params
