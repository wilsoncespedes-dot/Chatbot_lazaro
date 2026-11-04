"""Flujo canónico de POST /messages para ambos canales (#36)."""
from __future__ import annotations

from datetime import datetime, timezone

from orchestrator.privacy import notice_sha256

SERVICE_TOKEN = "svc-token"
HEADERS = {"X-Service-Token": SERVICE_TOKEN}
RECEIVED_AT = "2026-11-03T16:05:12Z"
FIXED_NOW = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)


def _consent(env, channel: str, external_user_id: str) -> None:
    env.repo.add_channel_privacy_consent(
        channel,
        external_user_id,
        env.settings.privacy_notice_version,
        notice_sha256(env.settings.privacy_notice_text),
        FIXED_NOW,
    )


def _canonical(channel: str, external_id: str = "77", **changes):
    data = {
        "channel": channel,
        "external_user_id": "10" if channel == "telegram" else "57300",
        "external_chat_id": "100" if channel == "telegram" else "57300",
        "external_message_id": external_id,
        "kind": "text",
        "text": "Hola",
        "received_at": RECEIVED_AT,
    }
    data.update(changes)
    return data


def test_canonical_whatsapp_message_is_processed_and_answered(env):
    """R10, R13, R16: WhatsApp se procesa con identidad de canal y responde."""
    _consent(env, "whatsapp", "57300")
    response = env.client.post(
        "/messages", json=_canonical("whatsapp", external_id="m1"), headers=HEADERS
    )
    assert response.status_code == 202
    assert response.json() == {"status": "accepted"}
    assert env.rag.calls == [("Hola", env.settings.rag_top_k)]
    assert env.gateway.channel_sent == [("whatsapp", "57300", "Respuesta final")]
    contact = env.repo.contacts[("whatsapp", "57300")]
    assert contact.external_user_id == "57300"
    assert contact.external_chat_id == "57300"
    assert contact.telegram_user_id is None
    assert contact.chat_id is None
    assert env.repo.messages[0].role == "user"


def test_same_canonical_message_produces_the_same_answer_in_both_channels(env):
    """R10, R14: el mismo mensaje lógico conserva el contenido y no fusiona contactos."""
    _consent(env, "telegram", "10")
    _consent(env, "whatsapp", "57300")
    telegram = env.client.post(
        "/messages", json=_canonical("telegram", external_id="10"), headers=HEADERS
    )
    whatsapp = env.client.post(
        "/messages", json=_canonical("whatsapp", external_id="m2"), headers=HEADERS
    )
    assert telegram.json() == {"status": "accepted"}
    assert whatsapp.json() == {"status": "accepted"}
    assert env.gateway.sent == [(100, "Respuesta final")]
    assert env.gateway.channel_sent == [("whatsapp", "57300", "Respuesta final")]
    assert env.repo.contacts[10].id != env.repo.contacts[("whatsapp", "57300")].id


def test_whatsapp_opaque_external_id_is_kept_as_text(env):
    """R1, R16: un id externo no numérico de WhatsApp se acepta y no se castea."""
    _consent(env, "whatsapp", "wa-abc")
    response = env.client.post(
        "/messages",
        json=_canonical(
            "whatsapp",
            external_id="wa-msg",
            external_user_id="wa-abc",
            external_chat_id="wa-chat",
        ),
        headers=HEADERS,
    )
    assert response.status_code == 202
    contact = env.repo.contacts[("whatsapp", "wa-abc")]
    assert (contact.external_user_id, contact.external_chat_id) == ("wa-abc", "wa-chat")
    assert contact.telegram_user_id is None


def test_canonical_telegram_with_opaque_ids_is_accepted_as_text(env):
    """R1, R3, R13: los ids canónicos son texto y no se castean ni rechazan."""
    _consent(env, "telegram", "tg-user")
    response = env.client.post(
        "/messages",
        json=_canonical(
            "telegram",
            external_id="m3",
            external_user_id="tg-user",
            external_chat_id="tg-chat",
        ),
        headers=HEADERS,
    )
    assert response.status_code == 202
    assert response.json() == {"status": "accepted"}
    contact = env.repo.contacts[("telegram", "tg-user")]
    assert (contact.external_user_id, contact.external_chat_id) == (
        "tg-user",
        "tg-chat",
    )
    assert contact.telegram_user_id is None
    assert contact.chat_id is None
    assert env.gateway.channel_sent == [
        ("telegram", "tg-chat", "Respuesta final")
    ]
    assert env.rag.calls == [("Hola", env.settings.rag_top_k)]
