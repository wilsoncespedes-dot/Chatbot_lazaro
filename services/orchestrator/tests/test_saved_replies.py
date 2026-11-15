"""Administración de respuestas guardadas (#51)."""
from __future__ import annotations

import pytest

from orchestrator.domain import SavedReply


def _create(env, panel, title: str = "Saludo", body: str = "Hola cliente"):
    return env.client.post(
        "/admin/respuestas",
        data={"csrf_token": panel.CSRF, "title": title, "body": body},
        follow_redirects=False,
    )


def _add_reply(env, panel, reply_id: str = "reply-1", **kwargs) -> SavedReply:
    reply = SavedReply(
        id=reply_id,
        title=kwargs.get("title", "Saludo"),
        body=kwargs.get("body", "Hola cliente"),
        active=kwargs.get("active", True),
        updated_at=panel.NOW,
    )
    env.repo.add_saved_reply(reply)
    return reply


def test_admin_can_create_update_and_toggle_saved_replies(env_factory, panel):
    """R1-R5, R12: CRUD del administrador, auditoría y lista con estados."""
    env = env_factory()
    panel.login_admin(env)

    created = _create(env, panel)
    assert created.status_code == 303
    assert created.headers["location"] == "/admin/respuestas"
    [reply] = env.repo.list_saved_replies()
    assert (reply.title, reply.body, reply.active) == ("Saludo", "Hola cliente", True)

    listed = env.client.get("/admin/respuestas")
    assert listed.status_code == 200
    assert "Saludo" in listed.text and "Hola cliente" in listed.text
    assert "Respuestas guardadas" in listed.text

    updated = env.client.post(
        f"/admin/respuestas/{reply.id}",
        data={
            "csrf_token": panel.CSRF,
            "title": "Saludo editado",
            "body": "Texto editado",
        },
        follow_redirects=False,
    )
    assert updated.status_code == 303
    current = env.repo.get_saved_reply(reply.id)
    assert (current.title, current.body) == ("Saludo editado", "Texto editado")

    off = env.client.post(
        f"/admin/respuestas/{reply.id}/activa",
        data={"csrf_token": panel.CSRF, "active": "0"},
        follow_redirects=False,
    )
    assert off.status_code == 303
    assert env.repo.get_saved_reply(reply.id).active is False
    listed_off = env.client.get("/admin/respuestas")
    assert "Saludo editado" in listed_off.text and "No" in listed_off.text

    on = env.client.post(
        f"/admin/respuestas/{reply.id}/activa",
        data={"csrf_token": panel.CSRF, "active": "1"},
        follow_redirects=False,
    )
    assert on.status_code == 303
    assert env.repo.get_saved_reply(reply.id).active is True

    audits = [
        row
        for row in env.repo.panel_audit
        if row.action.startswith("saved_reply_")
    ]
    assert [row.action for row in audits] == [
        "saved_reply_created",
        "saved_reply_updated",
        "saved_reply_active_changed",
        "saved_reply_active_changed",
    ]
    assert all(row.result == "ok" for row in audits)
    assert audits[0].target == reply.id
    assert all(row.target == reply.id for row in audits)
    assert "Saludo editado" not in repr(audits)
    assert "Texto editado" not in repr(audits)


@pytest.mark.parametrize(
    "role", ["asesor", "supervisor", "responsable_datos", "cliente"]
)
def test_non_admin_cannot_manage_saved_replies(env_factory, panel, role):
    """R6: cualquier perfil no admin recibe 403 y se audita el intento."""
    env = env_factory()
    existing = _add_reply(env, panel)
    panel.login(env, role=role)
    env.client.cookies.set("admin_session", f"{role}-session")

    read = env.client.get("/admin/respuestas", follow_redirects=False)
    write = env.client.post(
        "/admin/respuestas",
        data={"csrf_token": panel.CSRF, "title": "No", "body": "No"},
        follow_redirects=False,
    )
    edit = env.client.post(
        f"/admin/respuestas/{existing.id}",
        data={"csrf_token": panel.CSRF, "title": "No", "body": "No"},
        follow_redirects=False,
    )

    assert (read.status_code, write.status_code, edit.status_code) == (403, 403, 403)
    assert [reply.id for reply in env.repo.list_saved_replies()] == [existing.id]
    assert env.repo.get_saved_reply(existing.id).title == "Saludo"
    assert any(
        row.action == "saved_replies_viewed" and row.result == "forbidden"
        for row in env.repo.panel_audit
    )
    assert any(
        row.action == "saved_reply_created" and row.result == "forbidden"
        for row in env.repo.panel_audit
    )


def test_saved_reply_routes_require_session(env_factory, panel):
    """R7: sin sesión se redirige al login y no se guarda nada."""
    env = env_factory()

    read = env.client.get("/admin/respuestas", follow_redirects=False)
    write = env.client.post(
        "/admin/respuestas",
        data={"title": "No", "body": "No"},
        follow_redirects=False,
    )

    assert read.status_code == 303
    assert read.headers["location"] == "/admin/login"
    assert write.status_code == 303
    assert write.headers["location"] == "/admin/login"
    assert env.repo.list_saved_replies() == []


def test_saved_reply_routes_require_csrf(env_factory, panel):
    """R7: sin token CSRF válido responde 403 sin modificar datos."""
    env = env_factory()
    panel.login_admin(env)
    existing = _add_reply(env, panel)

    created = env.client.post(
        "/admin/respuestas",
        data={"title": "Nueva", "body": "Texto"},
        follow_redirects=False,
    )
    edited = env.client.post(
        f"/admin/respuestas/{existing.id}",
        data={"csrf_token": "otro", "title": "Cambio", "body": "Cambio"},
        follow_redirects=False,
    )
    toggled = env.client.post(
        f"/admin/respuestas/{existing.id}/activa",
        data={"active": "0"},
        follow_redirects=False,
    )

    assert (created.status_code, edited.status_code, toggled.status_code) == (
        403,
        403,
        403,
    )
    [reply] = env.repo.list_saved_replies()
    assert (reply.id, reply.title, reply.active) == (existing.id, "Saludo", True)


@pytest.mark.parametrize(
    "overrides,data",
    [
        ({}, {"title": "", "body": "Texto"}),
        ({}, {"title": "   ", "body": "Texto"}),
        ({}, {"title": "Título", "body": ""}),
        ({}, {"title": "Título", "body": "   "}),
        ({"saved_reply_title_max_chars": 5}, {"title": "123456", "body": "Texto"}),
        ({"saved_reply_text_max_chars": 5}, {"title": "Título", "body": "123456"}),
        ({}, {"title": "a\tb", "body": "Texto"}),
        ({}, {"title": "Título", "body": "a\tb"}),
    ],
)
def test_invalid_saved_replies_are_rejected(env_factory, panel, overrides, data):
    """R8: vacío, demasiado largo o con controles -> 422 sin guardar."""
    env = env_factory(**overrides)
    panel.login_admin(env)

    response = env.client.post(
        "/admin/respuestas",
        data={"csrf_token": panel.CSRF, **data},
        follow_redirects=False,
    )

    assert response.status_code == 422
    assert env.repo.list_saved_replies() == []
    assert env.repo.panel_audit[-1].result == "validation_error"


@pytest.mark.parametrize(
    "data",
    [
        {"title": "Hola {nombre}", "body": "Texto"},
        {"title": "Hola }", "body": "Texto"},
        {"title": "Título", "body": "${cliente}"},
        {"title": "Título", "body": "%(id)s"},
    ],
)
def test_variables_are_rejected_with_specific_code(env_factory, panel, data):
    """R9: marcadores de variable -> 422 `saved_reply_variables_not_allowed`."""
    env = env_factory()
    panel.login_admin(env)

    response = env.client.post(
        "/admin/respuestas",
        data={"csrf_token": panel.CSRF, **data},
        follow_redirects=False,
    )

    assert response.status_code == 422
    assert "saved_reply_variables_not_allowed" in response.text
    assert env.repo.list_saved_replies() == []


def test_update_rejects_invalid_or_variable_text(env_factory, panel):
    """R8, R9: la edición valida igual que la creación y no guarda parciales."""
    env = env_factory()
    existing = _add_reply(env, panel)
    panel.login_admin(env)

    invalid = env.client.post(
        f"/admin/respuestas/{existing.id}",
        data={"csrf_token": panel.CSRF, "title": "", "body": "Texto"},
        follow_redirects=False,
    )
    variables = env.client.post(
        f"/admin/respuestas/{existing.id}",
        data={"csrf_token": panel.CSRF, "title": "Título", "body": "{nombre}"},
        follow_redirects=False,
    )

    assert invalid.status_code == 422
    assert variables.status_code == 422
    assert "saved_reply_variables_not_allowed" in variables.text
    current = env.repo.get_saved_reply(existing.id)
    assert (current.title, current.body) == ("Saludo", "Hola cliente")


def test_saved_replies_limit_is_enforced(env_factory, panel):
    """R10: alcanzado SAVED_REPLIES_MAX -> 422 sin guardar."""
    env = env_factory(saved_replies_max=1)
    panel.login_admin(env)

    assert _create(env, panel, title="Primera", body="Uno").status_code == 303
    second = _create(env, panel, title="Segunda", body="Dos")

    assert second.status_code == 422
    [reply] = env.repo.list_saved_replies()
    assert reply.title == "Primera"


def test_missing_saved_reply_returns_404(env_factory, panel):
    """R11: editar o cambiar el estado de un id inexistente -> 404."""
    env = env_factory()
    panel.login_admin(env)

    edited = env.client.post(
        "/admin/respuestas/no-existe",
        data={"csrf_token": panel.CSRF, "title": "Título", "body": "Texto"},
        follow_redirects=False,
    )
    toggled = env.client.post(
        "/admin/respuestas/no-existe/activa",
        data={"csrf_token": panel.CSRF, "active": "0"},
        follow_redirects=False,
    )

    assert edited.status_code == 404
    assert toggled.status_code == 404
    assert "saved_reply_not_found" in edited.text
    assert "saved_reply_not_found" in toggled.text


def test_saved_reply_page_escapes_title_and_body(env_factory, panel):
    """R21: título y texto se escapan en la página de administración."""
    env = env_factory()
    _add_reply(
        env,
        panel,
        title="<script>alert(1)</script>",
        body="<b>hola</b>",
    )
    panel.login_admin(env)

    response = env.client.get("/admin/respuestas")

    assert response.status_code == 200
    assert "<script>alert(1)</script>" not in response.text
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in response.text
    assert "<b>hola</b>" not in response.text
    assert "&lt;b&gt;hola&lt;/b&gt;" in response.text
