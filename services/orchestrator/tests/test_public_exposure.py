"""Pruebas de exposición pública del orchestrator (#24 R29-R32)."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from starlette.requests import Request

from orchestrator.adapters.db_query import FakeDbQuery
from orchestrator.adapters.gateway import FakeGatewayClient
from orchestrator.adapters.handover import FakeHandoverClient
from orchestrator.adapters.llm import FakeLLM
from orchestrator.adapters.rag import FakeRagClient
from orchestrator.adapters.repository import FakeRepository
from orchestrator.admin_routes import client_ip
from orchestrator.config import Settings
from orchestrator.domain import Adapters
from orchestrator.main import create_app

SERVICE_TOKEN = "svc-token"
PASSWORD = "clave-segura-123"
FIXED_NOW = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
INTERNAL_HEADERS = {"X-Service-Token": SERVICE_TOKEN}

INTERNAL_REQUESTS = [
    (
        "/messages",
        {
            "update_id": 1,
            "telegram_user_id": 10,
            "chat_id": 100,
            "text": "hola",
            "received_at": "2026-01-02T03:04:00+00:00",
        },
    ),
    ("/profiles", {"username": "admin1", "role": "admin", "password": PASSWORD}),
    ("/profiles/profile-1/link-token", None),
    ("/cases/case-1/reply", {"advisor_id": "555", "text": "hola"}),
]


def _snapshot(env) -> tuple:
    return (
        dict(env.repo.contacts),
        list(env.repo.messages),
        list(env.repo.events),
        set(env.repo.processed),
        dict(env.repo.case_links),
        dict(env.repo.profiles),
        dict(env.repo.sessions),
        list(env.repo.login_failures),
        list(env.gateway.sent),
    )


@pytest.mark.parametrize(("path", "body"), INTERNAL_REQUESTS)
@pytest.mark.parametrize("headers", [{}, {"X-Service-Token": "otro"}])
def test_r29_internal_routes_require_valid_service_token(env, path, body, headers):
    """R29: sin token válido las rutas internas responden 401 sin efectos."""
    before = _snapshot(env)
    response = env.client.post(path, json=body, headers=headers)
    assert response.status_code == 401
    assert response.json()["error"] == "unauthorized"
    assert _snapshot(env) == before


def test_r29_health_stays_public(env):
    """R29: /health no exige token aunque el orchestrator sea público."""
    response = env.client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "orchestrator"}


@dataclass
class AdminEnv:
    client: TestClient
    repo: FakeRepository
    settings: Settings
    clock: list[datetime] = field(default_factory=lambda: [FIXED_NOW])


@pytest.fixture()
def admin_env() -> AdminEnv:
    settings = Settings(
        service_token=SERVICE_TOKEN,
        password_hash_iterations=100000,
        admin_cookie_secure=False,
        admin_session_ttl_minutes=60,
        admin_events_limit=50,
        admin_login_max_attempts=3,
        admin_login_window_minutes=15,
        admin_trust_proxy_headers=False,
        telegram_bot_username="LazaroBot",
    )
    clock = [FIXED_NOW]
    repo = FakeRepository()
    adapters = Adapters(
        repository=repo,
        rag=FakeRagClient(),
        llm=FakeLLM(reply=""),
        gateway=FakeGatewayClient(),
        handover=FakeHandoverClient(),
        db_query=FakeDbQuery(),
        clock=lambda: clock[0],
        new_id=lambda: "generated-id",
    )
    client = TestClient(create_app(settings, adapters))
    return AdminEnv(client=client, repo=repo, settings=settings, clock=clock)


def _create_profile(env: AdminEnv, username: str = "admin1") -> dict:
    response = env.client.post(
        "/profiles",
        json={"username": username, "role": "admin", "password": PASSWORD},
        headers=INTERNAL_HEADERS,
    )
    assert response.status_code == 201, response.text
    return response.json()


def _login(env: AdminEnv, username: str, password: str, headers: dict | None = None):
    return env.client.post(
        "/admin/login",
        data={"username": username, "password": password},
        headers=headers or {},
        follow_redirects=False,
    )


@pytest.mark.parametrize("path", ["/admin", "/admin/profiles"])
def test_r31_admin_requires_session_even_with_service_token(admin_env, path):
    """R31: /admin sin sesión redirige a login aunque traiga X-Service-Token válido."""
    response = admin_env.client.get(
        path, headers=INTERNAL_HEADERS, follow_redirects=False
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/admin/login"


@pytest.mark.parametrize("csrf_token", [None, "", "incorrecto"])
def test_r31_admin_post_requires_valid_csrf(admin_env, csrf_token):
    """R31: un POST del panel con sesión y sin csrf válido responde 403."""
    _create_profile(admin_env)
    assert _login(admin_env, "admin1", PASSWORD).status_code == 303

    form = {"username": "otro", "role": "asesor", "password": PASSWORD}
    if csrf_token is not None:
        form["csrf_token"] = csrf_token
    response = admin_env.client.post(
        "/admin/profiles", data=form, follow_redirects=False
    )
    assert response.status_code == 403
    assert len(admin_env.repo.profiles) == 1


def test_r31_admin_login_is_not_opened_by_service_token(admin_env):
    """R31: /admin/login sigue siendo la entrada del panel, no una ruta interna."""
    response = admin_env.client.get("/admin/login", headers=INTERNAL_HEADERS)
    assert response.status_code == 200


def _request(headers: dict[str, str] | None = None) -> Request:
    raw_headers = [
        (key.lower().encode(), value.encode()) for key, value in (headers or {}).items()
    ]
    return Request(
        {"type": "http", "headers": raw_headers, "client": ("testclient", 12345)}
    )


def test_r32_uses_first_forwarded_value_never_the_proxy_terminal():
    """R32: se usa el primer valor de X-Forwarded-For, no el salto del proxy."""
    settings = Settings(admin_trust_proxy_headers=True)
    ip = client_ip(_request({"X-Forwarded-For": "1.2.3.4, 10.0.0.1"}), settings)
    assert ip == "1.2.3.4"
    assert ip != "10.0.0.1"


def test_r32_first_forwarded_value_is_stripped():
    """R32: los espacios alrededor del primer valor se eliminan."""
    settings = Settings(admin_trust_proxy_headers=True)
    assert client_ip(_request({"X-Forwarded-For": " 1.2.3.4 "}), settings) == "1.2.3.4"


@pytest.mark.parametrize("header", [None, "", " ", ", 10.0.0.1"])
def test_r32_falls_back_to_connection_ip(header):
    """R32: cabecera ausente o primer valor vacío -> IP de la conexión."""
    settings = Settings(admin_trust_proxy_headers=True)
    headers = {} if header is None else {"X-Forwarded-For": header}
    assert client_ip(_request(headers), settings) == "testclient"


def test_r32_same_proxy_terminal_from_different_clients_does_not_block(admin_env):
    """R32: 5 fallos de IPs distintas con el mismo valor terminal no bloquean al sexto."""
    admin_env.settings.admin_trust_proxy_headers = True
    _create_profile(admin_env)

    for index in range(5):
        response = _login(
            admin_env,
            f"usuario{index}",
            "mala",
            headers={"X-Forwarded-For": f"10.0.0.{index + 1}, 10.9.9.9"},
        )
        assert response.status_code == 401

    assert [failure.ip for failure in admin_env.repo.login_failures] == [
        f"10.0.0.{index + 1}" for index in range(5)
    ]
    allowed = _login(
        admin_env,
        "admin1",
        PASSWORD,
        headers={"X-Forwarded-For": "192.0.2.50, 10.9.9.9"},
    )
    assert allowed.status_code == 303


def test_r31_admin_route_blocks_before_internal_token_check(admin_env):
    """R31: el token de servicio no sustituye la sesión del panel en POST."""
    response = admin_env.client.post(
        "/admin/profiles",
        data={"username": "otro", "role": "asesor", "password": PASSWORD},
        headers=INTERNAL_HEADERS,
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert admin_env.repo.profiles == {}
