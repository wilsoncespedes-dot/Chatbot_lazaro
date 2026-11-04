"""Contratos del mensaje normalizado y de la respuesta abstracta multicanal (#36)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from lazaro_contracts import (
    MAX_LIST_OPTIONS,
    MAX_OPTION_COUNT,
    MAX_OPTION_LENGTH,
    ChannelCapabilities,
    ChannelSendRequest,
    LinkBlock,
    ListBlock,
    MessageRequest,
    NormalizedMessage,
    OptionsBlock,
    ResponseBlocks,
    TemplateBlock,
    TextBlock,
    normalize_legacy_message,
)

EXAMPLES_DIR = Path(__file__).resolve().parent.parent / "examples"
RECEIVED_AT = "2026-11-03T16:05:12Z"


def _message(**changes):
    data = {
        "channel": "whatsapp",
        "external_user_id": "573001112233",
        "external_chat_id": "573001112233",
        "external_message_id": "wamid-1",
        "kind": "text",
        "text": "Hola",
        "received_at": RECEIVED_AT,
    }
    data.update(changes)
    return data


# ── R1: mensaje normalizado ──────────────────────────────────────────────────


@pytest.mark.parametrize("channel", ["telegram", "whatsapp"])
def test_normalized_message_accepts_both_channels(channel: str):
    """R1: el mismo modelo representa mensajes de Telegram y WhatsApp."""
    message = NormalizedMessage.model_validate(_message(channel=channel))
    assert message.channel == channel


def test_normalized_message_accepts_text_and_button_content():
    """R1: texto y botón se representan con sus campos propios."""
    text = NormalizedMessage.model_validate(_message())
    button = NormalizedMessage.model_validate(
        _message(kind="button", text=None, button_id="acepto")
    )
    assert (text.kind, text.text) == ("text", "Hola")
    assert (button.kind, button.button_id) == ("button", "acepto")


def test_normalized_button_accepts_policy_proof():
    """S15: la prueba del aviso viaja solo con los botones."""
    button = NormalizedMessage.model_validate(
        _message(
            kind="button",
            text=None,
            button_id="privacy.accept",
            button_proof="a" * 32,
        )
    )
    assert button.button_proof == "a" * 32

    with pytest.raises(ValidationError):
        NormalizedMessage.model_validate(_message(button_proof="a" * 32))


def test_options_block_accepts_aligned_button_metadata():
    """S15: IDs y pruebas alineados permiten pintar botones interactivos."""
    block = OptionsBlock.model_validate(
        {
            "type": "options",
            "options": ["Acepto", "No acepto"],
            "option_ids": ["privacy.accept", "privacy.reject"],
            "option_proofs": ["a" * 32, "b" * 32],
        }
    )
    assert block.option_ids == ["privacy.accept", "privacy.reject"]

    with pytest.raises(ValidationError):
        OptionsBlock.model_validate(
            {
                "type": "options",
                "options": ["Acepto", "No acepto"],
                "option_ids": ["privacy.accept"],
            }
        )
    with pytest.raises(ValidationError):
        OptionsBlock.model_validate(
            {
                "type": "options",
                "options": ["Acepto"],
                "option_proofs": ["a" * 32],
            }
        )


def test_normalized_message_accepts_unsupported_kind():
    """R1: audio, imagen o documento se representan como no soportados."""
    message = NormalizedMessage.model_validate(
        _message(kind="unsupported", text=None)
    )
    assert message.kind == "unsupported"


def test_normalized_text_requires_text():
    """R1: un mensaje de tipo texto sin contenido no es válido."""
    with pytest.raises(ValidationError):
        NormalizedMessage.model_validate(_message(text=None))


def test_normalized_button_requires_button_id():
    """R1: un mensaje de tipo botón sin button_id no es válido."""
    with pytest.raises(ValidationError):
        NormalizedMessage.model_validate(_message(kind="button", text=None))


def test_normalized_message_rejects_unknown_kind():
    """R1: solo texto, botón o no soportado son tipos válidos."""
    with pytest.raises(ValidationError):
        NormalizedMessage.model_validate(_message(kind="audio"))


def test_normalized_message_rejects_client_id_from_adapter():
    """R1: el adaptador no puede imponer la identidad interna `client_id`."""
    with pytest.raises(ValidationError):
        NormalizedMessage.model_validate(_message(client_id="c-1"))


def test_normalized_message_rejects_naive_received_at():
    """R1: la fecha de recepción debe incluir zona horaria."""
    with pytest.raises(ValidationError):
        NormalizedMessage.model_validate(_message(received_at="2026-11-03T16:05:12"))


def test_normalized_message_rejects_missing_external_message_id():
    """R1: el identificador externo del mensaje es obligatorio."""
    data = _message()
    del data["external_message_id"]
    with pytest.raises(ValidationError):
        NormalizedMessage.model_validate(data)


def test_legacy_message_translates_to_telegram_channel():
    """R1: el payload Telegram histórico se traduce con update_id como id externo."""
    legacy = MessageRequest.model_validate_json(
        (EXAMPLES_DIR / "message_request.json").read_text(encoding="utf-8")
    )
    normalized = normalize_legacy_message(legacy)
    assert normalized.channel == "telegram"
    assert normalized.external_message_id == str(legacy.update_id)
    assert normalized.external_user_id == str(legacy.telegram_user_id)
    assert normalized.external_chat_id == str(legacy.chat_id)
    assert normalized.kind == "text" and normalized.text == legacy.text


# ── R2: respuesta abstracta ──────────────────────────────────────────────────


def test_text_block_accepts_text():
    """R2: el bloque de texto transporta el texto de la respuesta."""
    block = TextBlock.model_validate({"type": "text", "text": "Hola"})
    assert block.text == "Hola"


def test_options_block_limits_count_and_length():
    """R2: opciones máximo 3 y 20 caracteres."""
    OptionsBlock.model_validate(
        {"type": "options", "options": ["a"] * MAX_OPTION_COUNT}
    )
    OptionsBlock.model_validate(
        {"type": "options", "options": ["a" * MAX_OPTION_LENGTH]}
    )
    with pytest.raises(ValidationError):
        OptionsBlock.model_validate(
            {"type": "options", "options": ["a"] * (MAX_OPTION_COUNT + 1)}
        )
    with pytest.raises(ValidationError):
        OptionsBlock.model_validate(
            {"type": "options", "options": ["a" * (MAX_OPTION_LENGTH + 1)]}
        )


def test_list_block_requires_between_four_and_ten_options():
    """R2: la lista admite de 4 a 10 opciones."""
    ListBlock.model_validate({"type": "list", "options": ["a", "b", "c", "d"]})
    ListBlock.model_validate(
        {"type": "list", "options": [str(i) for i in range(MAX_LIST_OPTIONS)]}
    )
    for invalid in (["a", "b", "c"], [str(i) for i in range(MAX_LIST_OPTIONS + 1)]):
        with pytest.raises(ValidationError):
            ListBlock.model_validate({"type": "list", "options": invalid})


def test_link_block_requires_text_and_url():
    """R2: el bloque de enlace lleva texto y una URL."""
    block = LinkBlock.model_validate(
        {"type": "link", "text": "Abrir", "url": "https://example.com"}
    )
    assert block.url == "https://example.com"
    with pytest.raises(ValidationError):
        LinkBlock.model_validate({"type": "link", "text": "Abrir"})


def test_template_block_accepts_name_and_variables():
    """R2: la plantilla lleva nombre y variables."""
    block = TemplateBlock.model_validate(
        {"type": "template", "name": "aviso", "variables": ["10 de noviembre"]}
    )
    assert (block.name, block.variables) == ("aviso", ["10 de noviembre"])


def test_response_blocks_accepts_mixed_blocks():
    """R2: una respuesta puede combinar texto y opciones."""
    blocks = ResponseBlocks.model_validate_json(
        (EXAMPLES_DIR / "response_blocks.json").read_text(encoding="utf-8")
    )
    assert isinstance(blocks.root[0], TextBlock)
    assert isinstance(blocks.root[1], OptionsBlock)


def test_response_blocks_rejects_empty_response():
    """R2: una respuesta abstracta necesita al menos un bloque."""
    with pytest.raises(ValidationError):
        ResponseBlocks.model_validate([])


def test_response_blocks_allows_only_one_link():
    """R2: como máximo un enlace por mensaje."""
    link = {"type": "link", "text": "Abrir", "url": "https://example.com"}
    ResponseBlocks.model_validate([link])
    with pytest.raises(ValidationError):
        ResponseBlocks.model_validate([link, link])


def test_response_blocks_rejects_unknown_block_type():
    """R2: la unión está discriminada por `type`."""
    with pytest.raises(ValidationError):
        ResponseBlocks.model_validate([{"type": "video", "text": "x"}])


# ── Capacidades y variante canónica de /send ────────────────────────────────


def test_channel_capabilities_describe_window_and_limits():
    """R2, R7: las capacidades informan ventana, límites y plantillas."""
    capabilities = ChannelCapabilities.model_validate_json(
        (EXAMPLES_DIR / "channel_capabilities.json").read_text(encoding="utf-8")
    )
    assert capabilities.free_text_allowed is False
    assert capabilities.requires_template is True
    assert capabilities.max_options == MAX_OPTION_COUNT
    assert capabilities.max_list_options == MAX_LIST_OPTIONS


def test_channel_capabilities_reject_inverted_list_bounds():
    """R2: el mínimo de lista no puede superar el máximo."""
    with pytest.raises(ValidationError):
        ChannelCapabilities(
            free_text_allowed=True,
            max_options=3,
            min_list_options=10,
            max_list_options=4,
            supports_links=True,
            requires_template=False,
        )


def test_channel_send_request_is_canonical_and_carries_blocks():
    """R2: la variante canónica de /send lleva canal, destino y bloques."""
    request = ChannelSendRequest.model_validate_json(
        (EXAMPLES_DIR / "channel_send_request.json").read_text(encoding="utf-8")
    )
    assert request.channel == "whatsapp"
    assert request.destination == "573001112233"
    assert isinstance(request.blocks[0], TextBlock)


def test_channel_send_request_requires_blocks():
    """R2: sin bloques no hay respuesta que enviar."""
    with pytest.raises(ValidationError):
        ChannelSendRequest.model_validate(
            {"channel": "telegram", "destination": "1", "blocks": []}
        )


def test_examples_are_valid_json():
    """R1, R2: los ejemplos nuevos son JSON válido."""
    for path in EXAMPLES_DIR.glob("*block*.json"):
        json.loads(path.read_text(encoding="utf-8"))
    for name in ("normalized_message.json", "normalized_button_message.json"):
        json.loads((EXAMPLES_DIR / name).read_text(encoding="utf-8"))
