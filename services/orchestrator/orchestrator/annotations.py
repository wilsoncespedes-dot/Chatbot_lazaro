"""Validadores puros de notas, etiquetas y respuestas guardadas (#50, #51)."""
from __future__ import annotations

import re

_CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f-\x9f]")
_TEXT_CONTROL_CHARS = re.compile(r"[\x00-\x09\x0b-\x1f\x7f-\x9f]")
_VARIABLE_MARKERS = ("{", "}", "%(")


def _invalid(message: str) -> None:
    from .domain import PanelValidationError

    raise PanelValidationError(message)


def validate_note_text(raw: str, max_chars: int) -> str:
    """R5: texto obligatorio tras `strip()` y acotado por `CASE_NOTE_MAX_CHARS`."""
    text = raw.strip()
    if not text:
        _invalid("La nota no puede estar vacía.")
    if len(text) > max_chars:
        _invalid("La nota supera el máximo de caracteres permitido.")
    return text


def validate_tag_name(raw: str, max_chars: int) -> str:
    """R17: nombre no vacío, sin caracteres de control y acotado."""
    text = raw.strip()
    if not text:
        _invalid("El nombre de la etiqueta no puede estar vacío.")
    if _CONTROL_CHARS.search(text):
        _invalid("El nombre de la etiqueta contiene caracteres no válidos.")
    text = " ".join(text.split())
    if len(text) > max_chars:
        _invalid("El nombre de la etiqueta supera el máximo de caracteres permitido.")
    return text


def normalize_tag_key(name: str) -> str:
    """R18: clave sin distinguir mayúsculas ni espacios repetidos."""
    return " ".join(name.casefold().split())


def _variables_not_allowed() -> None:
    from .domain import SavedReplyVariablesNotAllowed

    raise SavedReplyVariablesNotAllowed(
        "El texto no admite variables ni datos del cliente."
    )


def _reject_variables(text: str) -> None:
    if any(marker in text for marker in _VARIABLE_MARKERS):
        _variables_not_allowed()


def validate_saved_reply_title(raw: str, max_chars: int) -> str:
    """R8, R9: título obligatorio, sin control, acotado y sin variables."""
    text = raw.strip()
    if not text:
        _invalid("El título de la respuesta no puede estar vacío.")
    _reject_variables(text)
    if len(text) > max_chars:
        _invalid("El título supera el máximo de caracteres permitido.")
    if _CONTROL_CHARS.search(text):
        _invalid("El título contiene caracteres no válidos.")
    return text


def validate_saved_reply_text(raw: str, max_chars: int) -> str:
    """R8, R9: texto obligatorio, permite saltos de línea y rechaza variables."""
    text = raw.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not text:
        _invalid("El texto de la respuesta no puede estar vacío.")
    _reject_variables(text)
    if len(text) > max_chars:
        _invalid("El texto supera el máximo de caracteres permitido.")
    if _TEXT_CONTROL_CHARS.search(text):
        _invalid("El texto contiene caracteres no válidos.")
    return text
