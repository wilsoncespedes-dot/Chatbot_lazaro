"""Responder y plantillas del panel multicanal (#41)."""
from __future__ import annotations

from datetime import timedelta

import pytest
from lazaro_contracts import TemplateBlock


def _post(env, path: str, data: dict):
    return env.client.post(path, data=data, follow_redirects=False)


def _whatsapp_case(env, panel, case_id: str = "case-1", last_user_at=None):
    contact = panel.link_case(
        env, case_id, channel="whatsapp", user="57300", chat="57301"
    )
    if last_user_at is not None:
        panel.add_message(env, contact, "user", "hola", last_user_at)
    return contact


def test_reply_telegram_uses_gateway_send(env_factory, panel):
    """R14: un caso Telegram entrega con gateway.send y guarda el mensaje."""
    env = env_factory()
    panel.login(env)
    contact = panel.link_case(env)
    response = _post(
        env,
        "/asesor/reply",
        {"csrf_token": panel.CSRF, "case_id": "case-1", "text": "Hola cliente"},
    )
    assert response.status_code == 303
    assert (contact.chat_id, "Hola cliente") in env.gateway.sent
    assert env.handover.authorized == [("case-1", "700", "reply")]
    advisor = [m for m in env.repo.messages if m.role == "advisor"]
    assert [m.text for m in advisor] == ["Hola cliente"]


def test_reply_whatsapp_open_uses_channel_send(env_factory, panel):
    """R14: un caso WhatsApp con ventana abierta usa send_channel."""
    env = env_factory()
    panel.login(env)
    _whatsapp_case(env, panel, last_user_at=panel.NOW - timedelta(hours=1))
    response = _post(
        env,
        "/asesor/reply",
        {"csrf_token": panel.CSRF, "case_id": "case-1", "text": "Hola"},
    )
    assert response.status_code == 303
    assert env.gateway.channel_sent == [("whatsapp", "57301", "Hola")]


def test_reply_whatsapp_closed_returns_409_without_sending(env_factory, panel):
    """R16: WhatsApp cerrada rechaza el texto libre sin enviar ni guardar."""
    env = env_factory()
    panel.login(env)
    _whatsapp_case(env, panel)
    response = _post(
        env,
        "/asesor/reply",
        {"csrf_token": panel.CSRF, "case_id": "case-1", "text": "Hola"},
    )
    assert response.status_code == 409
    assert 'data-code="channel_window_closed"' in response.text
    assert env.gateway.channel_sent == []
    assert [m for m in env.repo.messages if m.role == "advisor"] == []


def test_template_valid_is_sent_and_stored(env_factory, panel):
    """R17, R18: plantilla permitida en WhatsApp cerrada se envía y se guarda."""
    env = env_factory()
    panel.login(env)
    contact = _whatsapp_case(env, panel)
    response = _post(
        env,
        "/asesor/reply",
        {"csrf_token": panel.CSRF, "case_id": "case-1", "template": "respuesta_asesor"},
    )
    assert response.status_code == 303
    [(channel, destination, blocks)] = env.gateway.blocks_sent
    assert (channel, destination) == ("whatsapp", "57301")
    assert isinstance(blocks[0], TemplateBlock)
    assert blocks[0].name == "respuesta_asesor"
    advisor = [m for m in env.repo.messages if m.role == "advisor"]
    assert [m.text for m in advisor] == ["[plantilla:respuesta_asesor]"]
    assert ("advisor_reply", "advisor:700") in env.events()


@pytest.mark.parametrize(
    "setup",
    ["unknown", "telegram", "open"],
)
def test_template_rejected_without_calling_gateway(env_factory, setup, panel):
    """R19, R20: plantilla desconocida, canal Telegram o ventana abierta -> 422."""
    env = env_factory()
    panel.login(env)
    if setup == "telegram":
        panel.link_case(env)
        template = "respuesta_asesor"
    elif setup == "open":
        _whatsapp_case(env, panel, last_user_at=panel.NOW - timedelta(hours=1))
        template = "respuesta_asesor"
    else:
        _whatsapp_case(env, panel)
        template = "desconocida"
    response = _post(
        env,
        "/asesor/reply",
        {"csrf_token": panel.CSRF, "case_id": "case-1", "template": template},
    )
    assert response.status_code == 422
    assert env.gateway.blocks_sent == []
    assert env.gateway.channel_sent == []


@pytest.mark.parametrize(
    "data",
    [
        {"text": "hola", "template": "respuesta_asesor"},
        {},
    ],
)
def test_reply_requires_exactly_one_of_text_or_template(env_factory, data, panel):
    """R15: exactamente uno de text o template."""
    env = env_factory()
    panel.login(env)
    panel.link_case(env)
    response = _post(
        env, "/asesor/reply", {"csrf_token": panel.CSRF, "case_id": "case-1", **data}
    )
    assert response.status_code == 422
    assert env.handover.authorized == []
    assert env.gateway.sent == []


def test_gateway_422_maps_to_channel_window_closed(env_factory, panel):
    """R21: un 422 del gateway se presenta como 409 y no guarda mensaje."""
    env = env_factory()
    panel.login(env)
    _whatsapp_case(env, panel, last_user_at=panel.NOW - timedelta(hours=1))
    env.gateway.reject_channel = True
    response = _post(
        env,
        "/asesor/reply",
        {"csrf_token": panel.CSRF, "case_id": "case-1", "text": "Hola"},
    )
    assert response.status_code == 409
    assert 'data-code="channel_window_closed"' in response.text
    assert [m for m in env.repo.messages if m.role == "advisor"] == []


def test_authorize_happens_before_window_check(env_factory, panel):
    """R23: una denegación responde 403 sin consultar la ventana ni leer mensajes."""
    env = env_factory()
    panel.login(env)
    panel.link_case(env, channel="whatsapp", user="57300", chat="57301")
    env.handover.authorize_error = "forbidden"

    def boom(*args, **kwargs):
        raise AssertionError("no debe leer mensajes")

    env.repo.last_user_message_at = boom
    response = _post(
        env,
        "/asesor/reply",
        {"csrf_token": panel.CSRF, "case_id": "case-1", "text": "Hola"},
    )
    assert response.status_code == 403
    assert env.handover.authorized == [("case-1", "700", "reply")]


def test_responder_command_on_closed_whatsapp_sends_failed_reply(env_factory, panel):
    """R22: /responder a WhatsApp cerrada avisa con ADVISOR_COMMAND_FAILED_REPLY."""
    env = env_factory()
    _whatsapp_case(env, panel)
    env.post(text="/responder case-1 hola", user=111, chat=111)
    assert (111, env.settings.advisor_command_failed_reply) in env.gateway.sent
    assert all(destination != "57301" for _, destination, _ in env.gateway.channel_sent)


def test_case_view_renders_selector_or_textarea(env_factory, panel):
    """R24, R25: selector de plantillas con ventana cerrada; textarea si no."""
    env = env_factory()
    panel.login(env)
    _whatsapp_case(env, panel, "case-wa")
    panel.link_case(env, "case-tg")
    env.handover.case_list = []
    env.handover.authorized_advisors = None
    closed = env.client.get("/asesor/cases/case-wa")
    assert closed.status_code == 200
    assert '<select name="template">' in closed.text
    assert '<textarea name="text"' not in closed.text

    open_case = _whatsapp_case(env, panel, "case-open", last_user_at=panel.NOW - timedelta(hours=1))
    opened = env.client.get("/asesor/cases/case-open")
    assert opened.status_code == 200
    assert '<textarea name="text"' in opened.text
    assert '<select name="template">' not in opened.text

    telegram = env.client.get("/asesor/cases/case-tg")
    assert '<textarea name="text"' in telegram.text
