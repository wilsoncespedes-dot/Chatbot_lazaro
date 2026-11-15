"""Tests de POST /cases/{id}/client-message: disponible en panel, sin Telegram (#48)."""
from __future__ import annotations

import logging

import pytest
from lazaro_contracts import CaseClientMessageResponse, ErrorResponse

HEADERS = {"X-Service-Token": "svc-token"}
AT = "2026-01-02T03:00:00Z"


def _post(env, case_id: str = "case-1", text: str = "Sigue sin funcionar", at: str = AT):
    return env.client.post(
        f"/cases/{case_id}/client-message", json={"text": text, "at": at}, headers=HEADERS
    )


def _assert_error(response, status: int, code: str) -> None:
    assert response.status_code == status
    ErrorResponse.model_validate(response.json())
    assert response.json()["error"] == code


def test_client_message_assigned_case_is_available_in_panel(env):
    """R27, R8: caso assigned -> available_in_panel, sin enviar nada por Telegram."""
    env.add_case("case-1", status="assigned", advisor_id="111")
    response = _post(env, text="Sigue sin funcionar")
    assert response.status_code == 200
    parsed = CaseClientMessageResponse.model_validate(response.json())
    assert (parsed.status, parsed.case_id) == ("available_in_panel", "case-1")
    assert env.gateway.sent == []


@pytest.mark.parametrize("status", ["open", "timed_out", "closed"])
def test_client_message_not_assigned_cases_send_nothing(env, status):
    """R28: solo assigned queda disponible; el resto responde not_assigned."""
    env.add_case("case-1", status=status)
    response = _post(env)
    assert response.status_code == 200
    assert response.json() == {"status": "not_assigned", "case_id": "case-1"}
    assert env.gateway.sent == []


def test_client_message_unknown_case_returns_404(env):
    """R28: un caso inexistente responde 404 sin enviar."""
    _assert_error(_post(env, case_id="no-existe"), 404, "not_found")
    assert env.gateway.sent == []


def test_client_message_never_modifies_case(env):
    """R27: no se modifica el caso ni se registra nada."""
    env.add_case("case-1", status="assigned", advisor_id="111")
    env.add_case("case-open", status="open")
    before = {key: value.model_copy(deep=True) for key, value in env.repo.cases.items()}
    before_notifications = list(env.repo.notifications)

    _post(env, case_id="case-1")
    _post(env, case_id="case-open")
    _post(env, case_id="no-existe")

    assert env.repo.cases == before
    assert env.repo.requests == []
    assert env.repo.denials == []
    assert env.repo.notifications == before_notifications


@pytest.mark.parametrize("mode", ["assigned", "not_assigned"])
def test_client_message_logs_do_not_contain_text(env, caplog, mode):
    """R27: el texto del cliente nunca aparece en el log."""
    secret = "SECRETO-CLIENTE-789"
    env.add_case("case-1", status="assigned" if mode == "assigned" else "open")
    caplog.set_level(logging.DEBUG)
    _post(env, text=secret)
    assert caplog.records
    assert secret not in caplog.text


def test_http_close_sends_no_notice_to_client(env):
    """R8: close por HTTP no envía aviso al cliente."""
    env.add_case("case-1", status="assigned", advisor_id="111", chat_id=100)
    response = env.client.post(
        "/cases/case-1/close", json={"advisor_id": "111"}, headers=HEADERS
    )
    assert response.status_code == 200
    assert response.json() == {"status": "closed", "case_id": "case-1"}
    assert env.gateway.sent == []
