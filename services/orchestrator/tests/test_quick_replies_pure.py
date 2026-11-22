"""Lógica pura de respuestas rápidas del bot (#71)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from lazaro_contracts import ImageBlock, LinkBlock, ListBlock, TextBlock

from orchestrator.domain import QuickReply, QuickReplyImageInvalid, QuickReplyInvalid
from orchestrator.quick_replies import (
    build_blocks,
    parse_triggers,
    pick_reply,
    validate_image,
)

NOW = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 16
JPEG = b"\xff\xd8\xff" + b"0" * 16
WEBP = b"RIFF" + b"\x00\x00\x00\x00" + b"WEBP" + b"0" * 16


def _reply(
    reply_id: str = "qr-1",
    *,
    name: str = "Horario",
    triggers: tuple[str, ...] = ("horario",),
    blocks: tuple[dict, ...] | None = None,
    image_id: str | None = None,
    active: bool = True,
    priority: int = 0,
    created_at: datetime | None = None,
) -> QuickReply:
    return QuickReply(
        id=reply_id,
        name=name,
        triggers=triggers,
        blocks=blocks or ({"type": "text", "text": "Atendemos de 9 a 5"},),
        image_id=image_id,
        active=active,
        priority=priority,
        created_at=created_at or NOW,
        updated_at=created_at or NOW,
    )


def test_parse_triggers_splits_lines_and_commas_without_duplicates():
    """R5, R6: disparadores por línea o coma, normalizados para deduplicar."""
    assert parse_triggers("Cómo pago\nhorario, CÓMO PAGO") == [
        "Cómo pago",
        "horario",
    ]


@pytest.mark.parametrize(
    "raw",
    ["", "   ", "a", "x" * 81, ",".join(f"tema{i}" for i in range(21))],
)
def test_parse_triggers_rejects_empty_short_long_and_too_many(raw):
    """R5, R6: sin disparadores, menos de 2, más de 80 o más de 20 -> inválido."""
    with pytest.raises(QuickReplyInvalid):
        parse_triggers(raw)


def test_pick_reply_normalizes_case_accents_and_punctuation():
    """R13: minúsculas, sin tildes ni puntuación y espacios colapsados."""
    reply = _reply(triggers=("como pago",))
    assert pick_reply("¿CÓMO   PAGO?", [reply]) is reply


def test_pick_reply_requires_whole_words():
    """R13: «pago» no coincide con «pagos» ni con una palabra mayor."""
    reply = _reply(triggers=("pago",))
    assert pick_reply("quiero pagos", [reply]) is None
    assert pick_reply("quiero pagar", [reply]) is None
    assert pick_reply("quiero pago ya", [reply]) is reply


def test_pick_reply_ignores_inactive_replies():
    """R15: una respuesta desactivada nunca se evalúa."""
    reply = _reply(active=False)
    assert pick_reply("horario", [reply]) is None


def test_pick_reply_uses_priority_then_oldest_then_id():
    """R14: mayor prioridad; en empate la más antigua y luego el id menor."""
    old = _reply("qr-b", priority=5, created_at=NOW, triggers=("horario",))
    newer = _reply(
        "qr-a", priority=5, created_at=NOW + timedelta(minutes=1), triggers=("horario",)
    )
    lower_id = _reply(
        "qr-a", priority=5, created_at=NOW, triggers=("horario",)
    )
    high = _reply("qr-z", priority=9, created_at=NOW, triggers=("horario",))

    assert pick_reply("horario", [old, newer, high]) is high
    assert pick_reply("horario", [old, newer]) is old
    assert pick_reply("horario", [lower_id, old]) is lower_id


def test_pick_reply_returns_none_without_match():
    """R16: sin coincidencia el flujo sigue normal."""
    assert pick_reply("otra cosa", [_reply()]) is None


@pytest.mark.parametrize(
    ("data", "content_type"),
    [(PNG, "image/png"), (JPEG, "image/jpeg"), (WEBP, "image/webp")],
)
def test_validate_image_accepts_png_jpeg_and_webp_by_signature(data, content_type):
    """R24: la firma binaria decide el tipo real, no el nombre."""
    assert validate_image(data, 2048) == content_type


@pytest.mark.parametrize("data", [b"", b"no-es-imagen", b"GIF89a" + b"0" * 10])
def test_validate_image_rejects_empty_or_foreign_content(data):
    """R25: vacío o firma no admitida -> `quick_reply_image_invalid`."""
    with pytest.raises(QuickReplyImageInvalid) as error:
        validate_image(data, 2048)
    assert error.value.code == "quick_reply_image_invalid"


def test_validate_image_rejects_too_large():
    """R25: más bytes que el máximo configurado -> inválido."""
    with pytest.raises(QuickReplyImageInvalid):
        validate_image(PNG + b"x" * 64, 16)


def test_build_blocks_converts_more_than_three_options_to_a_list():
    """R1: hasta 10 opciones se representan con el bloque de lista del contrato."""
    reply = _reply(
        blocks=(
            {
                "type": "options",
                "options": ["Uno", "Dos", "Tres", "Cuatro"],
            },
        )
    )
    blocks = build_blocks(reply, supports_images=False, image_url=None)
    assert len(blocks) == 1
    assert isinstance(blocks[0], ListBlock)
    assert list(blocks[0].options) == ["Uno", "Dos", "Tres", "Cuatro"]


def test_build_blocks_sends_image_when_channel_supports_it():
    """R32: con `supports_images` la imagen viaja como `ImageBlock`."""
    reply = _reply(
        blocks=(
            {"type": "text", "text": "Escanea el QR"},
            {"type": "image", "url": "https://cdn.example/qr.png", "alt_text": "QR"},
        )
    )
    blocks = build_blocks(
        reply, supports_images=True, image_url="https://panel.example/media/x.png"
    )
    assert isinstance(blocks[0], TextBlock)
    assert isinstance(blocks[1], ImageBlock)
    assert str(blocks[1].url) == "https://cdn.example/qr.png"


def test_build_blocks_degrades_image_to_link_without_support():
    """R33: un canal sin imágenes recibe un enlace con el texto alternativo."""
    reply = _reply(
        blocks=(
            {"type": "text", "text": "Escanea el QR"},
            {"type": "image", "url": "https://cdn.example/qr.png", "alt_text": "QR"},
        )
    )
    blocks = build_blocks(reply, supports_images=False, image_url=None)
    links = [block for block in blocks if isinstance(block, LinkBlock)]
    assert len(links) == 1
    assert (links[0].text, str(links[0].url)) == ("QR", "https://cdn.example/qr.png")


def test_build_blocks_uses_text_when_reply_already_has_a_link():
    """R34: con un enlace previo la imagen degradada va como texto «alt: url»."""
    reply = _reply(
        blocks=(
            {"type": "image", "url": "https://cdn.example/qr.png", "alt_text": "QR"},
            {"type": "link", "text": "Manual", "url": "https://example.com/manual"},
        )
    )
    blocks = build_blocks(reply, supports_images=False, image_url=None)
    assert [block.type for block in blocks] == ["text", "link"]
    assert blocks[0].text == "QR: https://cdn.example/qr.png"


def test_build_blocks_omits_uploaded_image_without_absolute_url():
    """R35: sin URL absoluta se omite la imagen y se envía el resto."""
    reply = _reply(
        blocks=(
            {"type": "text", "text": "Escanea el QR"},
            {"type": "image", "alt_text": "QR"},
        ),
        image_id="a" * 32,
    )
    blocks = build_blocks(reply, supports_images=True, image_url=None)
    assert [block.type for block in blocks] == ["text"]


def test_build_blocks_builds_absolute_url_for_uploaded_image():
    """R32: la imagen subida usa la URL absoluta calculada al enviar."""
    reply = _reply(
        blocks=(
            {"type": "text", "text": "Escanea el QR"},
            {"type": "image", "alt_text": "QR"},
        ),
        image_id="a" * 32,
    )
    blocks = build_blocks(
        reply,
        supports_images=True,
        image_url=f"https://panel.example/media/respuestas/{'a' * 32}",
    )
    assert isinstance(blocks[1], ImageBlock)
    assert str(blocks[1].url).endswith("/media/respuestas/" + "a" * 32)
