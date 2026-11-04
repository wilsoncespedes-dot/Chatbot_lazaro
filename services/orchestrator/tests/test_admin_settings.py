"""Ajustes operativos y horarios (#42)."""
from __future__ import annotations

from datetime import timedelta

import pytest

from orchestrator.domain import (
    create_client,
    list_clients_admin,
    operational_settings,
)

PASSWORD = "clave-segura-123"
CSRF = "csrf-token"


@pytest.fixture()
def env(env_factory, panel):
    env = env_factory(admin_cookie_secure=False, password_hash_iterations=100000)
    panel.login_admin(env)
    return env


def _save(env, **changes):
    data = {"csrf_token": CSRF, **changes}
    return env.client.post("/admin/ajustes", data=data, follow_redirects=False)


def test_settings_page_shows_effective_default_origin_and_range(env):
    """R36: cada clave muestra efectivo, por defecto, origen y rango."""
    page = env.client.get("/admin/ajustes")
    assert page.status_code == 200
    assert "identity.validity_days" in page.text
    assert "business_hours.start" in page.text
    assert "entorno" in page.text
    assert "1..366" in page.text
    assert "HH:MM" in page.text


def test_valid_settings_are_saved_in_app_settings(env):
    """R37: los valores válidos se guardan y se leen como efectivos."""
    response = _save(
        env,
        **{
            "identity.validity_days": "10",
            "business_hours.enabled": "true",
            "business_hours.start": "08:00",
            "business_hours.end": "18:00",
        },
    )
    assert response.status_code == 303
    stored = env.repo.get_app_settings(
        ("identity.", "business_hours.")
    )
    assert stored["identity.validity_days"] == "10"
    assert stored["business_hours.enabled"] == "true"
    effective = operational_settings(env.settings, env.adapters)
    assert effective.identity.validity_days == 10
    assert effective.hours.enabled is True
    assert effective.hours.start.strftime("%H:%M") == "08:00"


def test_invalid_settings_save_nothing(env):
    """R38: un valor inválido invalida todo el formulario."""
    before = env.repo.get_app_settings(("identity.", "suppression."))
    response = _save(
        env,
        **{
            "identity.validity_days": "10",
            "suppression.due_soon_business_days": "15",
        },
    )
    assert response.status_code == 422
    assert env.repo.get_app_settings(("identity.", "suppression.")) == before


def test_empty_value_deletes_key_and_restores_default(env):
    """R74: un valor vacío elimina la clave para que rija el entorno."""
    assert _save(env, **{"identity.validity_days": "10"}).status_code == 303
    assert "identity.validity_days" in env.repo.get_app_settings(("identity.",))
    assert _save(env, **{"identity.validity_days": ""}).status_code == 303
    assert "identity.validity_days" not in env.repo.get_app_settings(("identity.",))
    assert (
        operational_settings(env.settings, env.adapters).identity.validity_days
        == env.settings.credential_validity_days
    )


def test_effective_change_applies_to_client_status_without_restart(env):
    """R40: el nuevo expiry_notice_days cambia el estado por_vencer sin reiniciar."""
    create_client(
        "cliente1",
        PASSWORD,
        None,
        env.adapters.clock() + timedelta(days=2),
        env.settings,
        env.adapters,
    )
    assert _save(env, **{"identity.expiry_notice_days": "1"}).status_code == 303
    assert list_clients_admin(env.settings, env.adapters)[0].status == "vigente"
    assert _save(env, **{"identity.expiry_notice_days": "3"}).status_code == 303
    assert list_clients_admin(env.settings, env.adapters)[0].status == "por_vencer"


def test_settings_update_is_audited_per_key(env):
    """R44: settings_update se audita con cada clave modificada."""
    assert _save(
        env,
        **{
            "identity.validity_days": "12",
            "business_hours.enabled": "true",
        },
    ).status_code == 303
    targets = {
        row.target
        for row in env.repo.panel_audit
        if row.action == "settings_update"
    }
    assert {"identity.validity_days", "business_hours.enabled"} <= targets
