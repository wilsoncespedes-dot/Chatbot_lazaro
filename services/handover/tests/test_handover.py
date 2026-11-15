"""Tests de POST /handover: casos en la bandeja del panel y respuesta queued/no_advisors."""
from __future__ import annotations

from lazaro_contracts import HandoverResponse

from handover.domain import build_advisor_notice


def _msg(role: str, text: str) -> dict:
    return {"role": role, "text": text, "at": "2026-01-02T02:59:00Z"}


def test_handover_creates_case_and_queues_it_without_telegram(env):
    """R14, R8: crea el caso y responde queued sin enviar avisos por Telegram."""
    messages = [_msg("user", "no puedo facturar"), _msg("bot", "te paso con un asesor")]
    response = env.handover(case_id="case-1", contact_id="contact-1", chat_id=900,
                            reason="no_relevant_chunks", last_messages=messages)

    assert response.status_code == 200
    assert response.json() == {"status": "queued", "case_id": "case-1"}
    HandoverResponse.model_validate(response.json())

    case = env.repo.cases["case-1"]
    assert (case.contact_id, case.chat_id, case.reason, case.status) == (
        "contact-1", 900, "no_relevant_chunks", "open"
    )
    assert [m.text for m in case.last_messages] == ["no puedo facturar", "te paso con un asesor"]
    assert env.gateway.sent == []
    assert env.repo.notifications == []


def test_notice_builder_still_respects_limits():
    """R8: el aviso histórico (si se usara) sigue recortado a 4096 y 300 por mensaje."""
    from datetime import datetime, timezone

    from lazaro_contracts import LastMessage, MAX_TEXT_LENGTH

    at = datetime(2026, 1, 1, tzinfo=timezone.utc)
    messages = [LastMessage(role="user", text="x" * 4096, at=at) for _ in range(10)]
    notice = build_advisor_notice("c" * 64, "no_relevant_chunks", messages)
    assert len(notice) <= MAX_TEXT_LENGTH
    assert notice.startswith("Caso " + "c" * 64)


def test_handover_reuses_open_case_of_same_contact(env):
    """R14: un segundo /handover del mismo contacto reutiliza el caso abierto."""
    env.handover(case_id="case-1", contact_id="contact-1", last_messages=[_msg("user", "uno")])
    response = env.handover(case_id="case-2", contact_id="contact-1",
                            last_messages=[_msg("user", "uno"), _msg("user", "dos")])
    assert response.status_code == 200
    assert response.json() == {"status": "queued", "case_id": "case-1"}
    assert set(env.repo.cases) == {"case-1"}
    assert [m.text for m in env.repo.cases["case-1"].last_messages] == ["uno", "dos"]


def test_handover_reuses_assigned_case(env):
    """R14: un caso assigned también se reutiliza y no cambia de estado."""
    env.add_case("case-a", status="assigned", contact_id="contact-1", advisor_id="111")
    response = env.handover(case_id="case-new", contact_id="contact-1",
                            last_messages=[_msg("user", "sigo aquí")])
    assert response.json() == {"status": "queued", "case_id": "case-a"}
    case = env.repo.cases["case-a"]
    assert case.status == "assigned" and case.advisor_id == "111"
    assert [m.text for m in case.last_messages] == ["sigo aquí"]
    assert "case-new" not in env.repo.cases


def test_handover_does_not_reuse_closed_or_timed_out_cases(env):
    """R14: si el contacto solo tiene casos closed o timed_out se crea uno nuevo."""
    env.add_case("old-closed", status="closed", contact_id="contact-1")
    env.add_case("old-timed", status="timed_out", contact_id="contact-1")
    response = env.handover(case_id="case-new", contact_id="contact-1")
    assert response.json()["case_id"] == "case-new"
    assert env.repo.cases["case-new"].status == "open"


def test_handover_without_advisors_returns_no_advisors_and_does_not_send(env_no_advisors):
    """R15: sin perfiles asesores -> no_advisors, sin POST /send y el caso pasa a timed_out."""
    env = env_no_advisors
    response = env.handover(case_id="case-1")
    assert response.status_code == 200
    assert response.json() == {"status": "no_advisors", "case_id": "case-1"}
    assert env.gateway.sent == []
    assert env.repo.notifications == []
    assert env.repo.cases["case-1"].status == "timed_out"


def test_no_advisors_case_is_not_notified_again_by_check_timeouts(env_no_advisors):
    """R15: el caso marcado timed_out por no_advisors no recibe HANDOVER_TIMEOUT_REPLY."""
    env = env_no_advisors
    env.handover(case_id="case-1")
    env.clock.advance(10_000)
    response = env.client.post("/cases/check-timeouts", json={},
                               headers={"X-Service-Token": "svc-token"})
    assert response.json() == {"timed_out_cases": []}
    assert env.gateway.sent == []


def test_no_advisors_keeps_reused_assigned_case_assigned(env_no_advisors):
    """R15: con no_advisors solo un caso open pasa a timed_out; uno assigned no cambia."""
    env = env_no_advisors
    env.add_case("case-a", status="assigned", contact_id="contact-1", advisor_id="111")
    response = env.handover(case_id="case-x", contact_id="contact-1")
    assert response.json() == {"status": "no_advisors", "case_id": "case-a"}
    assert env.repo.cases["case-a"].status == "assigned"


def test_handover_does_not_notify_even_if_gateway_fails(env):
    """R14: el gateway no se usa para casos nuevos."""
    env.gateway.fail_for = {"111", "222", "333"}
    response = env.handover(case_id="case-1", reason="user_request")
    assert response.json() == {"status": "queued", "case_id": "case-1"}
    assert env.gateway.sent == []
    assert env.repo.cases["case-1"].status == "open"
