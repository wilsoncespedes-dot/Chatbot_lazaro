"""Contrato de GET /cases (feature #33 contrato_listar_casos_asesor)."""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest
from pydantic import ValidationError

import lazaro_contracts
from lazaro_contracts import (
    DEFAULT_CASE_LIST_LIMIT,
    MAX_CASE_LIST_LIMIT,
    CaseListItem,
    CaseListQuery,
    CaseListResponse,
)

CONTRACTS_DIR = Path(__file__).resolve().parent.parent
ROOT = CONTRACTS_DIR.parent
DOC_PATH = CONTRACTS_DIR / "CONTRATOS.md"
EXAMPLES_DIR = CONTRACTS_DIR / "examples"
ROUTE = "GET /cases"
TABLE_HEADER = "| Campo | Tipo | Obligatorio | Descripción |"
ERRORS_HEADER = "| HTTP | error | Cuándo |"

VALID_ITEM = {
    "case_id": "case-1",
    "status": "open",
    "created_at": "2026-01-02T03:00:00Z",
    "actions": ["reply", "assign", "close"],
}


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
    return set(re.findall(r"^\| (\d{3}) \| `?([a-z_]+)`? \|", table_text, re.MULTILINE))


def _assumptions(text: str) -> str:
    return _section(text, "Supuestos a confirmar", 2)


def _assumption_row(assumption_id: str) -> str:
    match = re.search(
        rf"^\| {assumption_id} \|(.*)$", _assumptions(_doc()), re.MULTILINE
    )
    assert match, f"falta el supuesto {assumption_id}"
    return match.group(1)


# --- R1: sección en CONTRATOS.md -----------------------------------------------------------


def test_route_section_documents_exposer_caller_models_and_token() -> None:
    """R1: GET /cases documenta Expone, Llama, modelos y X-Service-Token."""
    section = _route()
    assert "- **Expone:** handover" in section
    assert "- **Llama:** orchestrator" in section
    assert "`CaseListQuery`" in section
    assert "`CaseListResponse`" in section
    assert "`X-Service-Token`" in section


def test_route_query_table_lists_advisor_id() -> None:
    """R1: la tabla de query de GET /cases lista advisor_id con TABLE_HEADER."""
    table = _subsection("Request")
    assert TABLE_HEADER in table
    assert "advisor_id" in _first_column_cells(table)
    assert "identificador" in table and "1–64" in table


def test_route_response_is_200_and_lists_exactly_four_fields() -> None:
    """R1: la respuesta es 200 y los campos son solo case_id, status, created_at, actions."""
    section = _subsection("Respuesta")
    assert TABLE_HEADER in section
    assert re.search(r"`200 [A-Z][A-Za-z ]+`", section)
    assert _first_column_cells(section) == {
        "case_id",
        "status",
        "created_at",
        "actions",
    }


def test_route_errors_table_has_401_422_and_500() -> None:
    """R1: la tabla de errores de GET /cases tiene 401, 422 y 500."""
    table = _subsection("Errores")
    assert ERRORS_HEADER in table
    assert {("401", "unauthorized"), ("422", "validation_error"), ("500", "internal_error")} <= (
        _error_rows(table)
    )


# --- R7: supuesto S14 ----------------------------------------------------------------------


def test_assumption_s14_documents_inclusion_actions_order_and_limit() -> None:
    """R7: S14 recoge filtros, actions, orden, límite, lista vacía y ausencia de cursor."""
    row = _assumption_row("S14")
    for fragment in (
        "`GET /cases`",
        "`open`",
        "`timed_out`",
        "`assigned`",
        "`reply`",
        "`assign`",
        "`close`",
        "`closed`",
        "`created_at`",
        "`case_id`",
        "`CASE_LIST_LIMIT`",
        "50",
        "200",
        "lista vacía",
        "cursor",
    ):
        assert fragment in row, fragment


def test_s1_to_s13_are_unchanged() -> None:
    """R7: añadir S14 no modifica ninguna fila existente (S1–S13)."""
    try:
        result = subprocess.run(
            ["git", "show", "HEAD:contracts/CONTRATOS.md"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
    except FileNotFoundError:  # pragma: no cover - git no disponible
        pytest.skip("git no disponible para comparar con HEAD")
    if result.returncode != 0:  # pragma: no cover - fichero aún no versionado
        pytest.skip("HEAD no tiene contracts/CONTRATOS.md")
    previous = _assumptions(result.stdout)
    current = _assumptions(_doc())
    for number in range(1, 14):
        identifier = f"S{number}"
        previous_row = re.search(rf"^\| {identifier} \|.*$", previous, re.MULTILINE)
        current_row = re.search(rf"^\| {identifier} \|.*$", current, re.MULTILINE)
        assert previous_row, identifier
        assert current_row, identifier
        assert current_row.group(0) == previous_row.group(0)


# --- R2-R5: modelos ------------------------------------------------------------------------


def test_models_and_constants_are_exported() -> None:
    """R2, R3, R4: modelos y constantes nuevas se exportan en lazaro_contracts.__all__."""
    for name in (
        "CaseListAction",
        "CaseListStatus",
        "CaseListQuery",
        "CaseListItem",
        "CaseListResponse",
    ):
        assert name in lazaro_contracts.__all__
        assert getattr(lazaro_contracts, name) is not None
    assert "DEFAULT_CASE_LIST_LIMIT" in lazaro_contracts.__all__
    assert "MAX_CASE_LIST_LIMIT" in lazaro_contracts.__all__
    assert DEFAULT_CASE_LIST_LIMIT == 50
    assert MAX_CASE_LIST_LIMIT == 200


def test_query_requires_advisor_id_and_rejects_unknown_fields() -> None:
    """R2: CaseListQuery exige advisor_id (1–64) y rechaza campos no declarados."""
    assert CaseListQuery(advisor_id="111").advisor_id == "111"
    for body in ({}, {"advisor_id": ""}, {"advisor_id": "x" * 65}, {"otro": "1"}):
        with pytest.raises(ValidationError):
            CaseListQuery.model_validate(body)


def test_item_requires_all_four_fields() -> None:
    """R3: CaseListItem exige case_id, status, created_at y actions."""
    item = CaseListItem.model_validate(VALID_ITEM)
    assert (item.case_id, item.status, item.actions) == (
        "case-1",
        "open",
        ["reply", "assign", "close"],
    )
    for field in VALID_ITEM:
        body = {key: value for key, value in VALID_ITEM.items() if key != field}
        with pytest.raises(ValidationError):
            CaseListItem.model_validate(body)


def test_item_rejects_naive_date() -> None:
    """R3: created_at es un AwareDatetime (fecha con zona horaria)."""
    with pytest.raises(ValidationError):
        CaseListItem.model_validate({**VALID_ITEM, "created_at": "2026-01-02T03:00:00"})


def test_item_rejects_status_outside_the_three_values() -> None:
    """R3: status solo admite open, timed_out o assigned."""
    for status in ("closed", "otro"):
        with pytest.raises(ValidationError):
            CaseListItem.model_validate({**VALID_ITEM, "status": status})


def test_item_rejects_empty_unknown_or_repeated_actions() -> None:
    """R3: actions es una lista no vacía, sin repetidos y solo de acciones conocidas."""
    for actions in ([], ["reply", "reply"], ["reply", "cerrar"]):
        with pytest.raises(ValidationError):
            CaseListItem.model_validate({**VALID_ITEM, "actions": actions})


@pytest.mark.parametrize(
    "field", ["contact_id", "chat_id", "reason", "last_messages", "advisor_id", "otro"]
)
def test_item_rejects_contact_and_conversation_fields(field: str) -> None:
    """R5: CaseListItem rechaza cualquier campo de contacto o conversación."""
    with pytest.raises(ValidationError):
        CaseListItem.model_validate({**VALID_ITEM, field: "x"})


def test_response_limits_items_to_max_and_has_default_constant() -> None:
    """R4: CaseListResponse admite hasta 200 elementos y rechaza 201."""
    item = CaseListItem.model_validate(VALID_ITEM)
    assert CaseListResponse([item] * MAX_CASE_LIST_LIMIT).root[-1] == item
    with pytest.raises(ValidationError):
        CaseListResponse([item] * (MAX_CASE_LIST_LIMIT + 1))


# --- R6, R21: ejemplos ---------------------------------------------------------------------


def test_examples_validate_against_their_models() -> None:
    """R6, R21: los tres ejemplos nuevos validan contra su modelo."""
    query_text = (EXAMPLES_DIR / "case_list_query.json").read_text(encoding="utf-8")
    response_text = (EXAMPLES_DIR / "case_list_response.json").read_text(encoding="utf-8")
    empty_text = (EXAMPLES_DIR / "case_list_response_empty.json").read_text(encoding="utf-8")

    query = CaseListQuery.model_validate_json(query_text)
    assert query.advisor_id == "222222222"

    response = CaseListResponse.model_validate_json(response_text)
    assert [item.status for item in response.root] == ["open", "assigned", "assigned"]
    assert [item.actions for item in response.root] == [
        ["reply", "assign", "close"],
        ["reply", "close"],
        ["close"],
    ]
    created = [item.created_at for item in response.root]
    assert created == sorted(created)
    assert [item.case_id for item in response.root] == ["case-100", "case-101", "case-102"]

    empty = CaseListResponse.model_validate_json(empty_text)
    assert empty.root == []
