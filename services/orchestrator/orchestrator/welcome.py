"""Bloque de bienvenida con los canales públicos activos (#73). Puro, sin IO."""
from __future__ import annotations

from collections.abc import Sequence

from .admin_channels import icon_glyph
from .channels import ChannelPolicy

MAX_WELCOME_CHANNELS = 10
MAX_CONTACT_URL_LENGTH = 200


def _contact_link(contact_url: str) -> str:
    """R36: un enlace guardado inválido se omite al renderizar."""
    if (
        contact_url.startswith("https://")
        and len(contact_url) <= MAX_CONTACT_URL_LENGTH
    ):
        return contact_url
    return ""


def channels_welcome_block(
    policies: Sequence[ChannelPolicy], intro: str, include_simulated: bool
) -> str:
    """R26–R33: lista breve, en texto plano, en orden alfabético por nombre."""
    visible = [
        policy
        for policy in policies
        if policy.active
        and policy.public
        and (include_simulated or not policy.simulated)
    ]
    visible.sort(key=lambda policy: policy.name.casefold())
    lines: list[str] = []
    for policy in visible[:MAX_WELCOME_CHANNELS]:
        line = f"{icon_glyph(policy.icon)} {policy.name}"
        link = _contact_link(policy.contact_url)
        if link:
            line = f"{line}: {link}"
        lines.append(f"- {line}")
    if not lines:
        return ""
    header = intro.strip() or "También puedes escribirnos por estos canales:"
    return f"{header}\n" + "\n".join(lines)
