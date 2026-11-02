"""Contrato de POST /privacy/purge (feature #27)."""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from pydantic import ValidationError

import lazaro_contracts
from lazaro_contracts import PrivacyPurgeRequest, PrivacyPurgeResponse

CONTRACTS_DIR = Path(__file__).resolve().parent.parent
DOC_PATH = CONTRACTS_DIR / "CONTRATOS.md"
EXAMPLES_DIR = CONTRACTS_DIR / "examples"


def _section(text: str, heading: str, level: int) -> str:
    lines = text.splitlines()
    marker = "#" * level + " " + heading
    start = lines.index(marker)
    body = []
    for line in lines[start + 1:]:
        match = re.match(r"^(#+) ", line)
        if match and len(match.group(1)) <= level:
            break
        body.append(line)
    return "\n".join(body)


def _purge_section() -> str:
    return _section(DOC_PATH.read_text(encoding="utf-8"), "POST /privacy/purge", 3)


def test_models_are_exported() -> None:
    """R52: PrivacyPurgeRequest y PrivacyPurgeResponse están en `__all__`."""
    assert "PrivacyPurgeRequest" in lazaro_contracts.__all__
    assert "PrivacyPurgeResponse" in lazaro_contracts.__all__
    assert lazaro_contracts.PrivacyPurgeRequest is PrivacyPurgeRequest
    assert lazaro_contracts.PrivacyPurgeResponse is PrivacyPurgeResponse


def test_request_accepts_empty_object() -> None:
    """R52: el request es el objeto vacío {}."""
    PrivacyPurgeRequest.model_validate_json("{}")
    with pytest.raises(ValidationError):
        PrivacyPurgeRequest.model_validate_json('{"extra": 1}')


def test_response_defaults_closed_active_cases_to_zero() -> None:
    """R27, R52: closed_active_cases vale 0 si no se informa."""
    response = PrivacyPurgeResponse(
        cutoff="2025-12-03T03:04:05Z",
        deleted={"messages": 1},
    )
    assert response.closed_active_cases == 0


def test_response_requires_cutoff_and_deleted() -> None:
    """R52: cutoff y deleted son obligatorios."""
    with pytest.raises(ValidationError):
        PrivacyPurgeResponse(deleted={})
    with pytest.raises(ValidationError):
        PrivacyPurgeResponse(cutoff="2025-12-03T03:04:05Z")


def test_response_rejects_naive_cutoff() -> None:
    """R52: cutoff es una fecha con zona horaria."""
    with pytest.raises(ValidationError):
        PrivacyPurgeResponse(cutoff="2025-12-03T03:04:05", deleted={})


def test_examples_validate_against_the_models() -> None:
    """R51, R52: los ejemplos de la ruta validan contra sus modelos."""
    request = (EXAMPLES_DIR / "privacy_purge_request.json").read_text(encoding="utf-8")
    response = (EXAMPLES_DIR / "privacy_purge_response.json").read_text(encoding="utf-8")
    PrivacyPurgeRequest.model_validate_json(request)
    parsed = PrivacyPurgeResponse.model_validate_json(response)
    assert parsed.closed_active_cases == 0


def test_doc_section_names_both_services_and_order() -> None:
    """R51: documenta orchestrator, handover y el orden handover → orchestrator."""
    section = _purge_section()
    assert "orchestrator" in section
    assert "handover" in section
    assert "handover → orchestrator" in section


def test_doc_section_documents_response_and_errors() -> None:
    """R51: request vacío, closed_active_cases y errores 401 y 503."""
    section = _purge_section()
    for fragment in (
        "`PrivacyPurgeRequest`",
        "`PrivacyPurgeResponse`",
        "`{}`",
        "`cutoff`",
        "`deleted`",
        "`closed_active_cases`",
        "401",
        "`unauthorized`",
        "503",
        "`privacy_not_configured`",
    ):
        assert fragment in section, fragment


def test_common_errors_table_has_privacy_not_configured() -> None:
    """R51: 503 privacy_not_configured se añade a la tabla común de errores."""
    rules = _section(DOC_PATH.read_text(encoding="utf-8"), "Reglas comunes", 2)
    assert "`privacy_not_configured`" in rules
    assert "503" in rules


def test_examples_are_mapped_in_the_contract_suite() -> None:
    """R51, R52: la suite de ejemplos incluye los dos JSON nuevos."""
    text = (CONTRACTS_DIR / "tests" / "test_examples.py").read_text(encoding="utf-8")
    assert "privacy_purge_request.json" in text
    assert "privacy_purge_response.json" in text
    data = json.loads(
        (EXAMPLES_DIR / "privacy_purge_response.json").read_text(encoding="utf-8")
    )
    assert isinstance(data["deleted"], dict)
