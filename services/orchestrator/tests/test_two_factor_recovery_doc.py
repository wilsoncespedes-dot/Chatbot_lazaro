"""Procedimiento documentado de recuperación operativa del segundo factor (#54)."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def _section() -> str:
    text = (ROOT / "docs" / "despliegue.md").read_text(encoding="utf-8")
    marker = "## 6. Recuperar el segundo factor del panel"
    start = text.index(marker)
    return text[start:]


def test_recovery_sql_is_transactional_and_targets_one_profile():
    """R46: transacción, perfil explícito, actor ops y borrado de las tres tablas."""
    section = _section()
    assert "BEGIN;" in section and "COMMIT;" in section
    assert ":'profile_id'" in section
    assert "ops:" in section
    assert "two_factor_reset_ops" in section
    insert_at = section.index("INSERT INTO panel_audit")
    for table in ("staff_recovery_codes", "staff_two_factor", "admin_sessions"):
        assert f"DELETE FROM {table}" in section
        assert insert_at < section.index(f"DELETE FROM {table}")


def test_recovery_doc_covers_key_loss_and_bootstrap():
    """R47: variante para la clave y aviso de que el bootstrap #23 no sirve."""
    section = _section()
    assert "PANEL_2FA_ENCRYPTION_KEY" in section
    assert "#23" in section
    assert "no rota" in section.lower() or "no se rota" in section.lower()


def test_recovery_doc_never_selects_secret_material_or_key_values():
    """R48: no se seleccionan secretos, hashes ni se pide la clave."""
    section = _section()
    assert re.search(r"SELECT[^;\n]*secret_ciphertext", section, re.IGNORECASE) is None
    assert re.search(r"SELECT[^;\n]*code_hash", section, re.IGNORECASE) is None
    assert "PANEL_2FA_ENCRYPTION_KEY=" not in section
