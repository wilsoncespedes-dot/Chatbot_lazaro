"""Tests del reenvío cliente → asesor en el orquestador (feature #16)."""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

import httpx
import pytest
from lazaro_contracts import CaseClientMessageResponse, CaseCloseResponse

from orchestrator.adapters.handover import HttpHandoverClient
from orchestrator.adapters.repository import FakeRepository, PostgresRepository
from orchestrator.config import Settings
from orchestrator.domain import (
    AuthorizationDenied,
    ForwardRejected,
    ServiceUnavailable,
)

FIXED_NOW = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
RECEIVED_AT = datetime(2026, 1, 2, 3, 4, 0, tzinfo=timezone.utc)
ROOT = Path(__file__).resolve().parents[3]
PKG = Path(__file__).resolve().parents[1] / "orchestrator"

CONVERSATION_TEXTS = [
    "ADVISOR_REPLY_CONFIRMATION",
    "ADVISOR_CLOSE_CONFIRMATION",
    "CASE_CLOSED_REPLY",
    "FORWARD_FAILED_REPLY",
    "ADVISOR_COMMAND_HELP",
    "ADVISOR_COMMAND_FORBIDDEN_REPLY",
    "ADVISOR_COMMAND_FAILED_REPLY",
    "ADVISOR_COMMAND_CASE_CLOSED_REPLY",
]


def _link(env, case_id: str = "case-1", user: int = 10, chat: int = 100):
    contact = env.repo.get_or_create_contact(user, chat, FIXED_NOW)
    env.repo.link_case(case_id, contact.id, FIXED_NOW)
    return contact


def _contact_messages(env, contact) -> list[tuple[str, str]]:
    return [(m.role, m.text) for m in env.repo.messages if m.contact_id == contact.id]


# --- Reenvío cliente → asesor ------------------------------------------------------------


def test_assigned_case_message_is_forwarded_without_rag(env):
    """conversacion_cliente_asesor R27, R28: caso assigned → client-message, sin RAG."""
    contact = _link(env)
    env.handover.client_message_status = "forwarded"
    env.post(text="Sigue sin funcionar")
    assert ("user", "Sigue sin funcionar") in _contact_messages(env, contact)
    assert env.handover.client_messages == [("case-1", "Sigue sin funcionar", RECEIVED_AT)]
    assert ("forwarded_to_advisor", "case:case-1") in env.events()
    assert env.rag.calls == []
    assert env.llm.calls == []
    assert env.handover.requests == []
    assert env.gateway.sent == []


def test_forward_runs_before_handover_keywords(env):
    """conversacion_cliente_asesor R27: el reenvío va antes de las palabras clave."""
    _link(env)
    env.handover.client_message_status = "forwarded"
    env.post(text="quiero un asesor")
    assert len(env.handover.client_messages) == 1
    assert env.handover.requests == []
    assert env.rag.calls == []


def test_forward_uses_last_linked_case(env):
    """conversacion_cliente_asesor R27, R35: se usa el caso vinculado más reciente."""
    contact = _link(env, case_id="case-old")
    env.repo.link_case("case-new", contact.id, FIXED_NOW)
    env.handover.client_message_status = "forwarded"
    env.post()
    assert env.handover.client_messages[0][0] == "case-new"


@pytest.mark.parametrize("flow", ["rag", "no_results", "keyword"])
def test_not_assigned_follows_current_flow(env, flow):
    """conversacion_cliente_asesor R29: not_assigned sigue el flujo actual sin cambios."""
    env.handover.client_message_status = "not_assigned"
    if flow == "no_results":
        env.rag.results = []
    text = "quiero un asesor" if flow == "keyword" else "mi pregunta"
    env.post(text=text, update_id=1)
    baseline_sent = list(env.gateway.sent)
    baseline_events = env.events()
    contact = env.repo.contacts[10]
    if env.repo.get_contact_last_case(contact.id) is None:
        env.repo.link_case("case-1", contact.id, FIXED_NOW)
    env.post(text=text, update_id=2)
    assert env.gateway.sent[len(baseline_sent):] == baseline_sent
    assert env.events()[len(baseline_events):] == baseline_events
    assert len(env.handover.client_messages) == 1


def test_unknown_case_follows_current_flow(env):
    """conversacion_cliente_asesor R30: 404 de client-message → flujo actual."""
    _link(env)
    env.handover.client_message_error = "not_found"
    env.post()
    assert len(env.rag.calls) == 1
    assert (100, "Respuesta final") in env.gateway.sent
    assert all(t != "forward_failed" for t, _ in env.events())


def test_contact_without_case_does_not_call_client_message(env):
    """conversacion_cliente_asesor R31: sin caso vinculado no se llama a client-message."""
    env.post()
    assert env.handover.client_messages == []
    assert len(env.rag.calls) == 1


@pytest.mark.parametrize(
    ("mode", "code"),
    [("error", "upstream_error"), ("fail", "handover_unavailable")],
)
def test_forward_failure_sends_fixed_text_without_rag(env, mode, code):
    """conversacion_cliente_asesor R32, R33: fallo de reenvío → texto fijo, sin RAG."""
    contact = _link(env)
    if mode == "error":
        env.handover.client_message_error = "upstream_error"
    else:
        env.handover.fail_client_message = True
    env.post()
    assert ("forward_failed", f"case:case-1 code:{code}") in env.events()
    assert env.gateway.sent == [(100, env.settings.forward_failed_reply)]
    assert ("bot", env.settings.forward_failed_reply) in _contact_messages(env, contact)
    assert env.rag.calls == []
    assert env.llm.calls == []
    assert env.handover.requests == []


def test_advisor_plain_message_follows_current_flow(env):
    """conversacion_cliente_asesor R34: un asesor que no usa comando es un cliente más."""
    env.post(text="¿Cómo instalo el módulo?", user=111, chat=111)
    assert len(env.rag.calls) == 1
    assert (111, "Respuesta final") in env.gateway.sent
    assert env.handover.authorized == []

    contact = env.repo.contacts[111]
    env.repo.link_case("case-1", contact.id, FIXED_NOW)
    env.handover.client_message_status = "forwarded"
    env.post(text="otra cosa", user=111, chat=111, update_id=2)
    assert env.handover.client_messages[-1][0] == "case-1"


# --- Repositorio -------------------------------------------------------------------------


def test_fake_repository_last_case_for_contact():
    """conversacion_cliente_asesor R35: FakeRepository devuelve el vínculo más reciente."""
    repo = FakeRepository()
    contact = repo.get_or_create_contact(10, 100, FIXED_NOW)
    assert repo.get_contact_last_case(contact.id) is None
    repo.link_case("case-1", contact.id, FIXED_NOW)
    repo.link_case("case-2", contact.id, FIXED_NOW)
    assert repo.get_contact_last_case(contact.id) == "case-2"
    repo.link_case("case-1", contact.id, FIXED_NOW)
    assert repo.get_contact_last_case(contact.id) == "case-2"


class _Cursor:
    def __init__(self, log):
        self.log = log

    def execute(self, sql, params=()):
        self.log.append((sql, tuple(params)))

    def fetchall(self):
        return []


class _Conn:
    def __init__(self):
        self.log: list = []

    def cursor(self):
        return _Cursor(self.log)

    def commit(self):
        pass

    def rollback(self):
        pass


def test_postgres_last_case_uses_parameters_only():
    """conversacion_cliente_asesor R35: SQL parametrizado, ordenado y con límite 1."""
    conn = _Conn()
    repo = PostgresRepository("postgresql://x", connect=lambda: conn)
    secret = "'; DROP TABLE x; --"
    assert repo.get_contact_last_case(secret) is None
    statements = [(sql, params) for sql, params in conn.log if not sql.startswith("CREATE")]
    assert len(statements) == 1
    sql, params = statements[0]
    assert "ORDER BY created_at DESC" in sql and "LIMIT 1" in sql
    assert secret not in sql and secret in params
    assert sql.count("%s") == len(params)


# --- Logs --------------------------------------------------------------------------------


@pytest.mark.parametrize("mode", ["forwarded", "upstream_error", "unavailable"])
def test_forward_logs_do_not_contain_client_text(env, caplog, mode):
    """conversacion_cliente_asesor R36: el texto del cliente nunca aparece en el log."""
    secret = "SECRETO-CLIENTE-456"
    _link(env)
    if mode == "forwarded":
        env.handover.client_message_status = "forwarded"
    elif mode == "upstream_error":
        env.handover.client_message_error = "upstream_error"
    else:
        env.handover.fail_client_message = True
    caplog.set_level(logging.DEBUG)
    env.post(text=secret)
    assert caplog.records
    assert secret not in caplog.text


# --- Cliente HTTP de handover ------------------------------------------------------------


@pytest.fixture()
def captured(monkeypatch):
    requests: list[tuple[httpx.Request, float]] = []
    holder = {"response": httpx.Response(200, json={})}

    def handler(request: httpx.Request) -> httpx.Response:
        return holder["response"]

    def fake_post(url, *, timeout=None, **kwargs):
        result = holder["response"]
        if isinstance(result, Exception):
            raise result
        with httpx.Client(transport=httpx.MockTransport(handler)) as client:
            req = client.build_request("POST", url, **kwargs)
            requests.append((req, timeout))
            return client.send(req)

    monkeypatch.setattr(httpx, "post", fake_post)
    return requests, holder


def test_http_handover_client_forward_posts_to_client_message_route(captured):
    """conversacion_cliente_asesor R37, R38: URL, token, timeout y cuerpo de la ruta."""
    requests, holder = captured
    holder["response"] = httpx.Response(200, json={"status": "forwarded", "case_id": "a b"})
    response = HttpHandoverClient("http://ho:8000/", "tok", 3).forward_client_message(
        "a b", "hola", datetime(2026, 1, 2, 3, 4, tzinfo=timezone.utc)
    )
    assert isinstance(response, CaseClientMessageResponse)
    assert (response.status, response.case_id) == ("forwarded", "a b")
    request, timeout = requests[0]
    assert request.url.raw_path == b"/cases/a%20b/client-message"
    assert request.headers["X-Service-Token"] == "tok"
    assert timeout == 3
    assert json.loads(request.content) == {"text": "hola", "at": "2026-01-02T03:04:00Z"}


@pytest.mark.parametrize(
    ("status", "code"), [(404, "not_found"), (502, "upstream_error")]
)
def test_http_handover_client_forward_maps_rejections(captured, status, code):
    """conversacion_cliente_asesor R39: 404 y 502 se convierten en ForwardRejected."""
    _, holder = captured
    holder["response"] = httpx.Response(status, json={"error": code, "message": "x"})
    with pytest.raises(ForwardRejected) as excinfo:
        HttpHandoverClient("http://ho", "tok").forward_client_message(
            "case-1", "hola", FIXED_NOW
        )
    assert excinfo.value.code == code


FAIL_CLOSED_FORWARD = [
    ("unauthorized", httpx.Response(401, json={"error": "unauthorized", "message": "x"})),
    ("validation", httpx.Response(422, json={"error": "validation_error", "message": "x"})),
    ("internal", httpx.Response(500, json={"error": "internal_error", "message": "x"})),
    ("wrong_error", httpx.Response(404, json={"error": "otro", "message": "x"})),
    ("not_json", httpx.Response(502, content=b"no-json")),
    ("wrong_status", httpx.Response(200, json={"status": "sent", "case_id": "case-1"})),
    ("other_case", httpx.Response(200, json={"status": "forwarded", "case_id": "case-2"})),
    ("connect_error", httpx.ConnectError("sin conexión")),
    ("timeout", httpx.ReadTimeout("sin respuesta")),
]


@pytest.mark.parametrize(("name", "response"), FAIL_CLOSED_FORWARD)
def test_http_handover_client_forward_fails_closed(captured, name, response):
    """conversacion_cliente_asesor R40: cualquier respuesta distinta de R38/R39 falla cerrada."""
    _, holder = captured
    holder["response"] = response
    with pytest.raises(ServiceUnavailable):
        HttpHandoverClient("http://ho", "tok").forward_client_message(
            "case-1", "hola", FIXED_NOW
        )


def test_http_handover_client_close_posts_to_close_route(captured):
    """conversacion_cliente_asesor R41: close llama a la ruta con token, cuerpo y timeout."""
    requests, holder = captured
    holder["response"] = httpx.Response(200, json={"status": "closed", "case_id": "a b"})
    response = HttpHandoverClient("http://ho:8000/", "tok", 3).close("a b", "111")
    assert isinstance(response, CaseCloseResponse)
    assert (response.status, response.case_id) == ("closed", "a b")
    request, timeout = requests[0]
    assert request.url.raw_path == b"/cases/a%20b/close"
    assert request.headers["X-Service-Token"] == "tok"
    assert timeout == 3
    assert json.loads(request.content) == {"advisor_id": "111"}


@pytest.mark.parametrize(
    ("status", "code"),
    [(403, "forbidden"), (404, "not_found"), (409, "case_closed")],
)
def test_http_handover_client_close_maps_denials(captured, status, code):
    """conversacion_cliente_asesor R42: 403/404/409 se convierten en AuthorizationDenied."""
    _, holder = captured
    holder["response"] = httpx.Response(status, json={"error": code, "message": "x"})
    with pytest.raises(AuthorizationDenied) as excinfo:
        HttpHandoverClient("http://ho", "tok").close("case-1", "111")
    assert excinfo.value.code == code


FAIL_CLOSED_CLOSE = [
    ("unauthorized", httpx.Response(401, json={"error": "unauthorized", "message": "x"})),
    ("validation", httpx.Response(422, json={"error": "validation_error", "message": "x"})),
    ("internal", httpx.Response(500, json={"error": "internal_error", "message": "x"})),
    ("wrong_error", httpx.Response(403, json={"error": "otro", "message": "x"})),
    ("other_case", httpx.Response(200, json={"status": "closed", "case_id": "case-2"})),
    ("not_json", httpx.Response(200, content=b"no-json")),
    ("connect_error", httpx.ConnectError("sin conexión")),
]


@pytest.mark.parametrize(("name", "response"), FAIL_CLOSED_CLOSE)
def test_http_handover_client_close_fails_closed(captured, name, response):
    """conversacion_cliente_asesor R43: cualquier respuesta distinta de R41/R42 falla cerrada."""
    _, holder = captured
    holder["response"] = response
    with pytest.raises(ServiceUnavailable):
        HttpHandoverClient("http://ho", "tok").close("case-1", "111")


# --- Configuración -----------------------------------------------------------------------


@pytest.mark.parametrize("name", CONVERSATION_TEXTS)
def test_conversation_texts_have_defaults_and_read_env(monkeypatch, name):
    """conversacion_cliente_asesor R44: cada texto fijo tiene valor por defecto y lee el entorno."""
    monkeypatch.delenv(name, raising=False)
    field = name.lower()
    assert getattr(Settings(), field).strip()
    monkeypatch.setenv(name, "x")
    assert getattr(Settings(), field) == "x"


@pytest.mark.parametrize("name", CONVERSATION_TEXTS)
def test_conversation_texts_are_in_env_example(monkeypatch, name):
    """conversacion_cliente_asesor R45: .env.example declara cada texto con su valor por defecto."""
    monkeypatch.delenv(name, raising=False)
    text = (ROOT / ".env.example").read_text(encoding="utf-8")
    line = next(ln for ln in text.splitlines() if ln.startswith(f"{name}="))
    assert line.split("=", 1)[1] == getattr(Settings(), name.lower())


def test_orchestrator_does_not_read_advisor_list():
    """conversacion_cliente_asesor R46: el orquestador no lee la lista de asesores."""
    assert "advisor_chat_ids" not in Settings.model_fields
    for path in PKG.rglob("*.py"):
        source = path.read_text(encoding="utf-8")
        assert "ADVISOR_CHAT_IDS" not in source
        assert "advisor_chat_ids" not in source
