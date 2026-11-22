"""R1, R5, R9 (#65): capacidades en ChannelInfo y consent_mode en config."""
from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from lazaro_contracts import (
    CONSENT_MODES,
    DEFAULT_CONSENT_MODE,
    ChannelCapabilities,
    ChannelCreateRequest,
    ChannelInfo,
    ChannelUpdateRequest,
)

DOC_PATH = Path(__file__).resolve().parent.parent / "CONTRATOS.md"
INFO = {
    "id": "canal-prueba",
    "name": "Canal de prueba",
    "adapter_type": "simulado",
    "icon": "chat",
    "color": "#1B6FA8",
    "config": {},
    "active": True,
    "configured": True,
    "has_secrets": False,
    "managed_by_environment": False,
    "created_at": "2026-11-21T12:00:00Z",
}
CAPS = {
    "free_text_allowed": False,
    "max_options": 3,
    "min_list_options": 0,
    "max_list_options": 10,
    "supports_links": True,
    "requires_template": True,
}
CREATE = {
    "id": "canal-prueba",
    "name": "Canal de prueba",
    "adapter_type": "simulado",
    "icon": "chat",
    "color": "#1B6FA8",
}


def test_capabilities_is_optional_and_defaults_to_none():
    """R1: el campo existe, es opcional y vale None por defecto."""
    info = ChannelInfo.model_validate(INFO)
    assert info.capabilities is None
    with_caps = ChannelInfo.model_validate({**INFO, "capabilities": CAPS})
    assert isinstance(with_caps.capabilities, ChannelCapabilities)
    assert with_caps.capabilities.requires_template is True
    assert ChannelInfo.model_validate({**INFO, "capabilities": None}).capabilities is None


def test_consent_modes_constants():
    assert CONSENT_MODES == ("texto", "boton")
    assert DEFAULT_CONSENT_MODE == "texto"


@pytest.mark.parametrize("mode", ["texto", "boton"])
def test_valid_consent_mode_is_accepted(mode):
    """R5: los dos modos válidos se aceptan en alta y edición."""
    assert ChannelCreateRequest.model_validate(
        {**CREATE, "config": {"consent_mode": mode}}
    ).config["consent_mode"] == mode
    assert ChannelUpdateRequest.model_validate(
        {"config": {"consent_mode": mode, "otra": 1}}
    ).config["consent_mode"] == mode


@pytest.mark.parametrize("mode", ["", "TEXTO", "voz", 1, None, ["texto"]])
def test_invalid_consent_mode_is_rejected(mode):
    """R5: cualquier otro valor es un error de validación (422)."""
    with pytest.raises(ValidationError):
        ChannelCreateRequest.model_validate({**CREATE, "config": {"consent_mode": mode}})
    with pytest.raises(ValidationError):
        ChannelUpdateRequest.model_validate({"config": {"consent_mode": mode}})


def test_stored_invalid_consent_mode_does_not_break_reading():
    """S3: leer un config guardado con un modo inválido no falla."""
    info = ChannelInfo.model_validate({**INFO, "config": {"consent_mode": "voz"}})
    assert info.config["consent_mode"] == "voz"


def test_contract_documents_capabilities_and_consent_mode():
    """R9: CONTRATOS.md documenta capabilities y consent_mode."""
    doc = DOC_PATH.read_text(encoding="utf-8")
    start = doc.index("### ChannelInfo y ChannelListResponse")
    section = doc[start : doc.index("### POST /channels", start)]
    assert "| `capabilities` |" in section
    assert "`consent_mode`" in section
    for fragment in ("`texto`", "`boton`", "por defecto", "422 validation_error"):
        assert fragment.lower() in section.lower(), fragment
