"""Lectura en vivo de conversaciones y auditoría (#68 R2, R5, R6)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from lazaro_contracts import CaseListItem

from orchestrator.states import ConversationState


def _contact(env, user: str = "61", chat: str = "161"):
    return env.repo.get_or_create_channel_contact(
        "telegram", user, chat, env.clock()
    )


def _bot_conversation(env):
    contact = _contact(env)
    env.repo.set_conversation_state(contact.id, ConversationState.ACTIVE, env.clock())
    env.repo.add_message(
        contact.id, "user", "MENSAJE SECRETO", env.clock() - timedelta(minutes=1)
    )
    env.repo.add_message(
        contact.id, "bot", "respuesta del bot", env.clock()
    )
    return contact


_NOW = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)


def _case(case_id: str, status: str, advisor_id: str | None = None) -> CaseListItem:
    return CaseListItem(
        case_id=case_id,
        status=status,  # type: ignore[arg-type]
        created_at=_NOW,
        actions=[],
        advisor_id=advisor_id,
    )


def test_bot_conversation_is_read_only(env_factory, panel):
    """R2: historial visible, estado y canal, sin formulario de respuesta."""
    env = env_factory()
    panel.login(env)
    contact = _bot_conversation(env)

    response = env.client.get(f"/asesor/conversaciones/{contact.id}")

    assert response.status_code == 200
    assert "MENSAJE SECRETO" in response.text
    assert "respuesta del bot" in response.text
    assert "Atendida por bot" in response.text
    assert "Telegram" in response.text
    assert "<textarea" not in response.text
    assert 'action="/asesor/reply"' not in response.text


def test_reading_records_audit_without_message_text(env_factory, panel):
    """R2: `conversation_read` con actor, rol, target y sin texto de mensajes."""
    env = env_factory()
    profile = panel.login(env)
    contact = _bot_conversation(env)

    env.client.get(f"/asesor/conversaciones/{contact.id}")

    audit = env.repo.panel_audit[-1]
    assert audit.action == "conversation_read"
    assert audit.result == "ok"
    assert audit.actor_profile_id == profile.id
    assert audit.actor_role == "asesor"
    assert audit.target == f"conversation:{contact.id}"
    assert "MENSAJE SECRETO" not in repr(audit)


def test_reading_does_not_change_state_or_send_anything(env_factory, panel):
    """R2: la lectura no toca estado, caso, bot ni envíos."""
    env = env_factory()
    panel.login(env)
    contact = _bot_conversation(env)
    before_state = env.repo.get_conversation_state(contact.id)
    before_events = list(env.repo.events)

    env.client.get(f"/asesor/conversaciones/{contact.id}")

    assert env.repo.get_conversation_state(contact.id) == before_state
    assert env.repo.events == before_events
    assert env.gateway.sent == []
    assert env.gateway.channel_sent == []
    assert env.handover.closed == []


def test_live_history_matches_initial_and_does_not_audit(env_factory, panel):
    """R2: el refresco en vivo devuelve el mismo historial sin auditar."""
    env = env_factory()
    panel.login(env)
    contact = _bot_conversation(env)

    page = env.client.get(f"/asesor/conversaciones/{contact.id}")
    audits_after_page = len(env.repo.panel_audit)
    live = env.client.get(f"/asesor/live/conversaciones/{contact.id}")

    assert live.status_code == 200
    for fragment in ("MENSAJE SECRETO", "respuesta del bot", "Cliente", "Telegram"):
        assert fragment in page.text
        assert fragment in live.text
    assert len(env.repo.panel_audit) == audits_after_page


def test_own_assigned_conversation_redirects_to_case(env_factory, panel):
    """R2: un asesor asignado va al caso con 303."""
    env = env_factory()
    panel.login(env)
    contact = _contact(env, "62", "162")
    env.repo.set_conversation_state(
        contact.id, ConversationState.WITH_ADVISOR, env.clock()
    )
    env.repo.add_message(contact.id, "user", "hola", env.clock())
    env.repo.link_case("case-1", contact.id, env.clock())
    env.handover.case_list = [_case("case-1", "assigned", "700")]

    response = env.client.get(
        f"/asesor/conversaciones/{contact.id}", follow_redirects=False
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/asesor/cases/case-1"


def test_unknown_invalid_or_excluded_conversation_is_404(env_factory, panel):
    """R2, R5: contacto inexistente, id inválido o estado excluido no revelan nada."""
    env = env_factory()
    panel.login(env)
    excluded = _contact(env, "63", "163")
    env.repo.set_conversation_state(excluded.id, ConversationState.NEW, env.clock())
    env.repo.add_message(excluded.id, "user", "no visible", env.clock())

    for target in ("no-existe", "x" * 65, excluded.id):
        response = env.client.get(f"/asesor/conversaciones/{target}")
        assert response.status_code == 404
        assert 'data-code="not_found"' in response.text


def test_purged_contact_is_not_listed_or_readable(env_factory, panel):
    """R6: sin mensajes guardados no hay fila ni contenido."""
    env = env_factory()
    panel.login(env)
    contact = _bot_conversation(env)
    env.repo.delete_contact_content("telegram", contact.external_user_id)

    page = env.client.get("/asesor/conversaciones")
    response = env.client.get(f"/asesor/conversaciones/{contact.id}")

    assert contact.id not in page.text
    assert response.status_code == 404


def test_bot_visibility_can_be_disabled(env_factory, panel):
    """R5: con `PANEL_BOT_CONVERSATIONS_VISIBLE=false` se oculta bot y cerrada."""
    env = env_factory(panel_bot_conversations_visible=False)
    panel.login(env)
    bot = _bot_conversation(env)
    pending = _contact(env, "64", "164")
    env.repo.set_conversation_state(pending.id, ConversationState.ACTIVE, env.clock())
    env.repo.add_message(pending.id, "user", "pendiente", env.clock())
    env.repo.link_case("case-pending", pending.id, env.clock())
    env.handover.case_list = [_case("case-pending", "open", None)]

    page = env.client.get("/asesor/conversaciones")
    read_bot = env.client.get(f"/asesor/conversaciones/{bot.id}")
    read_pending = env.client.get(f"/asesor/conversaciones/{pending.id}")

    assert bot.id not in page.text
    assert pending.id in page.text
    assert read_bot.status_code == 403
    assert read_pending.status_code == 200


def test_bot_visibility_true_shows_bot_and_closed(env_factory, panel):
    """R5: por defecto bot y cerrada son visibles para asesores."""
    env = env_factory()
    panel.login(env)
    bot = _bot_conversation(env)
    closed = _contact(env, "65", "165")
    env.repo.set_conversation_state(closed.id, ConversationState.ACTIVE, env.clock())
    env.repo.add_message(
        closed.id, "user", "resuelto", env.clock() - timedelta(minutes=5)
    )
    env.repo.add_event(closed.id, "case_closed", "case:old advisor:700", env.clock())

    page = env.client.get("/asesor/conversaciones")

    assert bot.id in page.text
    assert closed.id in page.text
    assert "Atendida por bot" in page.text
    assert "Cerrada" in page.text
