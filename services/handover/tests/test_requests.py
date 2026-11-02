"""Tests del registro de solicitudes de traspaso en handover (feature #11)."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from lazaro_contracts import HandoverRequest, LastMessage

from handover.domain import (
    HandoverRequestRecord,
    build_advisor_notice,
    open_case,
)
from handover.main import create_app

HEADERS = {"X-Service-Token": "svc-token"}
START = datetime(2026, 1, 2, 3, 0, 0, tzinfo=timezone.utc)
ADVISORS = [111, 222, 333]
SECRET = "TEXTO-CLIENTE-SECRETO"


def _msg(text: str = SECRET, role: str = "user") -> dict:
    return {"role": role, "text": text, "at": "2026-01-02T02:59:00Z"}


def _request(
    case_id: str = "case-1",
    contact_id: str = "contact-1",
    reason: str = "user_request",
    count: int = 1,
) -> HandoverRequest:
    return HandoverRequest(
        case_id=case_id,
        contact_id=contact_id,
        chat_id=900,
        reason=reason,
        last_messages=[LastMessage(role="user", text=SECRET, at=START) for _ in range(count)],
    )


def _raise(monkeypatch, env, method: str, exc: Exception | None = None) -> None:
    def boom(*args, **kwargs):
        raise exc or RuntimeError("fallo-simulado")

    monkeypatch.setattr(env.repo, method, boom)


def test_record_is_created_on_receipt_before_processing(env, monkeypatch):
    """R1: el registro `received` existe antes de buscar o crear el caso."""
    snapshots: list[list[HandoverRequestRecord]] = []
    original = env.repo.find_active_case

    def spy(contact_id):
        snapshots.append([record.model_copy(deep=True) for record in env.repo.requests])
        return original(contact_id)

    monkeypatch.setattr(env.repo, "find_active_case", spy)

    assert env.handover().status_code == 200
    assert len(snapshots) == 1
    [record] = snapshots[0]
    assert record.request_id == 1
    assert record.requested_case_id == "case-1"
    assert record.case_id is None
    assert record.contact_id == "contact-1"
    assert record.reason == "user_request"
    assert record.received_at == START
    assert record.result == "received"
    assert record.advisors_configured == 3
    assert record.notices_delivered == 0
    assert record.messages_count == 1


def test_record_contains_no_message_text(env):
    """R2: el registro no guarda el texto de last_messages ni otro texto."""
    messages = [_msg(SECRET), _msg(f"{SECRET}-2", role="bot")]
    env.handover(last_messages=messages)

    [record] = env.repo.requests
    assert SECRET not in record.model_dump_json()
    assert set(HandoverRequestRecord.model_fields) == {
        "request_id",
        "requested_case_id",
        "case_id",
        "contact_id",
        "reason",
        "received_at",
        "result",
        "advisors_configured",
        "notices_delivered",
        "messages_count",
    }


@pytest.mark.parametrize("count", [0, 1, 2])
def test_record_stores_message_count(env, monkeypatch, count):
    """R19: messages_count es el número de elementos de last_messages."""
    snapshots: list[list[HandoverRequestRecord]] = []
    original = env.repo.find_active_case

    def spy(contact_id):
        snapshots.append([record.model_copy(deep=True) for record in env.repo.requests])
        return original(contact_id)

    monkeypatch.setattr(env.repo, "find_active_case", spy)
    messages = [_msg(f"mensaje-{index}") for index in range(count)]

    env.handover(last_messages=messages)

    assert snapshots[0][0].messages_count == count
    assert env.repo.requests[0].messages_count == count


def test_notified_request_completes_record_with_delivered_count(env):
    """R3: resultado notified, caso efectivo y avisos entregados con éxito."""
    env.gateway.fail_for = {222}

    assert env.handover().status_code == 200

    [record] = env.repo.requests
    assert record.result == "notified"
    assert record.case_id == "case-1"
    assert record.advisors_configured == 3
    assert record.notices_delivered == 2


def test_no_advisors_request_is_recorded(env_no_advisors):
    """R4: sin asesores configurados también se registra con 0 asesores y 0 avisos."""
    response = env_no_advisors.handover()
    assert response.status_code == 200
    assert response.json() == {"status": "no_advisors", "case_id": "case-1"}

    [record] = env_no_advisors.repo.requests
    assert record.result == "no_advisors"
    assert record.case_id == "case-1"
    assert record.advisors_configured == 0
    assert record.notices_delivered == 0


def test_all_notices_failed_request_is_recorded(env):
    """R5: si todos los avisos fallan, resultado no_advisors y 0 entregados."""
    env.gateway.fail_for = set(ADVISORS)

    assert env.handover().status_code == 200

    [record] = env.repo.requests
    assert record.result == "no_advisors"
    assert record.case_id == "case-1"
    assert record.advisors_configured == 3
    assert record.notices_delivered == 0


def test_reused_case_creates_new_record_with_new_reason(env):
    """R6: reutilizar un caso crea un registro nuevo con el motivo de la petición."""
    env.handover(case_id="case-1", reason="no_relevant_chunks")
    env.clock.advance(60)
    env.handover(case_id="case-2", reason="user_request")

    first, second = env.repo.requests
    assert first.request_id != second.request_id
    assert first.requested_case_id == "case-1"
    assert first.reason == "no_relevant_chunks"
    assert second.requested_case_id == "case-2"
    assert second.case_id == "case-1"
    assert second.reason == "user_request"
    assert second.received_at == START + timedelta(seconds=60)


def test_reused_case_keeps_original_case_reason(env):
    """R7: Case.reason conserva el motivo original al reutilizar."""
    env.handover(case_id="case-1", reason="no_relevant_chunks")
    env.handover(case_id="case-2", reason="user_request")

    assert env.repo.cases["case-1"].reason == "no_relevant_chunks"


def test_internal_error_before_case_is_known_records_error(env, monkeypatch):
    """R8: error antes de conocer el caso -> error, case_id None y 0 entregados."""
    _raise(monkeypatch, env, "find_active_case")

    with pytest.raises(RuntimeError, match="fallo-simulado"):
        env.handover()

    [record] = env.repo.requests
    assert record.result == "error"
    assert record.case_id is None
    assert record.notices_delivered == 0


def test_internal_error_after_notice_records_error_with_case_and_count(env, monkeypatch):
    """R8: error tras un aviso entregado -> caso conocido y 1 entregado."""
    _raise(monkeypatch, env, "add_notification")

    with pytest.raises(RuntimeError, match="fallo-simulado"):
        env.handover()

    [record] = env.repo.requests
    assert record.result == "error"
    assert record.case_id == "case-1"
    assert record.notices_delivered == 1


def test_internal_error_returns_500_internal_error(env, monkeypatch):
    """R9: el error interno sigue respondiendo 500 internal_error."""
    _raise(monkeypatch, env, "find_active_case")
    client = TestClient(create_app(env.settings, env.adapters), raise_server_exceptions=False)

    response = client.post("/handover", json=_request().model_dump(mode="json"), headers=HEADERS)

    assert response.status_code == 500
    assert response.json()["error"] == "internal_error"


def test_record_creation_failure_does_not_change_response(env, monkeypatch):
    """R10: si falla la creación del registro, la respuesta y los avisos no cambian."""
    _raise(monkeypatch, env, "add_request")

    response = env.handover()

    assert response.status_code == 200
    assert response.json() == {"status": "notified", "case_id": "case-1"}
    assert [chat for chat, _ in env.gateway.sent] == ADVISORS
    assert env.repo.requests == []


def test_record_completion_failure_does_not_change_response(env, monkeypatch):
    """R11: si falla completar el registro, la respuesta no cambia y queda received."""
    _raise(monkeypatch, env, "complete_request")

    response = env.handover()

    assert response.status_code == 200
    assert response.json() == {"status": "notified", "case_id": "case-1"}
    [record] = env.repo.requests
    assert record.result == "received"
    assert record.case_id is None
    assert record.notices_delivered == 0


def test_error_completion_failure_propagates_original_error(env, monkeypatch):
    """R12: si falla completar a error, se propaga la excepción original."""
    _raise(monkeypatch, env, "find_active_case", RuntimeError("fallo-simulado"))
    _raise(monkeypatch, env, "complete_request", OSError("no se pudo actualizar"))

    with pytest.raises(RuntimeError, match="fallo-simulado"):
        open_case(_request(), env.settings, env.adapters)


@pytest.mark.parametrize("case", ["no_token", "invalid_body"])
def test_rejected_handover_creates_no_record(env, case):
    """R13: un 401 por token o un 422 por cuerpo no crean ningún registro."""
    if case == "no_token":
        response = env.handover(headers={})
        assert response.status_code == 401
    else:
        response = env.client.post(
            "/handover", json={"case_id": "case-1"}, headers=HEADERS
        )
        assert response.status_code == 422

    assert env.repo.requests == []


def test_handover_response_and_notifications_unchanged_with_record(env):
    """R14, R15: respuesta, avisos y notificaciones idénticos a la feature #7."""
    messages = [_msg("no puedo facturar"), _msg("te paso con un asesor", role="bot")]
    response = env.handover(
        case_id="case-1", contact_id="contact-1", chat_id=900,
        reason="no_relevant_chunks", last_messages=messages,
    )

    assert response.status_code == 200
    assert response.json() == {"status": "notified", "case_id": "case-1"}
    notice = build_advisor_notice(
        "case-1", "no_relevant_chunks", [LastMessage.model_validate(m) for m in messages]
    )
    assert env.gateway.sent == [(advisor, notice) for advisor in ADVISORS]
    assert [
        (n.case_id, n.advisor_id, n.reason, n.at, n.delivered) for n in env.repo.notifications
    ] == [("case-1", str(advisor), "no_relevant_chunks", START, True) for advisor in ADVISORS]


@pytest.mark.parametrize(
    ("method", "expected_code", "expected_message"),
    [
        ("find_active_case", "handover_request_failed", "request_id=1 case_id=None"),
        ("add_request", "handover_request_not_recorded", None),
        ("complete_request", "handover_request_update_failed", None),
    ],
)
def test_request_logs_are_error_level_and_contain_no_client_text(
    env, monkeypatch, caplog, method, expected_code, expected_message
):
    """R18, R20, R21: logs ERROR con su código y sin texto de clientes."""
    caplog.set_level(logging.DEBUG)
    _raise(monkeypatch, env, method)

    if method == "find_active_case":
        with pytest.raises(RuntimeError, match="fallo-simulado"):
            env.handover(last_messages=[_msg(SECRET)])
    else:
        env.handover(last_messages=[_msg(SECRET)])

    assert SECRET not in caplog.text
    records = [r for r in caplog.records if r.getMessage().startswith(expected_code)]
    assert records
    assert all(record.levelno == logging.ERROR for record in records)
    if expected_message is not None:
        assert expected_message in records[0].getMessage()
