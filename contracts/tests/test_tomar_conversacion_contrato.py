"""Contrato de POST /cases/take y GET /cases?scope=overview (#68)."""
from __future__ import annotations

import re
from pathlib import Path

import pytest
from pydantic import ValidationError

import lazaro_contracts
from lazaro_contracts import (
    CaseListItem,
    CaseListQuery,
    CaseTakeRequest,
    CaseTakeResponse,
)

CONTRACTS_DIR = Path(__file__).resolve().parent.parent
DOC_PATH = CONTRACTS_DIR / "CONTRATOS.md"
TABLE_HEADER = "| Campo | Tipo | Obligatorio | Descripción |"
ERRORS_HEADER = "| HTTP | error | Cuándo |"


def _doc() -> str:
    return DOC_PATH.read_text(encoding="utf-8")


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


def _take_section() -> str:
    return _section(_doc(), "POST /cases/take", 3)


def _subsection(name: str) -> str:
    return _section(_take_section(), name, 4)


def _first_column_cells(table_text: str) -> set[str]:
    return set(re.findall(r"^\| `([a-z_]+)` \|", table_text, re.MULTILINE))


def _error_rows(table_text: str) -> set[tuple[str, str]]:
    return set(re.findall(r"^\| (\d{3}) \| `?([a-z_]+)`? \|", table_text, re.MULTILINE))


def test_models_are_exported() -> None:
    """R38: los modelos nuevos están en lazaro_contracts.__all__."""
    for name in ("CaseTakeRequest", "CaseTakeResponse"):
        assert name in lazaro_contracts.__all__
        assert getattr(lazaro_contracts, name) is not None


def test_take_request_validates_required_fields_and_limit() -> None:
    """R38: CaseTakeRequest exige caso, contacto, chat, asesor y últimos mensajes."""
    body = {
        "case_id": "case-1",
        "contact_id": "contact-1",
        "chat_id": 900,
        "advisor_id": "222222222",
        "last_messages": [
            {"role": "user", "text": "Hola", "at": "2026-01-02T03:00:00Z"}
        ],
    }
    request = CaseTakeRequest.model_validate(body)
    assert request.contact_id == "contact-1"
    for field in body:
        partial = {key: value for key, value in body.items() if key != field}
        with pytest.raises(ValidationError):
            CaseTakeRequest.model_validate(partial)
    too_many = [
        {"role": "user", "text": f"m{i}", "at": "2026-01-02T03:00:00Z"}
        for i in range(11)
    ]
    with pytest.raises(ValidationError):
        CaseTakeRequest.model_validate({**body, "last_messages": too_many})


def test_take_response_is_taken_with_created_flag() -> None:
    """R38: CaseTakeResponse devuelve status taken, case_id y created."""
    parsed = CaseTakeResponse.model_validate(
        {"status": "taken", "case_id": "case-1", "created": True}
    )
    assert parsed.created is True
    with pytest.raises(ValidationError):
        CaseTakeResponse.model_validate(
            {"status": "otro", "case_id": "case-1", "created": True}
        )
    with pytest.raises(ValidationError):
        CaseTakeResponse.model_validate({"status": "taken", "case_id": "case-1"})


def test_overview_scope_and_empty_actions_are_valid() -> None:
    """R39: `overview` es un scope válido y la lista sin acciones es válida."""
    assert CaseListQuery(advisor_id="111", scope="overview").scope == "overview"
    item = CaseListItem.model_validate(
        {
            "case_id": "case-1",
            "status": "assigned",
            "created_at": "2026-01-02T03:00:00Z",
            "actions": [],
            "advisor_id": "111",
        }
    )
    assert item.actions == []


def test_contract_documents_take_route_and_overview() -> None:
    """R38, R39: CONTRATOS.md documenta la ruta de tomar y el scope overview."""
    section = _take_section()
    assert "- **Expone:** handover" in section
    assert "- **Llama:** orchestrator" in section
    assert "`CaseTakeRequest`" in section
    assert "`CaseTakeResponse`" in section
    assert "`X-Service-Token`" in section

    request = _subsection("Request")
    assert TABLE_HEADER in request
    assert _first_column_cells(request) == {
        "case_id",
        "contact_id",
        "chat_id",
        "advisor_id",
        "last_messages",
    }

    response = _subsection("Respuesta")
    assert TABLE_HEADER in response
    assert _first_column_cells(response) == {"status", "case_id", "created"}

    errors = _subsection("Errores")
    assert ERRORS_HEADER in errors
    assert {
        ("401", "unauthorized"),
        ("422", "validation_error"),
        ("403", "forbidden"),
        ("409", "case_changed"),
        ("500", "internal_error"),
    } <= _error_rows(errors)

    cases = _section(_doc(), "GET /cases", 3)
    assert "scope=overview" in cases
    assert "`overview`" in cases
    assert "`actions` = `[]`" in cases
