"""Tests del panel de asesores (#29 panel_asesores)."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from fastapi.testclient import TestClient
from lazaro_contracts import CaseListItem

from orchestrator.adapters.db_query import FakeDbQuery
from orchestrator.adapters.gateway import FakeGatewayClient
from orchestrator.adapters.handover import FakeHandoverClient, HttpHandoverClient
from orchestrator.adapters.llm import FakeLLM
from orchestrator.adapters.rag import FakeRagClient
from orchestrator.adapters.repository import FakeRepository
from orchestrator.accounts import hash_token
from orchestrator.config import Settings
from orchestrator.domain import (
    Adapters,
    AuthorizationDenied,
    ServiceUnavailable,
)
from orchestrator.main import create_app

SERVICE_TOKEN = "svc-token-asesor"
PASSWORD = "clave-segura-123"
FIXED_NOW = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
CSRF_RE = re.compile(r'name="csrf_token" value="([^"]+)"')
INTERNAL_HEADERS = {"X-Service-Token": SERVICE_TOKEN}
LOGIN_ERROR = "Usuario o contraseña incorrectos."


@dataclass
class Env:
    client: TestClient
    repo: FakeRepository
    settings: Settings
    adapters: Adapters
    handover: FakeHandoverClient
    gateway: FakeGatewayClient
    clock: list[datetime] = field(default_factory=lambda: [FIXED_NOW])


def _make_env(**settings_overrides) -> Env:
    values = {
        "service_token": SERVICE_TOKEN,
        "password_hash_iterations": 100000,
        "admin_cookie_secure": False,
        "admin_session_ttl_minutes": 60,
        "admin_login_max_attempts": 10,
        "admin_login_window_minutes": 15,
        "admin_trust_proxy_headers": False,
    }
    values.update(settings_overrides)
    settings = Settings(**values)
    clock = [FIXED_NOW]
    repo = FakeRepository()
    handover = FakeHandoverClient()
    gateway = FakeGatewayClient()
    adapters = Adapters(
        repository=repo,
        rag=FakeRagClient(),
        llm=FakeLLM(reply=""),
        gateway=gateway,
        handover=handover,
        db_query=FakeDbQuery(),
        clock=lambda: clock[0],
        new_id=lambda: "generated-id",
    )
    client = TestClient(create_app(settings, adapters))
    return Env(
        client=client,
        repo=repo,
        settings=settings,
        adapters=adapters,
        handover=handover,
        gateway=gateway,
        clock=clock,
    )


@pytest.fixture()
def env() -> Env:
    return _make_env()


@pytest.fixture()
def env_factory():
    return _make_env


def _create_profile(
    env: Env,
    username: str = "asesor1",
    role: str = "asesor",
    password: str = PASSWORD,
    telegram_user_id: int | None = 700,
) -> dict:
    response = env.client.post(
        "/profiles",
        json={"username": username, "role": role, "password": password},
        headers=INTERNAL_HEADERS,
    )
    assert response.status_code == 201, response.text
    profile = response.json()
    if telegram_user_id is not None:
        env.repo.profiles[profile["id"]].telegram_user_id = telegram_user_id
    return profile


def _login(env: Env, username: str = "asesor1", password: str = PASSWORD):
    return env.client.post(
        "/asesor/login",
        data={"username": username, "password": password},
        follow_redirects=False,
    )


def _login_ok(env: Env, username: str = "asesor1", password: str = PASSWORD):
    response = _login(env, username, password)
    assert response.status_code == 303, response.text
    return response


def _login_admin(env: Env, username: str = "admin1", password: str = PASSWORD):
    return env.client.post(
        "/admin/login",
        data={"username": username, "password": password},
        follow_redirects=False,
    )


def _csrf(env: Env) -> str:
    response = env.client.get("/asesor")
    assert response.status_code == 200, response.text
    match = CSRF_RE.search(response.text)
    assert match is not None
    return match.group(1)


def _post(env: Env, path: str, data: dict):
    return env.client.post(path, data=data, follow_redirects=False)


def _session_token(response) -> str:
    token = response.cookies.get("advisor_session")
    assert token
    return token


def _link_case(env: Env, case_id: str = "case-1", user: int = 10, chat: int = 100):
    contact = env.repo.get_or_create_contact(user, chat, FIXED_NOW)
    env.repo.link_case(case_id, contact.id, FIXED_NOW)
    return contact


def _case_item(case_id: str = "case-1") -> CaseListItem:
    return CaseListItem(
        case_id=case_id,
        status="open",
        created_at=FIXED_NOW,
        actions=["reply", "assign", "close"],
    )


# --- R1: login y sesión ---------------------------------------------------------------


def test_login_creates_advisor_session_and_cookie_attributes(env):
    """R1: login asesor -> 303, sesión con TTL y cookie HttpOnly/SameSite/Path."""
    _create_profile(env)
    response = _login(env)

    assert response.status_code == 303
    assert response.headers["location"] == "/asesor"
    cookie = response.headers["set-cookie"].lower()
    assert "advisor_session=" in cookie
    assert "httponly" in cookie
    assert "samesite=strict" in cookie
    assert "path=/asesor" in cookie
    assert "max-age=3600" in cookie
    assert "; secure" not in cookie

    token = env.client.cookies.get("advisor_session")
    session = env.repo.sessions[hash_token(token)]
    assert session.expires_at == FIXED_NOW + timedelta(minutes=60)
    assert session.csrf_token


def test_login_uses_secure_cookie_when_configured(env):
    """R1: ADMIN_COOKIE_SECURE añade Secure a la cookie del asesor."""
    env.settings.admin_cookie_secure = True
    _create_profile(env)
    response = _login(env)
    assert "; secure" in response.headers["set-cookie"].lower()


# --- R2: credenciales y rol ------------------------------------------------------------


def test_login_rejects_unknown_wrong_password_admin_and_client_identically(env):
    """R2: usuario inexistente, clave mal, admin y cliente dan 401 idénticos."""
    _create_profile(env, "asesor1", "asesor")
    _create_profile(env, "admin1", "admin")
    _create_profile(env, "cliente1", "cliente")

    responses = [
        _login(env, "no-existe", PASSWORD),
        _login(env, "asesor1", "clave-incorrecta"),
        _login(env, "admin1", PASSWORD),
        _login(env, "cliente1", PASSWORD),
    ]

    assert [response.status_code for response in responses] == [401, 401, 401, 401]
    assert len({response.text for response in responses}) == 1
    assert LOGIN_ERROR in responses[0].text
    assert env.repo.sessions == {}
    for response in responses:
        assert "advisor_session=" not in response.headers.get("set-cookie", "")


# --- R3: límite de intentos compartido -------------------------------------------------


def test_login_throttle_is_shared_with_admin_login_by_username(env):
    """R3: los fallos de /admin/login cuentan para /asesor/login."""
    env.settings.admin_login_max_attempts = 2
    _create_profile(env)
    assert _login_admin(env, "asesor1", "mala").status_code == 401
    assert _login_admin(env, "asesor1", "mala").status_code == 401

    blocked = _login(env, "asesor1", PASSWORD)
    assert blocked.status_code == 429
    assert LOGIN_ERROR in blocked.text
    assert env.repo.sessions == {}


def test_login_throttle_is_shared_with_admin_login_by_ip(env):
    """R3: los fallos desde la misma IP en /admin/login cuentan para /asesor."""
    env.settings.admin_login_max_attempts = 2
    _create_profile(env)
    assert _login_admin(env, "usuario-a", "mala").status_code == 401
    assert _login_admin(env, "usuario-b", "mala").status_code == 401

    blocked = _login(env, "asesor1", PASSWORD)
    assert blocked.status_code == 429
    assert env.repo.sessions == {}


def test_throttled_advisor_login_does_not_verify_password(env, monkeypatch):
    """R3: el 429 se decide antes de llamar a verify_password."""
    env.settings.admin_login_max_attempts = 1
    _create_profile(env)
    assert _login_admin(env, "asesor1", "mala").status_code == 401

    calls: list[int] = []

    def spy(password: str, stored: str) -> bool:
        calls.append(1)
        return False

    monkeypatch.setattr("orchestrator.domain.verify_password", spy)
    response = _login(env, "asesor1", PASSWORD)
    assert response.status_code == 429
    assert calls == []


# --- R4: sesión obligatoria ------------------------------------------------------------


def test_advisor_routes_redirect_without_session(env):
    """R4: sin cookie o con cookie desconocida -> 303 a /asesor/login."""
    response = env.client.get("/asesor", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/asesor/login"

    env.client.cookies.set("advisor_session", "desconocida")
    response = env.client.get("/asesor/cases", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/asesor/login"


def test_expired_or_demoted_session_redirects_to_login(env):
    """R4: sesión expirada o perfil que dejó de ser asesor -> 303."""
    profile = _create_profile(env)
    _login_ok(env)
    env.clock[0] = FIXED_NOW + timedelta(minutes=61)
    response = env.client.get("/asesor", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/asesor/login"

    env.clock[0] = FIXED_NOW
    _login_ok(env)
    env.repo.profiles[profile["id"]].role = "cliente"
    response = env.client.get("/asesor", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/asesor/login"


def test_logout_closes_advisor_session(env):
    """R4: POST /asesor/logout cierra la sesión y deja de dar acceso."""
    _create_profile(env)
    _login_ok(env)
    csrf = _csrf(env)

    response = _post(env, "/asesor/logout", {"csrf_token": csrf})
    assert response.status_code == 303
    assert response.headers["location"] == "/asesor/login"
    assert env.repo.sessions == {}

    response = env.client.get("/asesor", follow_redirects=False)
    assert response.status_code == 303


# --- R5: paneles separados -------------------------------------------------------------


def test_admin_session_does_not_open_advisor_panel_and_vice_versa(env_factory):
    """R5: cada rol solo entra a su panel aunque se fuerce la cookie."""
    admin_env = env_factory()
    _create_profile(admin_env, "admin1", "admin")
    admin_login = _login_admin(admin_env)
    assert admin_login.status_code == 303
    admin_token = admin_login.cookies.get("admin_session")
    admin_env.client.cookies.set("advisor_session", admin_token)
    response = admin_env.client.get("/asesor", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/asesor/login"

    advisor_env = env_factory()
    _create_profile(advisor_env, "asesor1", "asesor")
    advisor_login = _login_ok(advisor_env, "asesor1")
    advisor_token = _session_token(advisor_login)
    advisor_env.client.cookies.set("admin_session", advisor_token)
    response = advisor_env.client.get("/admin", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/admin/login"


# --- R6: CSRF --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("path", "body"),
    [
        ("/asesor/reply", {"case_id": "case-1", "text": "hola"}),
        ("/asesor/assign", {"case_id": "case-1"}),
        ("/asesor/close", {"case_id": "case-1"}),
    ],
)
@pytest.mark.parametrize("csrf", [None, "incorrecto"])
def test_post_without_valid_csrf_is_forbidden_without_calls(env, path, body, csrf):
    """R6: csrf ausente o erróneo -> 403 sin llamar a handover ni al gateway."""
    _create_profile(env)
    _login_ok(env)
    data = dict(body)
    if csrf is not None:
        data["csrf_token"] = csrf

    response = _post(env, path, data)

    assert response.status_code == 403
    assert env.handover.authorized == []
    assert env.handover.try_assigned == []
    assert env.handover.closed == []
    assert env.gateway.sent == []


# --- R7 y R8: cabeceras y secretos -----------------------------------------------------


def test_advisor_html_has_csp_and_no_external_resources(env):
    """R7: CSP y cabeceras equivalentes a /admin, sin recursos externos."""
    expected = "default-src 'self'; form-action 'self'; frame-ancestors 'none'"
    _create_profile(env)
    _login_ok(env)
    csrf = _csrf(env)
    pages = [
        env.client.get("/asesor/login"),
        env.client.get("/asesor"),
        env.client.get("/asesor/cases"),
        _post(env, "/asesor/reply", {"csrf_token": csrf, "case_id": "case-1", "text": ""}),
    ]
    for response in pages:
        assert response.status_code in (200, 422)
        assert response.headers["content-security-policy"] == expected
        assert response.headers["x-content-type-options"] == "nosniff"
        assert response.headers["cache-control"] == "no-store"
        assert "<script" not in response.text.lower()
        for value in re.findall(r'(?:src|href)="([^"]*)"', response.text):
            assert not value.startswith(("http://", "https://", "//"))


def test_advisor_responses_never_include_secrets(env):
    """R8: token de servicio, contraseña y hash no salen en respuestas del panel."""
    _create_profile(env)
    _login_ok(env)
    responses = [
        env.client.get("/asesor"),
        env.client.get("/asesor/cases"),
        _post(env, "/asesor/assign", {"case_id": "", "csrf_token": _csrf(env)}),
        _login(env, "asesor1", "clave-incorrecta"),
        env.client.get("/asesor/login"),
    ]
    for response in responses:
        haystack = response.text + str(response.headers) + str(response.cookies)
        assert SERVICE_TOKEN not in haystack
        assert "X-Service-Token" not in haystack
        assert PASSWORD not in haystack
        assert "pbkdf2_sha256$" not in haystack


# --- R9: perfil sin vínculo ------------------------------------------------------------


@pytest.mark.parametrize(
    ("path", "body"),
    [
        ("/asesor/reply", {"case_id": "case-1", "text": "hola"}),
        ("/asesor/assign", {"case_id": "case-1"}),
        ("/asesor/close", {"case_id": "case-1"}),
    ],
)
def test_unlinked_profile_cannot_act(env, path, body):
    """R9: sin telegram_user_id -> 403 telegram_not_linked sin llamadas."""
    _create_profile(env, telegram_user_id=None)
    _login_ok(env)
    response = _post(env, path, {**body, "csrf_token": _csrf(env)})

    assert response.status_code == 403
    assert "telegram_not_linked" in response.text
    assert env.handover.authorized == []
    assert env.handover.try_assigned == []
    assert env.handover.closed == []
    assert env.gateway.sent == []


# --- R10, R11 y R12: acciones ----------------------------------------------------------


def test_reply_uses_session_advisor_and_ignores_form_advisor(env):
    """R10: reply usa el telegram_user_id de la sesión y redirige con ok=reply."""
    _create_profile(env, telegram_user_id=700)
    contact = _link_case(env)
    _login_ok(env)

    response = _post(
        env,
        "/asesor/reply",
        {
            "csrf_token": _csrf(env),
            "case_id": "case-1",
            "text": "Hola, soy tu asesor",
            "advisor_id": "999",
        },
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/asesor?ok=reply"
    assert env.handover.authorized == [("case-1", "700", "reply")]
    assert env.handover.assigned == [("case-1", "700")]
    assert (contact.chat_id, "Hola, soy tu asesor") in env.gateway.sent


def test_assign_uses_session_advisor_and_redirects(env):
    """R11: assign llama a handover con el asesor de la sesión y redirige."""
    _create_profile(env, telegram_user_id=700)
    _login_ok(env)

    response = _post(
        env,
        "/asesor/assign",
        {"csrf_token": _csrf(env), "case_id": "case-1", "advisor_id": "999"},
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/asesor?ok=assign"
    assert env.handover.try_assigned == [("case-1", "700")]
    assert env.handover.authorized == []
    assert env.handover.assigned == []


def test_close_authorizes_closes_and_notifies_client(env):
    """R12: close autoriza, cierra, avisa al cliente y redirige con ok=close."""
    _create_profile(env, telegram_user_id=700)
    contact = _link_case(env)
    _login_ok(env)

    response = _post(
        env,
        "/asesor/close",
        {"csrf_token": _csrf(env), "case_id": "case-1"},
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/asesor?ok=close"
    assert env.handover.authorized == [("case-1", "700", "close")]
    assert env.handover.closed == [("case-1", "700")]
    assert (contact.chat_id, env.settings.case_closed_reply) in env.gateway.sent
    stored = [m for m in env.repo.messages if m.contact_id == contact.id and m.role == "bot"]
    assert [m.text for m in stored] == [env.settings.case_closed_reply]


# --- R14: errores del servicio ---------------------------------------------------------


@pytest.mark.parametrize(
    ("attribute", "value", "status", "code"),
    [
        ("authorize_error", "forbidden", 403, "forbidden"),
        ("authorize_error", "not_found", 404, "not_found"),
        ("authorize_error", "case_closed", 409, "case_closed"),
        ("fail_authorize", True, 502, "upstream_error"),
    ],
)
def test_reply_errors_use_fixed_panel_page(env, attribute, value, status, code):
    """R14: reply traduce los rechazos a la página fija y no escribe nada."""
    _create_profile(env, telegram_user_id=700)
    _link_case(env)
    _login_ok(env)
    setattr(env.handover, attribute, value)
    before_gateway = list(env.gateway.sent)
    before_messages = list(env.repo.messages)

    response = _post(
        env,
        "/asesor/reply",
        {"csrf_token": _csrf(env), "case_id": "case-1", "text": "hola"},
    )

    assert response.status_code == status
    assert f'data-code="{code}"' in response.text
    assert env.gateway.sent == before_gateway
    assert env.repo.messages == before_messages


@pytest.mark.parametrize(
    ("attribute", "value", "status", "code"),
    [
        ("assign_error", "forbidden", 403, "forbidden"),
        ("assign_error", "not_found", 404, "not_found"),
        ("assign_error", "case_closed", 409, "case_closed"),
        ("fail_try_assign", True, 502, "upstream_error"),
    ],
)
def test_assign_errors_use_fixed_panel_page(env, attribute, value, status, code):
    """R14: assign traduce los rechazos del contrato a la página fija."""
    _create_profile(env, telegram_user_id=700)
    _login_ok(env)
    setattr(env.handover, attribute, value)

    response = _post(
        env,
        "/asesor/assign",
        {"csrf_token": _csrf(env), "case_id": "case-1"},
    )

    assert response.status_code == status
    assert f'data-code="{code}"' in response.text


@pytest.mark.parametrize(
    ("attribute", "value", "status", "code"),
    [
        ("authorize_error", "not_found", 404, "not_found"),
        ("authorize_error", "case_closed", 409, "case_closed"),
        ("fail_authorize", True, 502, "upstream_error"),
        ("close_error", "case_closed", 409, "case_closed"),
        ("fail_close", True, 502, "upstream_error"),
    ],
)
def test_close_errors_use_fixed_panel_page(env, attribute, value, status, code):
    """R14: close traduce los rechazos a la página fija sin avisar al cliente."""
    _create_profile(env, telegram_user_id=700)
    _link_case(env)
    _login_ok(env)
    setattr(env.handover, attribute, value)

    response = _post(
        env,
        "/asesor/close",
        {"csrf_token": _csrf(env), "case_id": "case-1"},
    )

    assert response.status_code == status
    assert f'data-code="{code}"' in response.text
    assert env.gateway.sent == []
    assert env.repo.messages == []


@pytest.mark.parametrize(
    ("path", "body"),
    [
        ("/asesor/reply", {"case_id": "", "text": "hola"}),
        ("/asesor/reply", {"case_id": "case-1", "text": ""}),
        ("/asesor/assign", {"case_id": ""}),
        ("/asesor/assign", {"case_id": "x" * 65}),
        ("/asesor/close", {"case_id": ""}),
        ("/asesor/close", {"case_id": "x" * 65}),
    ],
)
def test_invalid_forms_return_422_without_calls(env, path, body):
    """R14: case_id fuera de Identifier o texto vacío -> 422 sin llamadas."""
    _create_profile(env, telegram_user_id=700)
    _login_ok(env)

    response = _post(env, path, {**body, "csrf_token": _csrf(env)})

    assert response.status_code == 422
    assert 'data-code="validation_error"' in response.text
    assert env.handover.authorized == []
    assert env.handover.try_assigned == []
    assert env.handover.closed == []
    assert env.gateway.sent == []


# --- R15: denegaciones registradas -----------------------------------------------------


@pytest.mark.parametrize(
    ("path", "setup"),
    [
        ("/asesor/reply", {"authorize_error": "forbidden"}),
        ("/asesor/assign", {"assign_error": "forbidden"}),
        ("/asesor/close", {"close_error": "forbidden"}),
    ],
)
def test_forbidden_actions_record_advisor_forbidden_event(env, path, setup):
    """R15: un 403 de handover deja advisor_forbidden en el contacto del caso."""
    _create_profile(env, telegram_user_id=700)
    contact = _link_case(env)
    _login_ok(env)
    for key, value in setup.items():
        setattr(env.handover, key, value)
    body = {"csrf_token": _csrf(env), "case_id": "case-1"}
    if path == "/asesor/reply":
        body["text"] = "hola"

    response = _post(env, path, body)

    assert response.status_code == 403
    event = env.repo.events[-1]
    assert (event.contact_id, event.type) == (contact.id, "advisor_forbidden")
    assert "case:case-1" in event.reason
    assert "advisor:700" in event.reason


def test_forbidden_without_linked_case_only_logs(env, caplog):
    """R15: sin contacto vinculado, la denegación solo deja un WARNING."""
    _create_profile(env, telegram_user_id=700)
    _login_ok(env)
    env.handover.assign_error = "forbidden"

    response = _post(
        env, "/asesor/assign", {"csrf_token": _csrf(env), "case_id": "case-x"}
    )

    assert response.status_code == 403
    assert env.repo.events == []
    assert any(
        "advisor_forbidden" in record.getMessage() and "case-x" in record.getMessage()
        for record in caplog.records
    )


def test_orphan_case_can_be_closed_but_not_replied_or_assigned(env_factory):
    """R14, R15: handover decide el caso huérfano; el panel solo traduce su respuesta."""
    env = env_factory()
    _create_profile(env, telegram_user_id=700)
    _link_case(env)
    _login_ok(env)
    csrf = _csrf(env)

    env.handover.authorize_error = "forbidden"
    reply = _post(
        env,
        "/asesor/reply",
        {"csrf_token": csrf, "case_id": "case-1", "text": "hola"},
    )
    assert reply.status_code == 403

    env.handover.authorize_error = None
    env.handover.assign_error = "forbidden"
    assign = _post(env, "/asesor/assign", {"csrf_token": csrf, "case_id": "case-1"})
    assert assign.status_code == 403

    env.handover.assign_error = None
    close = _post(env, "/asesor/close", {"csrf_token": csrf, "case_id": "case-1"})
    assert close.status_code == 303
    assert env.handover.closed == [("case-1", "700")]


# --- R13: listado de casos -------------------------------------------------------------


def test_cases_page_uses_session_advisor_and_hides_contact_data(env):
    """R13: usa el advisor_id de la sesión y muestra solo los campos del contrato."""
    _create_profile(env, telegram_user_id=700)
    env.handover.case_list = [_case_item("case-1")]
    _login_ok(env)

    response = env.client.get("/asesor/cases?advisor_id=999")

    assert response.status_code == 200
    assert env.handover.listed == ["700"]
    assert "case-1" in response.text
    assert "open" in response.text
    assert "reply, assign, close" in response.text
    assert FIXED_NOW.isoformat() in response.text
    assert "advisor_id=999" not in response.text
    assert "contact_id" not in response.text
    assert "chat_id" not in response.text


def test_cases_page_upstream_error_returns_502(env):
    """R13: si handover no responde, la página devuelve 502 fijo."""
    _create_profile(env, telegram_user_id=700)
    _login_ok(env)
    env.handover.fail_list_cases = True

    response = env.client.get("/asesor/cases")

    assert response.status_code == 502
    assert 'data-code="upstream_error"' in response.text


# --- Adaptadores HTTP ------------------------------------------------------------------


@pytest.fixture()
def http_handover(monkeypatch):
    holder = {"post": None, "get": None}
    requests = []

    def fake_post(url, *, timeout=None, **kwargs):
        request = httpx.Request(
            "POST", url, headers=kwargs.get("headers"), content=kwargs.get("content")
        )
        requests.append(("POST", request, timeout))
        result = holder["post"]
        if isinstance(result, Exception):
            raise result
        return result

    def fake_get(url, *, params=None, timeout=None, **kwargs):
        request = httpx.Request(
            "GET", url, headers=kwargs.get("headers"), params=params
        )
        requests.append(("GET", request, timeout))
        result = holder["get"]
        if isinstance(result, Exception):
            raise result
        return result

    monkeypatch.setattr(httpx, "post", fake_post)
    monkeypatch.setattr(httpx, "get", fake_get)
    return requests, holder


@pytest.mark.parametrize(
    ("status", "code"),
    [(403, "forbidden"), (404, "not_found"), (409, "case_closed")],
)
def test_http_try_assign_maps_denials(http_handover, status, code):
    """R11, R14: 403/404/409 de assign se convierten en AuthorizationDenied."""
    _, holder = http_handover
    holder["post"] = httpx.Response(status, json={"error": code, "message": "x"})

    with pytest.raises(AuthorizationDenied) as excinfo:
        HttpHandoverClient("http://ho", "tok").try_assign("case-1", "555")

    assert excinfo.value.code == code


def test_http_try_assign_uses_assign_route_and_fails_closed(http_handover):
    """R11, R14: assign usa su ruta y cualquier respuesta inválida falla cerrada."""
    requests, holder = http_handover
    holder["post"] = httpx.Response(200, json={"status": "assigned", "case_id": "a b"})
    response = HttpHandoverClient("http://ho:8000/", "tok", 3).try_assign("a b", "555")

    assert response.case_id == "a b"
    _, request, timeout = requests[0]
    assert request.url.raw_path == b"/cases/a%20b/assign"
    assert request.headers["X-Service-Token"] == "tok"
    assert timeout == 3
    assert json.loads(request.content) == {"advisor_id": "555"}

    holder["post"] = httpx.Response(502, json={"error": "upstream_error", "message": "x"})
    with pytest.raises(ServiceUnavailable):
        HttpHandoverClient("http://ho", "tok").try_assign("case-1", "555")


def test_http_list_cases_uses_session_advisor_and_token(http_handover):
    """R13: list_cases llama a GET /cases con advisor_id y X-Service-Token."""
    requests, holder = http_handover
    holder["get"] = httpx.Response(
        200,
        json=[
            {
                "case_id": "case-1",
                "status": "open",
                "created_at": "2026-01-02T03:04:05+00:00",
                "actions": ["reply", "close"],
            }
        ],
    )
    response = HttpHandoverClient("http://ho:8000/", "tok", 3).list_cases("700")

    assert [item.case_id for item in response.root] == ["case-1"]
    _, request, timeout = requests[0]
    assert request.url.path == "/cases"
    assert request.url.params["advisor_id"] == "700"
    assert request.headers["X-Service-Token"] == "tok"
    assert timeout == 3

    holder["get"] = httpx.Response(500, json={"error": "internal_error", "message": "x"})
    with pytest.raises(ServiceUnavailable):
        HttpHandoverClient("http://ho", "tok").list_cases("700")
