"""Tests de POST /cases/{id}/assign y POST /cases/{id}/close."""
from __future__ import annotations

from datetime import datetime, timezone

from lazaro_contracts import CaseAssignResponse, CaseCloseResponse, ErrorResponse

HEADERS = {"X-Service-Token": "svc-token"}
START = datetime(2026, 1, 2, 3, 0, 0, tzinfo=timezone.utc)


def _assign(env, case_id: str, advisor_id: str = "111"):
    return env.client.post(f"/cases/{case_id}/assign", json={"advisor_id": advisor_id},
                           headers=HEADERS)


def _close(env, case_id: str, advisor_id: str = "111"):
    return env.client.post(f"/cases/{case_id}/close", json={"advisor_id": advisor_id},
                           headers=HEADERS)


def _assert_error(response, status: int, code: str) -> None:
    assert response.status_code == status
    ErrorResponse.model_validate(response.json())
    assert response.json()["error"] == code


def test_assign_marks_case_assigned(env):
    """R11: un caso open pasa a assigned con el asesor y la fecha de asignación."""
    env.add_case("case-1", status="open")
    env.clock.advance(60)
    response = _assign(env, "case-1", "222")
    assert response.status_code == 200
    assert response.json() == {"status": "assigned", "case_id": "case-1"}
    CaseAssignResponse.model_validate(response.json())
    case = env.repo.cases["case-1"]
    assert (case.status, case.advisor_id, case.assigned_at) == ("assigned", "222", env.clock())


def test_assign_already_assigned_keeps_first_advisor(env):
    """R12: asignar un caso ya assigned responde 200 sin cambiar el asesor ni la fecha."""
    env.add_case("case-1", status="open")
    _assign(env, "case-1", "111")
    env.clock.advance(30)
    response = _assign(env, "case-1", "333")
    assert response.status_code == 200
    assert response.json() == {"status": "assigned", "case_id": "case-1"}
    case = env.repo.cases["case-1"]
    assert (case.advisor_id, case.assigned_at) == ("111", START)


def test_assign_timed_out_case(env):
    """R11: un caso timed_out también pasa a assigned (supuesto confirmado)."""
    env.add_case("case-1", status="timed_out")
    response = _assign(env, "case-1", "111")
    assert response.status_code == 200
    assert response.json() == {"status": "assigned", "case_id": "case-1"}
    assert env.repo.cases["case-1"].status == "assigned"


def test_assign_closed_case_returns_409(env):
    """R13: asignar un caso closed -> 409 case_closed sin modificarlo."""
    env.add_case("case-1", status="closed", closed_by="111", closed_at=START)
    before = env.repo.cases["case-1"].model_copy(deep=True)
    _assert_error(_assign(env, "case-1", "222"), 409, "case_closed")
    assert env.repo.cases["case-1"] == before


def test_assign_and_close_unknown_case_return_404(env):
    """R14: assign y close de un caso inexistente -> 404 not_found."""
    _assert_error(_assign(env, "no-existe"), 404, "not_found")
    _assert_error(_close(env, "no-existe"), 404, "not_found")
    assert env.repo.cases == {}


def test_close_marks_closed_and_records_advisor(env):
    """R15: cerrar un caso lo marca closed con el asesor y la fecha de cierre."""
    for status in ("open", "assigned", "timed_out"):
        env.add_case(f"case-{status}", status=status)
    env.clock.advance(120)
    for status in ("open", "assigned", "timed_out"):
        response = _close(env, f"case-{status}", "333")
        assert response.status_code == 200
        assert response.json() == {"status": "closed", "case_id": f"case-{status}"}
        CaseCloseResponse.model_validate(response.json())
        case = env.repo.cases[f"case-{status}"]
        assert (case.status, case.closed_by, case.closed_at) == ("closed", "333", env.clock())


def test_close_is_idempotent_and_keeps_first_closure(env):
    """R16: cerrar un caso ya cerrado responde 200 sin cambiar fecha ni asesor del cierre."""
    env.add_case("case-1", status="open")
    _close(env, "case-1", "111")
    env.clock.advance(500)
    response = _close(env, "case-1", "222")
    assert response.status_code == 200
    assert response.json() == {"status": "closed", "case_id": "case-1"}
    case = env.repo.cases["case-1"]
    assert (case.closed_by, case.closed_at) == ("111", START)
