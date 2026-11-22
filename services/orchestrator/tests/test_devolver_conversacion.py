"""Devolver al bot y resolver desde la conversación (#68 R4)."""
from __future__ import annotations

from datetime import datetime, timezone

from orchestrator.states import ConversationState

_NOW = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)


def _contact(env, user: str = "10", chat: str = "100"):
    return env.repo.get_or_create_channel_contact(
        "telegram", user, chat, env.clock()
    )


def _conversation(env):
    contact = _contact(env)
    env.repo.set_conversation_state(contact.id, ConversationState.ACTIVE, env.clock())
    env.repo.add_message(contact.id, "user", "hola", env.clock())
    return contact


def _take(env, panel, contact_id: str):
    return env.client.post(
        f"/asesor/conversaciones/{contact_id}/tomar",
        data={"csrf_token": panel.CSRF},
        follow_redirects=False,
    )


def test_return_reuses_existing_route_and_bot_resumes(env_factory, panel):
    """R4: devolver usa /asesor/return, deja active y el bot vuelve a responder."""
    env = env_factory()
    panel.login(env)
    contact = _conversation(env)
    env.handover.take_case_id = "case-new"
    assert _take(env, panel, contact.id).status_code == 303
    env.gateway.sent.clear()
    env.llm.calls.clear()

    response = env.client.post(
        "/asesor/return",
        data={"csrf_token": panel.CSRF, "case_id": "case-new"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/asesor?ok=return"
    assert env.handover.closed == [("case-new", "700")]
    assert env.repo.get_conversation_state(contact.id) == ConversationState.ACTIVE
    assert any(
        event.type == "advisor_returned" for event in env.repo.events
    )
    assert not any(event.type == "case_closed" for event in env.repo.events)

    env.post("después de devolver", update_id=2, user=10, chat=100)

    assert env.llm.calls


def test_resolving_records_case_closed_only_then(env_factory, panel):
    """R4: resolver registra `case_closed`; devolver no lo registra."""
    env = env_factory()
    panel.login(env)
    contact = _conversation(env)
    env.repo.set_conversation_state(
        contact.id, ConversationState.WITH_ADVISOR, env.clock()
    )
    env.repo.link_case("case-resolve", contact.id, env.clock())

    response = env.client.post(
        "/asesor/close",
        data={"csrf_token": panel.CSRF, "case_id": "case-resolve"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert env.repo.get_conversation_state(contact.id) == ConversationState.ACTIVE
    assert any(
        event.type == "case_closed"
        and event.reason == "case:case-resolve advisor:700"
        for event in env.repo.events
    )
    assert not any(event.type == "advisor_returned" for event in env.repo.events)
