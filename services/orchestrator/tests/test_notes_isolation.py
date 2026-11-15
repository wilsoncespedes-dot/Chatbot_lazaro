"""Aislamiento de las notas internas (#50): R10-R13."""
from __future__ import annotations

from datetime import timedelta

from orchestrator.domain import ClientSession, end_client_session

SENTINEL = "CENTINELA-NOTA-INTERNA-50"


def _add_note(env, panel, case_id: str = "case-1") -> None:
    panel.login(env)
    panel.link_case(env, case_id)
    response = env.client.post(
        f"/asesor/cases/{case_id}/notes",
        data={"csrf_token": panel.CSRF, "text": SENTINEL},
        follow_redirects=False,
    )
    assert response.status_code == 303


def test_note_never_reaches_channel_history_or_events(env_factory, panel):
    """R10, R11, R13: la nota no se envía ni se guarda en messages/events."""
    env = env_factory()
    _add_note(env, panel)
    contact = env.repo.get_case_contact("case-1")

    assert env.gateway.sent == []
    assert env.gateway.channel_sent == []
    assert env.gateway.blocks_sent == []
    assert env.handover.client_messages == []
    assert all(SENTINEL not in message.text for message in env.repo.messages)
    assert all(SENTINEL not in event.reason for event in env.repo.events)
    assert all(
        SENTINEL not in text
        for _role, text, _at in env.repo.case_messages(
            contact.id, panel.NOW - timedelta(days=1), 100
        )
    )


def test_note_is_not_in_llm_prompt_or_memory_or_summary(env_factory, panel):
    """R12: ni el turno de IA, ni el resumen ni la memoria contienen la nota."""
    env = env_factory(memory_enabled=True)
    _add_note(env, panel)
    contact = env.repo.get_case_contact("case-1")
    env.repo.add_message(contact.id, "user", "consulta normal", panel.NOW)
    env.repo.add_message(contact.id, "bot", "respuesta normal", panel.NOW)

    env.post("¿Cómo instalo el módulo?", update_id=1)
    assert env.llm.calls
    for system, user in env.llm.calls:
        assert SENTINEL not in system
        assert SENTINEL not in user

    session = ClientSession(
        id="s1",
        profile_id="perfil-1",
        contact_id=contact.id,
        started_at=panel.NOW - timedelta(hours=1),
        last_activity_at=panel.NOW,
    )
    env.repo.client_sessions[session.id] = session
    end_client_session(session, "idle", env.settings, env.adapters, notify=False)
    for system, user in env.llm.calls:
        assert SENTINEL not in system
        assert SENTINEL not in user
    items, _ = env.repo.get_client_memory("perfil-1")
    assert all(SENTINEL not in item for item in items)
    assert all(
        SENTINEL not in row.summary
        for row in env.repo.list_conversation_summaries("perfil-1", 10)
    )


def test_note_is_not_in_advisor_reply_text_or_whatsapp_template(env_factory, panel):
    """R13: la respuesta del asesor (texto o plantilla) no incluye la nota."""
    env = env_factory()
    _add_note(env, panel)
    contact = env.repo.get_case_contact("case-1")

    reply = env.client.post(
        "/asesor/reply",
        data={"csrf_token": panel.CSRF, "case_id": "case-1", "text": "respuesta"},
        follow_redirects=False,
    )
    assert reply.status_code == 303
    assert (contact.chat_id, "respuesta") in env.gateway.sent
    assert all(SENTINEL not in text for _chat, text in env.gateway.sent)

    env2 = env_factory()
    _add_note(env2, panel, "case-wa")
    env2.repo.case_links["case-wa"] = env2.repo.case_links["case-wa"]
    wa_contact = env2.repo.get_case_contact("case-wa")
    wa_contact.channel = "whatsapp"
    wa_contact.external_chat_id = "57301"
    template = env2.client.post(
        "/asesor/reply",
        data={
            "csrf_token": panel.CSRF,
            "case_id": "case-wa",
            "template": "respuesta_asesor",
        },
        follow_redirects=False,
    )
    assert template.status_code == 303
    assert all(
        SENTINEL not in str(blocks)
        for _channel, _destination, blocks in env2.gateway.blocks_sent
    )
