"""Matriz de permisos de los cinco roles del panel (#49)."""
from __future__ import annotations

from datetime import timedelta

import pytest

from orchestrator.adapters.handover import FakeHandoverClient

ROLES = ("admin", "supervisor", "asesor", "responsable_datos", "cliente")


@pytest.fixture()
def env(env_factory):
    return env_factory(
        admin_cookie_secure=False,
        password_hash_iterations=100000,
        suppression_executor_roles="admin,asesor,responsable_datos",
    )


def _login(env, panel, role: str):
    if role == "admin":
        return panel.login_admin(env)
    if role == "cliente":
        return panel.make_profile(env, "cliente1", "cliente")
    return panel.login(env, role, username=f"{role}1")


def _status(env, path: str, *, follow_redirects: bool = False) -> int:
    return env.client.get(path, follow_redirects=follow_redirects).status_code


# --- R1, R2: los cinco roles existen y se asignan desde /admin -----------------


def test_roles_constant_has_all_five_roles():
    """R1: ROLES contiene los cinco roles del sistema."""
    from orchestrator.accounts import ROLES as ACCOUNT_ROLES

    assert set(ACCOUNT_ROLES) == {
        "admin",
        "supervisor",
        "asesor",
        "responsable_datos",
        "cliente",
    }


def test_admin_role_selector_lists_five_roles(env, panel):
    """R2: el selector de rol de /admin/profiles ofrece los cinco roles."""
    panel.login_admin(env)
    response = env.client.get("/admin/profiles")
    assert response.status_code == 200
    for role in ROLES:
        assert f'value="{role}"' in response.text


def test_changing_role_saves_only_one_role_and_ends_sessions(env, panel):
    """R2, R4: guarda el rol nuevo y la sesión anterior deja de valer."""
    profile = panel.login(env, "asesor")
    admin = panel.login_admin(env)
    response = env.client.post(
        f"/admin/profiles/{profile.id}/role",
        data={"csrf_token": panel.CSRF, "role": "supervisor"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert env.repo.profiles[profile.id].role == "supervisor"
    assert all(
        session.profile_id != profile.id for session in env.repo.sessions.values()
    )
    assert any(
        session.profile_id == admin.id for session in env.repo.sessions.values()
    )
    assert _status(env, "/asesor") == 303


def test_invalid_role_does_not_modify_profile(env, panel):
    """R3: un rol fuera de la lista responde 422 y no cambia el perfil."""
    profile = panel.login(env, "asesor")
    panel.login_admin(env)
    before = env.repo.profiles[profile.id].role
    response = env.client.post(
        f"/admin/profiles/{profile.id}/role",
        data={"csrf_token": panel.CSRF, "role": "superadmin"},
        follow_redirects=False,
    )
    assert response.status_code == 422
    assert env.repo.profiles[profile.id].role == before


def _login_with_password(env, username: str, role: str, password: str = "ClaveSegura123"):
    from orchestrator.accounts import hash_password

    env.repo.create_profile(
        username,
        role,
        hash_password(password, env.settings.password_hash_iterations),
        env.adapters.clock(),
    )
    return env.client.post(
        "/asesor/login",
        data={"username": username, "password": password},
        follow_redirects=False,
    )


def test_supervisor_can_login_at_advisor_login(env):
    """R6: un supervisor inicia sesión en /asesor/login y entra al panel."""
    response = _login_with_password(env, "super1", "supervisor")
    assert response.status_code == 303
    assert response.headers["location"] == "/asesor"
    assert "advisor_session" in response.cookies


def test_data_responsible_login_redirects_to_suppressions(env):
    """R21: el responsable de datos entra directo a la cola de supresión."""
    response = _login_with_password(env, "datos1", "responsable_datos")
    assert response.status_code == 303
    assert response.headers["location"] == "/asesor/supresiones"


# --- R5: el rol sale de la sesión, nunca del formulario/query ------------------


def test_role_is_read_from_session_profile(env, panel):
    """R5: cambiar el rol en el formulario no da acceso si la sesión no lo tiene."""
    panel.login(env, "asesor")
    response = env.client.get(
        "/asesor/todos?role=supervisor", follow_redirects=False
    )
    assert response.status_code == 403


# --- R25: matriz de rutas ------------------------------------------------------


@pytest.mark.parametrize(
    ("role", "path", "expected"),
    [
        ("admin", "/asesor", 303),
        ("asesor", "/asesor", 200),
        ("asesor", "/asesor/cases", 200),
        ("asesor", "/asesor/todos", 403),
        ("asesor", "/asesor/metricas", 403),
        ("supervisor", "/asesor", 200),
        ("supervisor", "/asesor/cases", 200),
        ("supervisor", "/asesor/todos", 200),
        ("supervisor", "/asesor/metricas", 200),
        ("supervisor", "/admin", 303),
        ("responsable_datos", "/asesor/cases", 403),
        ("responsable_datos", "/asesor/todos", 403),
        ("responsable_datos", "/asesor/metricas", 403),
        ("responsable_datos", "/admin", 303),
    ],
)
def test_panel_permission_matrix(env, panel, role, path, expected):
    """R25: cada ruta comprueba el rol de la sesión en el servidor."""
    _login(env, panel, role)
    assert _status(env, path) == expected


def test_data_responsible_home_redirects_to_suppressions(env, panel):
    """R21, R22b: responsable_datos en /asesor va a /asesor/supresiones."""
    _login(env, panel, "responsable_datos")
    response = env.client.get("/asesor", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/asesor/supresiones"


def test_data_responsible_sees_only_suppression_queue(env, panel):
    """R21: el responsable de datos ve la cola y su formulario CSRF."""
    _login(env, panel, "responsable_datos")
    response = env.client.get("/asesor/supresiones")
    assert response.status_code == 200
    assert "Cola de supresión" in response.text
    assert "/asesor/cases" not in response.text


def test_data_responsible_not_executor_is_forbidden(env_factory, panel):
    """R23d: si su rol no está configurado, no ve la cola aunque exista la ruta."""
    env = env_factory(
        admin_cookie_secure=False,
        password_hash_iterations=100000,
        suppression_executor_roles="admin",
    )
    _login(env, panel, "responsable_datos")
    response = env.client.get("/asesor/supresiones")
    assert response.status_code == 403
    assert 'data-code="forbidden"' in response.text


def test_supervisor_is_attending_advisor_in_roster(env, panel):
    """R6b, R7: supervisor entra al roster y mantiene las acciones de asesor."""
    supervisor = panel.login(env, "supervisor")
    asesor = panel.make_profile(env, "asesor2", "asesor", 701)
    env.repo.set_advisor_presence(asesor.id, "available", panel.NOW)
    response = env.client.post(
        "/asesor/assign",
        data={"csrf_token": panel.CSRF, "case_id": "case-1"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert env.handover.try_assigned == [("case-1", supervisor.id)]


# --- R26: un asesor no escala privilegios -------------------------------------


@pytest.mark.parametrize(
    "path", ["/asesor/todos", "/asesor/metricas"]
)
def test_advisor_cannot_force_supervisor_urls(env, panel, path):
    """R26: forzar la URL de supervisor devuelve 403 sin consultar handover."""
    panel.login(env, "asesor")
    response = env.client.get(path, follow_redirects=False)
    assert response.status_code == 403
    assert env.handover.listed_all == []


def test_advisor_cannot_open_another_advisors_case(env, panel):
    """R18, R26: el 403 de un caso ajeno no revela el caso ni quién lo tiene."""
    panel.login(env, "asesor")
    other = panel.make_profile(env, "asesor2", "asesor", 701)
    env.handover = FakeHandoverClient(authorized_advisors={other.id})
    env.adapters.handover = env.handover
    panel.link_case(env, "case-other")
    response = env.client.get("/asesor/cases/case-other", follow_redirects=False)
    assert response.status_code == 403

    # Ni el id del caso, ni el nombre ni el id del asesor ajeno aparecen.
    assert "case-other" not in response.text
    assert other.username not in response.text
    assert other.id not in response.text

    # Mismo cuerpo que el 403 de un caso inexistente: no se filtra su existencia.
    missing = env.client.get("/asesor/cases/case-missing", follow_redirects=False)
    assert missing.status_code == 403
    assert response.text == missing.text


def test_advisor_cannot_force_reassign_form(env, panel):
    """R26, R27: un asesor no reasigna ni con CSRF válido."""
    panel.login(env, "asesor")
    response = env.client.post(
        "/asesor/casos/case-1/reasignar",
        data={"csrf_token": panel.CSRF, "target_profile_id": "222"},
        follow_redirects=False,
    )
    assert response.status_code == 403
    assert env.handover.reassigned == []


def test_reassign_without_csrf_is_forbidden(env, panel):
    """R27: sin token CSRF no se llama a handover ni cambia estado."""
    _login(env, panel, "supervisor")
    response = env.client.post(
        "/asesor/casos/case-1/reasignar",
        data={"target_profile_id": "222"},
        follow_redirects=False,
    )
    assert response.status_code == 403
    assert env.handover.reassigned == []
    assert env.repo.panel_audit == []


def test_supervisor_cannot_access_admin_routes(env, panel):
    """R20: un supervisor no entra a ninguna ruta /admin/**."""
    _login(env, panel, "supervisor")
    for path in ("/admin", "/admin/profiles", "/admin/metricas", "/admin/clientes"):
        assert _status(env, path) == 303


def test_client_role_cannot_login_to_advisor_panel(env):
    """R25: con credenciales válidas, el rechazo depende del rol `cliente`."""
    denied = _login_with_password(env, "cliente1", "cliente")
    assert denied.status_code == 401
    assert "advisor_session" not in denied.cookies
    assert "Usuario o contraseña incorrectos." in denied.text

    # Contraste: la misma contraseña con rol `asesor` sí abre el panel.
    allowed = _login_with_password(env, "asesor2", "asesor")
    assert allowed.status_code == 303
    assert allowed.headers["location"] == "/asesor"
    assert "advisor_session" in allowed.cookies
