"""Panel de solo lectura de ofertas MCP (#74)."""
from __future__ import annotations

import pytest

from orchestrator.adapters.mcp import FakeMcpClient, McpCallResult

DEMO_ROWS = [
    {
        "id": "demo-1",
        "destino": "Melgar",
        "titulo": "Oferta de demostración",
        "precio_cop": 350000,
        "valido_desde": "2026-01-01",
        "valido_hasta": "2026-12-31",
        "es_demo": True,
        "etiqueta": "DEMOSTRACIÓN",
    }
]


@pytest.fixture()
def admin_env(env_factory, panel):
    env = env_factory(admin_cookie_secure=False, password_hash_iterations=100000)
    panel.login_admin(env)
    return env


def test_admin_lists_demo_offers_with_badge(admin_env):
    """R27: el panel lista las ofertas con la etiqueta DEMOSTRACIÓN visible."""
    admin_env.adapters.mcp = FakeMcpClient(
        results={"ofertas_demo": McpCallResult(rows=DEMO_ROWS, demo=True)}
    )

    response = admin_env.client.get("/admin/mcp")

    assert response.status_code == 200
    assert "DEMOSTRACIÓN" in response.text
    assert "Melgar" in response.text
    assert "Oferta de demostración" in response.text


def test_admin_mcp_down_shows_unavailable(admin_env):
    """R28: si el MCP no responde, el panel muestra «no disponible» con 200."""
    admin_env.adapters.mcp = FakeMcpClient(fail=True)

    response = admin_env.client.get("/admin/mcp")

    assert response.status_code == 200
    assert "no disponible" in response.text.lower()
    assert "Traceback" not in response.text


def test_admin_mcp_requires_session(env_factory):
    """R29: sin sesión de administrador redirige al login del panel."""
    env = env_factory(admin_cookie_secure=False, password_hash_iterations=100000)

    response = env.client.get("/admin/mcp", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/admin/login"
