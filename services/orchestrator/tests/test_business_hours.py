"""Acuse de traspaso dentro y fuera de horario (#42)."""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone

import pytest

from orchestrator.domain import _handover

OUT_OF_HOURS = "Estamos fuera de horario; tu caso quedó en cola."


@pytest.fixture()
def env(env_factory):
    return env_factory(admin_cookie_secure=False)


def _contact(env):
    return env.repo.get_or_create_channel_contact(
        "telegram", "10", "100", env.adapters.clock()
    )


def test_out_of_hours_sends_configured_reply_event_and_keeps_case(env):
    """R42: fuera de horario envía out_of_hours_reply y registra el evento."""
    env.settings.business_hours_enabled = True
    env.repo.save_conversation_texts(
        replace(env.repo.get_conversation_texts(), out_of_hours_reply=OUT_OF_HOURS),
        "admin-1",
        env.adapters.clock(),
    )
    contact = _contact(env)
    assert _handover(contact, "user_request", env.settings, env.adapters) is True
    assert env.gateway.sent[-1] == (100, OUT_OF_HOURS)
    assert ("out_of_hours", "queued") in env.events()
    assert env.repo.case_links


def test_out_of_hours_without_text_falls_back_to_current_ack(env):
    """R42: si out_of_hours_reply está vacío se conserva el acuse actual."""
    env.settings.business_hours_enabled = True
    contact = _contact(env)
    _handover(contact, "user_request", env.settings, env.adapters)
    assert env.gateway.sent[-1] == (100, env.settings.handover_ack_reply)


def test_within_business_hours_or_disabled_keeps_current_ack(env):
    """R43: dentro de horario o desactivado se envía el acuse de siempre."""
    env.settings.business_hours_enabled = True
    env.settings.business_hours_start = "00:00"
    env.settings.business_hours_end = "23:59"
    env.adapters.clock = lambda: datetime(
        2026, 1, 2, 15, 0, 0, tzinfo=timezone.utc
    )
    contact = _contact(env)
    _handover(contact, "user_request", env.settings, env.adapters)
    assert env.gateway.sent[-1] == (100, env.settings.handover_ack_reply)
    assert not [event for event in env.repo.events if event.type == "out_of_hours"]

    env.settings.business_hours_enabled = False
    _handover(contact, "user_request", env.settings, env.adapters)
    assert env.gateway.sent[-1] == (100, env.settings.handover_ack_reply)
    assert not [event for event in env.repo.events if event.type == "out_of_hours"]
