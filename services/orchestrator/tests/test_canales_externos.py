"""Fases 6 y 7: los canales con webhook propio responden siempre por la outbox."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from orchestrator.privacy import notice_sha256

from fakes import drain_queues

HEADERS = {"X-Service-Token": "svc-token"}
RECEIVED_AT = "2026-11-23T12:00:00Z"
NOW = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
USER = "cliente-externo-1"
CHAT = "conversacion-1"

EXTERNAL_CHANNELS = ["tiktok", "facebook", "instagram"]


def _post(env, channel: str, message_id: str):
    return env.client.post(
        "/messages",
        json={
            "channel": channel,
            "external_user_id": USER,
            "external_chat_id": CHAT,
            "external_message_id": message_id,
            "kind": "text",
            "text": "¿Cómo instalo el módulo?",
            "received_at": RECEIVED_AT,
        },
        headers=HEADERS,
    )


@pytest.mark.parametrize("channel", EXTERNAL_CHANNELS)
def test_external_channel_message_is_answered_through_the_outbox(env, channel):
    """Un mensaje normalizado del canal deja la respuesta en la outbox de ese canal."""
    env.repo.add_channel_privacy_consent(
        channel,
        USER,
        env.settings.privacy_notice_version,
        notice_sha256(env.settings.privacy_notice_text),
        NOW,
    )

    response = _post(env, channel, f"{channel}-m1")
    assert response.status_code == 202
    drain_queues(env.settings, env.adapters)

    rows = [row for row in env.repo.outbox.values() if row["channel"] == channel]
    assert rows, "la respuesta debe pasar por la outbox"
    assert {row["destination"] for row in rows} == {CHAT}
    assert all(row["status"] == "sent" for row in rows)
    assert [sent[0:2] for sent in env.gateway.blocks_sent] == [(channel, CHAT)] * len(rows)
    assert env.gateway.sent == []  # nunca por la ruta heredada de Telegram
