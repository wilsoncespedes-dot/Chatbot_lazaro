"""Tests de autorización de asesores en handover (feature #14)."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi.testclient import TestClient
from lazaro_contracts import CaseAuthorizeResponse, ErrorResponse

from handover.config import Settings
from handover.domain import Denial, is_registered_advisor
from handover.main import create_app

HEADERS = {"X-Service-Token": "svc-token"}
START = datetime(2026, 1, 2, 3, 0, 0, tzinfo=timezone.utc)
ACTIONS = ("reply", "close")


def _authorize(env, case_id: str = "case-1", advisor_id: str = "111", action: str = "reply"):
    return env.client.post(
        f"/cases/{case_id}/authorize",
        json={"advisor_id": advisor_id, "action": action},
        headers=HEADERS,
    )


def _assign(env, case_id: str = "case-1", advisor_id: str = "111"):
    return env.client.post(
        f"/cases/{case_id}/assign", json={"advisor_id": advisor_id}, headers=HEADERS
    )


def _close(env, case_id: str = "case-1", advisor_id: str = "111"):
    return env.client.post(
        f"/cases/{case_id}/close", json={"advisor_id": advisor_id}, headers=HEADERS
    )


def _assert_error(response, status: int, code: str) -> None:
    assert response.status_code == status
    ErrorResponse.model_validate(response.json())
    assert response.json()["error"] == code


def _cases(env) -> dict:
    return {key: value.model_copy(deep=True) for key, value in env.repo.cases.items()}


# --- Autorizar ---------------------------------------------------------------------------


def test_registered_advisor_matches_decimal_id_exactly():
    """autorizacion_asesores R1: igualdad exacta con str(int) de ADVISOR_CHAT_IDS."""
    settings = Settings(advisor_chat_ids="111,-1003")
    for value in ("111", "-1003"):
        assert is_registered_advisor(value, settings) is True
    for value in ("999", "0111", "+111", " 111", "111 ", "1.11", "-111", None):
        assert is_registered_advisor(value, settings) is False


def test_authorize_unassigned_case_allows_any_registered_advisor(env):
    """autorizacion_asesores R2: caso open/timed_out permite a cualquier asesor."""
    for status in ("open", "timed_out"):
        for action in ACTIONS:
            for advisor in ("111", "222", "333"):
                case_id = f"case-{status}-{advisor}"
                env.add_case(case_id, status=status)
                response = _authorize(env, case_id, advisor, action)
                assert response.status_code == 200
                parsed = CaseAuthorizeResponse.model_validate(response.json())
                assert (parsed.allowed, parsed.case_id) == (True, case_id)


def test_authorize_assigned_case_allows_assigned_advisor(env):
    """autorizacion_asesores R3: el asesor asignado puede responder y cerrar su caso."""
    env.add_case("case-1", status="assigned", advisor_id="222")
    for action in ACTIONS:
        response = _authorize(env, "case-1", "222", action)
        assert response.status_code == 200
        assert response.json() == {"allowed": True, "case_id": "case-1"}


def test_authorize_unregistered_advisor_returns_403_before_checking_case(env_factory):
    """autorizacion_asesores R4: 403 antes de mirar el caso, también para el retirado."""
    setups = ("open", "timed_out", "assigned_other", "closed", "missing")
    for setup in setups:
        for action in ACTIONS:
            env = env_factory()
            if setup == "open":
                env.add_case("case-1", status="open")
            elif setup == "timed_out":
                env.add_case("case-1", status="timed_out")
            elif setup == "assigned_other":
                env.add_case("case-1", status="assigned", advisor_id="999")
            elif setup == "closed":
                env.add_case("case-1", status="closed", closed_by="111", closed_at=START)
            response = _authorize(env, "case-1", "999", action)
            _assert_error(response, 403, "forbidden")

    env = env_factory(advisors=[222, 333])
    env.add_case("case-1", status="assigned", advisor_id="111")
    for action in ACTIONS:
        _assert_error(_authorize(env, "case-1", "111", action), 403, "forbidden")


def test_authorize_unknown_case_returns_404(env):
    """autorizacion_asesores R5: un asesor registrado sobre un caso inexistente recibe 404."""
    _assert_error(_authorize(env, "no-existe", "111", "reply"), 404, "not_found")


def test_authorize_closed_case_returns_409(env):
    """autorizacion_asesores R6: authorize sobre un caso closed siempre da 409."""
    env.add_case("case-1", status="assigned", advisor_id="111")
    env.repo.cases["case-1"] = env.repo.cases["case-1"].model_copy(
        update={"status": "closed", "closed_by": "111", "closed_at": START}
    )
    for action in ACTIONS:
        _assert_error(_authorize(env, "case-1", "111", action), 409, "case_closed")


def test_authorize_assigned_case_rejects_other_advisor(env):
    """autorizacion_asesores R7: un caso assigned a otro asesor registrado da 403."""
    env.add_case("case-1", status="assigned", advisor_id="111")
    for action in ACTIONS:
        _assert_error(_authorize(env, "case-1", "222", action), 403, "forbidden")


def test_authorize_never_modifies_cases_nor_sends(env):
    """autorizacion_asesores R8: authorize no modifica casos ni llama al gateway."""
    env.add_case("open", status="open")
    env.add_case("closed", status="closed", closed_by="111", closed_at=START)
    env.add_case("orphan", status="assigned", advisor_id="999")
    before = _cases(env)
    requests = [
        ("open", "111", "reply"),
        ("orphan", "111", "close"),
        ("open", "999", "reply"),
        ("no-existe", "111", "reply"),
        ("closed", "111", "close"),
    ]
    for case_id, advisor, action in requests:
        _authorize(env, case_id, advisor, action)
    assert _cases(env) == before
    assert env.gateway.sent == []


# --- Asignar -----------------------------------------------------------------------------


def test_assign_unregistered_advisor_returns_403_and_keeps_case(env_factory):
    """autorizacion_asesores R11: assign con asesor no registrado da 403 sin cambios."""
    for setup in ("open", "timed_out", "assigned", "closed", "missing"):
        env = env_factory()
        if setup in ("open", "timed_out"):
            env.add_case("case-1", status=setup)
        elif setup == "assigned":
            env.add_case("case-1", status="assigned", advisor_id="111")
        elif setup == "closed":
            env.add_case("case-1", status="closed", closed_by="111", closed_at=START)
        before = _cases(env)
        _assert_error(_assign(env, "case-1", "999"), 403, "forbidden")
        assert _cases(env) == before


def test_assign_assigned_case_by_other_advisor_returns_403(env):
    """autorizacion_asesores R12: otro asesor no puede asignar un caso assigned."""
    env.add_case("case-1", status="assigned", advisor_id="111", assigned_at=START)
    before = _cases(env)
    _assert_error(_assign(env, "case-1", "333"), 403, "forbidden")
    case = env.repo.cases["case-1"]
    assert _cases(env) == before
    assert (case.advisor_id, case.assigned_at) == ("111", START)


def test_assign_assigned_case_by_same_advisor_keeps_it(env):
    """autorizacion_asesores R13: el asesor asignado recibe 200 sin cambiar la fecha."""
    env.add_case("case-1", status="assigned", advisor_id="111", assigned_at=START)
    env.clock.advance(500)
    response = _assign(env, "case-1", "111")
    assert response.status_code == 200
    assert response.json() == {"status": "assigned", "case_id": "case-1"}
    case = env.repo.cases["case-1"]
    assert (case.advisor_id, case.assigned_at) == ("111", START)


# --- Cerrar ------------------------------------------------------------------------------


def test_close_unregistered_advisor_returns_403_and_keeps_case(env_factory):
    """autorizacion_asesores R14: close con asesor no registrado da 403, también si closed."""
    for setup in ("open", "timed_out", "assigned", "closed", "missing"):
        env = env_factory()
        if setup in ("open", "timed_out"):
            env.add_case("case-1", status=setup)
        elif setup == "assigned":
            env.add_case("case-1", status="assigned", advisor_id="111")
        elif setup == "closed":
            env.add_case("case-1", status="closed", closed_by="111", closed_at=START)
        before = _cases(env)
        _assert_error(_close(env, "case-1", "999"), 403, "forbidden")
        assert _cases(env) == before


def test_close_assigned_case_by_other_advisor_returns_403(env):
    """autorizacion_asesores R15: un caso assigned a otro asesor registrado no se cierra."""
    env.add_case("case-1", status="assigned", advisor_id="111", assigned_at=START)
    before = _cases(env)
    _assert_error(_close(env, "case-1", "222"), 403, "forbidden")
    case = env.repo.cases["case-1"]
    assert _cases(env) == before
    assert (case.status, case.closed_by, case.closed_at) == ("assigned", None, None)


def test_close_assigned_case_by_assigned_advisor(env):
    """autorizacion_asesores R16, R41: el asignado cierra conservando los datos del caso."""
    env.add_case("case-1", status="assigned", advisor_id="111", assigned_at=START)
    env.clock.advance(60)
    response = _close(env, "case-1", "111")
    assert response.status_code == 200
    assert response.json() == {"status": "closed", "case_id": "case-1"}
    case = env.repo.cases["case-1"]
    assert (case.status, case.closed_by, case.closed_at) == ("closed", "111", env.clock())
    assert (case.advisor_id, case.assigned_at) == ("111", START)


def test_close_unassigned_case_by_any_registered_advisor(env):
    """autorizacion_asesores R17: sin asignar, cualquier asesor registrado lo cierra."""
    for status in ("open", "timed_out"):
        for advisor in ("111", "222", "333"):
            case_id = f"case-{status}-{advisor}"
            env.add_case(case_id, status=status)
            response = _close(env, case_id, advisor)
            assert response.status_code == 200
            case = env.repo.cases[case_id]
            assert (case.status, case.closed_by) == ("closed", advisor)


def test_close_closed_case_by_registered_advisor_keeps_first_closure(env):
    """autorizacion_asesores R18, R20: cerrar un caso closed da 200 sin cambios."""
    env.add_case("case-1", status="assigned", advisor_id="111", assigned_at=START)
    _close(env, "case-1", "111")
    env.clock.advance(500)
    response = _close(env, "case-1", "222")
    assert response.status_code == 200
    case = env.repo.cases["case-1"]
    assert (case.closed_by, case.closed_at) == ("111", START)
    assert env.repo.denials == []


# --- Registro de denegaciones ------------------------------------------------------------


def test_denials_are_recorded_with_case_advisor_action_and_date(env):
    """autorizacion_asesores R19: cada 403 deja su Denial con caso, asesor, acción y fecha."""
    env.add_case("case-1", status="open")
    _authorize(env, "case-1", "999", "reply")
    _authorize(env, "case-1", "999", "close")
    _assign(env, "case-1", "999")
    _close(env, "case-1", "999")
    _authorize(env, "no-existe", "999", "reply")
    assert env.repo.denials == [
        Denial(case_id="case-1", advisor_id="999", action="reply", at=START),
        Denial(case_id="case-1", advisor_id="999", action="close", at=START),
        Denial(case_id="case-1", advisor_id="999", action="assign", at=START),
        Denial(case_id="case-1", advisor_id="999", action="close", at=START),
        Denial(case_id="no-existe", advisor_id="999", action="reply", at=START),
    ]


def test_no_denial_recorded_for_allowed_or_other_errors(env):
    """autorizacion_asesores R20: 200, 404, 409 y 422 no son denegaciones."""
    env.add_case("open", status="open")
    env.add_case("orphan", status="assigned", advisor_id="999")
    env.add_case("closed", status="closed", closed_by="111", closed_at=START)
    assert _authorize(env, "open", "111", "reply").status_code == 200
    assert _authorize(env, "orphan", "111", "close").status_code == 200
    assert _close(env, "orphan", "111").status_code == 200
    _assert_error(_authorize(env, "no-existe", "111", "reply"), 404, "not_found")
    _assert_error(_authorize(env, "closed", "111", "reply"), 409, "case_closed")
    _assert_error(
        env.client.post(
            "/cases/open/authorize", json={"advisor_id": "111"}, headers=HEADERS
        ),
        422,
        "validation_error",
    )
    _assert_error(
        env.client.post("/cases/open/assign", json={}, headers=HEADERS), 422, "validation_error"
    )
    _assert_error(
        env.client.post("/cases/open/close", json={}, headers=HEADERS), 422, "validation_error"
    )
    assert env.repo.denials == []


def test_denial_record_failure_returns_500_and_keeps_case(env, monkeypatch):
    """autorizacion_asesores R22: si falla el registro de denegación, 500 sin tocar el caso."""

    def boom(denial):
        raise RuntimeError("no se pudo guardar")

    monkeypatch.setattr(env.repo, "add_denial", boom)
    client = TestClient(create_app(env.settings, env.adapters), raise_server_exceptions=False)
    for setup in ("open", "timed_out", "assigned", "closed"):
        if setup in ("open", "timed_out"):
            env.add_case(setup, status=setup)
        elif setup == "assigned":
            env.add_case(setup, status="assigned", advisor_id="111")
        else:
            env.add_case(setup, status="closed", closed_by="111", closed_at=START)
        before = _cases(env)
        for path, body in (
            ("authorize", {"advisor_id": "999", "action": "reply"}),
            ("assign", {"advisor_id": "999"}),
            ("close", {"advisor_id": "999"}),
        ):
            response = client.post(
                f"/cases/{setup}/{path}", json=body, headers=HEADERS
            )
            _assert_error(response, 500, "internal_error")
            assert _cases(env) == before


# --- Casos huérfanos ---------------------------------------------------------------------


def test_authorize_close_orphan_case_allowed_for_any_registered_advisor(env_factory):
    """autorizacion_asesores R46: cualquier asesor registrado autoriza cerrar un huérfano."""
    for advisor in ("111", "222", "333"):
        for orphan_advisor in ("999", None):
            env = env_factory(advisors=[111, 222, 333])
            env.add_case("case-1", status="assigned", advisor_id=orphan_advisor)
            response = _authorize(env, "case-1", advisor, "close")
            assert response.status_code == 200
            assert response.json() == {"allowed": True, "case_id": "case-1"}


def test_close_orphan_case_by_any_registered_advisor(env):
    """autorizacion_asesores R47, R54: cerrar un huérfano conserva el asesor retirado."""
    env.add_case("case-1", status="assigned", advisor_id="999", assigned_at=START)
    env.clock.advance(90)
    response = _close(env, "case-1", "222")
    assert response.status_code == 200
    case = env.repo.cases["case-1"]
    assert (case.status, case.closed_by, case.closed_at) == ("closed", "222", env.clock())
    assert (case.advisor_id, case.assigned_at) == ("999", START)
    assert env.repo.denials == []


def test_orphan_case_cannot_be_replied_or_assigned_by_other_advisor(env):
    """autorizacion_asesores R48, R12, R19: un huérfano no se responde ni se asigna."""
    env.add_case("case-1", status="assigned", advisor_id="999", assigned_at=START)
    before = _cases(env)
    _assert_error(_authorize(env, "case-1", "222", "reply"), 403, "forbidden")
    assert _cases(env) == before
    assert env.repo.denials[-1].action == "reply"
    _assert_error(_assign(env, "case-1", "222"), 403, "forbidden")
    assert _cases(env) == before
    assert env.repo.denials[-1].action == "assign"
