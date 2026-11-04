"""Plantillas de WhatsApp y su aprobación (#42)."""
from __future__ import annotations

import pytest

from orchestrator.domain import (
    PanelValidationError,
    advisor_send_template,
    change_template_status,
    create_template,
    effective_templates_for,
    execute_suppression_from_panel,
    update_template,
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
        "name": "respuesta_nueva",
        "purpose": "advisor_reply",
        "language": "es",
        "variables": "2",
        "body": "Hola {{1}}, tu caso {{2}}",
    }
    data.update(changes)
    return env.client.post("/admin/plantillas", data=data, follow_redirects=False)


def _admin(env):
    return next(p for p in env.repo.list_profiles() if p.role == "admin")


def test_create_valid_template_in_draft(env):
    """R25, R26: la plantilla se crea en `draft` y aparece en el listado."""
    assert _create(env).status_code == 303
    template = env.repo.whatsapp_templates["respuesta_nueva"]
    assert template.status == "draft"
    assert template.approved_by is None
    page = env.client.get("/admin/plantillas")
    assert "respuesta_nueva" in page.text
    assert "draft" in page.text


@pytest.mark.parametrize(
    "changes",
    [
        {"name": "Mayusculas"},
        {"purpose": "otro"},
        {"language": "es-ES"},
        {"variables": "11"},
        {"variables": "-1"},
        {"body": ""},
    ],
)
def test_invalid_template_returns_422(env, changes):
    """R27: un campo inválido devuelve 422 sin crear la plantilla."""
    response = _create(env, **changes)
    assert response.status_code == 422
    assert env.repo.whatsapp_templates == {}


def test_duplicate_template_returns_409(env):
    """R28: nombre repetido devuelve 409 template_exists."""
    assert _create(env).status_code == 303
    response = _create(env)
    assert response.status_code == 409
    assert "template_exists" in response.text


def test_allowed_transitions_register_approver_and_invalid_rejected(env):
    """R29, R30: transiciones válidas con autor/fecha y las inválidas con 409."""
    assert _create(env).status_code == 303
    assert env.client.post(
        "/admin/plantillas/respuesta_nueva/estado",
        data={"csrf_token": CSRF, "status": "pending"},
        follow_redirects=False,
    ).status_code == 303
    assert env.client.post(
        "/admin/plantillas/respuesta_nueva/estado",
        data={"csrf_token": CSRF, "status": "approved"},
        follow_redirects=False,
    ).status_code == 303
    template = env.repo.whatsapp_templates["respuesta_nueva"]
    assert template.status == "approved"
    assert template.approved_by == _admin(env).id
    assert template.approved_at == env.adapters.clock()

    before = template
    response = env.client.post(
        "/admin/plantillas/respuesta_nueva/estado",
        data={"csrf_token": CSRF, "status": "pending"},
        follow_redirects=False,
    )
    assert response.status_code == 409
    assert "invalid_transition" in response.text
    assert env.repo.whatsapp_templates["respuesta_nueva"] == before


def test_edit_returns_to_draft_and_clears_approval(env):
    """R31: editar idioma, variables o texto vuelve a `draft` y borra aprobación."""
    assert _create(env).status_code == 303
    actor = _admin(env)
    change_template_status("respuesta_nueva", "pending", actor, env.adapters)
    change_template_status("respuesta_nueva", "approved", actor, env.adapters)
    response = env.client.post(
        "/admin/plantillas/respuesta_nueva",
        data={
            "csrf_token": CSRF,
            "language": "en",
            "variables": "1",
            "body": "Nuevo texto",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    template = env.repo.whatsapp_templates["respuesta_nueva"]
    assert template.status == "draft"
    assert template.approved_by is None and template.approved_at is None
    assert (template.language, template.variables, template.body) == (
        "en", 1, "Nuevo texto",
    )


def test_effective_templates_use_approved_only_and_env_when_empty(env):
    """R32, R34: con registro solo cuentan las aprobadas; sin registro, entorno."""
    assert effective_templates_for("advisor_reply", env.settings, env.adapters) == (
        "respuesta_asesor",
    )
    create_template("borrador", "advisor_reply", "es", "0", "Hola", _admin(env), env.adapters)
    create_template("aprobada", "advisor_reply", "es", "0", "Hola", _admin(env), env.adapters)
    change_template_status("aprobada", "pending", _admin(env), env.adapters)
    change_template_status("aprobada", "approved", _admin(env), env.adapters)
    assert effective_templates_for("advisor_reply", env.settings, env.adapters) == (
        "aprobada",
    )


def test_unapproved_template_is_rejected_without_gateway(env):
    """R72: una plantilla no efectiva responde 422 sin llamar al gateway."""
    create_template("borrador", "advisor_reply", "es", "0", "Hola", _admin(env), env.adapters)
    contact = env.repo.get_or_create_channel_contact(
        "whatsapp", "57300", "57300", env.adapters.clock()
    )
    env.repo.link_case("case-1", contact.id, env.adapters.clock())
    with pytest.raises(PanelValidationError):
        advisor_send_template(
            "case-1", "700", "borrador", env.settings, env.adapters
        )
    assert env.gateway.blocks_sent == []


def _suppression_request(env):
    contact = env.repo.get_or_create_channel_contact(
        "whatsapp", "57300", "57300", env.adapters.clock()
    )
    env.repo.create_or_get_pending_suppression(
        "req-1", "p-cliente", contact.id, "whatsapp", env.adapters.clock()
    )
    return contact


def test_suppression_uses_approved_template_or_skips(env):
    """R35, R73: usa la primera plantilla efectiva o queda `skipped` sin gateway."""
    _suppression_request(env)
    actor = _admin(env)
    create_template(
        "borrador_sup", "suppression_result", "es", "0", "Hola", actor, env.adapters
    )
    execute_suppression_from_panel("req-1", actor, None, env.settings, env.adapters)
    assert env.repo.suppression_requests["req-1"].notification_result == "skipped"
    assert env.gateway.blocks_sent == []

    _suppression_request(env)
    create_template(
        "resultado_ok", "suppression_result", "es", "0", "Hola", actor, env.adapters
    )
    change_template_status("resultado_ok", "pending", actor, env.adapters)
    change_template_status("resultado_ok", "approved", actor, env.adapters)
    env.repo.suppression_requests["req-1"].status = "pending"
    execute_suppression_from_panel("req-1", actor, None, env.settings, env.adapters)
    assert env.repo.suppression_requests["req-1"].notification_result == "template"
    assert env.gateway.blocks_sent[-1][2][0].name == "resultado_ok"


def test_template_actions_are_audited_with_name(env):
    """R44: template_* se auditan con el nombre como destino."""
    assert _create(env).status_code == 303
    env.client.post(
        "/admin/plantillas/respuesta_nueva/estado",
        data={"csrf_token": CSRF, "status": "pending"},
        follow_redirects=False,
    )
    rows = [row for row in env.repo.panel_audit if row.action.startswith("template_")]
    assert {row.action for row in rows} == {"template_create", "template_status"}
    assert all(row.target == "respuesta_nueva" for row in rows)
