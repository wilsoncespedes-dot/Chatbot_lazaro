"""Guardas del orquestador para el contrato de canal abierto (#60)."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from orchestrator.privacy import notice_sha256
from orchestrator.states import ConversationState

from fakes import drain_queues

SERVICE_TOKEN = "svc-token"
HEADERS = {"X-Service-Token": SERVICE_TOKEN}
RECEIVED_AT = "2026-11-03T16:05:12Z"
NOW = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
MEDIA_MIME = {
    "image": "image/jpeg",
    "file": "application/pdf",
    "audio": "audio/ogg",
}


def _canonical(channel: str, message_id: str, **changes):
    data = {
        "channel": channel,
        "external_user_id": "10" if channel == "telegram" else "57300",
        "external_chat_id": "100" if channel == "telegram" else "57300",
        "external_message_id": message_id,
        "kind": "text",
        "text": "Hola",
        "received_at": RECEIVED_AT,
    }
    data.update(changes)
    return data


def _post(env, channel: str, message_id: str, **changes):
    response = env.client.post(
        "/messages",
        json=_canonical(channel, message_id, **changes),
        headers=HEADERS,
    )
    drain_queues(env.settings, env.adapters)
    return response


def _assert_nothing_happened(env, message_id: str) -> None:
    assert (env.repo.processed_messages) == set()
    assert env.repo.messages == []
    assert env.gateway.channel_sent == []
    assert env.gateway.sent == []
    assert env.rag.calls == []
    assert env.llm.calls == []
    assert env.repo.processed_messages == set()
    assert message_id not in {key[1] for key in env.repo.processed_messages}


def _consent(env, channel: str, user: str) -> None:
    env.repo.add_channel_privacy_consent(
        channel,
        user,
        env.settings.privacy_notice_version,
        notice_sha256(env.settings.privacy_notice_text),
        NOW,
    )


# ── R43, R44: canales y dirección ───────────────────────────────────────────


@pytest.mark.parametrize("channel", ["canal-externo", "instagram"])
def test_post_messages_accepts_any_valid_channel(env, channel: str):
    """R43 adaptado por #65 (R28, R29): cualquier canal válido recibe 202 y se procesa."""
    _consent(env, channel, "57300")
    response = _post(env, channel, "m-1")
    assert response.status_code == 202
    assert any(sent[0] == channel for sent in env.gateway.channel_sent)


def test_post_messages_rejects_outbound_direction(env):
    """R44: un NormalizedMessage outbound responde 422 sin procesar ni persistir."""
    _consent(env, "whatsapp", "57300")
    response = _post(env, "whatsapp", "out-1", direction="outbound")
    assert response.status_code == 422
    assert response.json()["error"] == "validation_error"
    _assert_nothing_happened(env, "out-1")


# ── R45: solo texto para tipos multimedia ───────────────────────────────────


@pytest.mark.parametrize("channel", ["telegram", "whatsapp"])
@pytest.mark.parametrize("kind", ["image", "file", "audio"])
def test_media_kinds_get_unsupported_reply_without_persistence(env, channel, kind):
    """R45: el tipo multimedia recibe el texto fijo sin estado ni persistencia."""
    user = "10" if channel == "telegram" else "57300"
    chat = "100" if channel == "telegram" else "57300"
    contact = env.repo.get_or_create_channel_contact(channel, user, chat, NOW)
    env.repo.set_conversation_state(contact.id, ConversationState.ACTIVE, NOW)

    response = _post(
        env,
        channel,
        f"media-{kind}",
        kind=kind,
        text="Mira esto",
        attachments=[{"type": kind, "mime_type": MEDIA_MIME[kind]}],
        metadata={"plataforma": "prueba"},
    )

    assert response.status_code == 202
    assert env.repo.get_conversation_state(contact.id) == ConversationState.ACTIVE
    if channel == "telegram":
        assert env.gateway.sent[-1] == (
            int(chat),
            env.settings.conversation_unsupported_reply,
        )
        # #64: toda la salida pasa por la outbox y se entrega con bloques del
        # contrato, también en Telegram; se comprueba una única entrega.
        assert env.gateway.channel_sent == [
            ("telegram", chat, env.settings.conversation_unsupported_reply)
        ]
    else:
        assert env.gateway.channel_sent[-1] == (
            "whatsapp",
            chat,
            env.settings.conversation_unsupported_reply,
        )
        assert env.gateway.sent == []
    assert env.repo.messages == []
    assert env.rag.calls == []
    assert env.llm.calls == []


# ── R46: el contrato acepta multimedia ──────────────────────────────────────


def test_post_messages_accepts_media_kind(env):
    """R46: un mensaje multimedia válido responde 202 accepted."""
    response = _post(
        env,
        "telegram",
        "media-1",
        kind="image",
        text=None,
        attachments=[{"type": "image", "mime_type": "image/jpeg"}],
        metadata={"plataforma": "prueba"},
    )
    assert response.status_code == 202
    assert response.json() == {"status": "accepted"}
