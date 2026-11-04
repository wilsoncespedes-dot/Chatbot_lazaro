"""Ruta del panel de asesor para consultar memoria del cliente (#40)."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from orchestrator.accounts import hash_token
from orchestrator.adapters.db_query import FakeDbQuery
from orchestrator.adapters.gateway import FakeGatewayClient
from orchestrator.adapters.handover import FakeHandoverClient
from orchestrator.adapters.llm import FakeLLM
from orchestrator.adapters.rag import FakeRagClient
from orchestrator.adapters.repository import FakeRepository
from orchestrator.config import Settings
from orchestrator.domain import Adapters
from orchestrator.main import create_app

SERVICE_TOKEN = "svc-token-memoria"
FIXED_NOW = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
ADVISOR_SESSION = "advisor_session"
CSRF = "csrf-token"


@dataclass
class Env:
    client: TestClient
    repo: FakeRepository
    handover: FakeHandoverClient
    settings: Settings
    adapters: Adapters


def _make_env(**overrides) -> Env:
    values = {
        "service_token": SERVICE_TOKEN,
        "admin_cookie_secure": False,
        "password_hash_iterations": 100000,
    }
    values.update(overrides)
    settings = Settings(**values)
    repo = FakeRepository()
    handover = FakeHandoverClient()
    adapters = Adapters(
        repository=repo,
        rag=FakeRagClient(),
        llm=FakeLLM(reply=""),
        gateway=FakeGatewayClient(),
        handover=handover,
        db_query=FakeDbQuery(),
        clock=lambda: FIXED_NOW,
        new_id=lambda: "generated",
    )
    client = TestClient(create_app(settings, adapters))
    return Env(client, repo, handover, settings, adapters)


@pytest.fixture()
def env() -> Env:
    return _make_env()


def _login(env: Env, telegram_user_id: int | None = 700) -> None:
    profile = env.repo.create_profile("asesor1", "asesor", "hash", FIXED_NOW)
    env.repo.profiles[profile.id].telegram_user_id = telegram_user_id
    env.repo.create_session(
        hash_token("session-token"),
        profile.id,
        CSRF,
        FIXED_NOW + timedelta(minutes=60),
    )
    env.client.cookies.set(ADVISOR_SESSION, "session-token")


def _link_case(
    env: Env,
    case_id: str = "case-1",
    profile_id: str | None = "p1",
    user: int = 10,
    chat: int = 100,
):
    contact = env.repo.get_or_create_contact(user, chat, FIXED_NOW)
    env.repo.link_case(case_id, contact.id, FIXED_NOW, profile_id=profile_id)
    return contact


def _seed(env: Env) -> None:
    env.repo.set_client_memory("p1", ("Prefiere correo",), "s1", FIXED_NOW)
    env.repo.upsert_conversation_summary(
        "s1", "p1", "c1", "telegram", "Resumen visible de p1", "session_end", FIXED_NOW
    )
    env.repo.set_client_memory("p2", ("DATO-DE-OTRO-CLIENTE",), "s2", FIXED_NOW)
    env.repo.upsert_conversation_summary(
        "s2", "p2", "c2", "whatsapp", "RESUMEN-DE-OTRO-CLIENTE", "session_end", FIXED_NOW
    )


def test_r27_memory_route_requires_a_session(env):
    """R27: sin sesión de asesor redirige al login."""
    response = env.client.get("/asesor/cases/case-1/memoria", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/asesor/login"


def test_r27_unlinked_profile_is_403_without_authorizing(env):
    """R27: un asesor sin Telegram vinculado no llega a consultar memoria."""
    _login(env, telegram_user_id=None)
    response = env.client.get("/asesor/cases/case-1/memoria")

    assert response.status_code == 403
    assert "telegram_not_linked" in response.text
    assert env.handover.authorized == []


def test_r27_invalid_case_id_is_422(env):
    """R27: un `case_id` que no cumple `Identifier` responde 422."""
    _login(env)
    response = env.client.get("/asesor/cases/" + "x" * 65 + "/memoria")

    assert response.status_code == 422
    assert 'data-code="validation_error"' in response.text
    assert env.handover.authorized == []


@pytest.mark.parametrize(
    ("attribute", "value", "status", "code"),
    [
        ("authorize_error", "forbidden", 403, "forbidden"),
        ("authorize_error", "case_closed", 409, "case_closed"),
        ("authorize_error", "not_found", 404, "not_found"),
        ("fail_authorize", True, 502, "upstream_error"),
    ],
)
def test_r28_r29_r55_r56_denials_do_not_read_memory(
    env, monkeypatch, attribute, value, status, code
):
    """R28, R29, R55, R56: cada rechazo devuelve su página sin leer memoria."""
    _login(env)
    _link_case(env)
    setattr(env.handover, attribute, value)

    def boom(*args, **kwargs):
        raise AssertionError("no debe leer memoria")

    monkeypatch.setattr(env.repo, "get_client_memory", boom)
    response = env.client.get("/asesor/cases/case-1/memoria")

    assert response.status_code == status
    assert f'data-code="{code}"' in response.text


def test_r27_authorize_is_called_before_reading_memory(env, monkeypatch):
    """R27: handover autoriza con `reply` antes de cualquier lectura de memoria."""
    _login(env)
    _link_case(env)
    _seed(env)
    original = env.repo.get_client_memory
    calls: list[str] = []

    def spy(profile_id: str):
        assert env.handover.authorized == [("case-1", "700", "reply")]
        calls.append(profile_id)
        return original(profile_id)

    monkeypatch.setattr(env.repo, "get_client_memory", spy)
    response = env.client.get("/asesor/cases/case-1/memoria")

    assert response.status_code == 200
    assert calls == ["p1"]


def test_r28_forbidden_records_the_event(env):
    """R28: un 403 deja `advisor_forbidden` en el contacto del caso."""
    _login(env)
    contact = _link_case(env)
    env.handover.authorize_error = "forbidden"

    response = env.client.get("/asesor/cases/case-1/memoria")

    assert response.status_code == 403
    event = env.repo.events[-1]
    assert (event.contact_id, event.type) == (contact.id, "advisor_forbidden")
    assert "case:case-1" in event.reason
    assert "advisor:700" in event.reason


def test_r30_r32_r33_r34_page_shows_only_the_case_client_and_escapes(env):
    """R30, R33, R34: memoria y resúmenes del cliente del caso, escapados y auditados."""
    _login(env)
    contact = _link_case(env)
    _seed(env)
    env.repo.set_client_memory(
        "p1", ("Prefiere <script>alert(1)</script>",), "s1", FIXED_NOW
    )

    response = env.client.get("/asesor/cases/case-1/memoria")

    assert response.status_code == 200
    assert "Prefiere &lt;script&gt;alert(1)&lt;/script&gt;" in response.text
    assert "<script>" not in response.text.lower()
    assert "Resumen visible de p1" in response.text
    assert "DATO-DE-OTRO-CLIENTE" not in response.text
    assert "RESUMEN-DE-OTRO-CLIENTE" not in response.text
    event = env.repo.events[-1]
    assert (event.contact_id, event.type) == (contact.id, "memory_viewed")
    assert event.reason == "case:case-1 advisor:700"


def test_r32_case_without_authenticated_client_shows_only_the_notice(env):
    """R32: sin `profile_id` en el vínculo se indica «Sin cliente autenticado»."""
    _login(env)
    _link_case(env, profile_id=None)
    _seed(env)

    response = env.client.get("/asesor/cases/case-1/memoria")

    assert response.status_code == 200
    assert "Sin cliente autenticado" in response.text
    assert "Prefiere correo" not in response.text
    assert "Resumen visible de p1" not in response.text
    assert env.repo.events == []


def test_cases_page_links_to_each_case_memory(env):
    """R30: la lista de casos enlaza a la memoria de cada caso."""
    _login(env)
    from lazaro_contracts import CaseListItem

    env.handover.case_list = [
        CaseListItem(
            case_id="case-1",
            status="open",
            created_at=FIXED_NOW,
            actions=["reply", "close"],
        )
    ]

    response = env.client.get("/asesor/cases")

    assert response.status_code == 200
    assert 'href="/asesor/cases/case-1/memoria"' in response.text
