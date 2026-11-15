"""Validadores puros de notas y etiquetas (#50)."""
from __future__ import annotations

import pytest

from orchestrator.annotations import (
    normalize_tag_key,
    validate_note_text,
    validate_tag_name,
)
from orchestrator.domain import PanelValidationError


def test_validate_note_text_strips_and_accepts_boundary():
    """R5: el texto se guarda sin espacios y el límite exacto es válido."""
    assert validate_note_text("  hola  ", 4) == "hola"
    assert validate_note_text("abcd", 4) == "abcd"


@pytest.mark.parametrize("raw", ["", "   ", "\n\t"])
def test_validate_note_text_rejects_blank(raw):
    """R5: vacío tras strip() -> validation_error."""
    with pytest.raises(PanelValidationError):
        validate_note_text(raw, 10)


def test_validate_note_text_rejects_too_long():
    """R5: superar CASE_NOTE_MAX_CHARS -> validation_error."""
    with pytest.raises(PanelValidationError):
        validate_note_text("abcde", 4)


def test_validate_tag_name_trims_and_collapses_spaces():
    """R17: nombre normalizado con espacios simples."""
    assert validate_tag_name("  Pago   urgente  ", 40) == "Pago urgente"


@pytest.mark.parametrize("raw", ["", "  ", "a\x00b", "a\nb", "a\tb"])
def test_validate_tag_name_rejects_blank_or_control(raw):
    """R17: vacío o con caracteres de control -> validation_error."""
    with pytest.raises(PanelValidationError):
        validate_tag_name(raw, 40)


def test_validate_tag_name_rejects_too_long():
    """R17: superar CASE_TAG_NAME_MAX_CHARS -> validation_error."""
    with pytest.raises(PanelValidationError):
        validate_tag_name("abcde", 4)


def test_normalize_tag_key_ignores_case_and_repeated_spaces():
    """R18: la clave de unicidad no distingue mayúsculas ni espacios."""
    assert normalize_tag_key("  Pago   URGENTE ") == "pago urgente"
