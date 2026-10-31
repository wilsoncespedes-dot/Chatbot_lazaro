"""Comprueba la estructura de contracts/CONTRATOS.md frente a los modelos."""
from __future__ import annotations

import re
from pathlib import Path

import pytest
from pydantic import BaseModel

import lazaro_contracts

DOC_PATH = Path(__file__).resolve().parent.parent / "CONTRATOS.md"

ROUTES: dict[str, str] = {
    "POST /messages": "orchestrator",
    "POST /send": "telegram_gateway",
    "POST /search": "rag",
    "POST /handover": "handover",
    "POST /cases/{id}/reply": "orchestrator",
    "POST /manuals": "rag",
    "POST /cases/{id}/close": "handover",
    "POST /cases/check-timeouts": "handover",
    "POST /cases/{id}/assign": "handover",
}

OWN_ERRORS: dict[str, list[tuple[str, str]]] = {
    "POST /send": [("502", "telegram_error")],
    "POST /manuals": [("415", "unsupported_format"), ("422", "empty_document")],
    "POST /cases/{id}/reply": [("404", "not_found"), ("502", "upstream_error")],
    "POST /cases/{id}/close": [("404", "not_found")],
    "POST /cases/{id}/assign": [("404", "not_found"), ("409", "case_closed")],
}

SUCCESS_CODES: dict[str, str] = {
    "POST /messages": "202",
    "POST /send": "200",
    "POST /search": "200",
    "POST /handover": "200",
    "POST /cases/{id}/reply": "200",
    "POST /manuals": "201",
    "POST /cases/{id}/close": "200",
    "POST /cases/check-timeouts": "200",
    "POST /cases/{id}/assign": "200",
}

TABLE_HEADER = "| Campo | Tipo | Obligatorio | Descripción |"
ERRORS_HEADER = "| HTTP | error | Cuándo |"


def _doc() -> str:
    return DOC_PATH.read_text(encoding="utf-8")


def _section(text: str, heading: str, level: int) -> str:
    """Devuelve el texto bajo `heading` hasta el siguiente encabezado de nivel <= level."""
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


def _models(route: str) -> list[type[BaseModel]]:
    names = re.findall(r"`([A-Za-z]+)`", _bullet(route, "Modelos"))
    return [getattr(lazaro_contracts, name) for name in names]


def _first_column_cells(table_text: str) -> set[str]:
    return set(re.findall(r"^\| `([a-z_]+)` \|", table_text, re.MULTILINE))


def _error_rows(table_text: str) -> set[tuple[str, str]]:
    return set(re.findall(r"^\| (\d{3}) \| `?([a-z_]+)`? \|", table_text, re.MULTILINE))


def _response_fields(model: type[BaseModel]) -> set[str]:
    if model is lazaro_contracts.SearchResponse:
        return set(lazaro_contracts.SearchResult.model_fields)
    return set(model.model_fields)


def test_doc_has_a_section_per_route() -> None:
    """R1: CONTRATOS.md tiene un encabezado '### POST <ruta>' por cada ruta del contrato."""
    headings = set(re.findall(r"^### (.+)$", _doc(), re.MULTILINE))
    assert set(ROUTES) <= headings


@pytest.mark.parametrize("route", ROUTES)
def test_route_names_exposing_service(route: str) -> None:
    """R2: cada ruta indica en '- **Expone:**' el servicio correcto."""
    assert _bullet(route, "Expone") == ROUTES[route]


@pytest.mark.parametrize("route", ROUTES)
def test_route_names_caller(route: str) -> None:
    """R3: cada ruta indica en '- **Llama:**' quién la llama (no vacío)."""
    assert _bullet(route, "Llama") != ""


@pytest.mark.parametrize("route", ROUTES)
def test_route_names_models_in_package(route: str) -> None:
    """R4: '- **Modelos:**' cita request y response con nombres de lazaro_contracts.__all__."""
    names = re.findall(r"`([A-Za-z]+)`", _bullet(route, "Modelos"))
    assert len(names) >= 2
    assert set(names) <= set(lazaro_contracts.__all__)
    request, response = _models(route)[:2]
    assert request.__name__.endswith("Request")
    assert response.__name__.endswith("Response")


@pytest.mark.parametrize("route", ROUTES)
def test_request_table_lists_every_request_field(route: str) -> None:
    """R5: '#### Request' tiene la tabla de campos con todos los del modelo de request."""
    table = _subsection(route, "Request")
    assert TABLE_HEADER in table
    request = _models(route)[0]
    assert set(request.model_fields) <= _first_column_cells(table)


def test_manuals_request_table_lists_multipart_parts() -> None:
    """R5: la tabla de POST /manuals lista las partes multipart file y name (S1)."""
    assert {"file", "name"} <= _first_column_cells(_subsection("POST /manuals", "Request"))


def test_check_timeouts_request_table_has_no_fields_row() -> None:
    """R5: la tabla de POST /cases/check-timeouts indica '(sin campos)'."""
    assert "(sin campos)" in _subsection("POST /cases/check-timeouts", "Request")


@pytest.mark.parametrize("route", ROUTES)
def test_response_section_has_success_code_and_fields(route: str) -> None:
    """R6: '#### Respuesta' indica el código de éxito y todos los campos del response."""
    section = _subsection(route, "Respuesta")
    assert TABLE_HEADER in section
    assert re.search(rf"`{SUCCESS_CODES[route]} [A-Z][A-Za-z ]+`", section)
    response = _models(route)[1]
    assert _response_fields(response) <= _first_column_cells(section)


@pytest.mark.parametrize("route", ROUTES)
def test_errors_table_has_common_rows(route: str) -> None:
    """R7: '#### Errores' tiene la tabla con 401 unauthorized y 422 validation_error."""
    table = _subsection(route, "Errores")
    assert ERRORS_HEADER in table
    assert {("401", "unauthorized"), ("422", "validation_error")} <= _error_rows(table)


@pytest.mark.parametrize("route", OWN_ERRORS)
def test_errors_table_has_route_specific_rows(route: str) -> None:
    """R8: cada ruta documenta sus errores propios."""
    assert set(OWN_ERRORS[route]) <= _error_rows(_subsection(route, "Errores"))


def test_common_rules_document_service_token() -> None:
    """R9: las reglas comunes exigen X-Service-Token = SERVICE_TOKEN, 401 y sus excepciones."""
    rules = _section(_doc(), "Reglas comunes", 2)
    assert "`X-Service-Token`" in rules
    assert "`SERVICE_TOKEN`" in rules
    assert "`401`" in rules
    assert "`unauthorized`" in rules
    assert "`GET /health`" in rules
    assert "webhook de Telegram" in rules


def test_common_rules_document_error_shape_and_codes() -> None:
    """R10: las reglas comunes documentan {error, message}, ErrorResponse y la tabla de códigos."""
    rules = _section(_doc(), "Reglas comunes", 2)
    assert '{"error": "<codigo>", "message": "<texto>"}' in rules
    assert "`ErrorResponse`" in rules
    expected = {
        ("401", "unauthorized"),
        ("422", "validation_error"),
        ("404", "not_found"),
        ("415", "unsupported_format"),
        ("422", "empty_document"),
        ("502", "telegram_error"),
        ("502", "upstream_error"),
        ("500", "internal_error"),
        ("409", "case_closed"),
    }
    rows = set(re.findall(r"^\| (\d{3})\s+\| `([a-z_]+)`", rules, re.MULTILINE))
    assert expected <= rows


def test_common_rules_document_duplicate_messages() -> None:
    """R11: update_id es el id único por mensaje; repetido → 202 con status duplicate."""
    rules = _section(_doc(), "Reglas comunes", 2)
    assert "`update_id`" in rules
    assert "identificador único por mensaje" in rules
    assert "`202`" in rules
    assert "`duplicate`" in rules
    assert "sin reprocesar" in rules


def test_common_rules_document_health() -> None:
    """R12: los 4 servicios exponen GET /health sin token con HealthResponse."""
    rules = _section(_doc(), "Reglas comunes", 2)
    for service in ("telegram_gateway", "orchestrator", "rag", "handover"):
        assert f"`{service}`" in rules
    assert "`GET /health` sin token" in rules
    assert '{"status": "ok", "service": "<nombre>"}' in rules
    assert "`HealthResponse`" in rules


def _assumptions() -> str:
    return _section(_doc(), "Supuestos a confirmar", 2)


def _assumption_row(assumption_id: str) -> str:
    match = re.search(rf"^\| {assumption_id} \|(.*)$", _assumptions(), re.MULTILINE)
    assert match, f"falta el supuesto {assumption_id}"
    return match.group(1)


def test_assumptions_include_manuals_multipart() -> None:
    """R13: S1 recoge que POST /manuals es multipart/form-data con partes file y name."""
    row = _assumption_row("S1")
    assert "`POST /manuals`" in row
    assert "`multipart/form-data`" in row
    assert "`file`" in row
    assert "`name`" in row


def test_assumptions_include_last_messages() -> None:
    """R14: S2 recoge últimos 10 mensajes, orden cronológico, {role, text, at}."""
    row = _assumption_row("S2")
    assert "`last_messages`" in row
    assert "10" in row
    assert "cronológico" in row
    assert "`{role, text, at}`" in row


def test_assumptions_mention_s1_to_s10() -> None:
    """R15: la sección de supuestos menciona S1 a S10."""
    for number in range(1, 11):
        _assumption_row(f"S{number}")


# ── contrato_asignar_caso (feature #9) ───────────────────────────────────────

ASSIGN_ROUTE = "POST /cases/{id}/assign"


def test_assign_route_is_called_by_orchestrator() -> None:
    """contrato_asignar_caso R3: '- **Llama:**' de POST /cases/{id}/assign cita orchestrator."""
    assert "orchestrator" in _bullet(ASSIGN_ROUTE, "Llama")


def test_assign_errors_table_has_internal_error() -> None:
    """contrato_asignar_caso R9: '#### Errores' de la ruta tiene la fila 500 internal_error."""
    assert ("500", "internal_error") in _error_rows(_subsection(ASSIGN_ROUTE, "Errores"))


def test_assign_section_documents_path_id() -> None:
    """contrato_asignar_caso R10: la ruta indica que {id} es el case_id (1–64)."""
    assert "`{id}` es el `case_id` (identificador, 1–64 caracteres)" in _route(ASSIGN_ROUTE)


def test_assign_section_documents_s11() -> None:
    """contrato_asignar_caso R11: la ruta describe assigned → 200 y closed → 409 (S11)."""
    section = _route(ASSIGN_ROUTE)
    for fragment in (
        "`assigned`",
        "`200`",
        "sin cambiar el asesor",
        "`closed`",
        "`409`",
        "`case_closed`",
        "S11",
    ):
        assert fragment in section, fragment


def test_common_rules_case_closed_row_cites_assign() -> None:
    """contrato_asignar_caso R12: la fila común 409 case_closed cita /cases/{id}/assign."""
    rules = _section(_doc(), "Reglas comunes", 2)
    match = re.search(r"^\| 409\s+\| `case_closed`\s+\|(.*)$", rules, re.MULTILINE)
    assert match, "falta la fila 409 case_closed en Reglas comunes"
    assert "/cases/{id}/assign" in match.group(1)


def test_assumptions_include_assign_idempotency() -> None:
    """contrato_asignar_caso R14: S11 recoge assigned → 200 sin cambio y closed → 409."""
    row = _assumption_row("S11")
    for fragment in (
        "`POST /cases/{id}/assign`",
        "`assigned`",
        "`200`",
        "sin cambiar el asesor",
        "`closed`",
        "`409`",
        "`case_closed`",
    ):
        assert fragment in row, fragment
