"""Validadores puros de respuestas guardadas (#51)."""
from __future__ import annotations

import pytest

from orchestrator.annotations import (
    validate_saved_reply_text,
    validate_saved_reply_title,
)
from orchestrator.domain import (
    PanelValidationError,
    SavedReplyVariablesNotAllowed,
)


def test_title_and_text_are_trimmed():
    """R8: se guarda el texto sin espacios sobrantes."""
    assert validate_saved_reply_title("  Saludo  ", 80) == "Saludo"
    assert validate_saved_reply_text("  Hola\ncliente  ", 1000) == "Hola\ncliente"


@pytest.mark.parametrize("raw", ["", "   "])
def test_empty_title_or_text_is_rejected(raw):
    """R8: vacío tras `strip` -> 422."""
    with pytest.raises(PanelValidationError):
        validate_saved_reply_title(raw, 80)
    with pytest.raises(PanelValidationError):
        validate_saved_reply_text(raw, 1000)


def test_title_and_text_max_length_is_enforced():
    """R8: supera el máximo configurado -> 422."""
    with pytest.raises(PanelValidationError):
        validate_saved_reply_title("x" * 6, 5)
    with pytest.raises(PanelValidationError):
        validate_saved_reply_text("x" * 6, 5)


@pytest.mark.parametrize("raw", ["a\x00b", "a\tb", "a\x7fb"])
def test_control_characters_are_rejected_in_title(raw):
    """R8: el título no admite caracteres de control."""
    with pytest.raises(PanelValidationError):
        validate_saved_reply_title(raw, 80)


def test_text_allows_newlines_but_not_other_control_characters():
    """R8: el texto permite saltos de línea y rechaza otros controles."""
    assert validate_saved_reply_text("Hola\ncliente", 1000) == "Hola\ncliente"
    assert validate_saved_reply_text("Hola\r\ncliente", 1000) == "Hola\ncliente"
    with pytest.raises(PanelValidationError):
        validate_saved_reply_text("Hola\tcliente", 1000)


@pytest.mark.parametrize("raw", ["Hola {nombre}", "Hola }", "${cliente}", "%(id)s"])
def test_variable_markers_are_rejected(raw):
    """R9: `{`, `}`, `${` y `%(` -> `saved_reply_variables_not_allowed`."""
    with pytest.raises(SavedReplyVariablesNotAllowed) as exc_info:
        validate_saved_reply_text(raw, 1000)
    assert exc_info.value.code == "saved_reply_variables_not_allowed"
    assert exc_info.value.status_code == 422
