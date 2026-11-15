"""Reasignación de casos por supervisor y vista global (#49)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from lazaro_contracts import (
    AdvisorRosterEntry,
    CaseListResponse,
    CaseReassignResponse,
    ErrorResponse,
)

from handover.adapters.repository import FakeCaseRepository

HEADERS = {"X-Service-Token": "svc-token"}
START = datetime(2026, 1, 2, 3, 0, 0, tzinfo=timezone.utc)
SUPERVISOR = "999"
OTHER_SUPERVISOR = "998"
ADVISOR = "111"
TARGET = "222"


def _roster(env, *, supervisor_role: str = "supervisor") -> None:
    env.repo.replace_roster(
        [
            AdvisorRosterEntry(profile_id=ADVISOR, role="asesor"),
            AdvisorRosterEntry(profile_id=TARGET, role="asesor"),
            AdvisorRosterEntry(profile_id="333", role="asesor"),
            AdvisorRosterEntry(profile_id=SUPERVISOR, role=supervisor_role),
            AdvisorRosterEntry(profile_id=OTHER_SUPERVISOR, role="supervisor"),
            AdvisorRosterEntry(profile_id="responsable-1", role="responsable_datos"),
            AdvisorRosterEntry(profile_id="admin-1", role="otro"),
        ],
        generation=2,
    )


def _reassign(
    env,
    case_id: str = "case-1",
    advisor_id: str = SUPERVISOR,
    target_advisor_id: str = TARGET,
    headers: dict | None = None,
):
    return env.client.post(
        f"/cases/{case_id}/reassign",
        json={"advisor_id": advisor_id, "target_advisor_id": target_advisor_id},
        headers=HEADERS if headers is None else headers,
    )


def _list(env, advisor_id: str = SUPERVISOR, scope: str = "all"):
    return env.client.get(
        "/cases",
        params={"advisor_id": advisor_id, "scope": scope},
        headers=HEADERS,
    )


def _assert_error(response, status: int, code: str) -> None:
    assert response.status_code == status
    ErrorResponse.model_validate(response.json())
    assert response.json()["error"] == code


def _case_state(env, case_id: str = "case-1"):
    return env.repo.cases[case_id].model_copy(deep=True)


class _LostToClosed(FakeCaseRepository):
    def reassign_if_assigned_to(self, case_id, from_id, to_id, at) -> bool:
        case = self.cases[case_id]
        self.cases[case_id] = case.model_copy(
            update={"status": "closed", "closed_at": at, "closed_by": from_id}
        )
        return False


class _LostToReplyReassign(FakeCaseRepository):
    def reassign_if_assigned_to(self, case_id, from_id, to_id, at) -> bool:
        case = self.cases[case_id]
        self.cases[case_id] = case.model_copy(update={"advisor_id": to_id})
        return False


class _LostToTransfer(FakeCaseRepository):
    def reassign_if_assigned_to(self, case_id, from_id, to_id, at) -> bool:
        case = self.cases[case_id]
        self.cases[case_id] = case.model_copy(update={"advisor_id": "333"})
        return False


# --- R7, R24: roster con rol ------------------------------------------------------------


def test_roster_registers_only_asesor_and_supervisor_and_keeps_role(env):
    """R7, R24: asesor y supervisor entran al roster; el resto no; se conserva el rol."""
    _roster(env)
    assert env.repo.get_roster() == {
        ADVISOR: None,
        TARGET: None,
        "333": None,
        SUPERVISOR: None,
        OTHER_SUPERVISOR: None,
    }
    assert env.repo.get_roster_roles()[SUPERVISOR] == "supervisor"
    assert env.repo.get_roster_roles()[ADVISOR] == "asesor"
    assert "responsable-1" not in env.repo.get_roster()


# --- R12, R12b: reasignación correcta ---------------------------------------------------


def test_supervisor_reassigns_assigned_case(env):
    """R12, R12b: cambia advisor_id sin cambiar estado y devuelve el asesor previo."""
    _roster(env)
    env.add_case("case-1", status="assigned", advisor_id=ADVISOR, assigned_at=START)
    env.clock.advance(90)

    response = _reassign(env)

    assert response.status_code == 200
    body = CaseReassignResponse.model_validate(response.json())
    assert body.status == "assigned"
    assert body.case_id == "case-1"
    assert body.previous_advisor_id == ADVISOR
    assert body.advisor_id == TARGET
    case = env.repo.cases["case-1"]
    assert (case.status, case.advisor_id, case.assigned_at) == (
        "assigned",
        TARGET,
        env.clock(),
    )
    assert env.repo.denials == []
    assert env.gateway.sent == []


def test_supervisor_can_reassign_orphan_case(env):
    """R15: un huérfano assigned sí se reasigna; previous_advisor_id queda nulo."""
    _roster(env)
    env.add_case("case-1", status="assigned", advisor_id=None)

    response = _reassign(env)

    assert response.status_code == 200
    body = CaseReassignResponse.model_validate(response.json())
    assert body.previous_advisor_id is None
    assert env.repo.cases["case-1"].advisor_id == TARGET


# --- R16: solo supervisor ----------------------------------------------------------------


@pytest.mark.parametrize("actor", [ADVISOR, "no-existe", "responsable-1", "admin-1"])
def test_non_supervisor_gets_403_and_denial(env, actor):
    """R16: asesor, id inexistente, responsable y admin reciben 403 sin cambios."""
    _roster(env)
    env.add_case("case-1", status="assigned", advisor_id=ADVISOR)
    before = _case_state(env)

    response = _reassign(env, advisor_id=actor)

    _assert_error(response, 403, "forbidden")
    assert _case_state(env) == before
    assert len(env.repo.denials) == 1
    denial = env.repo.denials[0]
    assert (denial.case_id, denial.advisor_id, denial.action) == (
        "case-1",
        actor,
        "reassign",
    )


def test_supervisor_role_is_read_from_roster_not_from_current_state(env):
    """R16: un perfil retirado del roster pierde el permiso aunque fuera supervisor."""
    _roster(env, supervisor_role="asesor")
    env.add_case("case-1", status="assigned", advisor_id=ADVISOR)
    before = _case_state(env)

    _assert_error(_reassign(env), 403, "forbidden")
    assert _case_state(env) == before


# --- R13: errores y carreras -------------------------------------------------------------


@pytest.mark.parametrize("status", ["open", "timed_out"])
def test_case_not_assigned_returns_409(env, status):
    """R15: open y timed_out responden 409 case_not_assigned sin cambios."""
    _roster(env)
    env.add_case("case-1", status=status)
    before = _case_state(env)

    _assert_error(_reassign(env), 409, "case_not_assigned")
    assert _case_state(env) == before


def test_closed_case_returns_409_case_closed(env):
    """R15: un caso closed responde 409 case_closed."""
    _roster(env)
    env.add_case("case-1", status="closed", closed_by=ADVISOR, closed_at=START)
    before = _case_state(env)

    _assert_error(_reassign(env), 409, "case_closed")
    assert _case_state(env) == before


def test_missing_case_returns_404(env):
    """R15: un caso inexistente responde 404 not_found."""
    _roster(env)
    _assert_error(_reassign(env, case_id="no-existe"), 404, "not_found")


@pytest.mark.parametrize("target", [ADVISOR, "no-existe", "responsable-1", "admin-1"])
def test_invalid_target_returns_422_without_changes(env, target):
    """R14: destino igual al actual o no atendedor registrado responde 422."""
    _roster(env)
    env.add_case("case-1", status="assigned", advisor_id=ADVISOR)
    before = _case_state(env)

    _assert_error(_reassign(env, target_advisor_id=target), 422, "validation_error")
    assert _case_state(env) == before
    assert env.repo.denials == []


def test_lost_race_to_closed_returns_case_closed(env_factory):
    """R13: si el caso se cerró entre lectura y escritura, 409 case_closed."""
    env = env_factory(repo=_LostToClosed())
    _roster(env)
    env.add_case("case-1", status="assigned", advisor_id=ADVISOR)

    _assert_error(_reassign(env), 409, "case_closed")
    assert env.repo.cases["case-1"].status == "closed"


def test_lost_race_to_reply_reassign_returns_case_changed(env_factory):
    """R13: si respondieron y reasignaron antes, 409 case_changed sin deshacerlo."""
    env = env_factory(repo=_LostToReplyReassign())
    _roster(env)
    env.add_case("case-1", status="assigned", advisor_id=ADVISOR)

    _assert_error(_reassign(env), 409, "case_changed")
    assert env.repo.cases["case-1"].advisor_id == TARGET


def test_lost_race_to_transfer_returns_case_changed(env_factory):
    """R13: si otro transfer lo movió, 409 case_changed y conserva el cambio."""
    env = env_factory(repo=_LostToTransfer())
    _roster(env)
    env.add_case("case-1", status="assigned", advisor_id=ADVISOR)

    _assert_error(_reassign(env), 409, "case_changed")
    assert env.repo.cases["case-1"].advisor_id == "333"


# --- R9, R10, R30: vista global ----------------------------------------------------------


def test_supervisor_scope_all_lists_every_state_and_advisor(env):
    """R8, R9: todos los casos, incluidos closed, con asesor y acciones permitidas."""
    _roster(env)
    env.add_case("case-open", status="open", created_at=START)
    env.add_case(
        "case-mine",
        status="assigned",
        advisor_id=SUPERVISOR,
        created_at=START + timedelta(seconds=1),
    )
    env.add_case(
        "case-other",
        status="assigned",
        advisor_id=ADVISOR,
        created_at=START + timedelta(seconds=2),
    )
    env.add_case(
        "case-orphan",
        status="assigned",
        advisor_id=None,
        created_at=START + timedelta(seconds=3),
    )
    env.add_case(
        "case-closed",
        status="closed",
        advisor_id=ADVISOR,
        closed_by=ADVISOR,
        closed_at=START,
        created_at=START + timedelta(seconds=4),
    )

    response = _list(env)

    assert response.status_code == 200
    body = CaseListResponse.model_validate(response.json())
    listed = {item.case_id: item for item in body.root}
    assert set(listed) == {
        "case-open",
        "case-mine",
        "case-other",
        "case-orphan",
        "case-closed",
    }
    assert listed["case-open"].actions == ["reply", "assign", "close"]
    assert listed["case-mine"].actions == ["reply", "close", "reassign"]
    assert listed["case-other"].actions == ["reassign"]
    assert listed["case-other"].advisor_id == ADVISOR
    assert listed["case-orphan"].actions == ["close", "reassign"]
    assert listed["case-closed"].actions == ["close"]
    assert listed["case-closed"].advisor_id == ADVISOR
    assert [item.case_id for item in body.root] == [
        "case-open",
        "case-mine",
        "case-other",
        "case-orphan",
        "case-closed",
    ]


@pytest.mark.parametrize("actor", [ADVISOR, "no-existe", "responsable-1"])
def test_scope_all_without_supervisor_returns_403(env, actor):
    """R10: scope=all con un advisor_id que no es supervisor responde 403."""
    _roster(env)
    env.add_case("case-1", status="open")

    response = _list(env, advisor_id=actor)

    _assert_error(response, 403, "forbidden")
    assert env.repo.denials[-1].action == "list_all"


def test_scope_mine_keeps_existing_behavior_for_supervisor(env):
    """R6b, R29: el supervisor conserva la bandeja propia con las reglas de asesor."""
    _roster(env)
    env.add_case("case-open", status="open", created_at=START)
    env.add_case(
        "case-other",
        status="assigned",
        advisor_id=ADVISOR,
        created_at=START + timedelta(seconds=1),
    )
    env.add_case(
        "case-mine",
        status="assigned",
        advisor_id=SUPERVISOR,
        created_at=START + timedelta(seconds=2),
    )

    response = _list(env, scope="mine")

    assert response.status_code == 200
    ids = [item["case_id"] for item in response.json()]
    assert ids == ["case-open", "case-mine"]


def test_scope_all_respects_case_list_limit(env_factory):
    """R9, S14: el límite se aplica a la vista global tras ordenar."""
    env = env_factory(settings_overrides={"case_list_limit": 2})
    _roster(env)
    env.add_case("case-1", created_at=START)
    env.add_case("case-2", created_at=START + timedelta(seconds=1))
    env.add_case("case-3", created_at=START + timedelta(seconds=2))

    response = _list(env)

    assert [item["case_id"] for item in response.json()] == ["case-1", "case-2"]


def test_reassign_requires_service_token_and_valid_body(env):
    """R30: token y validación de cuerpo aplican a la ruta nueva."""
    _roster(env)
    env.add_case("case-1", status="assigned", advisor_id=ADVISOR)
    _assert_error(_reassign(env, headers={}), 401, "unauthorized")
    _assert_error(
        _reassign(env, advisor_id=""), 422, "validation_error"
    )
