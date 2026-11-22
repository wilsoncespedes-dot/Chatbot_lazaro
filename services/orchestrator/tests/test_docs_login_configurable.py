"""La especificación documenta el login configurable como posibilidad (#73, R37)."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def test_spec_documents_configurable_login_as_possibility():
    """R37: subsección de login configurable, ID de cliente y bienvenida con canales."""
    text = (ROOT / "docs" / "especificacion.md").read_text(encoding="utf-8")

    assert "Login configurable (posibilidad, no implementada)" in text
    assert "ID de cliente" in text
    assert "Bienvenida con canales" in text
    assert "no se implementa" in text.lower()
