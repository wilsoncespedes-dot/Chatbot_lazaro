"""Documentación del consentimiento único por cliente (#72)."""
from __future__ import annotations

from pathlib import Path

DOC = Path(__file__).resolve().parents[1] / "CONTRATOS.md"


def test_contratos_documenta_consentimiento_por_cliente() -> None:
    """R27: tablas, variable, claves nuevas y supuesto legal documentados."""
    text = DOC.read_text(encoding="utf-8")
    assert "### Consentimiento por cliente (#72)" in text
    for table in ("identidades_cliente", "consentimientos_cliente"):
        assert table in text
    for column in ("cliente_id", "canal_id", "id_externo", "vinculado_en"):
        assert column in text
    for column in ("notice_version", "notice_sha256", "aceptado_en"):
        assert column in text
    assert "`CLIENT_CONSENT_RETENTION_DAYS`" in text
    assert "`consentimientos_cliente`" in text
    assert "`identidades_cliente`" in text
    assert "removed_counts" in text
    assert "Supuesto pendiente de confirmación legal" in text
