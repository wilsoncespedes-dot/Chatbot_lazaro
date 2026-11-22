"""Documentación de la imagen pública de respuestas rápidas (#71)."""
from __future__ import annotations

from pathlib import Path

DOC = Path(__file__).resolve().parents[1] / "CONTRATOS.md"


def test_media_de_respuestas_rapidas_es_publica_y_del_mismo_origen() -> None:
    """R26: CONTRATOS.md documenta la ruta pública de media sin autenticación."""
    text = DOC.read_text(encoding="utf-8")
    assert "### GET /media/respuestas/{image_id}" in text
    assert "**Autenticación:** ninguna (ruta pública del mismo origen)" in text
    assert "`X-Content-Type-Options: nosniff`" in text
