"""El login web de clientes conserva su formulario y flujo propios."""
from __future__ import annotations

from orchestrator.identity_page import render_login_form


def test_client_login_form_has_no_verification_code():
    """`/acceso` pide solo las credenciales de cliente ya previstas."""
    text = render_login_form("token")
    assert 'name="username"' in text
    assert 'name="password"' in text
    assert 'name="code"' not in text


def test_acceso_without_valid_link_keeps_its_400(env):
    """La página pública sigue respondiendo igual sin enlace válido."""
    response = env.client.get("/acceso", follow_redirects=False)
    assert response.status_code == 400
    assert 'name="code"' not in response.text
