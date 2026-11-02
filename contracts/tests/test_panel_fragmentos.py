"""Contrato de #22 panel_fragmentos: rutas de listado y activación de fragmentos."""
from __future__ import annotations

import re
from pathlib import Path

import pytest
from pydantic import ValidationError

import lazaro_contracts
from lazaro_contracts import (
    ChunkActiveRequest,
    ChunkItem,
    ChunkListResponse,
    ManualListResponse,
    ManualSummary,
)

DOC_PATH = Path(__file__).resolve().parent.parent / "CONTRATOS.md"

NEW_ROUTES = {
    "GET /manuals": {
        "service": "rag",
        "models": {"ManualListResponse", "ManualSummary"},
        "errors": {("401", "unauthorized"), ("500", "internal_error")},
    },
    "GET /manuals/{id}/chunks": {
        "service": "rag",
        "models": {"ChunkListResponse", "ChunkItem"},
        "errors": {
            ("401", "unauthorized"),
            ("404", "not_found"),
            ("500", "internal_error"),
        },
    },
    "PATCH /chunks/{id}/active": {
        "service": "rag",
        "models": {"ChunkActiveRequest", "ChunkItem"},
        "errors": {
            ("401", "unauthorized"),
            ("404", "not_found"),
            ("422", "validation_error"),
            ("500", "internal_error"),
        },
    },
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


def _route(route: str) -> str:
    return _section(_doc(), route, 3)


def _subsection(route: str, name: str) -> str:
    return _section(_route(route), name, 4)


def _bullet(route: str, label: str) -> str:
    match = re.search(rf"^- \*\*{label}:\*\* (.*)$", _route(route), re.MULTILINE)
    assert match, f"{route}: falta la línea '- **{label}:**'"
    return match.group(1).strip()


def _error_rows(route: str) -> set[tuple[str, str]]:
    return set(
        re.findall(
            r"^\| (\d{3}) \| `?([a-z_]+)`? \|",
            _subsection(route, "Errores"),
            re.MULTILINE,
        )
    )


def _first_column_cells(table_text: str) -> set[str]:
    return set(re.findall(r"^\| `([a-z_]+)` \|", table_text, re.MULTILINE))


@pytest.mark.parametrize("route", NEW_ROUTES)
def test_new_route_section_exists_and_names_rag(route: str) -> None:
    """R1: CONTRATOS.md documenta cada ruta nueva y su servicio expositor."""
    assert f"### {route}" in _doc()
    assert _bullet(route, "Expone") == NEW_ROUTES[route]["service"]
    assert _bullet(route, "Llama")


@pytest.mark.parametrize("route", NEW_ROUTES)
def test_new_route_models_are_exported(route: str) -> None:
    """R1: la ruta cita los modelos nuevos y todos están en lazaro_contracts."""
    names = set(re.findall(r"`([A-Za-z]+)`", _bullet(route, "Modelos")))
    assert names == NEW_ROUTES[route]["models"]
    assert names <= set(lazaro_contracts.__all__)


@pytest.mark.parametrize("route", NEW_ROUTES)
def test_new_route_documents_its_errors_only(route: str) -> None:
    """R1: 401/500 siempre; 404 solo con id; 422 solo en PATCH /active."""
    rows = _error_rows(route)
    assert rows == NEW_ROUTES[route]["errors"]
    table = _subsection(route, "Errores")
    assert "| HTTP | error | Cuándo |" in table
    if route == "PATCH /chunks/{id}/active":
        assert "422" in table
    else:
        assert "422" not in table


@pytest.mark.parametrize("route", NEW_ROUTES)
def test_new_route_success_and_fields_are_documented(route: str) -> None:
    """R1: la respuesta 200 lista los campos del modelo de salida."""
    section = _subsection(route, "Respuesta")
    assert "`200 OK`" in section
    assert "| Campo | Tipo | Obligatorio | Descripción |" in section
    if route == "GET /manuals":
        expected = set(ManualSummary.model_fields)
    elif route == "GET /manuals/{id}/chunks":
        expected = set(ChunkItem.model_fields)
    else:
        expected = set(ChunkItem.model_fields)
    assert expected <= _first_column_cells(section)


def test_active_route_documents_request_fields() -> None:
    """R1, R7: la petición de activación documenta el campo active."""
    table = _subsection("PATCH /chunks/{id}/active", "Request")
    assert set(ChunkActiveRequest.model_fields) == {"active"}
    assert "active" in _first_column_cells(table)
    assert "booleano" in table


def test_list_routes_document_ids_and_order() -> None:
    """R1: GET /manuals/{id}/chunks explica que {id} es manual_id y el orden ascendente."""
    manual_section = _route("GET /manuals")
    list_section = _route("GET /manuals/{id}/chunks")
    assert "más reciente primero" in manual_section
    assert "`{id}` es el `manual_id`" in list_section
    assert "orden ascendente de `order`" in list_section


def test_active_route_documents_preserved_metadata() -> None:
    """R1, R5: activar o desactivar no cambia texto, embedding, manual ni orden."""
    section = _route("PATCH /chunks/{id}/active")
    for fragment in ("texto", "embedding", "manual", "orden"):
        assert fragment in section, fragment


def test_published_route_rows_are_unchanged() -> None:
    """R1: las filas de las rutas publicadas siguen presentes sin cambios."""
    expected = {
        "POST /manuals": {("415", "unsupported_format"), ("422", "empty_document")},
        "PATCH /chunks/{id}": {("404", "not_found"), ("500", "internal_error")},
        "POST /search": set(),
    }
    for route, rows in expected.items():
        assert f"### {route}" in _doc()
        assert rows <= _error_rows(route)


# ── Modelos ─────────────────────────────────────────────────────────────────


def test_manual_list_response_is_a_root_list() -> None:
    """R1: ManualListResponse valida un arreglo de nivel superior."""
    response = ManualListResponse.model_validate_json(
        '[{"manual_id": "m1", "name": "Manual A", "chunks": 0}]'
    )
    assert response.root[0].manual_id == "m1"
    assert response.root[0].chunks == 0
    with pytest.raises(ValidationError):
        ManualListResponse.model_validate_json('{"manual_id": "m1"}')


def test_manual_summary_rejects_extra_fields_and_negative_chunks() -> None:
    """R1: ManualSummary rechaza campos extra y chunks negativos."""
    ManualSummary(manual_id="m1", name="Manual A", chunks=0)
    with pytest.raises(ValidationError):
        ManualSummary(manual_id="m1", name="Manual A", chunks=-1)
    with pytest.raises(ValidationError):
        ManualSummary(manual_id="m1", name="Manual A", chunks=1, extra="x")


def test_chunk_list_response_is_a_root_list_of_chunks() -> None:
    """R1: ChunkListResponse valida un arreglo de ChunkItem."""
    response = ChunkListResponse.model_validate_json(
        '[{"chunk_id": "c1", "manual_id": "m1", "manual": "Manual A", '
        '"order": 1, "text": "texto", "active": false}]'
    )
    assert response.root[0].chunk_id == "c1"
    assert response.root[0].active is False
    with pytest.raises(ValidationError):
        ChunkListResponse.model_validate_json('{"chunks": []}')


def test_chunk_item_has_the_chunk_update_response_fields() -> None:
    """R1: ChunkItem usa los mismos campos que ChunkUpdateResponse."""
    assert set(ChunkItem.model_fields) == set(
        lazaro_contracts.ChunkUpdateResponse.model_fields
    )


def test_chunk_item_rejects_extra_fields() -> None:
    """R1: un ChunkItem con un campo no declarado lanza ValidationError."""
    with pytest.raises(ValidationError):
        ChunkItem(
            chunk_id="c1",
            manual_id="m1",
            manual="Manual A",
            order=1,
            text="texto",
            active=True,
            extra="x",
        )


@pytest.mark.parametrize("value", [True, False])
def test_chunk_active_request_accepts_json_booleans(value: bool) -> None:
    """R7: true y false son válidos."""
    assert ChunkActiveRequest(active=value).active is value


@pytest.mark.parametrize("value", ["true", "false", 1, 0, None])
def test_chunk_active_request_rejects_non_booleans(value) -> None:
    """R7: StrictBool rechaza cadenas y números."""
    with pytest.raises(ValidationError):
        ChunkActiveRequest.model_validate({"active": value})


def test_chunk_active_request_requires_active_and_rejects_extra() -> None:
    """R7: sin active o con campos extra lanza ValidationError."""
    with pytest.raises(ValidationError):
        ChunkActiveRequest.model_validate({})
    with pytest.raises(ValidationError):
        ChunkActiveRequest.model_validate({"active": True, "extra": 1})


def test_new_models_are_exported_in_all() -> None:
    """R1: los cinco modelos nuevos están en __all__."""
    for name in (
        "ManualSummary",
        "ManualListResponse",
        "ChunkItem",
        "ChunkListResponse",
        "ChunkActiveRequest",
    ):
        assert name in lazaro_contracts.__all__
