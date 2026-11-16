"""El acceso a los paneles de personal usa usuario y contraseña."""
from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import pytest

from orchestrator import admin
from orchestrator.accounts import hash_password, hash_token

ROOT = Path(__file__).resolve().parents[3]
PASSWORD = "ClaveSegura123"


@pytest.mark.parametrize(
    ("panel", "role", "username", "cookie", "destination"),
    [
        ("admin", "admin", "admin1", "admin_session", "/admin"),
        ("asesor", "asesor", "asesor1", "advisor_session", "/asesor"),
    ],
)
def test_staff_login_needs_no_verification_code(
    env_factory, monkeypatch, panel, role, username, cookie, destination
):
    """Una cuenta con datos 2FA antiguos sigue entrando solo con su contraseña."""
    monkeypatch.setenv("PANEL_2FA_REQUIRED", "true")
    monkeypatch.setenv("PANEL_2FA_ENCRYPTION_KEY", "")
    env = env_factory(
        admin_cookie_secure=False,
        password_hash_iterations=100000,
    )
    profile = env.repo.create_profile(
        username, role, hash_password(PASSWORD, 100000), env.adapters.clock()
    )
    now = env.adapters.clock()
    env.repo.save_pending_two_factor(profile.id, "legacy-ciphertext", now)
    assert env.repo.activate_two_factor(profile.id, 1, [], now)

    login_page = env.client.get(f"/{panel}/login")
    assert 'name="username"' in login_page.text
    assert 'name="password"' in login_page.text
    assert 'name="code"' not in login_page.text
    assert "Código de verificación" not in login_page.text

    response = env.client.post(
        f"/{panel}/login",
        data={"username": username, "password": PASSWORD},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"] == destination
    token = response.cookies.get(cookie)
    assert token is not None
    session = env.repo.get_session_any(hash_token(token), now)
    assert session is not None and session.enroll_only is False


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("get", "/admin/2fa"),
        ("post", "/admin/2fa/start"),
        ("get", "/asesor/2fa"),
        ("post", "/asesor/2fa/start"),
        ("post", "/admin/profiles/profile-1/2fa/reset"),
    ],
)
def test_second_factor_routes_are_not_exposed(env, method, path):
    """Las rutas de registro y restablecimiento dejan de existir en los paneles."""
    response = getattr(env.client, method)(path, follow_redirects=False)
    assert response.status_code == 404


def test_admin_profile_page_has_no_factor_controls():
    """La administración de perfiles ya no ofrece opciones de 2FA."""
    page = admin.render_profiles([], "csrf")
    assert "Segundo factor" not in page
    assert "/2fa" not in page


@pytest.mark.parametrize(
    ("panel", "role", "cookie"),
    [
        ("admin", "admin", "admin_session"),
        ("asesor", "asesor", "advisor_session"),
    ],
)
def test_existing_restricted_session_can_open_panel(env_factory, panel, role, cookie):
    """Las sesiones limitadas al antiguo registro ya no fuerzan a reautenticarse."""
    env = env_factory(
        admin_cookie_secure=False,
        password_hash_iterations=100000,
    )
    profile = env.repo.create_profile(
        f"{role}1", role, hash_password(PASSWORD, 100000), env.adapters.clock()
    )
    now = env.adapters.clock()
    env.repo.create_session(
        hash_token("legacy-enrollment-session"),
        profile.id,
        "csrf-token",
        now + timedelta(hours=1),
        enroll_only=True,
    )
    env.client.cookies.set(cookie, "legacy-enrollment-session", path=f"/{panel}")

    response = env.client.get(f"/{panel}", follow_redirects=False)
    assert response.status_code == 200


def test_deployment_configuration_does_not_expose_second_factor():
    """El despliegue ya no pide ni configura secretos para el segundo factor."""
    public_configuration = "".join(
        (ROOT / path).read_text(encoding="utf-8")
        for path in (".env.example", "render.yaml", "docs/despliegue.md")
    )
    assert "PANEL_2FA_" not in public_configuration
