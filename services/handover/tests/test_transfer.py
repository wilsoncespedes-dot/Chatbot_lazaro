"""Tests de POST /cases/{id}/transfer (feature #41)."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest
from lazaro_contracts import CaseTransferResponse, ErrorResponse

from handover.adapters.repository import FakeCaseRepository

HEADERS = {"X-Service-Token": "svc-token"}
START = datetime(2026, 1, 2, 3, 0, 0, tzinfo=timezone.utc)


def _transfer(env, case_id: str = "case-1", advisor_id: str = "111",
              target_advisor_id: str = "222", headers: dict | None = None):
    return env.client.post(
        f"/cases/{case_id}/transfer",
        json={"advisor_id": advisor_id, "target_advisor_id": target_advisor_id},
        headers=HEADERS if headers is None else headers,
    )


def _assert_error(response, status: int, code: str) -> None:
    assert response.status_code == status
    ErrorResponse.model_validate(response.json())
    assert response.json()["error"] == code


def _cases(env) -> dict:
    return {key: value.model_copy(deep=True) for key, value in env.repo.cases.items()}


class _LostToTarget(FakeCaseRepository):
    def transfer_if_assigned_to(self, case_id, from_id, to_id, at) -> bool:
        case = self.cases[case_id]
        self.cases[case_id] = case.model_copy(
            update={"advisor_id": to_id, "assigned_at": at}
        )
        return False


class _LostToOther(FakeCaseRepository):
    def transfer_if_assigned_to(self, case_id, from_id, to_id, at) -> bool:
        case = self.cases[case_id]
        self.cases[case_id] = case.model_copy(update={"advisor_id": "333"})
        return False


def test_transfer_reassigns_case_and_updates_assigned_at(env):
    """R27: el asesor actual transfiere a otro registrado y responde 200."""
    env.add_case("case-1", status="assigned", advisor_id="111", assigned_at=START)
    env.clock.advance(90)

    response = _transfer(env)

    assert response.status_code == 200
    body = CaseTransferResponse.model_validate(response.json())
    assert (body.status, body.case_id, body.advisor_id) == (
        "assigned",
        "case-1",
        "222",
    )
    case = env.repo.cases["case-1"]
    assert (case.status, case.advisor_id, case.assigned_at) == (
        "assigned",
        "222",
        env.clock(),
    )


@pytest.mark.parametrize("advisor_id", ["999", "0111", "+111", " 111"])
def test_unregistered_actor_is_denied_and_records_transfer(env, advisor_id):
    """R28: actor no registrado -> 403 y denegación con acción transfer."""
    env.add_case("case-1", status="assigned", advisor_id="111")
    before = _cases(env)

    response = _transfer(env, advisor_id=advisor_id)

    _assert_error(response, 403, "forbidden")
    assert env.repo.cases == before
    assert len(env.repo.denials) == 1
    assert env.repo.denials[0].action == "transfer"


@pytest.mark.parametrize("status", ["open", "timed_out"])
def test_case_not_assigned_to_actor_is_denied(env, status):
    """R28: el caso no está assigned al actor -> 403 sin cambios."""
    env.add_case("case-1", status=status)
    before = _cases(env)

    response = _transfer(env)

    _assert_error(response, 403, "forbidden")
    assert env.repo.cases == before
    assert env.repo.denials[-1].action == "transfer"


def test_case_assigned_to_other_advisor_is_denied(env):
    """R28: un caso assigned a otro asesor no se transfiere."""
    env.add_case("case-1", status="assigned", advisor_id="222")
    before = _cases(env)

    response = _transfer(env, advisor_id="111")

    _assert_error(response, 403, "forbidden")
    assert env.repo.cases == before


@pytest.mark.parametrize(
    "target",
    ["999", "111"],
)
def test_invalid_or_same_target_returns_422_without_changes(env, target):
    """R29: destino no registrado o igual al actor -> 422 validation_error."""
    env.add_case("case-1", status="assigned", advisor_id="111")
    before = _cases(env)

    response = _transfer(env, target_advisor_id=target)

    _assert_error(response, 422, "validation_error")
    assert env.repo.cases == before
    assert env.repo.denials == []


def test_missing_case_returns_404(env):
    """R30: un caso inexistente responde 404 not_found."""
    _assert_error(_transfer(env, case_id="no-existe"), 404, "not_found")


def test_closed_case_returns_409(env):
    """R30: un caso cerrado responde 409 case_closed."""
    env.add_case("case-1", status="closed", closed_by="111", closed_at=START)
    _assert_error(_transfer(env), 409, "case_closed")


def test_lost_race_to_target_returns_200(env_factory):
    """R31: si la escritura pierde pero el caso ya está en el destino, responde 200."""
    repo = _LostToTarget()
    env = env_factory(repo=repo)
    env.add_case("case-1", status="assigned", advisor_id="111")

    response = _transfer(env)

    assert response.status_code == 200
    body = CaseTransferResponse.model_validate(response.json())
    assert body.advisor_id == "222"


def test_lost_race_to_other_advisor_returns_403(env_factory):
    """R31: si la escritura pierde y el caso quedó en otro, responde 403."""
    repo = _LostToOther()
    env = env_factory(repo=repo)
    env.add_case("case-1", status="assigned", advisor_id="111")

    response = _transfer(env)

    _assert_error(response, 403, "forbidden")
    assert repo.denials[-1].action == "transfer"


def test_transfer_without_token_returns_401(env):
    """R74: sin X-Service-Token válido responde 401 unauthorized."""
    env.add_case("case-1", status="assigned", advisor_id="111")
    _assert_error(_transfer(env, headers={}), 401, "unauthorized")


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"advisor_id": "111"},
        {"target_advisor_id": "222"},
        {"advisor_id": "", "target_advisor_id": "222"},
        {"advisor_id": "111", "target_advisor_id": "x" * 65},
    ],
)
def test_invalid_body_returns_422(env, body):
    """R74: un cuerpo que no cumple CaseTransferRequest responde 422."""
    response = env.client.post("/cases/case-1/transfer", json=body, headers=HEADERS)
    _assert_error(response, 422, "validation_error")
