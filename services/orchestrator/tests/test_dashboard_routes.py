"""Rutas del dashboard SVG (#75): permisos, filtros, CSP y auditoría."""
from __future__ import annotations

from datetime import timedelta

import pytest

from orchestrator import admin


def _seed(env, panel, channel: str = "telegram") -> None:
    now = env.adapters.clock()
    contact = env.repo.get_or_create_channel_contact(
        channel, f"u-{channel}", f"c-{channel}", now - timedelta(days=1)
    )
    env.repo.link_case("case-1", contact.id, now - timedelta(hours=3))
    env.repo.add_message(contact.id, "user", "hola", now - timedelta(hours=2))
    env.repo.add_message(
        contact.id, "advisor", "respuesta", now - timedelta(hours=1)
    )
    env.handover.case_list = [
        panel.case_item("case-1", status="open", created_at=now - timedelta(hours=3))
    ]


def _admin_env(env_factory, panel):
    env = env_factory(admin_cookie_secure=False, password_hash_iterations=100000)
    profile = panel.login_admin(env)
    _seed(env, panel)
    return env, profile


def test_admin_dashboard_shows_charts_table_form_and_interval(env_factory, panel):
    """R1, R6, R9, R14, R16, R21: dashboard completo para admin."""
    env, _ = _admin_env(env_factory, panel)

    response = env.client.get("/admin/dashboard?dias=7")

    assert response.status_code == 200
    body = response.text
    assert "Mensajes por canal" in body
    assert "Conversaciones por estado" in body
    assert "Tiempos de respuesta" in body
    assert "Primera respuesta: casos 1" in body
    assert "<svg" in body and "<caption>" in body
    assert 'action="/admin/dashboard"' in body
    assert 'name="dias"' in body and 'name="simulados"' in body
    assert "Intervalo:" in body


def test_dashboard_without_session_redirects_to_login(env_factory, panel):
    """R2: sin sesión redirige al login y no calcula métricas."""
    env = env_factory(admin_cookie_secure=False, password_hash_iterations=100000)

    response = env.client.get("/admin/dashboard", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/admin/login"


def test_admin_dashboard_rejects_other_roles_with_403(env_factory, panel):
    """R3: un rol sin permiso recibe 403 sin datos del dashboard."""
    env = env_factory(admin_cookie_secure=False, password_hash_iterations=100000)
    panel.login(env, role="supervisor")
    env.client.cookies.set("admin_session", "supervisor-session")
    _seed(env, panel)

    response = env.client.get("/admin/dashboard")

    assert response.status_code == 403
    assert "Mensajes por canal" not in response.text


def test_advisor_dashboard_rejects_asesor_with_403(env_factory, panel):
    """R3: un asesor no puede abrir /asesor/dashboard."""
    env = env_factory(admin_cookie_secure=False, password_hash_iterations=100000)
    panel.login(env, role="asesor")
    _seed(env, panel)

    response = env.client.get("/asesor/dashboard")

    assert response.status_code == 403
    assert "Mensajes por canal" not in response.text


def test_advisor_dashboard_without_session_redirects_to_advisor_login(
    env_factory, panel
):
    """R2: sin sesión en el panel de asesores redirige a /asesor/login."""
    env = env_factory(admin_cookie_secure=False, password_hash_iterations=100000)

    response = env.client.get("/asesor/dashboard", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/asesor/login"


@pytest.mark.parametrize("value", ["0", "91", "abc", ""])
def test_admin_dashboard_invalid_days_returns_422_before_repository(
    env_factory, panel, monkeypatch, value
):
    """R4: `dias` fuera de 1..90 responde 422 sin consultar métricas."""
    env, _ = _admin_env(env_factory, panel)

    def boom(*args, **kwargs):
        raise AssertionError("no debe consultar métricas")

    monkeypatch.setattr(env.repo, "dashboard_messages", boom)
    response = env.client.get(f"/admin/dashboard?dias={value}")

    assert response.status_code == 422
    assert "Mensajes por canal" not in response.text


def test_dashboard_invalid_simulados_returns_422(env_factory, panel, monkeypatch):
    """R5: `simulados` distinto de incluir/excluir responde 422."""
    env, _ = _admin_env(env_factory, panel)

    def boom(*args, **kwargs):
        raise AssertionError("no debe consultar métricas")

    monkeypatch.setattr(env.repo, "dashboard_messages", boom)
    response = env.client.get("/admin/dashboard?simulados=todos")

    assert response.status_code == 422


def test_dashboard_uses_panel_headers_without_changing_csp(env_factory, panel):
    """R28, R34: cabeceras del panel y `PANEL_CSP` sin cambios."""
    env, _ = _admin_env(env_factory, panel)

    admin_response = env.client.get("/admin/dashboard")

    assert admin_response.headers["content-security-policy"] == admin.PANEL_CSP

    advisor_env = env_factory(
        admin_cookie_secure=False, password_hash_iterations=100000
    )
    panel.login(advisor_env, role="supervisor")
    _seed(advisor_env, panel)
    advisor_response = advisor_env.client.get("/asesor/dashboard")
    assert advisor_response.status_code == 200
    assert advisor_response.headers["content-security-policy"] == admin.PANEL_CSP
    assert "script-src 'self'" in admin.PANEL_CSP


def test_dashboard_view_is_audited_with_range(env_factory, panel):
    """R7: cada vista deja `dashboard_viewed` con el rango como target."""
    env, _ = _admin_env(env_factory, panel)

    env.client.get("/admin/dashboard?dias=3")

    rows = [row for row in env.repo.panel_audit if row.action == "dashboard_viewed"]
    assert len(rows) == 1
    assert ".." in (rows[0].target or "")


def test_admin_navigation_and_supervisor_home_link_to_dashboard(env_factory, panel):
    """R8: el dashboard está enlazado desde admin y desde «Supervisión»."""
    env, _ = _admin_env(env_factory, panel)

    admin_home = env.client.get("/admin").text
    assert 'href="/admin/dashboard"' in admin_home
    assert "Dashboard" in admin_home

    advisor_env = env_factory(
        admin_cookie_secure=False, password_hash_iterations=100000
    )
    panel.login(advisor_env, role="supervisor")
    advisor_home = advisor_env.client.get("/asesor").text
    assert 'href="/asesor/dashboard"' in advisor_home
    assert "Supervisión" in advisor_home


def test_advisor_dashboard_shows_same_charts_for_supervisor(env_factory, panel):
    """R1: supervisor ve el mismo dashboard en /asesor/dashboard."""
    env = env_factory(admin_cookie_secure=False, password_hash_iterations=100000)
    panel.login(env, role="supervisor")
    _seed(env, panel)

    response = env.client.get("/asesor/dashboard")

    assert response.status_code == 200
    body = response.text
    assert "Mensajes por canal" in body
    assert "Conversaciones por estado" in body
    assert "Tiempos de respuesta" in body
    assert 'action="/asesor/dashboard"' in body
    assert any(
        row.action == "dashboard_viewed" for row in env.repo.panel_audit
    )


def test_dashboard_form_preselects_current_values(env_factory, panel):
    """R6: el formulario GET conserva los valores actuales."""
    env, _ = _admin_env(env_factory, panel)

    body = env.client.get("/admin/dashboard?dias=30&simulados=excluir").text

    assert 'value="30"' in body
    assert 'value="excluir" selected' in body


def test_simulated_filter_changes_the_dashboard(env_factory, panel):
    """R23, R24: `simulados=excluir` quita el canal simulado del dashboard."""
    env, _ = _admin_env(env_factory, panel)
    now = env.adapters.clock()
    simulated = env.repo.get_or_create_channel_contact(
        "simulado", "sim-1", "sim-chat", now - timedelta(days=1)
    )
    env.repo.add_message(
        simulated.id, "user", "prueba", now - timedelta(hours=2)
    )

    included = env.client.get("/admin/dashboard?simulados=incluir").text
    excluded = env.client.get("/admin/dashboard?simulados=excluir").text

    assert "[SIMULADO]" in included
    assert "[SIMULADO]" not in excluded


def test_handover_down_still_renders_other_charts(env_factory, panel):
    """R15: sin handover se muestra el aviso y los demás gráficos siguen."""
    env, _ = _admin_env(env_factory, panel)
    env.handover.fail_list_cases = True

    response = env.client.get("/admin/dashboard")

    assert response.status_code == 200
    assert "El servicio de casos no está disponible." in response.text
    assert "Mensajes por canal" in response.text
    assert "Tiempos de respuesta" in response.text
