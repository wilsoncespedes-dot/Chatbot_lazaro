"""Administración de clientes y credenciales (#42)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from orchestrator.domain import (
    ClientSession,
    list_clients_admin,
    save_operational_settings,
)

PASSWORD = "clave-segura-123"
CSRF = "csrf-token"


@pytest.fixture()
def env(env_factory, panel):
    env = env_factory(admin_cookie_secure=False, password_hash_iterations=100000)
    panel.login_admin(env)
    return env


def _create(env, **changes):
    data = {
        "csrf_token": CSRF,
        "username": "cliente1",
        "password": PASSWORD,
    }
    data.update(changes)
    return env.client.post("/admin/clientes", data=data, follow_redirects=False)


def _csrf_accepts(env):
    page = env.client.get("/admin/clientes")
    assert page.status_code == 200
    return page


def test_clients_table_shows_state_days_session_and_notice(env):
    """R1: la tabla lista usuario, estado, fechas, días, sesión y aviso."""
    assert _create(env).status_code == 303
    profile = next(p for p in env.repo.profiles.values() if p.username == "cliente1")
    env.repo.client_sessions["s1"] = ClientSession(
        id="s1",
        profile_id=profile.id,
        contact_id="c1",
        started_at=env.adapters.clock(),
        last_activity_at=env.adapters.clock(),
    )
    assert env.repo.current_expiry_notice_status(profile.id, env.repo.client_credentials[profile.id].valid_until) is None
    page = _csrf_accepts(env)
    assert page.status_code == 200
    assert "cliente1" in page.text
    assert "vigente" in page.text
    assert "Sí" in page.text


def test_days_and_state_are_calculated_from_dates_without_counter(env):
    """R2: avanzar el reloj cambia días y estado sin escribir contadores."""
    assert _create(env).status_code == 303
    profile = next(p for p in env.repo.profiles.values() if p.username == "cliente1")
    rows = list_clients_admin(env.settings, env.adapters)
    assert rows[0].days_remaining == 30
    env.adapters.clock = lambda: datetime(
        2026, 1, 29, 3, 4, 5, tzinfo=timezone.utc
    )
    rows = list_clients_admin(env.settings, env.adapters)
    assert rows[0].days_remaining == 3
    assert rows[0].status == "por_vencer"
    assert not hasattr(env.repo.client_credentials[profile.id], "days_remaining")


def test_create_without_dates_uses_configured_validity_days(env):
    """R4, R40: sin fechas usa identity.validity_days efectivo, cambiado en caliente."""
    actor = next(
        profile for profile in env.repo.list_profiles() if profile.role == "admin"
    )
    save_operational_settings(
        {"identity.validity_days": "10"}, actor, env.settings, env.adapters
    )
    assert _create(env).status_code == 303
    profile = next(p for p in env.repo.profiles.values() if p.username == "cliente1")
    credential = env.repo.client_credentials[profile.id]
    assert credential.valid_until - credential.valid_from == timedelta(days=10)


def test_create_with_explicit_dates(env):
    """R3, R4: las fechas AAAA-MM-DD se guardan en la credencial."""
    assert _create(
        env, valid_from="2026-02-01", valid_until="2026-03-01"
    ).status_code == 303
    profile = next(p for p in env.repo.profiles.values() if p.username == "cliente1")
    credential = env.repo.client_credentials[profile.id]
    assert credential.valid_from == datetime(2026, 2, 1, 5, 0, tzinfo=timezone.utc)
    assert credential.valid_until == datetime(2026, 3, 1, 5, 0, tzinfo=timezone.utc)


@pytest.mark.parametrize(
    "changes",
    [
        {"username": "ab"},
        {"username": "con espacio"},
        {"password": "corta"},
        {"valid_from": "2026-13-01"},
        {"valid_from": "2026-03-01", "valid_until": "2026-02-01"},
    ],
)
def test_invalid_client_returns_422_without_echoing_password(env, changes):
    """R5: datos inválidos devuelven 422 sin crear ni repetir la contraseña."""
    response = _create(env, **changes)
    assert response.status_code == 422
    assert "cliente1" not in env.repo.profiles.values().__repr__()
    assert PASSWORD not in response.text


def test_duplicate_client_returns_409(env):
    """R6: un usuario existente devuelve 409 username_taken sin filas nuevas."""
    assert _create(env).status_code == 303
    before = len(env.repo.profiles)
    response = _create(env)
    assert response.status_code == 409
    assert "username_taken" in response.text
    assert len(env.repo.profiles) == before


def test_renew_from_expired_and_valid(env):
    """R7: renovar extiende desde max(valid_until, now) en ambos casos."""
    assert _create(
        env, username="viejo", valid_from="2025-01-01", valid_until="2025-02-01"
    ).status_code == 303
    old = next(p for p in env.repo.profiles.values() if p.username == "viejo")
    assert env.client.post(
        f"/admin/clientes/{old.id}/renovar",
        data={"csrf_token": CSRF},
        follow_redirects=False,
    ).status_code == 303
    credential = env.repo.client_credentials[old.id]
    assert credential.valid_until == panel_now(env) + timedelta(days=30)

    assert _create(env, username="vigente").status_code == 303
    current = next(p for p in env.repo.profiles.values() if p.username == "vigente")
    previous = env.repo.client_credentials[current.id].valid_until
    env.client.post(
        f"/admin/clientes/{current.id}/renovar",
        data={"csrf_token": CSRF},
        follow_redirects=False,
    )
    assert env.repo.client_credentials[current.id].valid_until == previous + timedelta(
        days=30
    )


def panel_now(env):
    return env.adapters.clock()


def test_renew_revoked_returns_409_and_does_not_change(env):
    """R8: renovar una credencial revocada devuelve 409 sin modificarla."""
    assert _create(env).status_code == 303
    profile = next(p for p in env.repo.profiles.values() if p.username == "cliente1")
    env.client.post(
        f"/admin/clientes/{profile.id}/revocar",
        data={"csrf_token": CSRF},
        follow_redirects=False,
    )
    before = env.repo.client_credentials[profile.id].valid_until
    response = env.client.post(
        f"/admin/clientes/{profile.id}/renovar",
        data={"csrf_token": CSRF},
        follow_redirects=False,
    )
    assert response.status_code == 409
    assert "credential_revoked" in response.text
    assert env.repo.client_credentials[profile.id].valid_until == before


def test_revoke_closes_active_session(env):
    """R9: revocar cierra la sesión activa."""
    assert _create(env).status_code == 303
    profile = next(p for p in env.repo.profiles.values() if p.username == "cliente1")
    env.repo.client_sessions["s1"] = ClientSession(
        id="s1", profile_id=profile.id, contact_id="c1",
        started_at=panel_now(env), last_activity_at=panel_now(env),
    )
    response = env.client.post(
        f"/admin/clientes/{profile.id}/revocar",
        data={"csrf_token": CSRF},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert env.repo.client_sessions["s1"].ended_at is not None
    assert env.repo.client_credentials[profile.id].revoked_at is not None


def test_close_session_does_not_change_dates(env):
    """R10: cerrar sesión no toca valid_from, valid_until ni revoked_at."""
    assert _create(env).status_code == 303
    profile = next(p for p in env.repo.profiles.values() if p.username == "cliente1")
    credential = env.repo.client_credentials[profile.id]
    before = (credential.valid_from, credential.valid_until, credential.revoked_at)
    env.repo.client_sessions["s1"] = ClientSession(
        id="s1", profile_id=profile.id, contact_id="c1",
        started_at=panel_now(env), last_activity_at=panel_now(env),
    )
    response = env.client.post(
        f"/admin/clientes/{profile.id}/cerrar-sesion",
        data={"csrf_token": CSRF},
        follow_redirects=False,
    )
    assert response.status_code == 303
    credential = env.repo.client_credentials[profile.id]
    assert (credential.valid_from, credential.valid_until, credential.revoked_at) == before
    assert env.repo.client_sessions["s1"].ended_at is not None


@pytest.mark.parametrize("action", ["renovar", "revocar", "cerrar-sesion"])
def test_unknown_client_returns_404(env, action):
    """R11: un profile_id sin credencial responde 404 client_not_found."""
    response = env.client.post(
        f"/admin/clientes/no-existe/{action}",
        data={"csrf_token": CSRF},
        follow_redirects=False,
    )
    assert response.status_code == 404
    assert "client_not_found" in response.text


def test_sending_notice_period_is_shown_in_client_table(env):
    """S2: una fila `sending` huérfana se muestra como `sending` en el panel."""
    assert _create(env).status_code == 303
    profile = next(p for p in env.repo.profiles.values() if p.username == "cliente1")
    valid_until = env.repo.client_credentials[profile.id].valid_until
    env.repo.expiry_notices[(profile.id, valid_until)] = {
        "status": "sending",
        "method": None,
        "attempts": 1,
        "created_at": panel_now(env),
        "updated_at": panel_now(env),
    }
    page = _csrf_accepts(env)
    assert "sending" in page.text


def test_client_actions_are_audited_without_password(env):
    """R44: las acciones client_* se auditan con profile_id y sin contraseña."""
    assert _create(env).status_code == 303
    profile = next(p for p in env.repo.profiles.values() if p.username == "cliente1")
    env.client.post(
        f"/admin/clientes/{profile.id}/renovar",
        data={"csrf_token": CSRF},
        follow_redirects=False,
    )
    actions = {row.action for row in env.repo.panel_audit}
    assert {"client_create", "client_renew"} <= actions
    assert all(PASSWORD not in (row.target or "") for row in env.repo.panel_audit)
