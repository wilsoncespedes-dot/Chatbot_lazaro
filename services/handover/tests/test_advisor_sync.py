"""Sincronización del roster de asesores y generación compartida (#48)."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from lazaro_contracts import AdvisorRosterSyncResponse

SERVICE_TOKEN = "svc-token"
HEADERS = {"X-Service-Token": SERVICE_TOKEN}
GENERATION_HEADER = "X-Advisor-Roster-Generation"


def _sync(env, generation: int = 2, profiles=None, headers=None):
    return env.client.post(
        "/advisors/sync",
        json={
            "generation": generation,
            "profiles": profiles
            if profiles is not None
            else [{"profile_id": "perfil-1", "role": "asesor"}],
        },
        headers=HEADERS if headers is None else headers,
    )


@pytest.mark.parametrize("headers", [{}, {"X-Service-Token": "malo"}])
def test_sync_requires_valid_service_token(env, headers):
    """R10: sin token válido /advisors/sync responde 401 unauthorized."""
    response = env.client.post(
        "/advisors/sync",
        json={"generation": 1, "profiles": []},
        headers=headers,
    )
    assert response.status_code == 401
    assert response.json()["error"] == "unauthorized"
    assert env.repo.get_roster_generation() == 1


@pytest.mark.parametrize(
    "body",
    [
        {"profiles": []},
        {"generation": -1, "profiles": []},
        {"generation": 2, "profiles": [{"profile_id": "p1", "role": "admin"}]},
        {"generation": 2, "profiles": [{"role": "asesor"}]},
    ],
)
def test_sync_rejects_invalid_request(env, body):
    """R11: un cuerpo que no valida contra AdvisorRosterSyncRequest da 422."""
    response = env.client.post("/advisors/sync", json=body, headers=HEADERS)
    assert response.status_code == 422
    assert response.json()["error"] == "validation_error"
    assert env.repo.get_roster_generation() == 1


def test_sync_persists_roster_and_generation(env):
    """R9, R12, R49: reemplaza el roster y responde con la generación aplicada."""
    response = _sync(
        env,
        generation=2,
        profiles=[
            {"profile_id": "perfil-1", "role": "asesor"},
            {"profile_id": "perfil-2", "role": "otro"},
        ],
    )

    assert response.status_code == 200
    body = AdvisorRosterSyncResponse.model_validate(response.json())
    assert (body.status, body.generation, body.advisors, body.orphaned_cases) == (
        "synced",
        2,
        1,
        0,
    )
    assert env.repo.get_roster() == {"perfil-1": None}
    assert env.repo.get_roster_generation() == 2


def test_sync_persistence_failure_returns_500(env):
    """R12, R49: si falla la persistencia responde 500 internal_error."""

    def boom(*args, **kwargs):
        raise RuntimeError("fallo de persistencia")

    env.repo.replace_roster = boom
    client = TestClient(env.client.app, raise_server_exceptions=False)
    response = client.post(
        "/advisors/sync",
        json={"generation": 2, "profiles": [{"profile_id": "p1", "role": "asesor"}]},
        headers=HEADERS,
    )

    assert response.status_code == 500
    assert response.json()["error"] == "internal_error"


def test_sync_migrates_telegram_assignment_to_profile_id(env):
    """R30: un advisor_id igual a telegram_user_id pasa a ser el profile_id."""
    env.add_case("case-1", status="assigned", advisor_id="111")

    response = _sync(
        env,
        generation=2,
        profiles=[
            {"profile_id": "perfil-1", "role": "asesor", "telegram_user_id": 111}
        ],
    )

    assert response.status_code == 200
    case = env.repo.cases["case-1"]
    assert case.status == "assigned"
    assert case.advisor_id == "perfil-1"
    assert response.json()["orphaned_cases"] == 0


def test_sync_marks_unknown_assignment_as_orphan(env):
    """R31: un assigned sin coincidencia conserva el estado y queda huérfano."""
    env.add_case("case-1", status="assigned", advisor_id="999")

    response = _sync(
        env,
        generation=2,
        profiles=[
            {"profile_id": "perfil-1", "role": "asesor", "telegram_user_id": 111}
        ],
    )

    case = env.repo.cases["case-1"]
    assert response.json()["orphaned_cases"] == 1
    assert case.status == "assigned"
    assert case.advisor_id is None


def test_sync_preserves_case_identity_and_timestamps(env):
    """R32: la migración conserva identificadores, contactos, motivos y fechas."""
    env.add_case(
        "case-1",
        status="assigned",
        advisor_id="111",
        chat_id=901,
        contact_id="contact-9",
    )
    before = env.repo.cases["case-1"].model_copy(deep=True)

    _sync(
        env,
        generation=2,
        profiles=[
            {"profile_id": "perfil-1", "role": "asesor", "telegram_user_id": 111}
        ],
    )

    after = env.repo.cases["case-1"]
    assert after.case_id == before.case_id
    assert after.contact_id == before.contact_id
    assert after.chat_id == before.chat_id
    assert after.reason == before.reason
    assert after.created_at == before.created_at
    assert after.last_messages == before.last_messages


def test_repeated_sync_does_not_reinterpret_profile_ids(env):
    """R33: repetir la sincronización deja el mismo resultado."""
    env.add_case("case-1", status="assigned", advisor_id="111")
    profiles = [
        {"profile_id": "perfil-1", "role": "asesor", "telegram_user_id": 111}
    ]

    _sync(env, generation=2, profiles=profiles)
    assert env.repo.cases["case-1"].advisor_id == "perfil-1"

    _sync(env, generation=2, profiles=profiles)
    assert env.repo.cases["case-1"].advisor_id == "perfil-1"


def test_stale_generation_is_rejected_with_503(env):
    """R36: una generación distinta de la sincronizada responde 503."""
    response = env.handover(
        headers={**HEADERS, GENERATION_HEADER: "0"}
    )

    assert response.status_code == 503
    assert response.json()["error"] == "roster_out_of_sync"
    assert env.repo.cases == {}


def test_handover_with_current_generation_succeeds(env):
    """R36: la generación vigente permite crear el caso y responder queued."""
    response = env.handover(
        headers={**HEADERS, GENERATION_HEADER: str(env.repo.get_roster_generation())}
    )

    assert response.status_code == 200
    assert response.json() == {"status": "queued", "case_id": "case-1"}


def test_list_cases_with_stale_generation_is_rejected(env):
    """R36: GET /cases también exige la generación vigente."""
    env.add_case("case-1", status="open")

    response = env.client.get(
        "/cases",
        params={"advisor_id": "111"},
        headers={**HEADERS, GENERATION_HEADER: "99"},
    )

    assert response.status_code == 503
    assert response.json()["error"] == "roster_out_of_sync"
