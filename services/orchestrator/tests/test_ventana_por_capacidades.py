"""R19–R21 (#65): la ventana de texto libre sale de las capacidades del canal."""
from __future__ import annotations

from datetime import timedelta

import pytest
from fakes import channel_info, default_channel_infos, drain_queues
from lazaro_contracts import TemplateBlock

from orchestrator.adapters.channels import FakeChannelDirectory
from orchestrator.channels import policy_from_info
from orchestrator.panel import channel_window

NOW_HOURS = 24


def _post(env, data: dict):
    response = env.client.post("/asesor/reply", data=data, follow_redirects=False)
    drain_queues(env.settings, env.adapters)
    return response


def _with_channels(env, *extra):
    env.adapters.channels = FakeChannelDirectory([*default_channel_infos(), *extra])


def _case(env, panel, channel: str, last_user_at=None):
    contact = panel.link_case(env, "case-1", channel=channel, user="u-1", chat="d-1")
    if last_user_at is not None:
        panel.add_message(env, contact, "user", "hola", last_user_at)
    return contact


@pytest.mark.parametrize(
    ("windowed", "last_user", "expected"),
    [
        (True, None, "closed"),
        (True, timedelta(hours=1), "open"),
        (True, timedelta(hours=24), "closed"),
        (False, None, "not_applicable"),
        (False, timedelta(hours=30), "not_applicable"),
    ],
)
def test_channel_window_follows_policy(panel, windowed, last_user, expected):
    """R19: mismo algoritmo que antes, solo para canales con ventana."""
    policy = policy_from_info(channel_info("canal-x", windowed=windowed))
    last = None if last_user is None else panel.NOW - last_user
    assert channel_window(policy, last, panel.NOW, NOW_HOURS) == expected


def test_new_windowed_channel_blocks_free_text_when_closed(env_factory, panel):
    """R20: un canal nuevo con ventana cerrada rechaza el texto libre (409)."""
    env = env_factory()
    _with_channels(env, channel_info("canal-ventana", windowed=True, consent_mode="boton"))
    panel.login(env)
    _case(env, panel, "canal-ventana")
    response = _post(env, {"csrf_token": panel.CSRF, "case_id": "case-1", "text": "Hola"})
    assert response.status_code == 409
    assert 'data-code="channel_window_closed"' in response.text
    assert env.gateway.channel_sent == []


def test_new_windowed_channel_sends_template_when_closed(env_factory, panel):
    """R20: con ventana cerrada se usa la plantilla aprobada por el mismo canal."""
    env = env_factory()
    _with_channels(env, channel_info("canal-ventana", windowed=True))
    panel.login(env)
    _case(env, panel, "canal-ventana")
    response = _post(
        env,
        {"csrf_token": panel.CSRF, "case_id": "case-1", "template": "respuesta_asesor"},
    )
    assert response.status_code == 303
    [(channel, destination, blocks)] = env.gateway.blocks_sent
    assert (channel, destination) == ("canal-ventana", "d-1")
    assert isinstance(blocks[0], TemplateBlock)


def test_windowed_channel_with_open_window_sends_free_text(env_factory, panel):
    """R20: con la ventana abierta el texto libre sale por el canal."""
    env = env_factory()
    _with_channels(env, channel_info("canal-ventana", windowed=True))
    panel.login(env)
    _case(env, panel, "canal-ventana", last_user_at=panel.NOW - timedelta(hours=2))
    response = _post(env, {"csrf_token": panel.CSRF, "case_id": "case-1", "text": "Hola"})
    assert response.status_code == 303
    assert env.gateway.channel_sent == [("canal-ventana", "d-1", "Hola")]


@pytest.mark.parametrize("channel", ["simulado", "canal-ausente"])
def test_channel_without_window_never_requires_template(env_factory, panel, channel):
    """R21: sin ventana (o ausente del directorio) no se exige plantilla ni se bloquea."""
    env = env_factory()
    panel.login(env)
    _case(env, panel, channel)
    response = _post(env, {"csrf_token": panel.CSRF, "case_id": "case-1", "text": "Hola"})
    assert response.status_code == 303
    assert env.gateway.channel_sent == [(channel, "d-1", "Hola")]
    template = _post(
        env,
        {"csrf_token": panel.CSRF, "case_id": "case-1", "template": "respuesta_asesor"},
    )
    assert template.status_code == 422
    assert not any(
        isinstance(block, TemplateBlock)
        for _, _, blocks in env.gateway.blocks_sent
        for block in blocks
    )


def test_whatsapp_keeps_the_previous_window_behavior(env_factory, panel):
    """R20: WhatsApp (con ventana por capacidades) conserva el bloqueo de antes."""
    env = env_factory()
    panel.login(env)
    _case(env, panel, "whatsapp")
    response = _post(env, {"csrf_token": panel.CSRF, "case_id": "case-1", "text": "Hola"})
    assert response.status_code == 409
