"""Publicación de eventos del panel en tiempo real (#53)."""
from __future__ import annotations

from datetime import timedelta

import pytest
from lazaro_contracts import CaseReplyRequest

from orchestrator.adapters.repository import FakeRepository
from orchestrator.domain import (
    ClientSession,
    assign_case,
    close_case,
    execute_suppression,
    reassign_case,
    reply_to_case,
    return_case,
    transfer_case,
)


def test_add_message_publishes_event_for_latest_case(env_factory, panel):
    """R15: cada mensaje user/bot/advisor avisa del caso vinculado más reciente."""
    env = env_factory()
    contact = panel.link_case(
        env, "case-1", created_at=panel.NOW - timedelta(hours=1)
    )
    panel.link_case(env, "case-2", created_at=panel.NOW)
    for role in ("user", "bot", "advisor"):
        env.repo.add_message(contact.id, role, "hola", panel.NOW)
    messages = [event for event in env.repo.panel_events if event.kind == "message"]
    assert [event.case_id for event in messages] == ["case-2", "case-2", "case-2"]


def test_link_case_publishes_case_created(env_factory, panel):
    """R16: enlazar un caso nuevo publica `case_created` una sola vez."""
    env = env_factory()
    contact = panel.link_case(env, "case-1")
    created = [event for event in env.repo.panel_events if event.kind == "case_created"]
    assert [(event.case_id) for event in created] == ["case-1"]
    env.repo.link_case("case-1", contact.id, panel.NOW)
    created = [event for event in env.repo.panel_events if event.kind == "case_created"]
    assert len(created) == 1


@pytest.mark.parametrize(
    "action", ["assign", "close", "return", "transfer", "reassign", "reply"]
)
def test_panel_actions_publish_case_updated(env_factory, panel, action):
    """R17: asignar, cerrar, devolver, transferir, reasignar y responder avisan."""
    env = env_factory()
    panel.link_case(env, "case-1")
    actor = panel.make_profile(env, "actor", "asesor", 700)
    supervisor = panel.make_profile(env, "super", "supervisor", 701)
    target = panel.make_profile(env, "destino", "asesor", 222)
    panel.set_presence(env, target.id, "available")
    if action == "assign":
        assign_case("case-1", "700", env.adapters)
    elif action == "close":
        close_case("case-1", "700", env.settings, env.adapters)
    elif action == "return":
        return_case("case-1", "700", env.settings, env.adapters)
    elif action == "transfer":
        transfer_case("case-1", actor, target.id, env.settings, env.adapters)
    elif action == "reassign":
        reassign_case("case-1", supervisor, target.id, env.settings, env.adapters)
    else:
        reply_to_case(
            "case-1",
            CaseReplyRequest(advisor_id="700", text="respuesta"),
            env.settings,
            env.adapters,
        )
    updated = [event for event in env.repo.panel_events if event.kind == "case_updated"]
    assert any(event.case_id == "case-1" for event in updated)


def test_publish_failure_does_not_fail_message_or_action(
    env_factory, panel, monkeypatch
):
    """R18: un fallo de publicación no hace fallar el mensaje ni la acción."""
    env = env_factory()
    contact = panel.link_case(env, "case-1")

    def boom(*args, **kwargs):
        raise RuntimeError("sin base de datos")

    monkeypatch.setattr(env.repo, "publish_panel_event", boom)
    env.repo.add_message(contact.id, "user", "hola", panel.NOW)
    assign_case("case-1", "700", env.adapters)
    assert [message.text for message in env.repo.messages] == ["hola"]


def test_event_from_second_repository_instance_reaches_ws(env_factory, panel):
    """R19: un evento publicado por otra instancia llega a la conexión abierta."""
    env = env_factory()
    panel.login(env)
    panel.link_case(env, "case-1")
    env.handover.case_list = [panel.case_item("case-1")]
    other = FakeRepository()
    other.panel_events = env.repo.panel_events
    other._panel_event_times = env.repo._panel_event_times
    with env.client.websocket_connect(
        "/asesor/ws",
        headers={"origin": "http://testserver", "host": "testserver"},
    ) as ws:
        ws.receive_json()
        other.publish_panel_event("case-1", "case_updated", panel.NOW)
        event = ws.receive_json()
    assert event["case_id"] == "case-1"


def test_events_older_than_retention_deleted_on_publish(env_factory):
    """R21: al publicar se borran los eventos más antiguos que la retención."""
    env = env_factory()
    env.repo.panel_events_retention_hours = 24
    env.repo.publish_panel_event(
        "old", "message", env.adapters.clock() - timedelta(hours=48)
    )
    env.repo.publish_panel_event("new", "message", env.adapters.clock())
    assert [event.case_id for event in env.repo.panel_events] == ["new"]


def test_suppression_deletes_case_events(env_factory, panel):
    """R22: la supresión de datos borra los eventos de los casos purgados."""
    env = env_factory()
    now = panel.NOW
    client = env.repo.create_client_credential(
        "cliente1",
        "hash",
        now - timedelta(days=1),
        now + timedelta(days=30),
        now,
    )
    contact = env.repo.get_or_create_channel_contact("telegram", "10", "100", now)
    env.repo.client_sessions["s1"] = ClientSession(
        id="s1",
        profile_id=client.id,
        contact_id=contact.id,
        started_at=now - timedelta(minutes=10),
        last_activity_at=now - timedelta(minutes=1),
        ended_at=now,
    )
    env.repo.create_or_get_pending_suppression(
        "req-1", client.id, contact.id, "telegram", now
    )
    env.repo.link_case("case-1", contact.id, now)
    env.repo.publish_panel_event("case-1", "message", now)
    admin_profile = env.repo.create_profile("admin1", "admin", "hash", now)

    execute_suppression("req-1", admin_profile.id, env.settings, env.adapters)

    assert not any(event.case_id == "case-1" for event in env.repo.panel_events)
