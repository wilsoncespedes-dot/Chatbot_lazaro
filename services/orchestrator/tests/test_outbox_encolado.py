"""Encolado de la salida en `outbox` (#64, R17-R21)."""
from __future__ import annotations

from datetime import datetime, timezone

from lazaro_contracts import (
    CaseReplyRequest,
    MessageRequest,
    NormalizedMessage,
    normalize_legacy_message,
)

from orchestrator.domain import (
    _send,
    advisor_send_template,
    process_channel_message,
    reply_to_case,
)
from orchestrator.privacy import notice_sha256

FIXED = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
RECEIVED_AT = "2026-01-02T03:04:00+00:00"


def _consent(env, channel: str = "telegram", user: str = "10") -> None:
    env.repo.add_channel_privacy_consent(
        channel,
        user,
        env.settings.privacy_notice_version,
        notice_sha256(env.settings.privacy_notice_text),
        env.adapters.clock(),
    )


def _message(update_id: int = 1) -> MessageRequest:
    return MessageRequest(
        update_id=update_id,
        telegram_user_id=10,
        chat_id=100,
        # Pregunta real: «Hola» ya tiene respuesta propia de saludo (#86).
        text="¿Cómo emito una factura?",
        received_at=FIXED,
    )


def _link(env, case_id: str = "case-1", channel: str = "telegram"):
    contact = env.repo.get_or_create_channel_contact(
        channel, "10" if channel == "telegram" else "57300",
        "100" if channel == "telegram" else "57301", FIXED,
    )
    env.repo.link_case(case_id, contact.id, FIXED)
    return contact


def test_bot_reply_and_message_share_a_transaction(env):
    """R17: la respuesta del bot y su outbox se escriben juntas."""
    _consent(env)
    process_channel_message(
        normalize_legacy_message(_message()), env.settings, env.adapters
    )
    bot = [message for message in env.repo.messages if message.role == "bot"]
    assert [message.text for message in bot] == ["Respuesta final"]
    [(row)] = env.repo.outbox.values()
    assert row["kind"] == "bot"
    assert row["contact_id"] == bot[0].contact_id
    assert row["blocks"][0]["text"] == "Respuesta final"


def test_long_bot_reply_keeps_complete_history_and_queues_multiple_blocks(env):
    """R5: el historial conserva la respuesta y el outbox guarda sus partes completas."""
    contact = _link(env)
    text = ("Respuesta completa con todos los pasos.\n\n" * 120).strip()

    assert _send(contact, text, env.adapters)

    [message] = [row for row in env.repo.messages if row.role == "bot"]
    [(outbox)] = env.repo.outbox.values()
    parts = [block["text"] for block in outbox["blocks"]]
    assert message.text == text
    assert len(parts) > 1
    assert all(len(part) <= 3500 for part in parts)
    assert " ".join(" ".join(parts).split()) == " ".join(text.split())


def test_advisor_reply_is_enqueued(env):
    """R18: la respuesta del asesor se guarda con su outbox."""
    contact = _link(env)
    reply_to_case(
        "case-1",
        CaseReplyRequest(advisor_id="700", text="Hola, soy tu asesor"),
        env.settings,
        env.adapters,
    )
    advisor = [message for message in env.repo.messages if message.role == "advisor"]
    assert [message.text for message in advisor] == ["Hola, soy tu asesor"]
    [(row)] = env.repo.outbox.values()
    assert row["kind"] == "advisor"
    assert row["destination_key"] == f"telegram:{contact.chat_id}"


def test_advisor_template_is_enqueued(env):
    """R18: la plantilla del asesor se guarda con su outbox."""
    _link(env, channel="whatsapp")
    advisor_send_template(
        "case-1", "700", "respuesta_asesor", env.settings, env.adapters
    )
    [(row)] = env.repo.outbox.values()
    assert row["kind"] == "advisor"
    assert row["blocks"][0]["type"] == "template"


def test_notice_without_message_is_enqueued(env):
    """R19: un aviso sin mensaje guardado solo crea la fila de outbox."""
    _consent(env, "whatsapp", "57300")
    message = NormalizedMessage(
        channel="whatsapp",
        external_user_id="57300",
        external_chat_id="57300",
        external_message_id="m1",
        kind="image",
        text="Mira",
        attachments=[{"type": "image", "mime_type": "image/jpeg"}],
        received_at=FIXED,
    )
    process_channel_message(message, env.settings, env.adapters)
    assert env.repo.messages == []
    [(row)] = env.repo.outbox.values()
    assert row["kind"] == "notice"
    assert row["blocks"][0]["text"] == env.settings.conversation_unsupported_reply


def test_outbox_failure_reverts_message(env):
    """R20: si falla el outbox no queda el mensaje guardado."""
    contact = env.repo.get_or_create_contact(10, 100, FIXED)
    env.repo.fail_outbox_insert = True
    assert _send(contact, "Hola", env.adapters) is False
    assert env.repo.messages == []


def test_domain_does_not_call_gateway(env):
    """R21: el dominio no entrega al gateway; solo escribe el outbox."""
    _consent(env)
    process_channel_message(
        normalize_legacy_message(_message()), env.settings, env.adapters
    )
    assert env.gateway.sent == []
    assert env.gateway.channel_sent == []
    assert env.gateway.blocks_sent == []
    assert env.repo.outbox
