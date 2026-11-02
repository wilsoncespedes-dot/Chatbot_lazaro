"""Tests de GET /cases (feature #33 contrato_listar_casos_asesor)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from lazaro_contracts import CaseListResponse, ErrorResponse, LastMessage

from handover.adapters.repository import FakeCaseRepository
from handover.domain import can_act_on_case

HEADERS = {"X-Service-Token": "svc-token"}
START = datetime(2026, 1, 2, 3, 0, 0, tzinfo=timezone.utc)
FIELDS = {"case_id", "status", "created_at", "actions"}


def _get(env, advisor_id: str = "111", headers: dict | None = None):
    return env.client.get(
        "/cases",
        params={"advisor_id": advisor_id},
        headers=HEADERS if headers is None else headers,
    )


def _assert_error(response, status: int, code: str) -> None:
    assert response.status_code == status
    ErrorResponse.model_validate(response.json())
    assert response.json()["error"] == code


class _CountingRepository(FakeCaseRepository):
    def __init__(self) -> None:
        super().__init__()
        self.list_calls = 0

    def list_cases_for_advisor(
        self, advisor_id: str, registered_ids: list[str], limit: int
    ):
        self.list_calls += 1
        return super().list_cases_for_advisor(advisor_id, registered_ids, limit)


class _LeakyRepository(FakeCaseRepository):
    """Devuelve todos los casos para probar el descarte defensivo del dominio."""

    def list_cases_for_advisor(
        self, advisor_id: str, registered_ids: list[str], limit: int
    ):
        cases = sorted(self.cases.values(), key=lambda case: (case.created_at, case.case_id))
        return [case.model_copy(deep=True) for case in cases[:limit]]


class _BrokenRepository(FakeCaseRepository):
    def list_cases_for_advisor(
        self, advisor_id: str, registered_ids: list[str], limit: int
    ):
        raise RuntimeError("secreto-interno")


# --- R8: token -----------------------------------------------------------------------------


@pytest.mark.parametrize("headers", [{}, {"X-Service-Token": "otro"}])
def test_get_cases_without_valid_token_returns_401(env, headers):
    """R8: sin X-Service-Token válido GET /cases responde 401 unauthorized."""
    env.add_case("case-1", status="open")
    _assert_error(_get(env, headers=headers), 401, "unauthorized")
    assert env.repo.denials == []
    assert env.repo.notifications == []
    assert env.gateway.sent == []


# --- R9: validación de la query ------------------------------------------------------------


@pytest.mark.parametrize(
    "params",
    [
        {},
        {"advisor_id": ""},
        {"advisor_id": "x" * 65},
        {"advisor_id": "111", "otro": "1"},
    ],
)
def test_get_cases_rejects_invalid_query_with_422(env, params):
    """R9: falta advisor_id, vacío, más de 64 o parámetro extra -> 422 validation_error."""
    env.add_case("case-1", status="open")
    response = env.client.get("/cases", params=params, headers=HEADERS)
    _assert_error(response, 422, "validation_error")
    assert env.repo.cases["case-1"].status == "open"
    assert env.repo.denials == []


# --- R10: asesor no registrado -------------------------------------------------------------


def test_unregistered_advisor_gets_empty_list_without_querying(env_factory):
    """R10: un advisor_id fuera de ADVISOR_CHAT_IDS recibe 200 [] sin consultar el repo."""
    repo = _CountingRepository()
    env = env_factory(repo=repo)
    env.add_case("case-open", status="open")
    env.add_case("case-assigned", status="assigned", advisor_id="999")
    response = _get(env, advisor_id="999")
    assert response.status_code == 200
    assert response.json() == []
    assert repo.list_calls == 0
    assert env.repo.denials == []


# --- R11-R14: reglas de inclusión y actions ------------------------------------------------


def test_open_and_timed_out_cases_offer_reply_assign_and_close(env):
    """R11: open y timed_out se listan con actions reply, assign y close."""
    env.add_case("case-open", status="open")
    env.add_case("case-timeout", status="timed_out")
    response = _get(env)
    assert response.status_code == 200
    body = CaseListResponse.model_validate(response.json())
    actions = {item.case_id: item.actions for item in body.root}
    assert actions == {
        "case-open": ["reply", "assign", "close"],
        "case-timeout": ["reply", "assign", "close"],
    }


def test_case_assigned_to_requester_offers_reply_and_close(env):
    """R12: un caso assigned al solicitante se lista con actions reply y close."""
    env.add_case("case-own", status="assigned", advisor_id="111")
    response = _get(env, advisor_id="111")
    body = CaseListResponse.model_validate(response.json())
    assert len(body.root) == 1
    item = body.root[0]
    assert (item.case_id, item.status, item.created_at, item.actions) == (
        "case-own",
        "assigned",
        START,
        ["reply", "close"],
    )


def test_orphan_cases_offer_only_close(env):
    """R13: un caso huérfano (advisor_id nulo o retirado) se lista solo con close."""
    env.add_case("case-null", status="assigned", advisor_id=None)
    env.add_case("case-retired", status="assigned", advisor_id="999")
    response = _get(env, advisor_id="111")
    actions = {item["case_id"]: item["actions"] for item in response.json()}
    assert actions == {
        "case-null": ["close"],
        "case-retired": ["close"],
    }


def test_closed_and_assigned_to_another_registered_advisor_are_excluded(env):
    """R14: no se listan casos closed ni assigned a otro asesor registrado."""
    env.add_case("case-own", status="assigned", advisor_id="111")
    env.add_case("case-closed", status="closed", closed_by="111", closed_at=START)
    env.add_case("case-other", status="assigned", advisor_id="222")
    response = _get(env, advisor_id="111")
    assert [item["case_id"] for item in response.json()] == ["case-own"]


def test_actions_match_can_act_on_case_and_discard_other_cases(env_factory):
    """R11-R14: actions == can_act_on_case (salvo assign en assigned); descarta el resto."""
    repo = _LeakyRepository()
    env = env_factory(repo=repo)
    visible = [
        env.add_case("case-open", status="open"),
        env.add_case("case-timeout", status="timed_out"),
        env.add_case("case-own", status="assigned", advisor_id="111"),
        env.add_case("case-null", status="assigned", advisor_id=None),
        env.add_case("case-retired", status="assigned", advisor_id="999"),
    ]
    env.add_case("case-closed", status="closed", closed_by="111", closed_at=START)
    env.add_case("case-other", status="assigned", advisor_id="222")

    response = _get(env, advisor_id="111")
    body = CaseListResponse.model_validate(response.json())
    listed = {item.case_id: item.actions for item in body.root}
    assert set(listed) == {case.case_id for case in visible}

    for case in visible:
        expected = [
            action
            for action in ("reply", "assign", "close")
            if can_act_on_case(case, "111", action, env.settings)
            and not (action == "assign" and case.status == "assigned")
        ]
        assert listed[case.case_id] == expected


# --- R15-R16: orden y límite ---------------------------------------------------------------


def test_cases_are_ordered_by_created_at_then_case_id(env):
    """R15: orden ascendente por created_at y desempate ascendente por case_id."""
    env.add_case("case-b", status="open", created_at=START + timedelta(seconds=10))
    env.add_case("case-a", status="open", created_at=START + timedelta(seconds=10))
    env.add_case("case-0", status="open", created_at=START)
    response = _get(env)
    assert [item["case_id"] for item in response.json()] == ["case-0", "case-a", "case-b"]


def test_limit_applies_after_filtering(env_factory):
    """R16: CASE_LIST_LIMIT se aplica después de filtrar y deja fuera casos ajenos."""
    env = env_factory(settings_overrides={"case_list_limit": 2})
    env.add_case("foreign-old", status="assigned", advisor_id="222", created_at=START)
    env.add_case("closed-old", status="closed", created_at=START + timedelta(seconds=1),
                 closed_by="111", closed_at=START)
    env.add_case("visible-1", status="open", created_at=START + timedelta(seconds=2))
    env.add_case("visible-2", status="timed_out", created_at=START + timedelta(seconds=3))
    env.add_case("visible-3", status="open", created_at=START + timedelta(seconds=4))
    response = _get(env)
    assert [item["case_id"] for item in response.json()] == ["visible-1", "visible-2"]


def test_default_limit_is_50(env_factory, monkeypatch):
    """R22: sin CASE_LIST_LIMIT en el entorno se devuelven como máximo 50 casos."""
    monkeypatch.delenv("CASE_LIST_LIMIT", raising=False)
    env = env_factory()
    for index in range(51):
        env.add_case(f"case-{index:02d}", status="open",
                     created_at=START + timedelta(seconds=index))
    assert env.settings.case_list_limit == 50
    response = _get(env)
    assert len(response.json()) == 50
    assert [item["case_id"] for item in response.json()][:2] == ["case-00", "case-01"]
    assert "case-50" not in {item["case_id"] for item in response.json()}


# --- R18-R20: forma de la respuesta y efectos ----------------------------------------------


def test_response_only_exposes_the_four_contract_fields(env):
    """R18: cada elemento solo tiene case_id, status, created_at y actions, sin datos."""
    case = env.add_case(
        "case-1",
        status="open",
        chat_id=987654321,
        contact_id="contact-secreto",
    )
    env.repo.cases["case-1"] = case.model_copy(
        update={
            "reason": "user_request",
            "last_messages": [LastMessage(role="user", text="TEXTO-CLIENTE", at=START)],
        }
    )
    response = _get(env)
    assert response.status_code == 200
    body = CaseListResponse.model_validate(response.json())
    for item in response.json():
        assert set(item) == FIELDS
    assert body.root[0].case_id == "case-1"
    for secret in ("contact-secreto", "987654321", "TEXTO-CLIENTE", "user_request"):
        assert secret not in response.text


def test_listing_does_not_modify_cases_or_record_denials(env):
    """R19: GET /cases no modifica casos, denegaciones ni notificaciones."""
    env.add_case("case-open", status="open")
    env.add_case("case-own", status="assigned", advisor_id="111")
    env.add_case("case-other", status="assigned", advisor_id="222")
    before = {key: value.model_copy(deep=True) for key, value in env.repo.cases.items()}
    before_requests = [record.model_copy(deep=True) for record in env.repo.requests]

    assert _get(env, advisor_id="111").status_code == 200
    assert _get(env, advisor_id="999").status_code == 200

    assert env.repo.cases == before
    assert env.repo.requests == before_requests
    assert env.repo.denials == []
    assert env.repo.notifications == []
    assert env.gateway.sent == []


def test_repository_failure_returns_500_internal_error_without_details(env_factory):
    """R20: un fallo inesperado del repositorio responde 500 internal_error sin stack trace."""
    env = env_factory(repo=_BrokenRepository())
    client = TestClient(env.client.app, raise_server_exceptions=False)
    response = client.get("/cases", params={"advisor_id": "111"}, headers=HEADERS)
    _assert_error(response, 500, "internal_error")
    assert "secreto-interno" not in response.text
    assert "Traceback" not in response.text
