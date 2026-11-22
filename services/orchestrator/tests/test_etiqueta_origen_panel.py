"""Etiqueta de origen del canal en todo el panel y filtro por canal (#67)."""
from __future__ import annotations

import re
from datetime import timedelta

from fakes import channel_info
from lazaro_contracts import CHANNEL_ICONS

from orchestrator.adapters.channels import FakeChannelDirectory
from orchestrator.channel_label import (
    NEUTRAL_COLOR,
    UNKNOWN_NAME,
    label_from_policy,
    render_channel_label,
)
from orchestrator.channels import policy_from_info
from orchestrator.domain import CaseTag, advisor_case_history, channel_labels


def _set_channels(env, *infos) -> None:
    env.adapters.channels = FakeChannelDirectory(infos)


def _telegram(**changes):
    return channel_info(
        "telegram", name="Telegram", icon="telegram", **changes
    )


def _whatsapp(**changes):
    return channel_info(
        "whatsapp", name="WhatsApp", icon="whatsapp", **changes
    )


def _label_html(info) -> str:
    return render_channel_label(label_from_policy(policy_from_info(info)))


def _block(html: str, start: str, end: str) -> str:
    begin = html.index(start)
    return html[begin:html.index(end, begin)]


# --- R9-R14: ubicaciones -----------------------------------------------------


def test_inbox_channel_column_shows_label(env_factory, panel):
    """R9: cada conversación de la bandeja lleva ícono, nombre y color del canal."""
    env = env_factory()
    _set_channels(env, _telegram())
    panel.login(env)
    panel.link_case(env, "case-1")
    env.handover.case_list = [panel.case_item("case-1")]

    html = env.client.get("/asesor/cases").text

    assert _label_html(_telegram()) in html
    assert CHANNEL_ICONS["telegram"] in html
    assert "Telegram" in html


def test_all_cases_channel_column_shows_label(env_factory, panel):
    """R9: la vista `/asesor/todos` también muestra la etiqueta en la columna Canal."""
    env = env_factory()
    _set_channels(env, _telegram(), _whatsapp())
    panel.login(env, role="supervisor")
    panel.link_case(env, "case-tg")
    env.handover.case_list = [panel.case_item("case-tg")]

    html = env.client.get("/asesor/todos").text

    assert _label_html(_telegram()) in html
    assert "Telegram" in html


def test_chat_header_shows_channel_label(env_factory, panel):
    """R10: el encabezado del chat abierto muestra la etiqueta del canal."""
    env = env_factory()
    _set_channels(env, _telegram())
    panel.login(env)
    panel.link_case(env, "case-1")

    html = env.client.get("/asesor/cases/case-1").text
    header = _block(html, '<div class="chat-header">', "</div>")

    assert _label_html(_telegram()) in header
    assert "Telegram" in header


def test_each_chat_message_shows_its_channel_label(env_factory, panel):
    """R11: cada mensaje del historial lleva la etiqueta de su canal."""
    env = env_factory()
    _set_channels(env, _telegram())
    panel.login(env)
    contact = panel.link_case(env, "case-1")
    panel.add_message(env, contact, "user", "uno", panel.NOW - timedelta(minutes=2))
    panel.add_message(env, contact, "bot", "dos", panel.NOW - timedelta(minutes=1))

    html = env.client.get("/asesor/cases/case-1").text
    bubbles = re.findall(r'<li class="chat-msg .*?</li>', html, re.S)

    assert len(bubbles) == 2
    for bubble in bubbles:
        assert 'class="channel-label"' in bubble
        assert "Telegram" in bubble


def test_history_items_carry_contact_channel(env_factory, panel):
    """R12: `HistoryItem.channel` se rellena con el canal del contacto."""
    env = env_factory()
    _set_channels(env, _telegram())
    profile = panel.login(env)
    contact = panel.link_case(env, "case-1")
    panel.add_message(env, contact, "user", "hola", panel.NOW)

    history = advisor_case_history(
        "case-1", profile, env.settings, env.adapters
    )

    assert history
    assert all(item.channel == "telegram" for item in history)


def test_client_card_shows_label_with_and_without_profile(env_factory, panel):
    """R13: la ficha del cliente muestra la etiqueta con y sin cliente autenticado."""
    env = env_factory()
    _set_channels(env, _telegram())
    panel.login(env)
    client = env.repo.create_profile("cliente1", "cliente", "hash", panel.NOW)
    panel.link_case(env, "case-1", profile_id=client.id)

    authenticated = env.client.get("/asesor/cases/case-1").text
    card = _block(authenticated, "<h3>Cliente</h3>", "<h3>Notas internas</h3>")
    assert _label_html(_telegram()) in card

    anonymous = env_factory()
    _set_channels(anonymous, _telegram())
    panel.login(anonymous)
    panel.link_case(anonymous, "case-1", profile_id=None)
    page = anonymous.client.get("/asesor/cases/case-1").text
    card = _block(page, "<h3>Cliente</h3>", "<h3>Notas internas</h3>")
    assert _label_html(_telegram()) in card


def test_summaries_show_label_in_case_and_memory_views(env_factory, panel):
    """R14: la tabla de resúmenes muestra la etiqueta en el caso y en /memoria."""
    env = env_factory()
    _set_channels(env, _telegram(), _whatsapp())
    panel.login(env)
    client = env.repo.create_profile("cliente1", "cliente", "hash", panel.NOW)
    env.repo.upsert_conversation_summary(
        "s1",
        client.id,
        "c1",
        "whatsapp",
        "Resumen visible",
        "session_end",
        panel.NOW,
    )
    panel.link_case(
        env,
        "case-1",
        channel="whatsapp",
        user="57300",
        chat="57301",
        profile_id=client.id,
    )

    case_html = env.client.get("/asesor/cases/case-1").text
    memory_html = env.client.get("/asesor/cases/case-1/memoria").text

    expected = _label_html(_whatsapp())
    assert expected in _block(
        case_html, "<h3>Memoria y resúmenes</h3>", "<h3>Transferir</h3>"
    )
    assert expected in memory_html
    assert "WhatsApp" in memory_html


# --- R6-R8: canal desconocido, directorio caído e inactivo -------------------


def test_unknown_channel_shows_neutral_label_without_error(env_factory, panel):
    """R6: un id fuera del directorio muestra «Canal desconocido» y responde 200."""
    env = env_factory()
    _set_channels(env, _telegram())
    panel.login(env)
    panel.link_case(env, "case-1", channel="desconocido")

    response = env.client.get("/asesor/cases/case-1")

    assert response.status_code == 200
    assert UNKNOWN_NAME in response.text
    assert NEUTRAL_COLOR in response.text


def test_directory_down_uses_neutral_labels_without_error(env_factory, panel):
    """R7: si el directorio cae, las etiquetas son neutras y el panel no falla."""
    env = env_factory()
    env.adapters.channels = FakeChannelDirectory(fail=True)
    panel.login(env)
    panel.link_case(env, "case-1")
    env.handover.case_list = [panel.case_item("case-1")]

    labels = channel_labels(env.adapters, {"telegram"})
    case_page = env.client.get("/asesor/cases/case-1")
    inbox = env.client.get("/asesor/cases")

    assert labels["telegram"].name == UNKNOWN_NAME
    assert case_page.status_code == 200
    assert UNKNOWN_NAME in case_page.text
    assert inbox.status_code == 200
    assert UNKNOWN_NAME in inbox.text


def test_inactive_channel_keeps_its_label_in_panel_and_history(env_factory, panel):
    """R8: un canal desactivado conserva nombre, ícono y color en bandeja y chat."""
    env = env_factory()
    info = _telegram(active=False)
    _set_channels(env, info)
    panel.login(env)
    contact = panel.link_case(env, "case-1")
    panel.add_message(env, contact, "user", "hola", panel.NOW)
    env.handover.case_list = [panel.case_item("case-1")]

    inbox = env.client.get("/asesor/cases").text
    case_html = env.client.get("/asesor/cases/case-1").text
    live_history = env.client.get("/asesor/live/cases/case-1").text

    expected = _label_html(info)
    assert expected in inbox
    assert expected in case_html
    assert expected in live_history
    assert "✈️ Telegram" in live_history


# --- R15-R17: filtro ---------------------------------------------------------


def test_channel_filter_lists_every_registered_channel_including_inactive(
    env_factory, panel
):
    """R15: el filtro ofrece todos los canales del directorio, también inactivos."""
    env = env_factory()
    _set_channels(
        env,
        _telegram(),
        channel_info("tiktok", name="TikTok", active=False),
    )
    panel.login(env)
    env.handover.case_list = []

    html = env.client.get("/asesor/cases").text

    assert '<option value="telegram"' in html
    assert '<option value="tiktok"' in html
    assert "TikTok" in html


def test_channel_filter_combines_with_assignment_and_tag(env_factory, panel):
    """R16: canal, asignación y etiqueta se aplican juntos."""
    env = env_factory()
    _set_channels(env, _telegram(), _whatsapp())
    panel.login(env)
    panel.link_case(env, "case-tg")
    contact = panel.link_case(
        env, "case-wa", channel="whatsapp", user="57300", chat="57301"
    )
    env.repo.create_case_tag(
        CaseTag(id="tag-1", name="Urgente", active=True), "urgente", panel.NOW
    )
    env.repo.add_case_tag("case-wa", "tag-1", contact.id, "700", panel.NOW)
    env.handover.case_list = [
        panel.case_item("case-tg", "open", created_at=panel.NOW),
        panel.case_item(
            "case-wa",
            "assigned",
            ["reply", "close"],
            created_at=panel.NOW + timedelta(minutes=1),
        ),
    ]

    response = env.client.get(
        "/asesor/cases?canal=whatsapp&asignacion=mias&tag=tag-1"
    )

    assert response.status_code == 200
    assert "case-wa" in response.text
    assert "case-tg" not in response.text


def test_invalid_channel_filter_is_422_without_listing(env_factory, panel):
    """R17: un `canal` desconocido responde 422 con el mensaje de filtro existente."""
    env = env_factory()
    _set_channels(env, _telegram())
    panel.login(env)

    response = env.client.get("/asesor/cases?canal=no-existe")

    assert response.status_code == 422
    assert 'data-code="validation_error"' in response.text
    assert "Los datos enviados no son válidos." in response.text
    assert env.handover.listed == []


# --- R18, R19: vista en vivo -------------------------------------------------


def test_live_inbox_uses_the_same_labels_as_initial_load(env_factory, panel):
    """R18: `live_inbox` devuelve las filas con la misma etiqueta que la carga."""
    env = env_factory()
    _set_channels(env, _telegram(), _whatsapp())
    panel.login(env)
    panel.link_case(env, "case-tg", created_at=panel.NOW)
    panel.link_case(
        env, "case-wa", channel="whatsapp", user="57300", chat="57301"
    )
    env.handover.case_list = [
        panel.case_item("case-tg", "open", created_at=panel.NOW),
        panel.case_item(
            "case-wa",
            "assigned",
            ["reply", "close"],
            created_at=panel.NOW + timedelta(minutes=1),
        ),
    ]

    page = env.client.get("/asesor/cases").text
    live = env.client.get("/asesor/live/inbox").text

    assert live.strip() in page
    assert live.count('class="channel-label"') == 2
    assert "Telegram" in live and "WhatsApp" in live


def test_live_case_history_uses_the_same_labels_as_initial_load(env_factory, panel):
    """R19: `live_case` devuelve los mensajes con la misma etiqueta por mensaje."""
    env = env_factory()
    _set_channels(env, _telegram())
    panel.login(env)
    contact = panel.link_case(env, "case-1")
    panel.add_message(env, contact, "user", "uno", panel.NOW - timedelta(minutes=1))
    panel.add_message(env, contact, "bot", "dos", panel.NOW)

    page = env.client.get("/asesor/cases/case-1").text
    live = env.client.get("/asesor/live/cases/case-1").text

    assert live.strip() in page
    assert live.count('class="channel-label"') == 2
    assert "Telegram" in live
