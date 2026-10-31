"""Tests de POST /handover: casos, avisos a asesores y registro de notificaciones."""
from __future__ import annotations

from datetime import datetime, timezone

from lazaro_contracts import MAX_TEXT_LENGTH, HandoverResponse, LastMessage

from handover.domain import build_advisor_notice

START = datetime(2026, 1, 2, 3, 0, 0, tzinfo=timezone.utc)
ADVISORS = [111, 222, 333]


def _msg(role: str, text: str) -> dict:
    return {"role": role, "text": text, "at": "2026-01-02T02:59:00Z"}


def test_handover_creates_case_and_notifies_three_advisors(env):
    """R1, R3, R5, R7: crea el caso, avisa a 3 asesores, registra cada aviso y responde notified."""
    messages = [_msg("user", "no puedo facturar"), _msg("bot", "te paso con un asesor")]
    response = env.handover(case_id="case-1", contact_id="contact-1", chat_id=900,
                            reason="no_relevant_chunks", last_messages=messages)

    assert response.status_code == 200
    assert response.json() == {"status": "notified", "case_id": "case-1"}
    HandoverResponse.model_validate(response.json())

    case = env.repo.cases["case-1"]
    assert (case.contact_id, case.chat_id, case.reason, case.status) == (
        "contact-1", 900, "no_relevant_chunks", "open"
    )
    assert [m.text for m in case.last_messages] == ["no puedo facturar", "te paso con un asesor"]
    assert case.created_at == START

    assert [chat for chat, _ in env.gateway.sent] == ADVISORS
    assert [
        (n.case_id, n.advisor_id, n.reason, n.at, n.delivered) for n in env.repo.notifications
    ] == [("case-1", str(a), "no_relevant_chunks", START, True) for a in ADVISORS]


def test_notice_contains_case_reason_and_messages(env):
    """R4: el aviso es texto plano con case_id, motivo y last_messages con su rol."""
    env.handover(case_id="case-7", reason="user_request",
                 last_messages=[_msg("user", "hola"), _msg("bot", "respuesta del bot")])
    _, text = env.gateway.sent[0]
    assert "case-7" in text
    assert "user_request" in text
    assert "[user] hola" in text
    assert "[bot] respuesta del bot" in text
    assert all(text == other for _, other in env.gateway.sent)


def test_notice_fits_4096_limit_with_long_messages():
    """R41: el aviso nunca supera 4096 caracteres, aunque los mensajes sean largos."""
    at = datetime(2026, 1, 1, tzinfo=timezone.utc)
    messages = [LastMessage(role="user", text="x" * 4096, at=at) for _ in range(10)]
    notice = build_advisor_notice("c" * 64, "no_relevant_chunks", messages)
    assert len(notice) <= MAX_TEXT_LENGTH
    assert notice.startswith("Caso " + "c" * 64)


def test_notice_cuts_each_message_to_300_characters():
    """R41: cada texto del aviso se recorta a 300 caracteres."""
    at = datetime(2026, 1, 1, tzinfo=timezone.utc)
    long_message = LastMessage(role="user", text="y" * 500, at=at)
    notice = build_advisor_notice("k", "user_request", [long_message])
    assert notice.splitlines()[1] == "[user] " + "y" * 300


def test_handover_reuses_open_case_of_same_contact(env):
    """R2: un segundo /handover del mismo contacto reutiliza el caso abierto."""
    env.handover(case_id="case-1", contact_id="contact-1", last_messages=[_msg("user", "uno")])
    response = env.handover(case_id="case-2", contact_id="contact-1",
                            last_messages=[_msg("user", "uno"), _msg("user", "dos")])
    assert response.status_code == 200
    assert response.json() == {"status": "notified", "case_id": "case-1"}
    assert set(env.repo.cases) == {"case-1"}
    assert [m.text for m in env.repo.cases["case-1"].last_messages] == ["uno", "dos"]


def test_handover_reuses_assigned_case(env):
    """R2: un caso assigned también se reutiliza y no cambia de estado."""
    env.add_case("case-a", status="assigned", contact_id="contact-1", advisor_id="111")
    response = env.handover(case_id="case-new", contact_id="contact-1",
                            last_messages=[_msg("user", "sigo aquí")])
    assert response.json() == {"status": "notified", "case_id": "case-a"}
    case = env.repo.cases["case-a"]
    assert case.status == "assigned" and case.advisor_id == "111"
    assert [m.text for m in case.last_messages] == ["sigo aquí"]
    assert "case-new" not in env.repo.cases


def test_handover_does_not_reuse_closed_or_timed_out_cases(env):
    """R1: si el contacto solo tiene casos closed o timed_out se crea uno nuevo."""
    env.add_case("old-closed", status="closed", contact_id="contact-1")
    env.add_case("old-timed", status="timed_out", contact_id="contact-1")
    response = env.handover(case_id="case-new", contact_id="contact-1")
    assert response.json()["case_id"] == "case-new"
    assert env.repo.cases["case-new"].status == "open"


def test_handover_without_advisors_returns_no_advisors_and_does_not_send(env_no_advisors):
    """R8, R10: sin asesores -> no_advisors, sin POST /send y el caso pasa a timed_out."""
    env = env_no_advisors
    response = env.handover(case_id="case-1")
    assert response.status_code == 200
    assert response.json() == {"status": "no_advisors", "case_id": "case-1"}
    assert env.gateway.sent == []
    assert env.repo.notifications == []
    assert env.repo.cases["case-1"].status == "timed_out"


def test_no_advisors_case_is_not_notified_again_by_check_timeouts(env_no_advisors):
    """R10: el caso marcado timed_out por no_advisors no recibe HANDOVER_TIMEOUT_REPLY."""
    env = env_no_advisors
    env.handover(case_id="case-1")
    env.clock.advance(10_000)
    response = env.client.post("/cases/check-timeouts", json={},
                               headers={"X-Service-Token": "svc-token"})
    assert response.json() == {"timed_out_cases": []}
    assert env.gateway.sent == []


def test_no_advisors_keeps_reused_assigned_case_assigned(env_no_advisors):
    """R10: con no_advisors solo un caso open pasa a timed_out; uno assigned no cambia."""
    env = env_no_advisors
    env.add_case("case-a", status="assigned", contact_id="contact-1", advisor_id="111")
    response = env.handover(case_id="case-x", contact_id="contact-1")
    assert response.json() == {"status": "no_advisors", "case_id": "case-a"}
    assert env.repo.cases["case-a"].status == "assigned"


def test_handover_one_failed_notice_still_notifies_others(env):
    """R6, R7: un aviso fallido se registra con delivered=false y se sigue con los demás."""
    env.gateway.fail_for = {222}
    response = env.handover(case_id="case-1", reason="user_request")
    assert response.json() == {"status": "notified", "case_id": "case-1"}
    assert [chat for chat, _ in env.gateway.sent] == [111, 333]
    assert [(n.advisor_id, n.delivered) for n in env.repo.notifications] == [
        ("111", True), ("222", False), ("333", True)
    ]
    assert all(n.reason == "user_request" and n.case_id == "case-1"
               for n in env.repo.notifications)
    assert env.repo.cases["case-1"].status == "open"


def test_handover_all_notices_fail_returns_no_advisors(env):
    """R9, R6, R10: si todos los avisos fallan -> no_advisors, delivered=false y timed_out."""
    env.gateway.fail_for = set(ADVISORS)
    response = env.handover(case_id="case-1")
    assert response.status_code == 200
    assert response.json() == {"status": "no_advisors", "case_id": "case-1"}
    assert [(n.advisor_id, n.delivered) for n in env.repo.notifications] == [
        ("111", False), ("222", False), ("333", False)
    ]
    assert env.repo.cases["case-1"].status == "timed_out"
