"""Permisos de las rutas nuevas de administración y del aviso (#42)."""
from __future__ import annotations

from datetime import timedelta

import pytest

from orchestrator.main import SERVICE_NAME  # noqa: F401

GET_PATHS = [
    "/admin/clientes",
    "/admin/texts/notice_text/historial",
    "/admin/plantillas",
    "/admin/ajustes",
    "/admin/metricas",
]
POST_PATHS = [
    "/admin/clientes",
    "/admin/clientes/p1/renovar",
    "/admin/clientes/p1/revocar",
    "/admin/clientes/p1/cerrar-sesion",
    "/admin/plantillas",
    "/admin/plantillas/una",
    "/admin/plantillas/una/estado",
    "/admin/ajustes",
]


@pytest.fixture()
def env(env_factory):
    return env_factory(admin_cookie_secure=False, password_hash_iterations=100000)


@pytest.mark.parametrize("path", GET_PATHS)
def test_get_without_session_redirects(env, path):
    """R12: sin sesión admin, toda ruta nueva GET redirige a login sin leer."""
    response = env.client.get(path, follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/admin/login"


@pytest.mark.parametrize("path", POST_PATHS)
def test_post_without_session_redirects_before_csrf(env, path):
    """R12: sin sesión admin, todo POST nuevo redirige sin ejecutar la acción."""
    response = env.client.post(path, data={}, follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/admin/login"


@pytest.mark.parametrize("path", GET_PATHS)
def test_advisor_session_is_not_an_admin_session(env, panel, path):
    """R12: una sesión de asesor no da acceso a las rutas de administración."""
    panel.login(env, "asesor")
    response = env.client.get(path, follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/admin/login"


@pytest.mark.parametrize("path", POST_PATHS)
def test_advisor_session_does_not_apply_post(env, panel, path):
    """R12: el POST de un asesor no aplica ningún cambio."""
    panel.login(env, "asesor")
    before_profiles = dict(env.repo.profiles)
    response = env.client.post(path, data={}, follow_redirects=False)
    assert response.status_code == 303
    assert env.repo.profiles == before_profiles


@pytest.mark.parametrize("path", GET_PATHS)
def test_expired_admin_session_redirects(env, panel, path):
    """R12: una sesión vencida no permite leer."""
    panel.login_admin(env)
    env.adapters.clock = lambda: env.settings and panel.NOW + timedelta(hours=2)
    response = env.client.get(path, follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/admin/login"


@pytest.mark.parametrize("path", POST_PATHS)
def test_post_without_or_with_wrong_csrf_is_forbidden(env, panel, path):
    """R13: sin CSRF correcto no se aplica ningún cambio."""
    panel.login_admin(env)
    before = (len(env.repo.profiles), len(env.repo.panel_audit))
    missing = env.client.post(path, data={}, follow_redirects=False)
    assert missing.status_code == 403
    wrong = env.client.post(
        path, data={"csrf_token": "otro"}, follow_redirects=False
    )
    assert wrong.status_code == 403
    assert (len(env.repo.profiles), len(env.repo.panel_audit)) == before


def test_expiry_notices_without_service_token_returns_401(env):
    """R14: la ruta interna del aviso exige X-Service-Token y no ejecuta la pasada."""
    response = env.client.post("/credentials/expiry-notices", json={})
    assert response.status_code == 401
    assert response.json()["error"] == "unauthorized"
    assert env.repo.expiry_notices == {}
