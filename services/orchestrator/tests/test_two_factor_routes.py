"""Rutas de registro del segundo factor en ambos paneles (#54)."""
from __future__ import annotations

import base64
import re
from datetime import timedelta

import pytest
from starlette.websockets import WebSocketDisconnect

from orchestrator import two_factor_page
from orchestrator.accounts import hash_password, hash_token
from orchestrator.two_factor import totp_at

PASSWORD = "ClaveSegura123"
KEY = base64.urlsafe_b64encode(b"k" * 32).decode("ascii")
CSRF_RE = re.compile(r'name="csrf_token" value="([^"]+)"')
SECRET_RE = re.compile(r"Secreto: <code>([A-Z2-7]+)</code>")
RECOVERY_RE = re.compile(r"<code>([a-z2-7]{4}(?:-[a-z2-7]{4}){3})</code>")


def _env(env_factory, *, required: bool = False, panel_live: bool = True):
    return env_factory(
        panel_2fa_encryption_key=KEY,
        panel_2fa_required=required,
        admin_cookie_secure=False,
        password_hash_iterations=100000,
        panel_live_enabled=panel_live,
        panel_ws_allowed_origins="http://testserver",
    )


def _profile(env, username: str, role: str):
    return env.repo.create_profile(
        username, role, hash_password(PASSWORD, 100000), env.adapters.clock()
    )


def _csrf(env, path: str) -> str:
    response = env.client.get(path)
    assert response.status_code == 200, response.text
    match = CSRF_RE.search(response.text)
    assert match is not None
    return match.group(1)


def _login(env, panel: str, username: str, code: str = ""):
    return env.client.post(
        f"/{panel}/login",
        data={"username": username, "password": PASSWORD, "code": code},
        follow_redirects=False,
    )


def _start(env, panel: str, csrf: str):
    return env.client.post(
        f"/{panel}/2fa/start",
        data={"csrf_token": csrf},
        follow_redirects=False,
    )


def _confirm(env, panel: str, csrf: str, code: str):
    return env.client.post(
        f"/{panel}/2fa/confirm",
        data={"csrf_token": csrf, "code": code},
        follow_redirects=False,
    )


def _totp_for_secret(secret_base32: str, env) -> str:
    padding = "=" * ((8 - len(secret_base32) % 8) % 8)
    secret = base64.b32decode(secret_base32 + padding)
    step = int(env.adapters.clock().timestamp()) // 30
    return totp_at(secret, step)


@pytest.mark.parametrize(
    ("panel", "role", "username"),
    [("admin", "admin", "admin1"), ("asesor", "asesor", "asesor1")],
)
def test_enrollment_in_both_panels_shows_secret_only_once(
    env_factory, panel, role, username
):
    """R5, R6, R8, R28, R30: registro completo y secreto visible una sola vez."""
    env = _env(env_factory)
    _profile(env, username, role)
    login = _login(env, panel, username)
    assert login.status_code == 303
    csrf = _csrf(env, f"/{panel}/2fa")
    assert SECRET_RE.search(env.client.get(f"/{panel}/2fa").text) is None

    started = _start(env, panel, csrf)
    assert started.status_code == 200
    assert "otpauth://totp/" in started.text
    assert started.headers["cache-control"] == "no-store"
    secret = SECRET_RE.search(started.text)
    assert secret is not None
    assert SECRET_RE.search(env.client.get(f"/{panel}/2fa").text) is None

    confirmed = _confirm(env, panel, csrf, _totp_for_secret(secret.group(1), env))
    assert confirmed.status_code == 200
    assert len(RECOVERY_RE.findall(confirmed.text)) >= 4
    assert confirmed.headers["cache-control"] == "no-store"
    assert SECRET_RE.search(env.client.get(f"/{panel}/2fa").text) is None

    again = _start(env, panel, csrf)
    assert again.status_code == 409
    assert "two_factor_already_enabled" in again.text


def test_invalid_confirmation_keeps_pending_and_csrf_is_required(env_factory):
    """R7, R40: código inválido mantiene el pendiente y el CSRF es obligatorio."""
    env = _env(env_factory)
    _profile(env, "admin1", "admin")
    _login(env, "admin", "admin1")
    csrf = _csrf(env, "/admin/2fa")

    no_csrf = env.client.post(
        "/admin/2fa/start", data={}, follow_redirects=False
    )
    assert no_csrf.status_code == 403
    assert SECRET_RE.search(no_csrf.text) is None

    started = _start(env, "admin", csrf)
    secret = SECRET_RE.search(started.text)
    assert secret is not None
    invalid = _confirm(env, "admin", csrf, "000000")
    assert invalid.status_code == 401
    assert SECRET_RE.search(env.client.get("/admin/2fa").text) is None
    record = env.repo.get_two_factor(env.repo.profiles["p1"].id)
    assert record is not None and record.enabled_at is None


def test_restricted_session_only_reaches_enrollment_and_logout(env_factory):
    """R23, R24: la sesión restringida no entra al panel ni al websocket."""
    env = _env(env_factory, required=True)
    _profile(env, "admin1", "admin")
    login = _login(env, "admin", "admin1")
    assert login.status_code == 303
    assert login.headers["location"] == "/admin/2fa"

    assert env.client.get("/admin", follow_redirects=False).status_code == 303
    assert env.client.get("/admin/static/admin.css").status_code == 200
    assert env.client.get("/admin/2fa").status_code == 200

    asesor = _profile(env, "asesor1", "asesor")
    env.repo.create_session(
        hash_token("restringida-asesor"),
        asesor.id,
        "csrf-asesor",
        env.adapters.clock() + timedelta(hours=1),
        True,
    )
    env.client.cookies.set("advisor_session", "restringida-asesor")
    with pytest.raises(WebSocketDisconnect):
        with env.client.websocket_connect(
            "/asesor/ws", headers={"host": "testserver", "origin": "http://testserver"}
        ) as ws:
            ws.receive_json()


def test_confirmation_promotes_restricted_session_and_removes_other_sessions(
    env_factory,
):
    """R25: al confirmar se conserva solo la sesión que confirmó."""
    env = _env(env_factory, required=True)
    profile = _profile(env, "admin1", "admin")
    _login(env, "admin", "admin1")
    env.repo.create_session(
        hash_token("otra-sesion"),
        profile.id,
        "csrf-otra",
        env.adapters.clock() + timedelta(hours=1),
        True,
    )
    other = _profile(env, "bea", "admin")
    env.repo.create_session(
        hash_token("sesion-ajena"),
        other.id,
        "csrf-ajena",
        env.adapters.clock() + timedelta(hours=1),
    )
    csrf = _csrf(env, "/admin/2fa")
    secret = SECRET_RE.search(_start(env, "admin", csrf).text)
    assert secret is not None
    confirmed = _confirm(env, "admin", csrf, _totp_for_secret(secret.group(1), env))
    assert confirmed.status_code == 200
    assert hash_token("otra-sesion") not in env.repo.sessions
    assert hash_token("sesion-ajena") in env.repo.sessions
    assert env.client.get("/admin", follow_redirects=False).status_code == 200


def test_normal_session_confirmation_also_removes_other_sessions(env_factory):
    """R25: desde una sesión normal también se cierran las demás del perfil."""
    env = _env(env_factory, required=False)
    profile = _profile(env, "admin1", "admin")
    _login(env, "admin", "admin1")
    env.repo.create_session(
        hash_token("otra-normal"),
        profile.id,
        "csrf-otra",
        env.adapters.clock() + timedelta(hours=1),
    )
    csrf = _csrf(env, "/admin/2fa")
    secret = SECRET_RE.search(_start(env, "admin", csrf).text)
    assert secret is not None
    assert _confirm(env, "admin", csrf, _totp_for_secret(secret.group(1), env)).status_code == 200
    assert hash_token("otra-normal") not in env.repo.sessions


@pytest.mark.parametrize("panel", ["admin", "asesor"])
def test_client_role_and_missing_session_cannot_enroll(env_factory, panel):
    """R9: un perfil cliente o sin sesión no crea secreto."""
    env = _env(env_factory)
    assert env.client.get(f"/{panel}/2fa", follow_redirects=False).status_code == 303
    assert env.client.post(f"/{panel}/2fa/start", data={}, follow_redirects=False).status_code == 303

    profile = _profile(env, "cliente1", "cliente")
    env.repo.create_session(
        hash_token("cliente-session"),
        profile.id,
        "csrf",
        env.adapters.clock() + timedelta(hours=1),
    )
    env.client.cookies.set("admin_session", "cliente-session")
    assert env.client.get(f"/{panel}/2fa", follow_redirects=False).status_code == 303
    assert env.repo.get_two_factor(profile.id) is None


def test_page_values_are_escaped():
    """R40: los valores mostrados en las páginas de segundo factor se escapan."""
    text = two_factor_page.render_status(
        "admin", "csrf", enabled=False, pending=False, error="<script>alert(1)</script>"
    )
    assert "<script>alert(1)</script>" not in text
    assert "&lt;script&gt;" in text
