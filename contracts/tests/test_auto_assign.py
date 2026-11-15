"""Contrato de POST /cases/{id}/auto-assign (feature #52)."""
from __future__ import annotations

import re
from pathlib import Path

import pytest
from pydantic import ValidationError

import lazaro_contracts
from lazaro_contracts import CaseAutoAssignRequest, CaseAutoAssignResponse

CONTRACTS_DIR = Path(__file__).resolve().parent.parent
DOC_PATH = CONTRACTS_DIR / "CONTRATOS.md"
EXAMPLES_DIR = CONTRACTS_DIR / "examples"
ROUTE = "POST /cases/{id}/auto-assign"
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


def _route() -> str:
    return _section(_doc(), ROUTE, 3)


def _subsection(name: str) -> str:
    return _section(_route(), name, 4)


def _first_column_cells(table_text: str) -> set[str]:
    return set(re.findall(r"^\| `([a-z_]+)` \|", table_text, re.MULTILINE))


def _error_rows(table_text: str) -> set[tuple[str, str]]:
    return set(
        re.findall(r"^\| (\d{3}) \| `?([a-z_]+)`? \|", table_text, re.MULTILINE)
    )


def test_route_documents_exposer_caller_models_and_token() -> None:
    """R24: la ruta documenta servicio, llamador, modelos y X-Service-Token."""
    section = _route()
    assert "- **Expone:** handover" in section
    assert "- **Llama:** orchestrator" in section
    assert "`CaseAutoAssignRequest`" in section
    assert "`CaseAutoAssignResponse`" in section
    assert "`X-Service-Token`" in section
    assert "`{id}` es el `case_id` (identificador, 1–64 caracteres)" in section


def test_request_table_lists_candidate_ids() -> None:
    """R24: el request documenta candidate_ids (1–200)."""
    table = _subsection("Request")
    assert TABLE_HEADER in table
    assert "candidate_ids" in _first_column_cells(table)
    assert "1–200" in table


def test_response_table_lists_status_case_id_and_advisor_id() -> None:
    """R24: la respuesta documenta los tres campos del modelo."""
    section = _subsection("Respuesta")
    assert TABLE_HEADER in section
    assert re.search(r"`200 [A-Z][A-Za-z ]+`", section)
    assert _first_column_cells(section) == {"status", "case_id", "advisor_id"}


def test_errors_table_documents_own_codes() -> None:
    """R24, R25: 401, 422, 404, 409, 503 y 500 documentados."""
    table = _subsection("Errores")
    assert ERRORS_HEADER in table
    assert {
        ("401", "unauthorized"),
        ("422", "validation_error"),
        ("404", "not_found"),
        ("409", "case_closed"),
        ("503", "roster_out_of_sync"),
        ("500", "internal_error"),
    } <= _error_rows(table)


def test_models_are_exported() -> None:
    """R24: los dos modelos se exportan desde lazaro_contracts."""
    for name in ("CaseAutoAssignRequest", "CaseAutoAssignResponse"):
        assert name in lazaro_contracts.__all__
        assert getattr(lazaro_contracts, name) is not None


def test_request_requires_between_one_and_two_hundred_ids() -> None:
    """R24: candidate_ids es una lista de 1 a 200 identificadores."""
    assert CaseAutoAssignRequest(candidate_ids=["111"]).candidate_ids == ["111"]
    for body in (
        {},
        {"candidate_ids": []},
        {"candidate_ids": ["111"] * 201},
        {"candidate_ids": ["111"], "extra": 1},
    ):
        with pytest.raises(ValidationError):
            CaseAutoAssignRequest.model_validate(body)


def test_response_rejects_status_outside_the_three_values() -> None:
    """R24: status solo admite assigned, queued o skipped."""
    for status in ("assigned", "queued", "skipped"):
        response = CaseAutoAssignResponse(
            status=status, case_id="case-1", advisor_id=None
        )
        assert response.status == status
    with pytest.raises(ValidationError):
        CaseAutoAssignResponse(
            status="notified", case_id="case-1", advisor_id=None  # type: ignore[arg-type]
        )


def test_examples_validate_against_their_models() -> None:
    """R24: los ejemplos del contrato validan contra sus modelos."""
    request = CaseAutoAssignRequest.model_validate_json(
        (EXAMPLES_DIR / "case_auto_assign_request.json").read_text(encoding="utf-8")
    )
    assert request.candidate_ids == ["222222222", "333333333"]
    assigned = CaseAutoAssignResponse.model_validate_json(
        (EXAMPLES_DIR / "case_auto_assign_response.json").read_text(encoding="utf-8")
    )
    assert assigned.status == "assigned"
    queued = CaseAutoAssignResponse.model_validate_json(
        (EXAMPLES_DIR / "case_auto_assign_response_queued.json").read_text(
            encoding="utf-8"
        )
    )
    assert queued.status == "queued" and queued.advisor_id is None
