"""Tests de POST /cases/{id}/client-message: reenvío cliente → asesor (feature #16)."""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

import httpx
import pytest
from lazaro_contracts import (
    CaseClientMessageRequest,
    CaseClientMessageResponse,
    ErrorResponse,
)

from handover.adapters.gateway import FakeGatewayClient, HttpGatewayClient
from handover.domain import Adapters, build_client_forward, forward_client_message

HEADERS = {"X-Service-Token": "svc-token"}
AT = "2026-01-02T03:00:00Z"
FIXED_AT = datetime(2026, 1, 2, 3, 0, 0, tzinfo=timezone.utc)


def _post(env, case_id: str = "case-1", text: str = "Sigue sin funcionar", at: str = AT):
    return env.client.post(
        f"/cases/{case_id}/client-message", json={"text": text, "at": at}, headers=HEADERS
    )


def _assert_error(response, status: int, code: str) -> None:
    assert response.status_code == status
    ErrorResponse.model_validate(response.json())
    assert response.json()["error"] == code


def test_client_message_assigned_case_is_forwarded_to_advisor(env):
    """conversacion_cliente_asesor R47: caso assigned → texto plano al asesor."""
    env.add_case("case-1", status="assigned", advisor_id="111")
    response = _post(env, text="Sigue sin funcionar")
    assert response.status_code == 200
    parsed = CaseClientMessageResponse.model_validate(response.json())
    assert (parsed.status, parsed.case_id) == ("forwarded", "case-1")
    assert env.gateway.sent == [(111, "Caso case-1 | Cliente: Sigue sin funcionar")]


def test_client_message_is_truncated_to_4096(env):
    """conversacion_cliente_asesor R48: el texto enviado nunca supera 4096 caracteres."""
    env.add_case("case-1", status="assigned", advisor_id="111")
    _post(env, text="a" * 4096)
    sent = env.gateway.sent[0][1]
    assert len(sent) == 4096
    assert sent.startswith("Caso case-1 | Cliente: ")

    env.gateway.sent.clear()
    env.add_case("case-2", status="assigned", advisor_id="111")
    _post(env, case_id="case-2", text="corto")
    assert env.gateway.sent == [(111, "Caso case-2 | Cliente: corto")]

    assert build_client_forward("case-1", "abc") == "Caso case-1 | Cliente: abc"
    assert len(build_client_forward("case-1", "a" * 4096)) == 4096


@pytest.mark.parametrize("status", ["open", "timed_out", "closed"])
def test_client_message_not_assigned_cases_send_nothing(env, status):
    """conversacion_cliente_asesor R49: solo assigned se reenvía."""
    env.add_case("case-1", status=status)
    response = _post(env)
    assert response.status_code == 200
    assert response.json() == {"status": "not_assigned", "case_id": "case-1"}
    assert env.gateway.sent == []


def test_client_message_unknown_case_returns_404(env):
    """conversacion_cliente_asesor R50: un caso inexistente responde 404 sin enviar."""
    _assert_error(_post(env, case_id="no-existe"), 404, "not_found")
    assert env.gateway.sent == []


def test_client_message_send_failure_returns_502(env_factory):
    """conversacion_cliente_asesor R51: si falla el envío al asesor, 502 upstream_error."""
    env = env_factory(gateway=FakeGatewayClient(fail_for={111}))
    env.add_case("case-1", status="assigned", advisor_id="111")
    _assert_error(_post(env), 502, "upstream_error")


@pytest.mark.parametrize("advisor_id", ["abc", "1.5", None])
def test_client_message_invalid_advisor_id_returns_502_without_send(env, advisor_id):
    """conversacion_cliente_asesor R52: advisor_id no decimal → 502 sin llamar al gateway."""
    env.add_case("case-1", status="assigned", advisor_id=advisor_id)
    _assert_error(_post(env), 502, "upstream_error")
    assert env.gateway.sent == []


def test_client_message_never_modifies_case(env):
    """conversacion_cliente_asesor R53: no se modifica el caso ni se registra nada."""
    env.add_case("case-1", status="assigned", advisor_id="111")
    env.add_case("case-open", status="open")
    env.add_case("case-fail", status="assigned", advisor_id="111")
    before = {key: value.model_copy(deep=True) for key, value in env.repo.cases.items()}
    before_notifications = list(env.repo.notifications)

    _post(env, case_id="case-1")
    _post(env, case_id="case-open")
    env.gateway.fail_for.add(111)
    _post(env, case_id="case-fail")
    env.gateway.fail_for.discard(111)
    _post(env, case_id="no-existe")

    assert env.repo.cases == before
    assert env.repo.requests == []
    assert env.repo.denials == []
    assert env.repo.notifications == before_notifications


def test_client_message_gateway_payload_is_plain_text(env, monkeypatch):
    """conversacion_cliente_asesor R54: POST /send solo lleva chat_id y text, sin formato."""
    captured: list[tuple[str, dict, float]] = []

    def fake_post(url, *, timeout=None, **kwargs):
        captured.append((url, json.loads(kwargs["content"]), timeout))
        return httpx.Response(
            200, json={"sent": True}, request=httpx.Request("POST", url)
        )

    monkeypatch.setattr(httpx, "post", fake_post)
    env.add_case("case-1", status="assigned", advisor_id="111")
    request = CaseClientMessageRequest(text="hola *x* <b>", at=FIXED_AT)
    adapters = Adapters(
        repository=env.repo,
        gateway=HttpGatewayClient("http://gw:8000", "tok", 3),
        clock=env.clock,
    )
    response = forward_client_message("case-1", request, adapters)
    assert response.status == "forwarded"
    url, payload, timeout = captured[0]
    assert url == "http://gw:8000/send"
    assert set(payload) == {"chat_id", "text"}
    assert payload["chat_id"] == 111
    assert payload["text"] == "Caso case-1 | Cliente: hola *x* <b>"
    assert timeout == 3


@pytest.mark.parametrize("mode", ["forwarded", "send_failed", "invalid_advisor_id"])
def test_client_message_logs_do_not_contain_text(env_factory, caplog, mode):
    """conversacion_cliente_asesor R57: el texto del cliente nunca aparece en el log."""
    secret = "SECRETO-CLIENTE-789"
    if mode == "send_failed":
        env = env_factory(gateway=FakeGatewayClient(fail_for={111}))
        env.add_case("case-1", status="assigned", advisor_id="111")
    elif mode == "invalid_advisor_id":
        env = env_factory()
        env.add_case("case-1", status="assigned", advisor_id="abc")
    else:
        env = env_factory()
        env.add_case("case-1", status="assigned", advisor_id="111")
    caplog.set_level(logging.DEBUG)
    _post(env, text=secret)
    assert caplog.records
    assert secret not in caplog.text


def test_http_close_sends_no_notice_to_client(env):
    """conversacion_cliente_asesor R59: close por HTTP no envía aviso al cliente."""
    env.add_case("case-1", status="assigned", advisor_id="111", chat_id=100)
    response = env.client.post(
        "/cases/case-1/close", json={"advisor_id": "111"}, headers=HEADERS
    )
    assert response.status_code == 200
    assert response.json() == {"status": "closed", "case_id": "case-1"}
    assert env.gateway.sent == []
