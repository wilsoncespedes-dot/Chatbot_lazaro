"""#63 R41-R42 adaptado por #65 (R28-R29): la guarda temporal ya no existe."""
from __future__ import annotations

import orchestrator.domain as domain

SERVICE_TOKEN = "svc-token"


def test_attended_channels_guard_was_removed():
    """#65 R28: no queda lista fija de canales aceptados."""
    assert not hasattr(domain, "ATTENDED_CHANNELS")
    assert not hasattr(domain, "INBOX_CHANNELS")


def test_simulated_channel_message_is_accepted_by_the_orchestrator(env):
    """#65 R29: un canal simulado recibe 202 de POST /messages."""
    response = env.client.post(
        "/messages",
        json={
            "channel": "tiktok-simulado",
            "external_user_id": "cliente-demo",
            "external_chat_id": "cliente-demo",
            "external_message_id": "sim-1",
            "kind": "text",
            "text": "Hola",
            "received_at": "2026-01-02T03:04:00+00:00",
        },
        headers={"X-Service-Token": SERVICE_TOKEN},
    )
    assert response.status_code == 202
