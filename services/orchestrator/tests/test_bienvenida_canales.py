"""Bienvenida con canales públicos y formulario de canal (#73)."""
from __future__ import annotations

from datetime import datetime

import pytest

from fakes import channel_info, drain_queues
from orchestrator.admin_channels import ChannelFormError, channel_form
from orchestrator.channels import ChannelPolicy
from orchestrator.welcome import MAX_WELCOME_CHANNELS, channels_welcome_block

NOW = datetime(2026, 1, 2, 3, 4, 5)


def _policy(
    channel_id: str,
    *,
    name: str | None = None,
    active: bool = True,
    public: bool = True,
    simulated: bool = False,
    contact_url: str = "",
    icon: str = "telegram",
) -> ChannelPolicy:
    return ChannelPolicy(
        id=channel_id,
        name=name or channel_id,
        icon=icon,
        color="#1B6FA8",
        active=active,
        windowed=False,
        consent_mode="texto",
        public=public,
        contact_url=contact_url,
        simulated=simulated,
    )


def _send_first_contact(env, user: str = "10", chat: str = "100"):
    body = {
        "channel": "telegram",
        "external_user_id": user,
        "external_chat_id": chat,
        "external_message_id": f"first-{user}",
        "kind": "text",
        "text": "Hola",
        "received_at": "2026-01-02T03:04:00+00:00",
    }
    response = env.client.post(
        "/messages", json=body, headers={"X-Service-Token": env.settings.service_token}
    )
    drain_queues(env.settings, env.adapters)
    assert response.status_code == 202
    texts = [text for _channel, _destination, text in env.gateway.channel_sent]
    return texts[-1] if texts else ""


def test_block_lists_only_active_public_channels_with_name_icon_and_link():
    """R27, R28: nombre, glifo y enlace solo de canales activos y públicos."""
    block = channels_welcome_block(
        [
            _policy(
                "telegram",
                name="Telegram",
                contact_url="https://t.me/lazaro",
                icon="telegram",
            ),
            _policy("whatsapp", name="WhatsApp", contact_url="https://wa.me/1"),
            _policy("web", name="Web", public=False),
            _policy("viejo", name="Viejo", active=False),
        ],
        "Canales:",
        False,
    )

    lines = block.splitlines()
    assert lines[0] == "Canales:"
    assert any("Telegram" in line and "✈️" in line and "https://t.me/lazaro" in line
               for line in lines)
    assert any("WhatsApp" in line and "https://wa.me/1" in line for line in lines)
    assert "Web" not in block
    assert "Viejo" not in block


def test_block_excludes_simulated_channels_by_default_and_includes_on_demand():
    """R29, R30: el ajuste de demostración habilita los canales simulados."""
    policies = [
        _policy("telegram", name="Telegram"),
        _policy("tiktok", name="TikTok (SIMULADO)", simulated=True, icon="web"),
    ]

    default = channels_welcome_block(policies, "Canales:", False)
    demonstration = channels_welcome_block(policies, "Canales:", True)

    assert "TikTok" not in default
    assert "TikTok" in demonstration


def test_empty_block_returns_empty_string():
    """R31: sin canales elegibles no se añade bloque."""
    assert channels_welcome_block([], "Canales:", False) == ""
    assert channels_welcome_block([_policy("web", public=False)], "Canales:", False) == ""


def test_block_is_alphabetical_and_capped_at_ten_channels():
    """R33: máximo diez canales, en orden alfabético por nombre."""
    policies = [
        _policy(f"c{index}", name=f"Canal {index:02d}")
        for index in range(12, 0, -1)
    ]

    block = channels_welcome_block(policies, "Canales:", False)
    lines = block.splitlines()[1:]

    assert len(lines) == MAX_WELCOME_CHANNELS
    names = [line.split(" ", 2)[-1] for line in lines]
    assert names == sorted(names)
    assert "Canal 01" in block and "Canal 10" in block
    assert "Canal 11" not in block and "Canal 12" not in block


def test_stored_contact_url_that_is_not_https_is_rendered_without_link():
    """R36: un enlace guardado inválido no se muestra, pero el canal sí."""
    block = channels_welcome_block(
        [_policy("telegram", name="Telegram", contact_url="http://inseguro")],
        "Canales:",
        False,
    )
    assert "Telegram" in block
    assert "http://inseguro" not in block

    too_long = channels_welcome_block(
        [_policy("web", name="Web", contact_url="https://" + "a" * 300)],
        "Canales:",
        False,
    )
    assert "Web" in too_long and "https://" not in too_long


def test_first_contact_appends_public_channels_to_the_greeting(env_factory):
    """R26, R27: el aviso de primer contacto con saludo incluye los canales públicos."""
    env = env_factory()
    env.adapters.channels.set_infos(
        [
            channel_info(
                "telegram",
                name="Telegram",
                public=True,
                contact_url="https://t.me/lazaro",
                icon="telegram",
            ),
            channel_info("whatsapp", name="WhatsApp", public=False),
        ]
    )

    text = _send_first_contact(env)

    assert env.repo.get_conversation_texts().greeting in text
    assert "Telegram" in text and "https://t.me/lazaro" in text
    assert "WhatsApp" not in text


def test_first_contact_without_directory_sends_greeting_without_list(env_factory):
    """R32: si el directorio falla, el saludo sale sin la lista y sin romper."""
    env = env_factory()
    env.adapters.channels.fail = True

    text = _send_first_contact(env)

    assert env.repo.get_conversation_texts().greeting in text
    assert env.settings.conversation_channels_intro not in text


def _channel_form(**overrides):
    data = {
        "name": "Telegram",
        "icon": "telegram",
        "color": "#1B6FA8",
        "consent_mode": "texto",
    }
    data.update(overrides)
    return channel_form(data, creating=False, current_config={})


def test_channel_form_saves_public_flag_and_contact_url():
    """R34: el formulario permite marcar público y guardar el enlace de contacto."""
    data = _channel_form(public="si", contact_url="https://t.me/lazaro")

    assert data.config["public"] == "true"
    assert data.config["contact_url"] == "https://t.me/lazaro"


def test_channel_form_clears_public_flag_and_rejects_invalid_contact_url():
    """R34, R35: desmarcar quita el canal; un enlace inválido se rechaza."""
    cleared = _channel_form(
        current_config={"public": "true", "contact_url": "https://t.me/viejo"},
    )
    assert "public" not in cleared.config
    assert "contact_url" not in cleared.config

    with pytest.raises(ChannelFormError):
        _channel_form(contact_url="http://inseguro")
    with pytest.raises(ChannelFormError):
        _channel_form(contact_url="https://" + "a" * 250)
