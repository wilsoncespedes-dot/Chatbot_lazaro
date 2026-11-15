"""Regresión de #48: `/responder` y `/cerrar` ya no son comandos de asesor."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

FIXED_NOW = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)


def _link(env, case_id: str = "case-1", user: int = 10, chat: int = 100):
    contact = env.repo.get_or_create_contact(user, chat, FIXED_NOW)
    env.repo.link_case(case_id, contact.id, FIXED_NOW)
    return contact


def _sender_messages(env, user: int = 111):
    contact_ids = {
        contact.id
        for contact in env.repo.contacts.values()
        if contact.telegram_user_id == user
    }
    return [m for m in env.repo.messages if m.contact_id in contact_ids]


@pytest.mark.parametrize("text", ["/responder case-1 hola", "/cerrar case-1"])
def test_telegram_text_is_ordinary_and_does_not_touch_cases(env, text):
    """R1, R2, R47: el texto es ordinario y no responde, asigna ni cierra casos."""
    _link(env)
    env.post(text=text, user=111, chat=111)
    assert env.handover.authorized == []
    assert env.handover.closed == []
    assert env.handover.assigned == []
    assert env.handover.requests == []
    assert _sender_messages(env, 111)


def test_command_text_is_not_removed_from_sender_history(env):
    """R1: el texto se guarda como un mensaje normal del remitente."""
    env.post(text="/responder case-1 hola", user=111, chat=111)
    texts = [
        message.text
        for message in _sender_messages(env, 111)
        if message.role == "user"
    ]
    assert texts == ["/responder case-1 hola"]


def test_command_text_does_not_send_anything_to_the_case_client(env):
    """R47: un chat que fue asesor no consigue enviar nada al cliente del caso."""
    _link(env)
    env.post(text="/responder case-1 Ya está resuelto", user=111, chat=111)
    assert all(chat != 100 for chat, _ in env.gateway.sent)


def test_command_text_does_not_close_an_assigned_case(env):
    """R2: `/cerrar` no cierra el caso ni llama a handover.close."""
    _link(env)
    env.handover.case_list = []
    env.post(text="/cerrar case-1", user=111, chat=111)
    assert env.handover.closed == []
    assert env.handover.authorized == []


def test_command_text_from_linked_client_is_forwarded_as_ordinary_message(env):
    """R1: para un cliente con caso assigned, el texto sigue el flujo de mensaje normal."""
    _link(env)
    env.handover.client_message_status = "available_in_panel"
    env.post(text="/responder case-1 hola", user=10, chat=100)
    assert env.handover.client_messages
    assert env.handover.closed == []
    assert env.handover.authorized == []


def test_command_text_does_not_bypass_consent(env):
    """R1: sigue la compuerta de privacidad como cualquier texto."""
    env.post(text="/responder case-1 hola", user=222, chat=222, consent=False)
    assert env.handover.authorized == []
    assert env.repo.contacts.get(222) is None
    assert env.gateway.sent and "consentimiento" in env.gateway.sent[-1][1].lower()


def test_command_text_does_not_call_rag_or_llm_actions_for_cases(env):
    """R2: no se ejecutan acciones de caso a partir del texto."""
    env.post(text="/cerrar case-1", user=111, chat=111)
    assert env.handover.authorized == []
    assert env.handover.closed == []
    assert env.handover.assigned == []
