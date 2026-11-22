"""Lógica pura de respuestas rápidas del bot (#71): disparadores, imagen y bloques.

No hace IO ni llama al modelo: el dominio decide y los adaptadores ejecutan.
"""
from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING

from lazaro_contracts import (
    ImageBlock,
    LinkBlock,
    ListBlock,
    OptionsBlock,
    ResponseBlock,
    TextBlock,
)

from .classifier import _phrase

if TYPE_CHECKING:
    from .domain import QuickReply

MAX_TRIGGERS = 20
MIN_TRIGGER_CHARS = 2
MAX_TRIGGER_CHARS = 80
MAX_REPLY_NAME_CHARS = 200
MAX_REPLY_TEXT_CHARS = 4096
MAX_REPLY_OPTIONS = 10
MAX_REPLY_OPTION_CHARS = 20
MIN_PRIORITY = 0
MAX_PRIORITY = 1000

_TRIGGER_SPLIT = re.compile(r"[,\n]")


@dataclass(frozen=True)
class QuickReplyForm:
    """Campos del formulario HTML, sin interpretar (todo texto)."""

    name: str = ""
    triggers: str = ""
    text: str = ""
    options: str = ""
    link_text: str = ""
    link_url: str = ""
    image_url: str = ""
    image_alt: str = ""
    priority: str = "0"
    active: bool = True

    @classmethod
    def from_mapping(cls, values: Mapping[str, str]) -> "QuickReplyForm":
        def value(key: str) -> str:
            return str(values.get(key, "") or "")

        active_raw = values.get("active")
        active = True if active_raw is None else str(active_raw) in (
            "1",
            "true",
            "on",
            "si",
            "sí",
        )
        return cls(
            name=value("name"),
            triggers=value("triggers"),
            text=value("text"),
            options=value("options"),
            link_text=value("link_text"),
            link_url=value("link_url"),
            image_url=value("image_url"),
            image_alt=value("image_alt"),
            priority=value("priority"),
            active=active,
        )


def _invalid(message: str) -> None:
    from .domain import QuickReplyInvalid

    raise QuickReplyInvalid(message)


def _image_invalid(message: str) -> None:
    from .domain import QuickReplyImageInvalid

    raise QuickReplyImageInvalid(message)


def parse_triggers(raw: str) -> list[str]:
    """R5, R6: una por línea o coma; exige 1..20 y 2..80 normalizados."""
    pieces = [piece.strip() for piece in _TRIGGER_SPLIT.split(raw) if piece.strip()]
    if not pieces:
        _invalid("La respuesta rápida necesita al menos un disparador.")
    triggers: list[str] = []
    seen: set[str] = set()
    for piece in pieces:
        normalized = _phrase(piece)
        if not MIN_TRIGGER_CHARS <= len(normalized) <= MAX_TRIGGER_CHARS:
            _invalid("Cada disparador debe tener entre 2 y 80 caracteres.")
        if normalized in seen:
            continue
        seen.add(normalized)
        triggers.append(piece)
    if len(triggers) > MAX_TRIGGERS:
        _invalid("No se admiten más de 20 disparadores.")
    return triggers


def pick_reply(text: str, replies: Sequence["QuickReply"]) -> "QuickReply | None":
    """R13–R16: palabras completas, solo activas, prioridad y desempate estable."""
    haystack = f" {_phrase(text)} "
    matches: list["QuickReply"] = []
    for reply in replies:
        if not reply.active:
            continue
        for trigger in reply.triggers:
            key = _phrase(trigger)
            if key and f" {key} " in haystack:
                matches.append(reply)
                break
    if not matches:
        return None
    return min(matches, key=lambda reply: (-reply.priority, reply.created_at, reply.id))


def validate_image(data: bytes, max_bytes: int) -> str:
    """R24, R25: firma binaria PNG/JPEG/WebP y tamaño máximo."""
    if not data:
        _image_invalid("La imagen está vacía.")
    if len(data) > max_bytes:
        _image_invalid("La imagen supera el tamaño máximo permitido.")
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if len(data) >= 12 and data[0:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    _image_invalid("La imagen debe ser PNG, JPEG o WebP.")


def build_blocks(
    reply: "QuickReply",
    *,
    supports_images: bool,
    image_url: str | None,
) -> list[ResponseBlock]:
    """R32–R35: bloques listos para el canal, con degradación de imagen."""
    has_link = any(block.get("type") == "link" for block in reply.blocks)
    result: list[ResponseBlock] = []
    for block in reply.blocks:
        kind = block.get("type")
        if kind == "text":
            text = str(block.get("text", ""))
            if text:
                result.append(TextBlock(type="text", text=text))
        elif kind == "options":
            options = [str(item) for item in block.get("options", [])]
            if 1 <= len(options) <= 3:
                result.append(OptionsBlock(type="options", options=options))
            elif 4 <= len(options) <= 10:
                result.append(ListBlock(type="list", options=options))
        elif kind == "link":
            text = str(block.get("text", ""))
            url = str(block.get("url", ""))
            if text and url:
                result.append(LinkBlock(type="link", text=text, url=url))
        elif kind == "image":
            url = str(block.get("url", "") or image_url or "")
            alt = str(block.get("alt_text", "") or "Imagen")
            if not url:
                continue
            if supports_images:
                result.append(ImageBlock(type="image", url=url, alt_text=alt))
            elif has_link:
                result.append(TextBlock(type="text", text=f"{alt}: {url}"))
            else:
                result.append(LinkBlock(type="link", text=alt, url=url))
    return result


def image_id_valid(image_id: str) -> bool:
    """R27: los ids de imagen son `uuid4().hex`."""
    return re.fullmatch(r"[0-9a-f]{32}", image_id) is not None
