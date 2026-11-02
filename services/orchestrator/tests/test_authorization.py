"""Tests de autorización de asesores en el orquestador (feature #14)."""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

import httpx
import pytest
from lazaro_contracts import CaseAuthorizeResponse, ErrorResponse

from orchestrator.adapters.handover import HttpHandoverClient
from orchestrator.domain import AuthorizationDenied, ServiceUnavailable

HEADERS = {"X-Service-Token": "svc-token"}
FIXED_NOW = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)


def _reply(
    env,
    case_id: str = "case-1",
    advisor_id: str = "555",
    text: str = "Hola, soy tu asesor",
):
    return env.client.post(
        f"/cases/{case_id}/reply",
        json={"advisor_id": advisor_id, "text": text},
        headers=HEADERS,
    )


def _open_case(env):
    env.post(text="quiero un asesor", update_id=1)
    return env.repo.contacts[10]


def _snapshot(env) -> tuple:
    return (
        len(env.repo.messages),
        len(env.repo.events),
        list(env.gateway.sent),
        list(env.handover.assigned),
    )


def _assert_error(response, status: int, code: str) -> None:
    assert response.status_code == status
    ErrorResponse.model_validate(response.json())
    assert response.json()["error"] == code


# --- Orden y resultado de la autorización ------------------------------------------------


def test_reply_authorizes_before_lookup_send_and_store(env):
    """autorizacion_asesores R23: authorize es la primera llamada de reply."""
    _open_case(env)
    original = env.handover.authorize
    captured = {}

    def wrapper(case_id, advisor_id, action):
        captured["sent"] = len(env.gateway.sent)
        captured["messages"] = len(env.repo.messages)
        captured["events"] = len(env.repo.events)
        captured["assigned"] = list(env.handover.assigned)
        return original(case_id, advisor_id, action)

    env.handover.authorize = wrapper
    before = (len(env.gateway.sent), len(env.repo.messages), len(env.repo.events), [])
    response = _reply(env)
    assert response.status_code == 200
    assert env.handover.authorized == [("case-1", "555", "reply")]
    assert captured == {
        "sent": before[0],
        "messages": before[1],
        "events": before[2],
        "assigned": before[3],
    }


def test_reply_forbidden_for_unknown_case_returns_403_not_404(env):
    """autorizacion_asesores R23, R25: un no asesor recibe 403 aunque el caso no exista."""
    env.handover.authorize_error = "forbidden"
    _assert_error(_reply(env, "no-existe"), 403, "forbidden")


def test_reply_allowed_follows_authorize_send_store_assign_order(env):
    """autorizacion_asesores R24: orden authorize → send → add_message → assign."""
    _open_case(env)
    calls = []
    original_authorize = env.handover.authorize
    original_send = env.gateway.send
    original_add_message = env.repo.add_message
    original_assign = env.handover.assign

    def authorize(*args, **kwargs):
        calls.append("authorize")
        return original_authorize(*args, **kwargs)

    def send(*args, **kwargs):
        calls.append("send")
        return original_send(*args, **kwargs)

    def add_message(*args, **kwargs):
        calls.append("add_message")
        return original_add_message(*args, **kwargs)

    def assign(*args, **kwargs):
        calls.append("assign")
        return original_assign(*args, **kwargs)

    env.handover.authorize = authorize
    env.gateway.send = send
    env.repo.add_message = add_message
    env.handover.assign = assign
    response = _reply(env)
    assert response.status_code == 200
    assert response.json() == {"sent": True}
    assert calls == ["authorize", "send", "add_message", "assign"]


def test_reply_forbidden_returns_403_without_sending_or_storing(env):
    """autorizacion_asesores R25: un 403 no envía, no guarda mensaje y no asigna."""
    _open_case(env)
    env.handover.authorize_error = "forbidden"
    before = (len(env.repo.messages), list(env.gateway.sent), list(env.handover.assigned))
    _assert_error(_reply(env), 403, "forbidden")
    assert (
        len(env.repo.messages),
        list(env.gateway.sent),
        list(env.handover.assigned),
    ) == before
    assert ("advisor_reply", "advisor:555") not in env.events()


def test_reply_closed_case_returns_409_without_sending(env):
    """autorizacion_asesores R26: un caso cerrado produce 409 sin enviar ni guardar."""
    _open_case(env)
    env.handover.authorize_error = "case_closed"
    before = _snapshot(env)
    _assert_error(_reply(env), 409, "case_closed")
    assert _snapshot(env) == before
    assert ("advisor_reply", "advisor:555") not in env.events()


def test_reply_case_unknown_in_handover_returns_404_without_sending(env):
    """autorizacion_asesores R27: 404 de handover se propaga sin tocar nada."""
    _open_case(env)
    env.handover.authorize_error = "not_found"
    before = _snapshot(env)
    _assert_error(_reply(env), 404, "not_found")
    assert _snapshot(env) == before


def test_reply_authorize_unavailable_returns_502_without_sending(env):
    """autorizacion_asesores R28: si no se puede autorizar, falla cerrado con 502."""
    _open_case(env)
    env.handover.fail_authorize = True
    before = _snapshot(env)
    _assert_error(_reply(env), 502, "upstream_error")
    assert _snapshot(env) == before


def test_reply_forbidden_records_advisor_forbidden_event(env):
    """autorizacion_asesores R29: un 403 con contacto vinculado deja el evento."""
    contact = _open_case(env)
    env.handover.authorize_error = "forbidden"
    _assert_error(_reply(env), 403, "forbidden")
    event = env.repo.events[-1]
    assert (event.contact_id, event.type, event.reason, event.at) == (
        contact.id,
        "advisor_forbidden",
        "case:case-1 advisor:555 code:forbidden",
        FIXED_NOW,
    )


def test_reply_forbidden_unlinked_case_logs_without_event(env, caplog):
    """autorizacion_asesores R30: sin contacto vinculado solo queda el log."""
    env.handover.authorize_error = "forbidden"
    caplog.set_level(logging.INFO)
    before_events = list(env.repo.events)
    _assert_error(_reply(env), 403, "forbidden")
    assert env.repo.events == before_events
    assert any(
        "advisor_forbidden" in record.getMessage()
        and "case-1" in record.getMessage()
        and "555" in record.getMessage()
        for record in caplog.records
    )


@pytest.mark.parametrize(
    "mode", ["forbidden", "case_closed", "not_found", "fail_authorize"]
)
def test_reply_denied_or_failed_logs_do_not_contain_text(env, caplog, mode):
    """autorizacion_asesores R31: los logs de denegación no incluyen el texto."""
    secret = f"TEXTO-UNICO-{mode}"
    _open_case(env)
    if mode == "fail_authorize":
        env.handover.fail_authorize = True
    else:
        env.handover.authorize_error = mode
    caplog.set_level(logging.DEBUG)
    _reply(env, text=secret)
    assert secret not in caplog.text


def test_reply_assign_forbidden_after_send_records_assign_failed(env):
    """autorizacion_asesores R35: si assign falla tras enviar, 200 y assign_failed."""
    contact = _open_case(env)

    def assign_boom(case_id, advisor_id):
        raise ServiceUnavailable("Handover caído")

    env.handover.assign = assign_boom
    response = _reply(env)
    assert response.status_code == 200
    assert response.json() == {"sent": True}
    assert ("assign_failed", "case-1") in env.events()
    advisor = [m for m in env.repo.messages if m.role == "advisor"]
    assert [(m.contact_id, m.text) for m in advisor] == [(contact.id, "Hola, soy tu asesor")]


# --- Cliente HTTP ------------------------------------------------------------------------


@pytest.fixture()
def http_handover(monkeypatch):
    holder = {"response": None}
    requests = []

    def fake_post(url, *, timeout=None, **kwargs):
        request = httpx.Request(
            "POST",
            url,
            headers=kwargs.get("headers"),
            content=kwargs.get("content"),
        )
        requests.append((request, timeout))
        result = holder["response"]
        if isinstance(result, Exception):
            raise result
        return result

    monkeypatch.setattr(httpx, "post", fake_post)
    return requests, holder


def test_http_handover_client_authorize_posts_to_authorize_route(http_handover):
    """autorizacion_asesores R32: authorize llama a la ruta correcta con token y timeout."""
    requests, holder = http_handover
    holder["response"] = httpx.Response(
        200, json={"allowed": True, "case_id": "a b"}
    )
    response = HttpHandoverClient("http://ho:8000/", "tok", 3).authorize(
        "a b", "555", "reply"
    )
    assert isinstance(response, CaseAuthorizeResponse)
    assert (response.allowed, response.case_id) == (True, "a b")
    request, timeout = requests[0]
    assert request.url.raw_path == b"/cases/a%20b/authorize"
    assert request.headers["X-Service-Token"] == "tok"
    assert timeout == 3
    assert json.loads(request.content) == {"advisor_id": "555", "action": "reply"}


@pytest.mark.parametrize(
    ("status", "code"),
    [(403, "forbidden"), (404, "not_found"), (409, "case_closed")],
)
def test_http_handover_client_authorize_maps_denials(http_handover, status, code):
    """autorizacion_asesores R33: 403/404/409 se convierten en AuthorizationDenied."""
    _, holder = http_handover
    holder["response"] = httpx.Response(status, json={"error": code, "message": "x"})
    with pytest.raises(AuthorizationDenied) as excinfo:
        HttpHandoverClient("http://ho", "tok").authorize("case-1", "555", "reply")
    assert excinfo.value.code == code


FAIL_CLOSED_RESPONSES = [
    ("unauthorized", httpx.Response(401, json={"error": "unauthorized", "message": "x"})),
    ("validation", httpx.Response(422, json={"error": "validation_error", "message": "x"})),
    ("internal", httpx.Response(500, json={"error": "internal_error", "message": "x"})),
    ("bad_gateway", httpx.Response(502, json={"error": "upstream_error", "message": "x"})),
    ("wrong_error", httpx.Response(403, json={"error": "otro", "message": "x"})),
    ("not_json", httpx.Response(404, content=b"no-json")),
    ("allowed_false", httpx.Response(200, json={"allowed": False, "case_id": "case-1"})),
    ("other_case", httpx.Response(200, json={"allowed": True, "case_id": "case-2"})),
    ("ok_not_json", httpx.Response(200, content=b"no-json")),
    ("connect_error", httpx.ConnectError("sin conexión")),
    ("timeout", httpx.ReadTimeout("sin respuesta")),
]


@pytest.mark.parametrize(("name", "response"), FAIL_CLOSED_RESPONSES)
def test_http_handover_client_authorize_fails_closed(http_handover, name, response):
    """autorizacion_asesores R34: cualquier respuesta no válida falla cerrada."""
    _, holder = http_handover
    holder["response"] = response
    with pytest.raises(ServiceUnavailable):
        HttpHandoverClient("http://ho", "tok").authorize("case-1", "555", "reply")


# --- Caso cerrado ------------------------------------------------------------------------


@pytest.mark.parametrize("linked", [True, False])
def test_reply_closed_case_does_not_record_advisor_forbidden(env, caplog, linked):
    """autorizacion_asesores R53: un 409 no deja evento ni log advisor_forbidden."""
    if linked:
        _open_case(env)
    env.handover.authorize_error = "case_closed"
    caplog.set_level(logging.DEBUG)
    before_events = list(env.repo.events)
    _assert_error(_reply(env), 409, "case_closed")
    assert env.repo.events == before_events
    assert "advisor_forbidden" not in caplog.text
