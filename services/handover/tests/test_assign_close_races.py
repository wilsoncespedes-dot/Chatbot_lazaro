"""Carreras de asignación y cierre de handover (feature #14)."""
from __future__ import annotations

from datetime import datetime, timezone

from lazaro_contracts import ErrorResponse

from handover.adapters.repository import FakeCaseRepository
from handover.domain import Denial, assign_case, close_case

HEADERS = {"X-Service-Token": "svc-token"}
START = datetime(2026, 1, 2, 3, 0, 0, tzinfo=timezone.utc)


class RaceRepository(FakeCaseRepository):
    """Ejecuta un gancho una sola vez al empezar la escritura condicional."""

    def __init__(self) -> None:
        super().__init__()
        self.hook = None
        self._hook_done = False

    def _run_hook(self) -> None:
        if self.hook is not None and not self._hook_done:
            self._hook_done = True
            self.hook()

    def assign_if_unassigned(self, case_id: str, advisor_id: str, at: datetime) -> bool:
        self._run_hook()
        return super().assign_if_unassigned(case_id, advisor_id, at)

    def close_if_still_allowed(
        self, case_id: str, advisor_id: str, allowed_assignee: str | None, at: datetime
    ) -> bool:
        self._run_hook()
        return super().close_if_still_allowed(case_id, advisor_id, allowed_assignee, at)


def _env_with_repo(env_factory):
    repo = RaceRepository()
    env = env_factory(repo=repo)
    return env, repo


def _assign(env, case_id: str, advisor_id: str):
    return env.client.post(
        f"/cases/{case_id}/assign", json={"advisor_id": advisor_id}, headers=HEADERS
    )


def _close(env, case_id: str, advisor_id: str):
    return env.client.post(
        f"/cases/{case_id}/close", json={"advisor_id": advisor_id}, headers=HEADERS
    )


def _assert_error(response, status: int, code: str) -> None:
    assert response.status_code == status
    ErrorResponse.model_validate(response.json())
    assert response.json()["error"] == code


def test_assign_loses_race_to_other_advisor_returns_403(env_factory):
    """autorizacion_asesores R38, R37, R19: el assign que pierde la carrera da 403."""
    env, repo = _env_with_repo(env_factory)
    env.add_case("case-1", status="open")
    repo.hook = lambda: assign_case("case-1", "111", env.settings, env.adapters)
    _assert_error(_assign(env, "case-1", "222"), 403, "forbidden")
    case = env.repo.cases["case-1"]
    assert (case.status, case.advisor_id, case.assigned_at) == ("assigned", "111", START)
    assert env.repo.denials == [
        Denial(case_id="case-1", advisor_id="222", action="assign", at=START)
    ]


def test_assign_loses_race_to_close_returns_409(env_factory):
    """autorizacion_asesores R39: si el caso se cerró en medio, assign da 409."""
    env, repo = _env_with_repo(env_factory)
    env.add_case("case-1", status="open")
    repo.hook = lambda: close_case("case-1", "111", env.settings, env.adapters)
    _assert_error(_assign(env, "case-1", "222"), 409, "case_closed")
    case = env.repo.cases["case-1"]
    assert (case.status, case.closed_by, case.advisor_id) == ("closed", "111", None)
    assert env.repo.denials == []


def test_assign_race_with_same_advisor_keeps_first_assignment(env_factory):
    """autorizacion_asesores R40: el mismo asesor recibe 200 sin cambiar assigned_at."""
    env, repo = _env_with_repo(env_factory)
    env.add_case("case-1", status="open")

    def hook():
        assign_case("case-1", "222", env.settings, env.adapters)
        env.clock.advance(30)

    repo.hook = hook
    response = _assign(env, "case-1", "222")
    assert response.status_code == 200
    assert response.json() == {"status": "assigned", "case_id": "case-1"}
    assert env.repo.cases["case-1"].assigned_at == START
    assert env.repo.denials == []


def test_close_loses_race_to_other_advisor_assignment_returns_403(env_factory):
    """autorizacion_asesores R55, R41, R19: el cierre no gana a una asignación ajena."""
    env, repo = _env_with_repo(env_factory)
    env.add_case("case-1", status="open")
    repo.hook = lambda: assign_case("case-1", "222", env.settings, env.adapters)
    _assert_error(_close(env, "case-1", "111"), 403, "forbidden")
    case = env.repo.cases["case-1"]
    assert (case.status, case.advisor_id, case.assigned_at) == ("assigned", "222", START)
    assert (case.closed_by, case.closed_at) == (None, None)
    assert env.repo.denials == [
        Denial(case_id="case-1", advisor_id="111", action="close", at=START)
    ]


def test_close_loses_race_to_other_close_keeps_first_closure(env_factory):
    """autorizacion_asesores R42: el segundo cierre da 200 y conserva el primero."""
    env, repo = _env_with_repo(env_factory)
    env.add_case("case-1", status="open")

    def hook():
        close_case("case-1", "222", env.settings, env.adapters)
        env.clock.advance(30)

    repo.hook = hook
    response = _close(env, "case-1", "111")
    assert response.status_code == 200
    case = env.repo.cases["case-1"]
    assert (case.closed_by, case.closed_at) == ("222", START)
    assert env.repo.denials == []


def test_close_race_with_own_assignment_closes_case(env_factory):
    """autorizacion_asesores R41: cerrar tras asignarse a sí mismo en medio funciona."""
    env, repo = _env_with_repo(env_factory)
    env.add_case("case-1", status="open")
    repo.hook = lambda: assign_case("case-1", "111", env.settings, env.adapters)
    response = _close(env, "case-1", "111")
    assert response.status_code == 200
    case = env.repo.cases["case-1"]
    assert (case.status, case.closed_by) == ("closed", "111")
    assert (case.advisor_id, case.assigned_at) == ("111", START)
    assert env.repo.denials == []


def test_close_orphan_race_with_other_close_keeps_first_closure(env_factory):
    """autorizacion_asesores R54, R42: cerrar un huérfano en carrera conserva el primero."""
    env, repo = _env_with_repo(env_factory)
    env.add_case("case-1", status="assigned", advisor_id="999", assigned_at=START)

    def hook():
        close_case("case-1", "222", env.settings, env.adapters)
        env.clock.advance(30)

    repo.hook = hook
    response = _close(env, "case-1", "111")
    assert response.status_code == 200
    case = env.repo.cases["case-1"]
    assert (case.closed_by, case.closed_at) == ("222", START)
    assert case.advisor_id == "999"
    assert env.repo.denials == []


def test_assign_and_close_write_only_their_fields(env, monkeypatch):
    """autorizacion_asesores R37, R41, R43: no se usa update_case ni se tocan otros campos."""

    def boom(case):
        raise AssertionError("no debe usarse update_case")

    monkeypatch.setattr(env.repo, "update_case", boom)
    for status in ("open", "timed_out"):
        env.add_case(f"assign-{status}", status=status, contact_id="contact-x", chat_id=7)
        env.add_case(f"close-{status}", status=status, contact_id="contact-y", chat_id=8)
        before_assign = env.repo.cases[f"assign-{status}"].model_copy(deep=True)
        before_close = env.repo.cases[f"close-{status}"].model_copy(deep=True)
        assert _assign(env, f"assign-{status}", "111").status_code == 200
        assert _close(env, f"close-{status}", "111").status_code == 200
        assigned = env.repo.cases[f"assign-{status}"]
        closed = env.repo.cases[f"close-{status}"]
        for original, current in ((before_assign, assigned), (before_close, closed)):
            assert current.last_messages == original.last_messages
            assert current.contact_id == original.contact_id
            assert current.chat_id == original.chat_id
            assert current.reason == original.reason
