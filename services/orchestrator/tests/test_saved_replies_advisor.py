"""Uso de respuestas guardadas desde la vista de conversación (#51)."""
from __future__ import annotations

from orchestrator.domain import SavedReply

from fakes import drain_queues


def _add_reply(
    env,
    panel,
    reply_id: str = "reply-1",
    title: str = "Saludo",
    body: str = "Hola cliente",
    active: bool = True,
) -> SavedReply:
    reply = SavedReply(
        id=reply_id,
        title=title,
        body=body,
        active=active,
        updated_at=panel.NOW,
    )
    env.repo.add_saved_reply(reply)
    return reply


def test_selector_lists_only_active_titles(env_factory, panel):
    """R13: el selector ofrece solo títulos de respuestas activas."""
    env = env_factory()
    panel.login(env)
    panel.link_case(env, "case-1")
    _add_reply(env, panel, "reply-1", "Saludo activo", "Cuerpo activo")
    _add_reply(env, panel, "reply-off", "Vieja", "Cuerpo viejo", active=False)

    response = env.client.get("/asesor/cases/case-1")

    assert response.status_code == 200
    assert 'name="respuesta"' in response.text
    assert "Saludo activo" in response.text
    assert "Vieja" not in response.text
    assert "Cuerpo activo" not in response.text


def test_loading_a_reply_prefills_textarea_without_sending(env_factory, panel):
    """R14, R15: carga en el textarea y no envía nada al cliente."""
    env = env_factory()
    panel.login(env)
    panel.link_case(env, "case-1")
    reply = _add_reply(env, panel, body="Cuerpo para editar")

    response = env.client.get(f"/asesor/cases/case-1?respuesta={reply.id}")

    assert response.status_code == 200
    assert "Cuerpo para editar" in response.text
    assert env.gateway.sent == []
    assert env.gateway.channel_sent == []
    assert env.gateway.blocks_sent == []


def test_advisor_can_edit_loaded_reply_before_sending(env_factory, panel):
    """R16, R19: se envía el texto editado y se aplican las reglas de respuesta."""
    env = env_factory()
    profile = panel.login(env)
    panel.link_case(env, "case-1")
    reply = _add_reply(env, panel, body="Texto original")

    loaded = env.client.get(f"/asesor/cases/case-1?respuesta={reply.id}")
    assert loaded.status_code == 200

    sent = env.client.post(
        "/asesor/reply",
        data={
            "csrf_token": panel.CSRF,
            "case_id": "case-1",
            "text": "Texto editado por el asesor",
        },
        follow_redirects=False,
    )
    drain_queues(env.settings, env.adapters)

    assert sent.status_code == 303
    assert (100, "Texto editado por el asesor") in env.gateway.sent
    assert all("Texto original" not in text for _, text in env.gateway.sent)
    assert ("case-1", profile.id, "reply") in env.handover.authorized


def test_inactive_or_missing_reply_shows_empty_field_and_notice(env_factory, panel):
    """R17: respuesta desactivada o inexistente -> campo vacío con aviso."""
    env = env_factory()
    panel.login(env)
    panel.link_case(env, "case-1")
    _add_reply(env, panel, "reply-off", body="No debe cargarse", active=False)

    for reply_id in ("reply-off", "no-existe"):
        response = env.client.get(f"/asesor/cases/case-1?respuesta={reply_id}")
        assert response.status_code == 200
        assert "No debe cargarse" not in response.text
        assert "La respuesta guardada no existe o está desactivada." in response.text
        assert (
            '<textarea name="text" maxlength="4096" required></textarea>'
            in response.text
        )


def test_closed_whatsapp_window_hides_selector_and_ignores_forced_reply(
    env_factory, panel
):
    """R18: con la ventana cerrada no se ofrecen ni cargan respuestas guardadas."""
    env = env_factory()
    panel.login(env)
    panel.link_case(
        env, "case-1", channel="whatsapp", user="57300", chat="57301"
    )
    reply = _add_reply(env, panel, body="Cuerpo guardado")

    response = env.client.get(f"/asesor/cases/case-1?respuesta={reply.id}")

    assert response.status_code == 200
    assert "Plantilla" in response.text
    assert 'name="respuesta"' not in response.text
    assert "Cuerpo guardado" not in response.text


def test_unauthorized_case_does_not_reveal_saved_reply(env_factory, panel):
    """R20: sin autorización no se revela el texto guardado."""
    env = env_factory()
    panel.login(env)
    panel.link_case(env, "case-1")
    reply = _add_reply(env, panel, body="SECRETO")
    env.handover.authorize_error = "forbidden"

    with_param = env.client.get(f"/asesor/cases/case-1?respuesta={reply.id}")
    without_param = env.client.get("/asesor/cases/case-1")

    assert with_param.status_code == 403
    assert without_param.status_code == 403
    assert "SECRETO" not in with_param.text


def test_saved_reply_text_is_escaped_and_not_interpolated(env_factory, panel):
    """R21, R22: se escapa el HTML y no se sustituyen datos del cliente."""
    env = env_factory()
    panel.login(env)
    panel.link_case(env, "case-1")
    reply = _add_reply(
        env,
        panel,
        title="<script>t</script>",
        body="Hola {username} <b>x</b>",
    )

    response = env.client.get(f"/asesor/cases/case-1?respuesta={reply.id}")

    assert response.status_code == 200
    assert "&lt;script&gt;t&lt;/script&gt;" in response.text
    assert "Hola {username} &lt;b&gt;x&lt;/b&gt;" in response.text
    assert "<b>x</b>" not in response.text
    assert "Hola asesor1" not in response.text


def test_sending_from_closed_whatsapp_window_is_blocked(env_factory, panel):
    """R19: el envío conserva la verificación de la ventana de WhatsApp."""
    env = env_factory()
    panel.login(env)
    panel.link_case(
        env, "case-1", channel="whatsapp", user="57300", chat="57301"
    )

    response = env.client.post(
        "/asesor/reply",
        data={"csrf_token": panel.CSRF, "case_id": "case-1", "text": "Hola"},
        follow_redirects=False,
    )

    assert response.status_code == 409
    assert env.gateway.sent == []
    assert env.gateway.channel_sent == []
