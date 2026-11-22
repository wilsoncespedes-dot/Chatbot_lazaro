"""POST /cases/take y GET /cases?scope=overview (#68)."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import pytest
from lazaro_contracts import CaseListResponse, CaseTakeRequest, ErrorResponse, LastMessage

from handover.domain import CaseChanged, take_case

HEADERS = {"X-Service-Token": "svc-token"}
NOW = datetime(2026, 1, 2, 3, 0, 0, tzinfo=timezone.utc)


def _body(
    case_id: str = "case-new",
    contact_id: str = "contact-1",
    advisor_id: str = "111",
    chat_id: int = 900,
) -> dict:
    return {
        "case_id": case_id,
        "contact_id": contact_id,
        "chat_id": chat_id,
        "advisor_id": advisor_id,
        "last_messages": [
            {"role": "user", "text": "Necesito ayuda", "at": "2026-01-02T02:59:00Z"}
        ],
    }


def _take(env, body: dict | None = None, headers: dict | None = None):
    return env.client.post(
        "/cases/take",
        json=body or _body(),
        headers=HEADERS if headers is None else headers,
    )


def _assert_error(response, status: int, code: str) -> None:
    assert response.status_code == status
    ErrorResponse.model_validate(response.json())
    assert response.json()["error"] == code


@pytest.mark.parametrize("headers", [{}, {"X-Service-Token": "otro"}])
def test_take_requires_service_token(env, headers):
    """R38: sin token válido no crea caso ni envía avisos."""
    _assert_error(_take(env, headers=headers), 401, "unauthorized")
    assert env.repo.cases == {}
    assert env.gateway.sent == []


def test_take_creates_assigned_case_without_notices(env):
    """R38, R41: sin caso crea uno assigned y no envía avisos."""
    response = _take(env)

    assert response.status_code == 200
    payload = response.json()
    assert payload == {"status": "taken", "case_id": "case-new", "created": True}
    case = env.repo.get_case("case-new")
    assert case is not None
    assert (case.contact_id, case.status, case.advisor_id) == (
        "contact-1",
        "assigned",
        "111",
    )
    assert case.reason == "advisor_take"
    assert env.gateway.sent == []
    assert env.repo.notifications == []


def test_take_assigns_open_case_without_creating_another(env):
    """R16, R38: un caso abierto sin asesor se asigna, created=false."""
    env.add_case("case-open", status="open", contact_id="contact-1", chat_id=900)

    response = _take(env, _body(case_id="case-other"))

    assert response.status_code == 200
    assert response.json() == {
        "status": "taken",
        "case_id": "case-open",
        "created": False,
    }
    assert len(env.repo.cases) == 1
    assert env.repo.get_case("case-open").status == "assigned"


def test_take_is_idempotent_for_the_same_advisor(env):
    """R22: el mismo asesor repite la toma y recibe el mismo caso."""
    first = _take(env)
    second = _take(env, _body(case_id="case-otro"))

    assert first.json()["created"] is True
    assert second.status_code == 200
    assert second.json()["case_id"] == "case-new"
    assert second.json()["created"] is False
    assert len(env.repo.cases) == 1


def test_take_assigned_to_another_advisor_is_case_changed(env):
    """R21: un caso asignado a otro asesor responde 409 sin cambios."""
    env.add_case(
        "case-open",
        status="assigned",
        contact_id="contact-1",
        advisor_id="222",
    )

    response = _take(env)

    _assert_error(response, 409, "case_changed")
    case = env.repo.get_case("case-open")
    assert case.advisor_id == "222"
    assert len(env.repo.cases) == 1


def test_take_from_unregistered_advisor_is_forbidden(env):
    """R40: un advisor_id fuera del roster no crea caso."""
    response = _take(env, _body(advisor_id="999"))

    _assert_error(response, 403, "forbidden")
    assert env.repo.cases == {}
    assert env.gateway.sent == []


def test_take_invalid_body_is_422(env):
    """R38: el cuerpo debe validar contra CaseTakeRequest."""
    response = _take(env, {"case_id": "case-1"})
    _assert_error(response, 422, "validation_error")
    assert env.repo.cases == {}


def _request_body(contact_id: str, case_id: str, advisor_id: str) -> CaseTakeRequest:
    return CaseTakeRequest(
        case_id=case_id,
        contact_id=contact_id,
        chat_id=900,
        advisor_id=advisor_id,
        last_messages=[
            LastMessage(role="user", text="Hola", at=datetime(2026, 1, 2, 2, 59, tzinfo=timezone.utc))
        ],
    )


def test_concurrent_advisors_create_a_single_case(env):
    """R20: dos asesores a la vez dejan un único caso y solo uno gana."""
    requests = [
        _request_body("contact-1", "case-a", "111"),
        _request_body("contact-1", "case-b", "222"),
    ]

    def attempt(req):
        try:
            return take_case(req, env.settings, env.adapters)
        except CaseChanged:
            return "case_changed"

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(attempt, requests))

    assert sum(1 for result in results if result == "case_changed") == 1
    assert len(env.repo.cases) == 1
    case = next(iter(env.repo.cases.values()))
    assert case.status == "assigned"
    assert case.advisor_id in ("111", "222")


def test_concurrent_same_advisor_creates_one_case(env):
    """R22: dos tomas del mismo asesor no duplican el caso."""
    requests = [
        _request_body("contact-1", "case-a", "111"),
        _request_body("contact-1", "case-b", "111"),
    ]

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda req: take_case(req, env.settings, env.adapters), requests))

    assert len(env.repo.cases) == 1
    assert sorted(result.created for result in results) == [False, True]
    assert len({result.case_id for result in results}) == 1


def test_overview_lists_only_unclosed_cases_without_actions(env):
    """R39: overview devuelve los casos no cerrados con actions vacías."""
    env.add_case(
        "case-open",
        status="open",
        contact_id="contact-open",
        created_at=env.clock.now,
    )
    env.add_case(
        "case-assigned",
        status="assigned",
        contact_id="contact-assigned",
        advisor_id="111",
        created_at=env.clock.now + timedelta(minutes=1),
    )
    env.add_case(
        "case-closed",
        status="closed",
        contact_id="contact-closed",
        created_at=env.clock.now + timedelta(minutes=2),
    )

    response = env.client.get(
        "/cases",
        params={"advisor_id": "111", "scope": "overview"},
        headers=HEADERS,
    )

    assert response.status_code == 200
    listed = CaseListResponse.model_validate(response.json())
    assert [item.case_id for item in listed.root] == ["case-open", "case-assigned"]
    assert all(item.actions == [] for item in listed.root)
    assert listed.root[1].advisor_id == "111"


def test_overview_for_unregistered_advisor_is_empty(env):
    """R39: un perfil fuera del roster no ve casos."""
    env.add_case("case-open", status="open")

    response = env.client.get(
        "/cases",
        params={"advisor_id": "999", "scope": "overview"},
        headers=HEADERS,
    )

    assert response.status_code == 200
    assert CaseListResponse.model_validate(response.json()).root == []
