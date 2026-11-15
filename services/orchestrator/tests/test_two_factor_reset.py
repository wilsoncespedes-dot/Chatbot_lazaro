"""Restablecimiento del segundo factor por un administrador (#54)."""
from __future__ import annotations

import base64
import re
from datetime import datetime, timedelta, timezone

from orchestrator.accounts import hash_password, hash_token
from orchestrator.two_factor import encrypt_secret, generate_secret, totp_at

PASSWORD = "ClaveSegura123"
KEY = base64.urlsafe_b64encode(b"k" * 32).decode("ascii")
CSRF_RE = re.compile(r'name="csrf_token" value="([^"]+)"')
NOW = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
STEP = int(NOW.timestamp()) // 30


def _env(env_factory, *, required: bool = False):
    return env_factory(
        panel_2fa_encryption_key=KEY,
        panel_2fa_required=required,
        admin_cookie_secure=False,
        password_hash_iterations=100000,
    )


def _profile(env, username: str, role: str = "admin"):
    return env.repo.create_profile(
        username, role, hash_password(PASSWORD, 100000), env.adapters.clock()
    )


def _enable(env, profile) -> bytes:
    secret = generate_secret()
    env.repo.save_pending_two_factor(
        profile.id, encrypt_secret(secret, KEY), env.adapters.clock()
    )
    env.repo.activate_two_factor(profile.id, 0, ["hash-a"], env.adapters.clock())
    return secret


def _login(env, username: str, code: str = ""):
    return env.client.post(
        "/admin/login",
        data={"username": username, "password": PASSWORD, "code": code},
        follow_redirects=False,
    )


def _csrf(env) -> str:
    response = env.client.get("/admin/profiles")
    assert response.status_code == 200, response.text
    match = CSRF_RE.search(response.text)
    assert match is not None
    return match.group(1)


def _reset(env, target_id: str, csrf: str):
    return env.client.post(
        f"/admin/profiles/{target_id}/2fa/reset",
        data={"csrf_token": csrf},
        follow_redirects=False,
    )


def test_reset_removes_factor_sessions_and_audits(env_factory):
    """R35: restablece el factor, cierra sesiones y audita el objetivo."""
    env = _env(env_factory)
    actor = _profile(env, "admin1")
    target = _profile(env, "admin2")
    _enable(env, target)
    env.repo.create_session(
        hash_token("target-session"),
        target.id,
        "csrf-target",
        env.adapters.clock() + timedelta(hours=1),
    )
    _login(env, "admin1")
    response = _reset(env, target.id, _csrf(env))
    assert response.status_code == 303
    assert env.repo.get_two_factor(target.id) is None
    assert hash_token("target-session") not in env.repo.sessions
    assert any(
        row.action == "two_factor_reset"
        and row.target == target.id
        and row.actor_profile_id == actor.id
        for row in env.repo.panel_audit
    )


def test_self_reset_is_rejected_without_changes(env_factory):
    """R36: un administrador no puede restablecerse a sí mismo."""
    env = _env(env_factory)
    actor = _profile(env, "admin1")
    _enable(env, actor)
    env.repo.create_session(
        hash_token("actor-session"),
        actor.id,
        "csrf",
        env.adapters.clock() + timedelta(hours=1),
    )
    env.client.cookies.set("admin_session", "actor-session")
    response = _reset(env, actor.id, _csrf(env))
    assert response.status_code == 400
    assert env.repo.get_two_factor(actor.id) is not None


def test_missing_profile_and_factor_return_404_and_409(env_factory):
    """R37: perfil inexistente o sin factor no cambian nada."""
    env = _env(env_factory)
    _profile(env, "admin1")
    target = _profile(env, "admin2")
    _login(env, "admin1")
    csrf = _csrf(env)
    assert _reset(env, "no-existe", csrf).status_code == 404
    assert _reset(env, target.id, csrf).status_code == 409
    assert env.repo.get_two_factor(target.id) is None


def test_non_admin_and_bad_csrf_are_forbidden_and_audited(env_factory):
    """R38: sin rol admin o sin CSRF no hay cambios y se audita forbidden."""
    env = _env(env_factory)
    supervisor = _profile(env, "super1", "supervisor")
    target = _profile(env, "admin2")
    _enable(env, target)
    env.repo.create_session(
        hash_token("super-session"),
        supervisor.id,
        "csrf",
        env.adapters.clock() + timedelta(hours=1),
    )
    env.client.cookies.set("admin_session", "super-session", path="/admin")
    assert _reset(env, target.id, "csrf").status_code == 403
    assert env.repo.get_two_factor(target.id) is not None
    assert any(
        row.action == "two_factor_reset" and row.result == "forbidden"
        for row in env.repo.panel_audit
    )

    # La cookie manual anterior no debe convivir con la que crea el login: se
    # limpia para que la petición sin CSRF se evalúe con el administrador.
    env.client.cookies.clear()
    actor = _profile(env, "admin1")
    _login(env, "admin1")
    assert _reset(env, target.id, "csrf-invalido").status_code == 403
    assert any(
        row.actor_profile_id == actor.id and row.result == "forbidden"
        for row in env.repo.panel_audit
    )


def test_reset_profile_logs_in_without_factor_and_gets_restricted_session(
    env_factory,
):
    """R39: tras el restablecimiento, el login lo trata como sin segundo factor."""
    env = _env(env_factory, required=True)
    actor = _profile(env, "admin1")
    target = _profile(env, "admin2")
    _enable(env, target)
    secret = _enable(env, actor)
    login = _login(env, "admin1", totp_at(secret, STEP))
    assert login.status_code == 303
    # El actor ya tiene 2FA activo, así que entra al panel normal.
    assert login.headers["location"] == "/admin"
    response = _reset(env, target.id, _csrf(env))
    assert response.status_code == 303

    logged = _login(env, "admin2")
    assert logged.status_code == 303
    assert logged.headers["location"] == "/admin/2fa"
