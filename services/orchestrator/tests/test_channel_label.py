"""Componente único de etiqueta de origen del canal (#67). Puro, sin IO."""
from __future__ import annotations

import re

import pytest
from fakes import channel_info
from lazaro_contracts import CHANNEL_ICONS, DEFAULT_CHANNEL_ICON

from orchestrator import admin
from orchestrator.channel_label import (
    NEUTRAL_COLOR,
    UNKNOWN_GLYPH,
    UNKNOWN_NAME,
    ChannelLabel,
    label_from_policy,
    label_from_values,
    render_channel_label,
    unknown_label,
)
from orchestrator.channels import default_policy, policy_from_info


def _label(channel_id: str = "telegram", **info) -> ChannelLabel:
    return label_from_policy(policy_from_info(channel_info(channel_id, **info)))


def test_component_renders_svg_with_glyph_and_name():
    """R1: SVG con el emoji del ícono y el nombre del canal como texto visible."""
    html = render_channel_label(_label(name="Telegram", icon="telegram"))
    assert html.startswith('<svg class="channel-label"')
    assert 'role="img"' in html
    assert f"{CHANNEL_ICONS['telegram']} Telegram" in html
    assert html.endswith("</svg>")


def test_component_escapes_name_icon_and_color():
    """R2: nombre, ícono y color se escapan antes de insertarse en el marcado."""
    html = render_channel_label(
        ChannelLabel(
            name='<b>"x"</b>',
            glyph="<i>",
            color='#FFF"><script>alert(1)</script>',
            known=True,
        )
    )
    for raw in ("<b>", "<i>", "<script", '"x"'):
        assert raw not in html
    assert "&lt;b&gt;" in html
    assert "&lt;i&gt;" in html


def test_name_is_visible_text_and_aria_label():
    """R3: la etiqueta no depende del color; incluye el nombre como texto y aria-label."""
    html = render_channel_label(_label(name="Soporte"))
    assert 'aria-label="Soporte"' in html
    assert ">💬 Soporte</text>" in html


@pytest.mark.parametrize("color", ["#FFFFFF", "#12345", "white", "#GGGGGG"])
def test_illegible_or_malformed_color_uses_neutral(color):
    """R4: color no `#RRGGBB` o con contraste < 4.5 usa el neutro y conserva el nombre."""
    info = channel_info("canal-x", name="Canal X").model_copy(
        update={"color": color}
    )
    label = label_from_policy(policy_from_info(info))
    assert label.color == NEUTRAL_COLOR
    assert label.name == "Canal X"


def test_legible_color_is_kept():
    """R4: un color `#RRGGBB` con contraste suficiente se conserva."""
    assert _label(color="#1B6FA8").color == "#1B6FA8"


def test_unknown_icon_uses_default_glyph():
    """R5: un ícono fuera de CHANNEL_ICONS usa el glifo por defecto."""
    info = channel_info("canal-x", name="Raro").model_copy(
        update={"icon": "inexistente"}
    )
    assert label_from_policy(policy_from_info(info)).glyph == CHANNEL_ICONS[
        DEFAULT_CHANNEL_ICON
    ]


def test_unknown_label_is_neutral():
    """R6: la etiqueta de un canal ausente es neutra y no depende del color."""
    label = unknown_label()
    assert (label.name, label.glyph, label.color, label.known) == (
        UNKNOWN_NAME,
        UNKNOWN_GLYPH,
        NEUTRAL_COLOR,
        False,
    )


def test_default_policy_is_not_known():
    """R6: la política por defecto distingue un id ausente del directorio."""
    assert default_policy("tiktok").known is False


def test_rendered_label_has_no_inline_styles_or_scripts():
    """R20: cumple PANEL_CSP; sin estilos, scripts ni atributos `on*` en línea."""
    html = render_channel_label(unknown_label())
    assert "style=" not in html.lower()
    assert "<style" not in html.lower()
    assert "<script" not in html.lower()
    assert re.search(r"\son[a-z]+\s*=", html.lower()) is None


def test_admin_channel_label_delegates_to_component():
    """R1/R4: `/admin/canales` usa el mismo componente (misma salida visual)."""
    info = channel_info("simulado", name="Pruebas")
    expected = render_channel_label(
        label_from_values(info.name, CHANNEL_ICONS["tienda"], info.color)
    )
    assert admin._channel_label(info, CHANNEL_ICONS["tienda"]) == expected
