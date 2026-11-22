"""Marca, orden y aviso en vivo de la intención de compra (#70)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from lazaro_contracts import CaseListItem

from orchestrator import advisor_panel
from orchestrator.domain import ConversationRow
from orchestrator.panel_live import PanelEvent, event_payload
from orchestrator.states import ConversationState

NOW = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)


def _contact(env, user: str = "11", chat: str = "111"):
    return env.repo.get_or_create_channel_contact(
        "telegram", user, chat, env.clock()
    )


def _message(env, contact, text: str, at):
    env.repo.add_message(contact.id, "user", text, at)


def _case(case_id: str, status: str, advisor_id: str | None = None):
    return CaseListItem(
        case_id=case_id,
        status=status,  # type: ignore[arg-type]
        created_at=NOW,
        actions=[],
        advisor_id=advisor_id,
    )


def _interest_contact(env, panel, user="21", chat="121", at=None):
    contact = _contact(env, user, chat)
    env.repo.set_conversation_state(contact.id, ConversationState.ACTIVE, panel.NOW)
    _message(env, contact, "hola", at or panel.NOW)
    env.repo.add_event(contact.id, "purchase_intent", "phrase", panel.NOW)
    return contact


def test_inbox_shows_the_purchase_interest_badge(env_factory, panel):
    """R13, R24: la bandeja marca la conversación con el texto «Interés de compra»."""
    env = env_factory()
    panel.login(env)
    contact = _interest_contact(env, panel)

    text = env.client.get("/asesor/conversaciones").text

    assert contact.id in text
    assert "Interés de compra" in text


def test_mark_expires_after_the_configured_window(env_factory, panel):
    """R13: pasada `PURCHASE_INTENT_MARK_HOURS`, la marca desaparece."""
    env = env_factory()
    panel.login(env)
    contact = _contact(env, "22", "122")
    env.repo.set_conversation_state(contact.id, ConversationState.ACTIVE, panel.NOW)
    _message(env, contact, "hola", panel.NOW - timedelta(hours=80))
    env.repo.add_event(
        contact.id, "purchase_intent", "phrase", panel.NOW - timedelta(hours=73)
    )

    text = env.client.get("/asesor/conversaciones").text

    assert contact.id in text
    assert "Interés de compra" not in text


def test_mark_expires_when_a_later_case_closed_exists(env_factory, panel):
    """R13: una detección anterior al último `case_closed` no marca la bandeja."""
    env = env_factory()
    panel.login(env)
    contact = _contact(env, "23", "123")
    env.repo.set_conversation_state(contact.id, ConversationState.ACTIVE, panel.NOW)
    _message(env, contact, "antes", panel.NOW - timedelta(hours=3))
    env.repo.add_event(
        contact.id, "purchase_intent", "phrase", panel.NOW - timedelta(hours=2)
    )
    env.repo.add_event(
        contact.id, "case_closed", "case:case-1", panel.NOW - timedelta(hours=1)
    )
    _message(env, contact, "después", panel.NOW - timedelta(minutes=30))

    text = env.client.get("/asesor/conversaciones").text

    assert contact.id in text
    assert "Interés de compra" not in text


def test_mark_is_hidden_for_closed_conversations(env_factory, panel):
    """R13: una conversación derivada `cerrada` no conserva la marca."""
    env = env_factory()
    panel.login(env)
    contact = _contact(env, "24", "124")
    env.repo.set_conversation_state(contact.id, ConversationState.ACTIVE, panel.NOW)
    _message(env, contact, "hola", panel.NOW - timedelta(hours=2))
    env.repo.add_event(
        contact.id, "case_closed", "case:case-1", panel.NOW - timedelta(hours=1)
    )
    env.repo.add_event(
        contact.id, "purchase_intent", "phrase", panel.NOW - timedelta(minutes=30)
    )

    text = env.client.get("/asesor/conversaciones").text

    assert contact.id in text
    assert "Cerrada" in text
    assert "Interés de compra" not in text


def test_order_is_pending_then_interest_then_rest(env_factory, panel):
    """R14: pendientes primero, luego interés de compra, luego el resto."""
    env = env_factory()
    panel.login(env)

    pending = _contact(env, "31", "131")
    env.repo.set_conversation_state(pending.id, ConversationState.ACTIVE, panel.NOW)
    _message(env, pending, "pendiente", panel.NOW - timedelta(minutes=100))
    panel.link_case(env, "case-pending", user="31", chat="131")

    interest = _interest_contact(env, panel, "32", "132", panel.NOW - timedelta(minutes=50))
    plain = _contact(env, "33", "133")
    env.repo.set_conversation_state(plain.id, ConversationState.ACTIVE, panel.NOW)
    _message(env, plain, "normal", panel.NOW - timedelta(minutes=10))

    env.handover.case_list = [_case("case-pending", "open")]

    text = env.client.get("/asesor/conversaciones").text

    assert text.index(pending.id) < text.index(interest.id)
    assert text.index(interest.id) < text.index(plain.id)


def test_badge_text_is_escaped_and_does_not_rely_on_color():
    """R24: el indicador lleva texto y todo lo demás se escapa."""
    row = ConversationRow(
        contact_id="<b>contacto</b>",
        channel="telegram",
        status="atendida_por_bot",
        case_id=None,
        assigned_advisor=None,
        last_activity_at=datetime(2026, 1, 2, tzinfo=timezone.utc),
        client_name="<script>alert(1)</script>",
        window=None,
        purchase_intent=True,
    )

    html = advisor_panel.render_conversations_table([row], "csrf")

    assert "Interés de compra" in html
    assert "&lt;b&gt;contacto&lt;/b&gt;" in html
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html
    assert "<script>" not in html


def test_live_payload_is_minimal_for_purchase_intent():
    """R15: el payload en vivo solo lleva `type`, `id` y `case_id`."""
    payload = event_payload(
        PanelEvent(id=7, case_id="case-1", kind="purchase_intent")
    )
    assert payload == {"type": "purchase_intent", "id": 7, "case_id": "case-1"}


def test_live_javascript_accepts_purchase_intent(env_factory):
    """R16: el JavaScript del panel refresca también con `purchase_intent`."""
    env = env_factory()
    script = env.client.get("/asesor/static/panel_live.js").text
    assert "purchase_intent" in script


def test_live_fragment_matches_initial_load(env_factory, panel):
    """R16, R24: la carga inicial y el refresco en vivo muestran la misma marca."""
    env = env_factory()
    panel.login(env)
    contact = _interest_contact(env, panel)

    page = env.client.get("/asesor/conversaciones").text
    live = env.client.get("/asesor/live/conversaciones").text

    for fragment in (contact.id, "Interés de compra"):
        assert fragment in page
        assert fragment in live
