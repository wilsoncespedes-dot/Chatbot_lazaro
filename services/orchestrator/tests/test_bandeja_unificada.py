"""Bandeja unificada de conversaciones: estados, orden, filtros y límite (#68)."""
from __future__ import annotations

from datetime import timedelta

from lazaro_contracts import CaseListItem

from orchestrator.states import ConversationState


def _contact(env, user: str = "11", chat: str = "111", channel: str = "telegram"):
    return env.repo.get_or_create_channel_contact(channel, user, chat, env.clock())


def _message(env, contact, text: str, at):
    env.repo.add_message(contact.id, "user", text, at)


def _case(
    case_id: str,
    status: str,
    advisor_id: str | None = None,
    at=None,
) -> CaseListItem:
    return CaseListItem(
        case_id=case_id,
        status=status,  # type: ignore[arg-type]
        created_at=at,
        actions=[],
        advisor_id=advisor_id,
    )


def test_list_shows_all_states_without_excluded_or_empty_contacts(env_factory, panel):
    """R1, R6: lista estados visibles y descarta estados excluidos."""
    env = env_factory()
    panel.login(env)

    bot = _contact(env, "11", "111")
    env.repo.set_conversation_state(bot.id, ConversationState.ACTIVE, panel.NOW)
    _message(env, bot, "Hola bot", panel.NOW - timedelta(minutes=4))

    pending = _contact(env, "12", "112")
    env.repo.set_conversation_state(pending.id, ConversationState.ACTIVE, panel.NOW)
    _message(env, pending, "Quiero un asesor", panel.NOW - timedelta(minutes=5))
    panel.link_case(env, "case-pending", user="12", chat="112")

    assigned = _contact(env, "13", "113")
    env.repo.set_conversation_state(
        assigned.id, ConversationState.WITH_ADVISOR, panel.NOW
    )
    _message(env, assigned, "Hola asesor", panel.NOW - timedelta(minutes=6))
    panel.link_case(env, "case-assigned", user="13", chat="113")
    env.repo.set_conversation_state(
        assigned.id, ConversationState.WITH_ADVISOR, panel.NOW
    )

    closed = _contact(env, "14", "114")
    env.repo.set_conversation_state(closed.id, ConversationState.ACTIVE, panel.NOW)
    _message(env, closed, "Ya me resolvieron", panel.NOW - timedelta(minutes=10))
    env.repo.add_event(
        closed.id, "case_closed", "case:case-old advisor:700", panel.NOW
    )

    excluded_new = _contact(env, "15", "115")
    env.repo.set_conversation_state(excluded_new.id, ConversationState.NEW, panel.NOW)
    _message(env, excluded_new, "no debe verse new", panel.NOW)

    excluded_closed = _contact(env, "16", "116")
    env.repo.set_conversation_state(
        excluded_closed.id, ConversationState.CLOSED, panel.NOW
    )
    _message(env, excluded_closed, "no debe verse closed", panel.NOW)

    empty = _contact(env, "17", "117")
    env.repo.set_conversation_state(empty.id, ConversationState.ACTIVE, panel.NOW)

    env.handover.case_list = [
        _case("case-pending", "open", at=panel.NOW - timedelta(minutes=5)),
        _case("case-assigned", "assigned", advisor_id="700", at=panel.NOW),
    ]

    response = env.client.get("/asesor/conversaciones")

    assert response.status_code == 200
    text = response.text
    for contact in (bot, pending, assigned, closed):
        assert contact.id in text
    for contact in (excluded_new, excluded_closed, empty):
        assert contact.id not in text
    for label in (
        "Atendida por bot",
        "Pendiente",
        "Atendida por asesor",
        "Cerrada",
        "Telegram",
    ):
        assert label in text
    assert "asesor1" in text
    assert env.repo.panel_audit[-1].action == "conversation_inbox_viewed"
    assert env.repo.panel_audit[-1].result == "ok"


def test_pending_conversations_come_first(env_factory, panel):
    """R1: `pendiente` primero y el resto por última actividad descendente."""
    env = env_factory()
    panel.login(env)

    older_bot = _contact(env, "21", "121")
    env.repo.set_conversation_state(older_bot.id, ConversationState.ACTIVE, panel.NOW)
    _message(env, older_bot, "viejo", panel.NOW - timedelta(minutes=30))

    newer_bot = _contact(env, "22", "122")
    env.repo.set_conversation_state(newer_bot.id, ConversationState.ACTIVE, panel.NOW)
    _message(env, newer_bot, "nuevo", panel.NOW - timedelta(minutes=1))

    pending = _contact(env, "23", "123")
    env.repo.set_conversation_state(pending.id, ConversationState.ACTIVE, panel.NOW)
    _message(env, pending, "pendiente", panel.NOW - timedelta(minutes=10))
    panel.link_case(env, "case-pending", user="23", chat="123")

    env.handover.case_list = [
        _case("case-pending", "open", at=panel.NOW - timedelta(minutes=10))
    ]

    text = env.client.get("/asesor/conversaciones").text

    assert text.index(pending.id) < text.index(newer_bot.id)
    assert text.index(newer_bot.id) < text.index(older_bot.id)


def test_channel_and_status_filters_combine_with_and(env_factory, panel):
    """R1: los filtros `canal` y `estado` se combinan con AND."""
    env = env_factory()
    panel.login(env)

    telegram = _contact(env, "31", "131", channel="telegram")
    env.repo.set_conversation_state(telegram.id, ConversationState.ACTIVE, panel.NOW)
    _message(env, telegram, "telegram", panel.NOW)

    whatsapp = _contact(env, "32", "132", channel="whatsapp")
    env.repo.set_conversation_state(whatsapp.id, ConversationState.ACTIVE, panel.NOW)
    _message(env, whatsapp, "whatsapp", panel.NOW)

    response = env.client.get(
        "/asesor/conversaciones?canal=whatsapp&estado=atendida_por_bot"
    )

    assert response.status_code == 200
    assert whatsapp.id in response.text
    assert telegram.id not in response.text
    assert "WhatsApp" in response.text


def test_invalid_filters_are_422_without_calling_handover(env_factory, panel):
    """R1: un canal o estado fuera del vocabulario responde 422 sin listar casos."""
    env = env_factory()
    panel.login(env)

    for query in ("canal=email", "estado=otro"):
        response = env.client.get(f"/asesor/conversaciones?{query}")
        assert response.status_code == 422
        assert 'data-code="validation_error"' in response.text
    assert env.handover.listed_overview == []


def test_inbox_limit_is_configurable(env_factory, panel):
    """R1: `PANEL_CONVERSATIONS_LIMIT` limita las conversaciones listadas."""
    env = env_factory(panel_conversations_limit=1)
    panel.login(env)
    for index, user in enumerate(("41", "42")):
        contact = _contact(env, user, f"1{user}")
        env.repo.set_conversation_state(
            contact.id, ConversationState.ACTIVE, panel.NOW
        )
        _message(
            env, contact, f"mensaje {index}", panel.NOW + timedelta(minutes=index)
        )

    text = env.client.get("/asesor/conversaciones").text

    assert 'href="/asesor/conversaciones/c2"' in text
    assert 'href="/asesor/conversaciones/c1"' not in text


def test_live_table_matches_initial_load(env_factory, panel):
    """R2: el refresco en vivo devuelve las mismas filas, etiquetas y estados."""
    env = env_factory()
    panel.login(env)
    contact = _contact(env, "51", "151")
    env.repo.set_conversation_state(contact.id, ConversationState.ACTIVE, panel.NOW)
    _message(env, contact, "hola", panel.NOW)

    page = env.client.get("/asesor/conversaciones").text
    live = env.client.get("/asesor/live/conversaciones").text

    for fragment in (contact.id, "Atendida por bot", "Telegram"):
        assert fragment in page
        assert fragment in live
    assert "Tomar conversación" in page
    assert "Tomar conversación" in live
