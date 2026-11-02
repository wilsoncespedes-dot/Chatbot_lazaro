"""Dependencias, constantes, exportaciones e imports permitidos de lazaro_contracts."""
from __future__ import annotations

import ast
import sys
from pathlib import Path

import pydantic
import pytest
from pydantic import BaseModel

import lazaro_contracts

CONTRACTS_DIR = Path(__file__).resolve().parent.parent
ROOT = CONTRACTS_DIR.parent
PACKAGE_DIR = CONTRACTS_DIR / "lazaro_contracts"

MODEL_NAMES = [
    "MessageRequest",
    "MessageResponse",
    "SendRequest",
    "SendResponse",
    "SearchRequest",
    "SearchResult",
    "SearchResponse",
    "HandoverRequest",
    "LastMessage",
    "HandoverResponse",
    "CaseReplyRequest",
    "CaseReplyResponse",
    "ManualUploadRequest",
    "ManualUploadResponse",
    "CaseCloseRequest",
    "CaseCloseResponse",
    "CaseAssignRequest",
    "CaseAssignResponse",
    "CaseAuthorizeRequest",
    "CaseAuthorizeResponse",
    "CaseClientMessageRequest",
    "CaseClientMessageResponse",
    "CheckTimeoutsRequest",
    "CheckTimeoutsResponse",
    "ChunkUpdateRequest",
    "ChunkUpdateResponse",
    "ChunkItem",
    "ChunkListResponse",
    "ChunkActiveRequest",
    "ManualSummary",
    "ManualListResponse",
    "ErrorResponse",
    "HealthResponse",
]


def _requirement_lines(path: Path) -> list[str]:
    lines = path.read_text(encoding="utf-8").splitlines()
    return [line.strip() for line in lines if line.strip() and not line.strip().startswith("#")]


def test_contracts_requirements_pins_pydantic_v2() -> None:
    """R50: contracts/requirements.txt contiene exactamente 'pydantic>=2.12,<3'."""
    assert _requirement_lines(CONTRACTS_DIR / "requirements.txt") == ["pydantic>=2.12,<3"]


def test_dev_requirements_include_contracts() -> None:
    """R51: requirements-dev.txt incluye '-r contracts/requirements.txt'."""
    assert "-r contracts/requirements.txt" in _requirement_lines(ROOT / "requirements-dev.txt")


def test_constants_have_contract_values() -> None:
    """R45: el paquete exporta las constantes con sus valores."""
    expected = {
        "SERVICE_TOKEN_HEADER": "X-Service-Token",
        "MAX_TEXT_LENGTH": 4096,
        "MAX_LAST_MESSAGES": 10,
        "MAX_TOP_K": 20,
        "MAX_IDENTIFIER_LENGTH": 64,
        "MAX_MANUAL_NAME_LENGTH": 200,
    }
    for name, value in expected.items():
        assert name in lazaro_contracts.__all__
        assert getattr(lazaro_contracts, name) == value


def test_pydantic_major_version_is_2() -> None:
    """R17: pydantic instalado es de la versión mayor 2."""
    assert pydantic.VERSION.startswith("2.")


@pytest.mark.parametrize("name", MODEL_NAMES)
def test_model_is_exported_and_is_base_model(name: str) -> None:
    """R16, R17: cada modelo está en __all__, se importa del paquete y es BaseModel."""
    assert name in lazaro_contracts.__all__
    model = getattr(lazaro_contracts, name)
    assert isinstance(model, type)
    assert issubclass(model, BaseModel)


def test_all_names_are_importable() -> None:
    """R16: todo nombre de __all__ existe en el paquete."""
    for name in lazaro_contracts.__all__:
        assert hasattr(lazaro_contracts, name)


def test_case_authorize_action_is_exported() -> None:
    """contrato_autorizacion_asesores R37: CaseAuthorizeAction está en __all__ y existe."""
    assert "CaseAuthorizeAction" in lazaro_contracts.__all__
    assert hasattr(lazaro_contracts, "CaseAuthorizeAction")


def _imported_modules(path: Path) -> list[tuple[str, int]]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found: list[tuple[str, int]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.extend((alias.name, 0) for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            found.append((node.module or "", node.level))
    return found


def _is_allowed(module: str, level: int) -> bool:
    if level > 0:
        return True
    top = module.split(".")[0]
    return top in sys.stdlib_module_names or top in {"pydantic", "lazaro_contracts", "__future__"}


@pytest.mark.parametrize(
    "path", sorted(PACKAGE_DIR.glob("*.py")), ids=lambda p: p.name
)
def test_package_imports_only_stdlib_and_pydantic(path: Path) -> None:
    """R46: los módulos solo importan stdlib, pydantic o el propio paquete."""
    forbidden = [m for m, level in _imported_modules(path) if not _is_allowed(m, level)]
    assert forbidden == []


def test_package_has_the_expected_modules() -> None:
    """R46: el recorrido de imports cubre los módulos del paquete."""
    names = {path.name for path in PACKAGE_DIR.glob("*.py")}
    expected = {"__init__.py", "common.py", "messages.py", "search.py", "manuals.py", "cases.py"}
    assert expected <= names
