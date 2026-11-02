"""Tests de POST /messages, contacto, historial, eventos y flujo principal."""
from __future__ import annotations

from datetime import datetime, timezone

FIXED_NOW = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
RECEIVED_AT = datetime(2026, 1, 2, 3, 4, 0, tzinfo=timezone.utc)


def _no_side_effects(env):
    return (
        env.rag.calls == []
        and env.llm.calls == []
        and env.gateway.sent == []
        and env.handover.requests == []
        and env.repo.messages == []
        and env.repo.events == []
    )


def test_new_message_returns_202_accepted_and_is_processed(env):
    """R1"""
    response = env.post()
    assert response.status_code == 202
    assert response.json() == {"status": "accepted"}
    assert env.gateway.sent == [(100, "Respuesta final")]


def test_duplicate_update_returns_202_duplicate_without_processing(env):
    """R2"""
    env.repo.processed.add(5)
    response = env.post(update_id=5)
    assert response.status_code == 202
    assert response.json() == {"status": "duplicate"}
    assert _no_side_effects(env)


def test_messages_without_token_returns_401(env):
    """R3"""
    response = env.post(headers={})
    assert response.status_code == 401
    assert response.json()["error"] == "unauthorized"
    assert _no_side_effects(env) and env.repo.processed == set()


def test_messages_invalid_body_returns_422(env):
    """R4"""
    response = env.client.post(
        "/messages", json={"update_id": 1}, headers={"X-Service-Token": "svc-token"}
    )
    assert response.status_code == 422
    assert response.json()["error"] == "validation_error"
    assert _no_side_effects(env)


def test_new_telegram_user_creates_contact(env):
    """R5"""
    env.post(user=10, chat=100)
    contact = env.repo.contacts[10]
    assert (contact.telegram_user_id, contact.chat_id) == (10, 100)


def test_existing_telegram_user_reuses_contact(env):
    """R6"""
    env.post(update_id=1, user=10, chat=100)
    env.post(update_id=2, user=10, chat=100)
    assert len(env.repo.contacts) == 1
    assert {m.contact_id for m in env.repo.messages} == {env.repo.contacts[10].id}


def test_incoming_and_outgoing_messages_saved_with_dates(env):
    """R7, R8"""
    env.post(text="hola manual")
    user_msg, bot_msg = env.repo.messages
    assert (user_msg.role, user_msg.text, user_msg.at) == ("user", "hola manual", RECEIVED_AT)
    assert (bot_msg.role, bot_msg.text, bot_msg.at) == ("bot", "Respuesta final", FIXED_NOW)


def test_failed_send_is_not_saved_as_outgoing(env):
    """R26"""
    env.gateway.fail = True
    response = env.post()
    assert response.status_code == 202
    assert [m.role for m in env.repo.messages] == ["user"]


def test_rag_answer_event_saved(env):
    """R9"""
    env.post()
    event = next(e for e in env.repo.events if e.type == "rag_answer")
    assert (event.type, event.reason, event.at) == ("rag_answer", "chunks_found", FIXED_NOW)
    assert event.contact_id == env.repo.contacts[10].id


def test_no_results_event_saved(env):
    """R10"""
    env.rag.results = []
    env.post()
    event = next(e for e in env.repo.events if e.type == "no_results")
    assert (event.type, event.reason, event.at) == ("no_results", "no_relevant_chunks", FIXED_NOW)
    assert event.contact_id == env.repo.contacts[10].id


def test_handover_event_saved(env):
    """R11; #32: umbral 1 para conservar la derivación en el primer fallo."""
    env.settings.auto_handover_failure_threshold = 1
    env.post(text="quiero un asesor")
    assert ("handover", "user_request") in env.events()
    env.rag.results = []
    env.post(text="algo raro", update_id=2)
    assert ("handover", "no_relevant_chunks") in env.events()
    assert all(e.at == FIXED_NOW for e in env.repo.events)


def test_search_called_with_text_and_rag_top_k(env):
    """R12, R33"""
    env.post(text="pregunta concreta")
    assert env.rag.calls == [("pregunta concreta", 7)]
