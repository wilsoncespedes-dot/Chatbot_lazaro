"""Configuración de memoria por cliente y roles del ejecutor de supresión (#40)."""
from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from orchestrator.config import Settings

ROOT = Path(__file__).resolve().parents[3]

MEMORY_VARS = (
    "MEMORY_ENABLED",
    "MEMORY_MAX_ITEMS",
    "MEMORY_ITEM_MAX_CHARS",
    "MEMORY_SUMMARY_MAX_CHARS",
    "MEMORY_INPUT_MAX_MESSAGES",
    "MEMORY_CONTEXT_MESSAGES",
    "MEMORY_PANEL_SUMMARIES",
    "MEMORY_SENSITIVE_MIN_DIGITS",
    "MEMORY_SENSITIVE_KEYWORDS",
    "SUPPRESSION_EXECUTOR_ROLES",
)


def test_r52_memory_defaults_are_safe_and_off():
    """R52: apagada por defecto y con los límites documentados."""
    settings = Settings()

    assert settings.memory_enabled is False
    assert settings.memory_max_items == 20
    assert settings.memory_item_max_chars == 300
    assert settings.memory_summary_max_chars == 1500
    assert settings.memory_input_max_messages == 200
    assert settings.memory_context_messages == 6
    assert settings.memory_panel_summaries == 5
    assert settings.memory_sensitive_min_digits == 6
    assert settings.suppression_executor_roles == "admin"
    assert settings.memory_sensitive_keyword_list
    assert settings.suppression_executor_role_set == frozenset({"admin"})


def test_r52_env_example_and_render_declare_the_new_variables():
    """R52: todas las variables nuevas están en .env.example y Render apaga memoria."""
    env_text = (ROOT / ".env.example").read_text(encoding="utf-8")
    declared = {
        line.split("=", 1)[0].strip()
        for line in env_text.splitlines()
        if "=" in line and not line.lstrip().startswith("#")
    }
    for name in MEMORY_VARS:
        assert name in declared, name

    render_text = (ROOT / "render.yaml").read_text(encoding="utf-8")
    assert "key: MEMORY_ENABLED" in render_text
    assert 'value: "false"' in render_text


@pytest.mark.parametrize(
    "field,value",
    [
        ("memory_max_items", 0),
        ("memory_max_items", 101),
        ("memory_item_max_chars", 49),
        ("memory_item_max_chars", 1001),
        ("memory_summary_max_chars", 199),
        ("memory_summary_max_chars", 4001),
        ("memory_input_max_messages", 9),
        ("memory_input_max_messages", 1001),
        ("memory_context_messages", -1),
        ("memory_context_messages", 21),
        ("memory_panel_summaries", 0),
        ("memory_panel_summaries", 51),
        ("memory_sensitive_min_digits", 3),
        ("memory_sensitive_min_digits", 21),
    ],
)
def test_r54_numeric_memory_variables_out_of_range_fail_at_start(field, value):
    """R54: una variable numérica fuera de rango impide arrancar."""
    with pytest.raises(ValidationError):
        Settings(**{field: value})


@pytest.mark.parametrize("value", ["", " , ", "admin,cliente", "asesor,otro"])
def test_r54_suppression_roles_must_be_admin_or_asesor(value):
    """R54: roles vacíos o ajenos a admin/asesor impiden arrancar."""
    with pytest.raises(ValidationError):
        Settings(suppression_executor_roles=value)


def test_r54_suppression_roles_accept_admin_and_asesor():
    """R54: `admin,asesor` es válido y se deduplica."""
    settings = Settings(suppression_executor_roles="admin, asesor,admin")

    assert settings.suppression_executor_role_set == frozenset({"admin", "asesor"})


def test_r54_empty_sensitive_keywords_fail():
    """R54: la lista de palabras sensibles no puede quedar vacía."""
    with pytest.raises(ValidationError):
        Settings(memory_sensitive_keywords=" , ")
