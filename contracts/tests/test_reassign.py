"""Contrato de POST /cases/{id}/reassign (feature #49)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from lazaro_contracts import (
    MAX_IDENTIFIER_LENGTH,
    CaseReassignRequest,
    CaseReassignResponse,
    ContractModel,
)

EXAMPLES_DIR = Path(__file__).resolve().parent.parent / "examples"


def _example(name: str):
    return json.loads((EXAMPLES_DIR / name).read_text(encoding="utf-8"))


def test_reassign_models_are_contract_models() -> None:
    """R28: request y response heredan de ContractModel y rechazan campos extra."""
    assert issubclass(CaseReassignRequest, ContractModel)
    assert issubclass(CaseReassignResponse, ContractModel)


def test_reassign_request_requires_advisor_and_target() -> None:
    """R28: el request exige advisor_id y target_advisor_id."""
    request = CaseReassignRequest.model_validate(_example("case_reassign_request.json"))
    assert (request.advisor_id, request.target_advisor_id) == ("999999999", "333333333")
    for field in ("advisor_id", "target_advisor_id"):
        body = {key: value for key, value in _example("case_reassign_request.json").items()
                if key != field}
        with pytest.raises(ValidationError):
            CaseReassignRequest.model_validate(body)
    with pytest.raises(ValidationError):
        CaseReassignRequest.model_validate(
            {**_example("case_reassign_request.json"), "extra": "x"}
        )


@pytest.mark.parametrize(
    "value", ["", "x" * (MAX_IDENTIFIER_LENGTH + 1)], ids=["empty", "too_long"]
)
def test_reassign_request_rejects_invalid_identifiers(value: str) -> None:
    """R28: los identificadores siguen las reglas comunes."""
    body = _example("case_reassign_request.json")
    for field in ("advisor_id", "target_advisor_id"):
        with pytest.raises(ValidationError):
            CaseReassignRequest.model_validate({**body, field: value})


def test_reassign_response_requires_status_case_and_previous() -> None:
    """R28, R12b: la respuesta publica estado, caso, asesor previo y nuevo."""
    response = CaseReassignResponse.model_validate(
        _example("case_reassign_response.json")
    )
    assert response.status == "assigned"
    assert response.previous_advisor_id == "222222222"
    assert response.advisor_id == "333333333"


@pytest.mark.parametrize("status", ["open", "assigned ", "ASSIGNED", ""])
def test_reassign_response_rejects_invalid_status(status: str) -> None:
    """R28: status solo admite assigned."""
    body = _example("case_reassign_response.json")
    with pytest.raises(ValidationError):
        CaseReassignResponse.model_validate({**body, "status": status})


def test_reassign_response_accepts_orphan_previous_advisor() -> None:
    """R15: un caso huérfano reasignado deja previous_advisor_id nulo."""
    body = _example("case_reassign_response.json")
    response = CaseReassignResponse.model_validate({**body, "previous_advisor_id": None})
    assert response.previous_advisor_id is None


def test_reassign_response_rejects_unknown_field() -> None:
    """R28: un campo no declarado se rechaza."""
    body = _example("case_reassign_response.json")
    with pytest.raises(ValidationError):
        CaseReassignResponse.model_validate({**body, "extra": "x"})
