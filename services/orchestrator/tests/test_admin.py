"""Tests del panel administrativo (#21 panel_administracion)."""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from orchestrator.adapters.db_query import FakeDbQuery
from orchestrator.adapters.gateway import FakeGatewayClient
from orchestrator.adapters.handover import FakeHandoverClient
from orchestrator.adapters.llm import FakeLLM
from orchestrator.adapters.rag import FakeRagClient
from orchestrator.adapters.repository import FakeRepository
from orchestrator.accounts import hash_token
from orchestrator.config import Settings
from orchestrator.domain import Adapters
from orchestrator.main import create_app

SERVICE_TOKEN = "svc-token-centinela"
PASSWORD = "clave-segura-123"
FIXED_NOW = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
CSRF_RE = re.compile(r'name="csrf_token" value="([^"]+)"')
INTERNAL_HEADERS = {"X-Service-Token": SERVICE_TOKEN}


@dataclass
class Env:
    client: TestClient
    repo: FakeRepository
    settings: Settings
    adapters: Adapters
    clock: list[datetime] = field(default_factory=lambda: [FIXED_NOW])


@pytest.fixture()
def env() -> Env:
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
    return Env(client=client, repo=repo, settings=settings, adapters=adapters, clock=clock)


def _create_profile(
    env: Env, username: str = "admin1", role: str = "admin", password: str = PASSWORD
) -> dict:
    response = env.client.post(
        "/profiles",
        json={"username": username, "role": role, "password": password},
        headers=INTERNAL_HEADERS,
    )
    assert response.status_code == 201, response.text
    return response.json()


def _login(env: Env, username: str, password: str, headers: dict | None = None):
    return env.client.post(
        "/admin/login",
        data={"username": username, "password": password},
        headers=headers or {},
        follow_redirects=False,
    )


def _login_ok(env: Env, username: str = "admin1", password: str = PASSWORD):
    response = _login(env, username, password)
    assert response.status_code == 303, response.text
    return response


def _csrf(env: Env, path: str = "/admin/profiles") -> str:
    response = env.client.get(path)
    assert response.status_code == 200, response.text
    match = CSRF_RE.search(response.text)
    assert match is not None
    return match.group(1)


# --- R1: login y sesión ----------------------------------------------------------------


def test_login_creates_session_and_sets_cookie_attributes(env):
    """R1: login admin -> 303 y cookie HttpOnly/SameSite=Strict/Path=/admin con TTL."""
    _create_profile(env)
    response = _login(env, "admin1", PASSWORD)

    assert response.status_code == 303
    assert response.headers["location"] == "/admin"
    cookie = response.headers["set-cookie"].lower()
    assert "admin_session=" in cookie
    assert "httponly" in cookie
    assert "samesite=strict" in cookie
    assert "path=/admin" in cookie
    assert "max-age=3600" in cookie
    assert "; secure" not in cookie

    token = env.client.cookies.get("admin_session")
    session = env.repo.sessions[hash_token(token)]
    assert session.expires_at == FIXED_NOW + timedelta(minutes=60)
    assert session.csrf_token


def test_session_ttl_is_configurable(env):
    """R1: la expiración de la sesión sale de ADMIN_SESSION_TTL_MINUTES."""
    env.settings.admin_session_ttl_minutes = 30
    _create_profile(env)
    response = _login(env, "admin1", PASSWORD)
    assert "max-age=1800" in response.headers["set-cookie"].lower()
    token = env.client.cookies.get("admin_session")
    assert env.repo.sessions[hash_token(token)].expires_at == FIXED_NOW + timedelta(
        minutes=30
    )


def test_login_uses_secure_cookie_when_configured(env):
    """R1: ADMIN_COOKIE_SECURE añade el atributo Secure a la cookie."""
    env.settings.admin_cookie_secure = True
    _create_profile(env)
    response = _login(env, "admin1", PASSWORD)
    assert "; secure" in response.headers["set-cookie"].lower()


# --- R2: credenciales inválidas --------------------------------------------------------


def test_failed_login_returns_same_response_for_all_three_cases(env):
    """R2: usuario inexistente, clave mal y rol no admin dan 401 idénticos sin sesión."""
    _create_profile(env, "admin1", "admin")
    _create_profile(env, "asesor1", "asesor")

    responses = [
        _login(env, "no-existe", PASSWORD),
        _login(env, "admin1", "clave-incorrecta"),
        _login(env, "asesor1", PASSWORD),
    ]

    assert [response.status_code for response in responses] == [401, 401, 401]
    assert len({response.text for response in responses}) == 1
    assert env.repo.sessions == {}
    for response in responses:
        assert "admin_session=" not in response.headers.get("set-cookie", "")


def test_login_unknown_user_still_runs_password_comparison(env, monkeypatch):
    """R2: mismo número de PBKDF2 exista o no el usuario, con clave u rol inválidos."""
    env.settings.admin_login_max_attempts = 100
    _create_profile(env, "admin1", "admin")
    _create_profile(env, "asesor1", "asesor")

    calls: list[int] = []
    original = hashlib.pbkdf2_hmac

    def spy(hash_name, password, salt, iterations, *args, **kwargs):
        calls.append(1)
        return original(hash_name, password, salt, iterations, *args, **kwargs)

    monkeypatch.setattr(hashlib, "pbkdf2_hmac", spy)

    # Calienta la caché del hash ficticio: en el primer login aún se calcula.
    assert _login(env, "no-existe", PASSWORD).status_code == 401
    calls.clear()

    def count(username: str, password: str) -> int:
        calls.clear()
        assert _login(env, username, password).status_code == 401
        return len(calls)

    unknown = count("no-existe", PASSWORD)
    wrong = count("admin1", "clave-incorrecta")
    not_admin = count("asesor1", PASSWORD)

    assert unknown == wrong == not_admin == 1


# --- R3: sesión obligatoria ------------------------------------------------------------


def test_admin_routes_redirect_without_session(env):
    """R3: sin cookie o con cookie desconocida -> 303 a /admin/login sin ejecutar."""
    response = env.client.get("/admin", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/admin/login"

    env.client.cookies.set("admin_session", "desconocida")
    response = env.client.get("/admin/profiles", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/admin/login"


def test_expired_session_redirects_to_login(env):
    """R3: una cookie expirada no da acceso."""
    _create_profile(env)
    _login_ok(env)
    env.clock[0] = FIXED_NOW + timedelta(minutes=61)
    response = env.client.get("/admin", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/admin/login"


def test_logout_closes_session(env):
    """R3: tras POST /admin/logout la cookie deja de dar acceso."""
    _create_profile(env)
    _login_ok(env)
    csrf = _csrf(env, "/admin")
    response = env.client.post(
        "/admin/logout", data={"csrf_token": csrf}, follow_redirects=False
    )
    assert response.status_code == 303
    assert env.repo.sessions == {}
    response = env.client.get("/admin", follow_redirects=False)
    assert response.status_code == 303


def test_demoted_admin_session_is_rejected(env):
    """R3: si el perfil deja de ser admin, su sesión se ignora."""
    first = _create_profile(env, "admin1", "admin")
    _create_profile(env, "admin2", "admin")
    _login_ok(env, "admin1")
    assert env.repo.set_role(first["id"], "asesor") is True
    response = env.client.get("/admin", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/admin/login"


def test_login_and_static_css_are_public(env):
    """R3: login y admin.css se sirven sin sesión."""
    login = env.client.get("/admin/login")
    assert login.status_code == 200
    css = env.client.get("/admin/static/admin.css")
    assert css.status_code == 200
    assert css.headers["content-type"].startswith("text/css")


# --- R4: CSRF --------------------------------------------------------------------------


def test_post_without_or_with_wrong_csrf_is_forbidden(env):
    """R4: un POST con sesión sin csrf o con otro token -> 403 sin efecto."""
    _create_profile(env)
    _login_ok(env)
    before = len(env.repo.profiles)

    body = {"username": "nuevo", "role": "asesor", "password": PASSWORD}
    missing = env.client.post("/admin/profiles", data=body, follow_redirects=False)
    assert missing.status_code == 403
    wrong = env.client.post(
        "/admin/profiles",
        data={**body, "csrf_token": "token-equivocado"},
        follow_redirects=False,
    )
    assert wrong.status_code == 403
    assert len(env.repo.profiles) == before


def test_post_without_session_redirects_before_csrf(env):
    """R4, R3: sin sesión el POST redirige a login, no evalúa CSRF."""
    response = env.client.post(
        "/admin/profiles",
        data={"username": "nuevo", "role": "asesor", "password": PASSWORD},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/admin/login"


# --- R5: CSP y sin recursos externos ---------------------------------------------------


def _admin_pages(env: Env) -> list:
    _create_profile(env)
    _login_ok(env)
    csrf = _csrf(env)
    profile_id = next(iter(env.repo.profiles))
    link = env.client.post(
        f"/admin/profiles/{profile_id}/link-token", data={"csrf_token": csrf}
    )
    return [
        env.client.get("/admin/login"),
        env.client.get("/admin"),
        env.client.get("/admin/profiles"),
        env.client.get("/admin/events"),
        link,
    ]


def test_admin_html_has_csp_and_no_external_resources(env):
    """R5: toda respuesta HTML lleva la CSP y no hay src/href externos."""
    expected = (
        "default-src 'self'; form-action 'self'; frame-ancestors 'none'"
    )
    for response in _admin_pages(env):
        assert response.status_code == 200
        assert response.headers["content-security-policy"] == expected
        assert "<script" not in response.text.lower()
        for value in re.findall(r'(?:src|href)="([^"]*)"', response.text):
            assert not value.startswith(("http://", "https://", "//"))


# --- R6: sin secretos ------------------------------------------------------------------


def test_admin_responses_never_include_service_token_or_password(env):
    """R6: ni SERVICE_TOKEN, ni la contraseña, ni el hash salen en cuerpo/cabeceras/cookies."""
    responses = _admin_pages(env)
    responses.append(_login(env, "admin1", "clave-incorrecta"))
    responses.append(
        env.client.post(
            "/admin/profiles",
            data={"username": "nuevo", "role": "asesor", "password": PASSWORD},
            follow_redirects=False,
        )
    )
    for response in responses:
        haystack = response.text + str(response.headers) + str(response.cookies)
        assert SERVICE_TOKEN not in haystack
        assert PASSWORD not in haystack
        assert "pbkdf2_sha256$" not in haystack


# --- R7: crear perfiles ----------------------------------------------------------------


def test_create_profile_from_panel_and_list_it(env):
    """R7: crear perfil -> 303 y aparece con username, rol y si está vinculado."""
    created = _create_profile(env)
    _login_ok(env)
    csrf = _csrf(env)

    response = env.client.post(
        "/admin/profiles",
        data={
            "csrf_token": csrf,
            "username": "Asesor.Uno",
            "role": "asesor",
            "password": PASSWORD,
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/admin/profiles"

    page = env.client.get("/admin/profiles").text
    assert "asesor.uno" in page
    assert "asesor" in page
    assert "No" in page

    env.repo.profiles[created["id"]].telegram_user_id = 700
    page = env.client.get("/admin/profiles").text
    assert "Sí" in page


@pytest.mark.parametrize(
    "data",
    [
        {"username": "ab", "role": "asesor"},
        {"username": "con espacio", "role": "asesor"},
        {"username": "valido1", "role": "root"},
        {"username": "valido2", "role": "admin", "password": "corta"},
    ],
)
def test_invalid_profile_from_panel_returns_422(env, data):
    """R7: datos inválidos vuelven a mostrar el formulario con 422 sin crear."""
    _create_profile(env)
    _login_ok(env)
    csrf = _csrf(env)
    body = {"password": PASSWORD, **data, "csrf_token": csrf}
    response = env.client.post("/admin/profiles", data=body, follow_redirects=False)
    assert response.status_code == 422
    assert len(env.repo.profiles) == 1


def test_duplicate_profile_from_panel_returns_409(env):
    """R7: username repetido -> 409 sin crear el perfil."""
    _create_profile(env)
    _login_ok(env)
    csrf = _csrf(env)
    response = env.client.post(
        "/admin/profiles",
        data={
            "csrf_token": csrf,
            "username": "admin1",
            "role": "asesor",
            "password": PASSWORD,
        },
        follow_redirects=False,
    )
    assert response.status_code == 409
    assert "username_taken" in response.text
    assert len(env.repo.profiles) == 1


# --- R8: cambio de rol ----------------------------------------------------------------


def test_change_role_and_protect_last_admin(env):
    """R8: cambia el rol y no deja el panel sin administradores."""
    first = _create_profile(env, "admin1", "admin")
    _login_ok(env)
    csrf = _csrf(env)

    blocked = env.client.post(
        f"/admin/profiles/{first['id']}/role",
        data={"csrf_token": csrf, "role": "asesor"},
        follow_redirects=False,
    )
    assert blocked.status_code == 409
    assert "last_admin" in blocked.text
    assert env.repo.profiles[first["id"]].role == "admin"

    _create_profile(env, "admin2", "admin")
    csrf = _csrf(env)
    changed = env.client.post(
        f"/admin/profiles/{first['id']}/role",
        data={"csrf_token": csrf, "role": "asesor"},
        follow_redirects=False,
    )
    assert changed.status_code == 303
    assert changed.headers["location"] == "/admin/profiles"
    assert env.repo.profiles[first["id"]].role == "asesor"


def test_change_role_rejects_invalid_role(env):
    """R8: un rol fuera de la lista responde 422 sin cambiar nada."""
    profile = _create_profile(env, "admin1", "admin")
    _login_ok(env)
    csrf = _csrf(env)
    response = env.client.post(
        f"/admin/profiles/{profile['id']}/role",
        data={"csrf_token": csrf, "role": "root"},
        follow_redirects=False,
    )
    assert response.status_code == 422
    assert env.repo.profiles[profile["id"]].role == "admin"


# --- R9: enlace de vinculación ---------------------------------------------------------


def test_link_token_page_shows_link_and_expiry_once_with_no_store(env):
    """R9: el enlace se muestra una vez con expires_at y Cache-Control: no-store."""
    _create_profile(env)
    _login_ok(env)
    csrf = _csrf(env)
    profile_id = next(iter(env.repo.profiles))

    response = env.client.post(
        f"/admin/profiles/{profile_id}/link-token", data={"csrf_token": csrf}
    )
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert len(env.repo.link_tokens) == 1
    stored = next(iter(env.repo.link_tokens.values()))
    token = response.text.split("?start=", 1)[1].split("<", 1)[0]
    assert token
    assert env.repo.link_tokens.get(hash_token(token)) is stored
    assert response.text.count(token) == 1
    assert stored.expires_at.isoformat() in response.text


def test_link_token_for_unknown_profile_returns_404(env):
    """R9: perfil inexistente -> 404 sin emitir token."""
    _create_profile(env)
    _login_ok(env)
    csrf = _csrf(env)
    response = env.client.post(
        "/admin/profiles/no-existe/link-token", data={"csrf_token": csrf}
    )
    assert response.status_code == 404
    assert env.repo.link_tokens == {}


# --- R10: eventos redactados -----------------------------------------------------------


def test_events_are_recent_first_short_and_redacted(env):
    """R10: últimos eventos, contacto a 8 caracteres y motivos redactados."""
    _create_profile(env)
    _login_ok(env)
    long_token = "a" * 24
    env.repo.add_event(
        "abcdef1234567890",
        "handover",
        f"case:abc123 email:ana@example.com tel:3001234567 token:{long_token}",
        FIXED_NOW - timedelta(minutes=2),
    )
    env.repo.add_event("contact-2", "rag_answer", "chunks_found", FIXED_NOW)

    page = env.client.get("/admin/events")
    assert page.status_code == 200
    text = page.text
    assert "abcdef12" in text
    assert "abcdef1234567890" not in text
    assert "ana@example.com" not in text
    assert "3001234567" not in text
    assert long_token not in text
    assert text.count("[redactado]") >= 3
    assert "case:abc123" in text
    assert text.index("rag_answer") < text.index("handover")


def test_events_respect_configured_limit(env):
    """R10: se muestran como máximo ADMIN_EVENTS_LIMIT eventos."""
    env.settings.admin_events_limit = 2
    _create_profile(env)
    _login_ok(env)
    for i in range(5):
        env.repo.add_event(
            f"contact-{i}", f"event_{i}", "reason", FIXED_NOW + timedelta(minutes=i)
        )
    text = env.client.get("/admin/events").text
    assert "event_4" in text and "event_3" in text
    assert "event_2" not in text and "event_1" not in text and "event_0" not in text


# --- R11: límite de intentos -----------------------------------------------------------


def test_login_throttled_by_username_after_max_failures(env):
    """R11: N fallos del mismo username -> 429 con la misma página y sin sesión."""
    env.settings.admin_trust_proxy_headers = True
    _create_profile(env, "admin1", "admin")
    first = _login(
        env, "admin1", "mala", headers={"X-Forwarded-For": "10.0.0.1"}
    )
    assert first.status_code == 401
    for i in range(1, 3):
        response = _login(
            env, "admin1", "mala", headers={"X-Forwarded-For": f"10.0.0.{i + 1}"}
        )
        assert response.status_code == 401

    blocked = _login(
        env, "admin1", PASSWORD, headers={"X-Forwarded-For": "10.0.0.99"}
    )
    assert blocked.status_code == 429
    assert blocked.text == first.text
    assert env.repo.sessions == {}
    assert "admin_session=" not in blocked.headers.get("set-cookie", "")


def test_login_throttled_by_ip_after_max_failures(env):
    """R11: N fallos desde la misma IP -> 429 aunque cambie el username."""
    _create_profile(env, "admin1", "admin")
    for i in range(3):
        assert _login(env, f"usuario{i}", "mala").status_code == 401
    blocked = _login(env, "admin1", PASSWORD)
    assert blocked.status_code == 429
    assert env.repo.sessions == {}


def test_throttled_login_does_not_call_verify_password(env, monkeypatch):
    """R11: el 429 se decide antes de verify_password."""
    _create_profile(env, "admin1", "admin")
    for _ in range(3):
        assert _login(env, "admin1", "mala").status_code == 401

    calls: list[int] = []

    def spy(password: str, stored: str) -> bool:
        calls.append(1)
        return False

    monkeypatch.setattr("orchestrator.domain.verify_password", spy)
    response = _login(env, "admin1", PASSWORD)
    assert response.status_code == 429
    assert calls == []


def test_throttle_expires_when_failures_leave_the_window(env):
    """R11: pasada la ventana se puede volver a intentar."""
    _create_profile(env, "admin1", "admin")
    for _ in range(3):
        assert _login(env, "admin1", "mala").status_code == 401
    env.clock[0] = FIXED_NOW + timedelta(minutes=16)
    response = _login(env, "admin1", PASSWORD)
    assert response.status_code == 303


def test_successful_login_resets_username_failures(env):
    """R11: acertar reinicia el contador de fallos de ese username."""
    env.settings.admin_trust_proxy_headers = True
    _create_profile(env, "admin1", "admin")
    for i in range(2):
        assert (
            _login(
                env, "admin1", "mala", headers={"X-Forwarded-For": f"10.1.0.{i}"}
            ).status_code
            == 401
        )
    assert (
        _login(
            env, "admin1", PASSWORD, headers={"X-Forwarded-For": "10.1.0.50"}
        ).status_code
        == 303
    )
    assert not [
        failure for failure in env.repo.login_failures if failure.username == "admin1"
    ]
    again = _login(
        env, "admin1", "mala", headers={"X-Forwarded-For": "10.1.0.99"}
    )
    assert again.status_code == 401


def test_forwarded_for_is_ignored_without_trust(env):
    """R11: sin ADMIN_TRUST_PROXY_HEADERS se usa la IP de la conexión."""
    _create_profile(env, "admin1", "admin")
    _login(env, "admin1", "mala", headers={"X-Forwarded-For": "1.2.3.4"})
    assert env.repo.login_failures[-1].ip == "testclient"


def test_forwarded_for_is_used_with_trust(env):
    """R32: con ADMIN_TRUST_PROXY_HEADERS se usa el primer valor de X-Forwarded-For."""
    env.settings.admin_trust_proxy_headers = True
    _create_profile(env, "admin1", "admin")
    _login(env, "admin1", "mala", headers={"X-Forwarded-For": "1.2.3.4, 5.6.7.8"})
    assert env.repo.login_failures[-1].ip == "1.2.3.4"


# --- Configuración ---------------------------------------------------------------------


def test_redact_reason_and_short_id_are_pure():
    """R10: la redacción es pura y respeta los códigos cortos."""
    from orchestrator.admin import redact_reason, short_id

    assert short_id("abcdef1234567890") == "abcdef12"
    assert short_id(None) == ""
    redacted = redact_reason(
        "case:abc123 email:ana@example.com tel:3001234567 token:aaaaaaaaaaaaaaaaaaaaaaaa"
    )
    assert redacted.count("[redactado]") == 3
    assert "case:abc123" in redacted
    assert "ana@example.com" not in redacted


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("admin_session_ttl_minutes", 4),
        ("admin_session_ttl_minutes", 1441),
        ("admin_events_limit", 0),
        ("admin_events_limit", 501),
        ("admin_login_max_attempts", 0),
        ("admin_login_max_attempts", 101),
        ("admin_login_window_minutes", 0),
        ("admin_login_window_minutes", 1441),
    ],
)
def test_admin_settings_validate_ranges(name, value):
    """R1, R10, R11: los valores fuera de rango se rechazan."""
    with pytest.raises(ValidationError):
        Settings(**{name: value})
