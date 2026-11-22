"""Etiqueta de origen del canal (#67): componente único, puro y sin IO."""
from __future__ import annotations

import html
from dataclasses import dataclass

from .admin_channels import icon_glyph, valid_color
from .channels import ChannelPolicy

NEUTRAL_COLOR = "#5B6470"
UNKNOWN_NAME = "Canal desconocido"
UNKNOWN_GLYPH = "❔"
LABEL_TEXT_COLOR = "#FFFFFF"
LABEL_HEIGHT = 26
LABEL_MIN_WIDTH = 24
LABEL_CHAR_WIDTH = 9
LABEL_TEXT_X = 10
LABEL_TEXT_Y = 18
LABEL_FONT_SIZE = 14
LABEL_RADIUS = 6

__all__ = [
    "ChannelLabel",
    "NEUTRAL_COLOR",
    "UNKNOWN_GLYPH",
    "UNKNOWN_NAME",
    "label_from_policy",
    "label_from_values",
    "render_channel_label",
    "unknown_label",
]


@dataclass(frozen=True)
class ChannelLabel:
    name: str
    glyph: str
    color: str
    known: bool


def _readable_color(color: str) -> str:
    """R4: color ilegible o mal formado se sustituye por el neutro."""
    return color if valid_color(color) else NEUTRAL_COLOR


def label_from_values(
    name: str, glyph: str, color: str, *, known: bool = True
) -> ChannelLabel:
    """Etiqueta a partir de valores ya resueltos (por ejemplo, el panel admin)."""
    return ChannelLabel(
        name=name, glyph=glyph, color=_readable_color(color), known=known
    )


def label_from_policy(policy: ChannelPolicy) -> ChannelLabel:
    """R4, R5: glifo e ícono de la política con color legible y estado conocido."""
    return ChannelLabel(
        name=policy.name,
        glyph=icon_glyph(policy.icon),
        color=_readable_color(policy.color),
        known=policy.known,
    )


def unknown_label() -> ChannelLabel:
    """R6: etiqueta neutra para un canal que no está en el directorio."""
    return ChannelLabel(
        name=UNKNOWN_NAME, glyph=UNKNOWN_GLYPH, color=NEUTRAL_COLOR, known=False
    )


def render_channel_label(label: ChannelLabel) -> str:
    """R1-R3, R20: SVG sin estilos ni scripts en línea, con nombre visible."""
    name = html.escape(label.name, quote=True)
    glyph = html.escape(label.glyph, quote=True)
    color = html.escape(label.color, quote=True)
    width = LABEL_MIN_WIDTH + LABEL_CHAR_WIDTH * len(f"{label.glyph} {label.name}")
    return (
        f'<svg class="channel-label" width="{width}" height="{LABEL_HEIGHT}" '
        f'role="img" aria-label="{name}">'
        f'<rect width="{width}" height="{LABEL_HEIGHT}" rx="{LABEL_RADIUS}" '
        f'fill="{color}"></rect>'
        f'<text x="{LABEL_TEXT_X}" y="{LABEL_TEXT_Y}" fill="{LABEL_TEXT_COLOR}" '
        f'font-size="{LABEL_FONT_SIZE}">{glyph} {name}</text>'
        "</svg>"
    )
