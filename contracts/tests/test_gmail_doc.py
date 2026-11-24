"""R17: la guía de Gmail documenta permisos, configuración y sincronización."""
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_gmail_docs_cover_routes_scopes_and_privacy():
    docs = (ROOT / "docs" / "gmail.md").read_text(encoding="utf-8")
    contract = (ROOT / "contracts" / "CONTRATOS.md").read_text(encoding="utf-8")
    assert "gmail.readonly" in docs
    assert "gmail.send" in docs
    assert "refresh_token" in docs
    assert "cada 5 segundos" in docs
    assert "/channels/{channel_id}/gmail/sync" in contract
    assert "gmail_history_expired" in contract
    assert "text/plain" in docs
