"""Texto nuevo de una respuesta de correo, sin la cita del mensaje anterior.

Los clientes de correo (Gmail, Outlook, Apple Mail) añaden debajo de la
respuesta el mensaje citado y, a veces, una firma. El bot solo debe ver lo que
el cliente escribió: si no, una respuesta «Acepto» llega con el aviso citado y
no se reconoce como decisión. Puro, sin IO.
"""
from __future__ import annotations

import re

# «El lun, 23 nov 2026 a las 18:45, Nombre (<correo>) escribió:» / «On … wrote:».
# Gmail la parte en dos líneas cuando es larga.
_ATTRIBUTION_START = re.compile(r"^(el|on)\s", re.IGNORECASE)
_ATTRIBUTION_END = re.compile(r"(escribió|wrote)\s*:\s*$", re.IGNORECASE)
_MAX_ATTRIBUTION_LENGTH = 300
_SEPARATORS = (
    re.compile(r"^-{2,}\s*(original message|mensaje original)\s*-{2,}$", re.IGNORECASE),
    re.compile(r"^_{10,}$"),
)
# Bloque de cabeceras de Outlook: «De: …» seguido de «Enviado:», «Para:», etc.
_HEADER_START = re.compile(r"^(de|from)\s*:", re.IGNORECASE)
_HEADER_FOLLOW = re.compile(
    r"^(enviado|sent|fecha|date|para|to|asunto|subject)\s*:", re.IGNORECASE
)
_SIGNATURE = re.compile(
    r"^(--\s*|enviado desde\b.*|sent from\b.*|obtener outlook para\b.*"
    r"|get outlook for\b.*)$",
    re.IGNORECASE,
)


def _is_attribution(lines: list[str], index: int) -> bool:
    line = lines[index].strip()
    if not _ATTRIBUTION_START.match(line) or len(line) > _MAX_ATTRIBUTION_LENGTH:
        return False
    if _ATTRIBUTION_END.search(line):
        return True
    following = lines[index + 1].strip() if index + 1 < len(lines) else ""
    return bool(following) and _ATTRIBUTION_END.search(following) is not None


def _is_header_block(lines: list[str], index: int) -> bool:
    if not _HEADER_START.match(lines[index].strip()):
        return False
    following = lines[index + 1 : index + 5]
    return any(_HEADER_FOLLOW.match(line.strip()) for line in following)


def _cut_index(lines: list[str]) -> int | None:
    for index, raw in enumerate(lines):
        line = raw.strip()
        if (
            line.startswith(">")
            or _SIGNATURE.match(line)
            or any(pattern.match(line) for pattern in _SEPARATORS)
            or _is_attribution(lines, index)
            or _is_header_block(lines, index)
        ):
            return index
    return None


def latest_reply_text(text: str) -> str:
    """Devuelve lo escrito encima de la cita y la firma.

    Si todo el cuerpo es cita (por ejemplo, un reenvío sin texto propio), se
    conserva el cuerpo completo para no perder el mensaje.
    """
    lines = text.splitlines()
    cut = _cut_index(lines)
    if cut is None:
        return text.strip()
    reply = "\n".join(lines[:cut]).strip()
    return reply or text.strip()
