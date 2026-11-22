"""Flujo del mensaje con respuestas rápidas del bot (#71)."""
from __future__ import annotations

import pytest
from lazaro_contracts import (
    ChannelCapabilities,
    ImageBlock,
    LinkBlock,
    TextBlock,
)

from orchestrator.adapters.channels import FakeChannelDirectory
from orchestrator.domain import QuickReply, ServiceUnavailable
from orchestrator.states import ConversationState

from fakes import channel_info


def _reply(
    reply_id: str = "qr-1",
    *,
    name: str = "Panel",
    triggers: tuple[str, ...] = ("panel",),
    blocks: tuple[dict, ...] | None = None,
    image_id: str | None = None,
    priority: int = 0,
) -> QuickReply:
    return QuickReply(
        id=reply_id,
        name=name,
        triggers=triggers,
        blocks=blocks
        or (
            {"type": "text", "text": "Escanea este código"},
            {
                "type": "link",
                "text": "Abrir el panel",
                "url": "https://panel.example/qr",
            },
        ),
        image_id=image_id,
        active=True,
        priority=priority,
        created_at=None,
        updated_at=None,
    )


def _add(env, reply: QuickReply) -> QuickReply:
    now = env.clock()
    stored = QuickReply(
        id=reply.id,
        name=reply.name,
        triggers=reply.triggers,
        blocks=reply.blocks,
        image_id=reply.image_id,
        active=reply.active,
        priority=reply.priority,
        created_at=now,
        updated_at=now,
    )
    env.repo.add_quick_reply(stored)
    return stored


def _events(env, kind: str) -> list:
    return [event for event in env.repo.events if event.type == kind]


def test_active_conversation_answers_without_llm_or_rag(env):
    """R17, R19, R20, R21: responde, registra evento e historial sin modelo ni RAG."""
    _add(env, _reply())
    env.rag.fail = True
    env.llm.fail = True

    response = env.post(text="Quiero ver el panel", update_id=1)

    assert response.status_code == 202
    assert env.rag.calls == []
    assert env.llm.calls == []
    [event] = _events(env, "quick_reply")
    assert event.reason == "qr-1"
    assert ("bot", "Escanea este código") in [
        (message.role, message.text) for message in env.repo.messages
    ]
    channel, destination, blocks = env.gateway.blocks_sent[-1]
    assert (channel, destination) == ("telegram", "100")
    assert isinstance(blocks[0], TextBlock)
    assert blocks[0].text == "Escanea este código"


def test_non_active_states_never_evaluate_quick_replies(env_factory):
    """R18: new, consentimiento, login, asesor, no_access y cerrada no disparan."""
    for state in (
        ConversationState.NEW,
        ConversationState.AWAITING_CONSENT,
        ConversationState.CLOSED,
        ConversationState.AWAITING_LOGIN,
        ConversationState.WITH_ADVISOR,
        ConversationState.NO_ACCESS,
    ):
        env = env_factory()
        contact = env.repo.get_or_create_contact(10, 100, env.clock())
        env.repo.set_conversation_state(contact.id, state, env.clock())
        _add(env, _reply())

        env.post(text="Quiero ver el panel", update_id=1)

        assert _events(env, "quick_reply") == [], state


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("borrar mis datos", ("escalation", "suppression")),
        ("quiero un asesor", ("escalation", "user_request")),
        ("no me sirves", ("escalation", "frustration")),
    ],
)
def test_suppression_handover_and_frustration_win_over_quick_reply(
    env_factory, text, expected
):
    """R17: los guardarraíles previos tienen prioridad sobre la respuesta rápida."""
    env = env_factory()
    _add(env, _reply(triggers=(text,)))

    env.post(text=text, update_id=1)

    assert expected in env.events()
    assert _events(env, "quick_reply") == []


def _image_reply() -> QuickReply:
    return _reply(
        blocks=(
            {"type": "text", "text": "Escanea el QR"},
            {"type": "image", "url": "https://cdn.example/qr.png", "alt_text": "QR"},
        )
    )


def test_directory_without_images_degrades_to_link(env):
    """R33: Telegram no informa `supports_images=true` y recibe un enlace."""
    _add(env, _image_reply())

    env.post(text="panel", update_id=1)

    blocks = env.gateway.blocks_sent[-1][2]
    assert not any(isinstance(block, ImageBlock) for block in blocks)
    link = next(block for block in blocks if isinstance(block, LinkBlock))
    assert (link.text, str(link.url)) == ("QR", "https://cdn.example/qr.png")


def test_unknown_channel_degrades_to_link(env):
    """R33: un canal fuera del directorio se trata como sin imágenes."""
    env.adapters.channels = FakeChannelDirectory([])
    _add(env, _image_reply())

    env.post(text="panel", update_id=1)

    blocks = env.gateway.blocks_sent[-1][2]
    assert any(isinstance(block, LinkBlock) for block in blocks)
    assert not any(isinstance(block, ImageBlock) for block in blocks)


def test_channel_with_images_receives_image_block(env):
    """R32: un canal que informa `supports_images=true` recibe la imagen."""
    capabilities = ChannelCapabilities(
        free_text_allowed=True,
        max_options=3,
        min_list_options=4,
        max_list_options=10,
        supports_links=True,
        requires_template=False,
        supports_images=True,
    )
    env.adapters.channels = FakeChannelDirectory(
        [channel_info("telegram", capabilities=capabilities)]
    )
    _add(env, _image_reply())

    env.post(text="panel", update_id=1)

    blocks = env.gateway.blocks_sent[-1][2]
    image = next(block for block in blocks if isinstance(block, ImageBlock))
    assert str(image.url) == "https://cdn.example/qr.png"


def test_purchase_intent_still_creates_case_after_quick_reply(env_factory):
    """R22: la respuesta rápida no impide la creación opcional de caso de #70."""
    env = env_factory(purchase_intent_create_case=True)
    contact = env.repo.get_or_create_contact(10, 100, env.clock())
    env.repo.set_conversation_state(
        contact.id, ConversationState.ACTIVE, env.clock()
    )
    _add(env, _reply(triggers=("panel",)))

    env.post(text="me interesa el panel", update_id=1)

    assert _events(env, "purchase_intent")
    assert _events(env, "quick_reply")
    [request] = env.handover.requests
    assert request.reason == "user_request"


def test_repository_read_failure_continues_with_normal_flow(env):
    """R23: si falla la lectura, se registra y sigue el flujo normal."""
    _add(env, _reply())

    def failing(_only_active: bool = False):
        raise RuntimeError("boom")

    env.repo.list_quick_replies = failing

    env.post(text="Quiero ver el panel", update_id=1)

    assert _events(env, "quick_reply") == []
    assert env.gateway.sent[-1] == (100, "Respuesta final")
    assert env.rag.calls


def test_send_failure_continues_with_normal_flow(env):
    """R23: si falla el envío, se registra y sigue el flujo normal."""
    _add(env, _reply())
    original = env.repo.add_message_with_outbox
    calls = {"count": 0}

    def failing_once(contact_id, role, text, at, entry):
        if calls["count"] == 0:
            calls["count"] += 1
            raise ServiceUnavailable("cola caída")
        return original(contact_id, role, text, at, entry)

    env.repo.add_message_with_outbox = failing_once

    env.post(text="Quiero ver el panel", update_id=1)

    assert _events(env, "quick_reply") == []
    assert env.gateway.sent[-1] == (100, "Respuesta final")


def test_no_match_keeps_the_normal_rag_flow(env):
    """R16: sin coincidencia se responde como antes."""
    _add(env, _reply(triggers=("panel",)))

    env.post(text="otra consulta", update_id=1)

    assert _events(env, "quick_reply") == []
    assert env.gateway.sent[-1] == (100, "Respuesta final")
