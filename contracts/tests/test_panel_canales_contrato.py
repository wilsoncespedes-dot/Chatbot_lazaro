"""R1, R2, R6 (#66): pistas de credenciales e íconos de canal en el contrato."""
from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from lazaro_contracts import CHANNEL_ICONS, DEFAULT_CHANNEL_ICON, ChannelInfo, credential_hint

DOC = Path(__file__).resolve().parent.parent / "CONTRATOS.md"
INFO = {
    "id": "canal-prueba",
    "name": "Canal de prueba",
    "adapter_type": "simulado",
    "icon": "chat",
    "color": "#1B6FA8",
    "config": {},
    "active": True,
    "configured": True,
    "has_secrets": True,
    "managed_by_environment": False,
    "created_at": "2026-11-21T12:00:00Z",
}


@pytest.mark.parametrize(
    ("value", "hint"),
    [("abcdefgh", "…efgh"), ("token-largo-1234", "…1234"), ("corto", "…"), ("1234567", "…")],
)
def test_credential_hint_shows_only_last_four_of_long_values(value, hint):
    """R1: `…` más 4 caracteres si mide 8 o más; si no, solo `…`."""
    assert credential_hint(value) == hint
    assert value not in credential_hint(value) or len(value) <= 4


def test_channel_info_credential_hints_default_and_validation():
    """R1: `credential_hints` es opcional, por defecto `{}` y con nombres válidos."""
    assert ChannelInfo.model_validate(INFO).credential_hints == {}
    info = ChannelInfo.model_validate({**INFO, "credential_hints": {"api_token": "…1234"}})
    assert info.credential_hints == {"api_token": "…1234"}
    with pytest.raises(ValidationError):
        ChannelInfo.model_validate({**INFO, "credential_hints": {"Mal Nombre": "…"}})


def test_channel_icons_closed_list():
    """R2: lista cerrada de íconos con chat, telegram y whatsapp como emoji."""
    assert {"chat", "telegram", "whatsapp"} <= set(CHANNEL_ICONS)
    assert DEFAULT_CHANNEL_ICON in CHANNEL_ICONS
    assert all(value and not value.isascii() for value in CHANNEL_ICONS.values())


def test_contract_documents_hints_and_icons():
    """R6: CONTRATOS.md documenta credential_hints y CHANNEL_ICONS."""
    doc = DOC.read_text(encoding="utf-8")
    start = doc.index("### ChannelInfo y ChannelListResponse")
    section = doc[start : doc.index("### POST /channels", start)]
    assert "| `credential_hints` |" in section
    assert "CHANNEL_ICONS" in section
