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
    "POST /cases/{id}/authorize": "handover",
    "POST /cases/{id}/client-message": "handover",
    "PATCH /chunks/{id}": "rag",
}

OWN_ERRORS: dict[str, list[tuple[str, str]]] = {
    "POST /send": [("502", "telegram_error")],
    "POST /manuals": [("415", "unsupported_format"), ("422", "empty_document")],
    "POST /cases/{id}/reply": [("404", "not_found"), ("502", "upstream_error")],
    "POST /cases/{id}/close": [("404", "not_found")],
    "POST /cases/{id}/assign": [("404", "not_found"), ("409", "case_closed")],
    "POST /cases/{id}/authorize": [
        ("403", "forbidden"),
        ("404", "not_found"),
        ("409", "case_closed"),
    ],
    "POST /cases/{id}/client-message": [
        ("404", "not_found"),
        ("502", "upstream_error"),
    ],
    "PATCH /chunks/{id}": [
        ("404", "not_found"),
        ("500", "internal_error"),
    ],
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
    "POST /cases/{id}/authorize": "200",
    "POST /cases/{id}/client-message": "200",
    "PATCH /chunks/{id}": "200",
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
        ("403", "forbidden"),
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


# ── contrato_autorizacion_asesores (feature #13) ─────────────────────────────

AUTHORIZE_ROUTE = "POST /cases/{id}/authorize"


def _request_row(route: str, field: str) -> str:
    table = _subsection(route, "Request")
    match = re.search(rf"^\| `{field}` \|(.*)$", table, re.MULTILINE)
    assert match, f"{route}: falta la fila del campo {field}"
    return match.group(1)


def test_authorize_route_is_called_by_orchestrator() -> None:
    """contrato_autorizacion_asesores R3: la línea Llama cita orchestrator."""
    assert "orchestrator" in _bullet(AUTHORIZE_ROUTE, "Llama")


def test_authorize_action_row_lists_reply_and_close() -> None:
    """contrato_autorizacion_asesores R6: la fila action lista reply y close."""
    row = _request_row(AUTHORIZE_ROUTE, "action")
    assert "`reply`" in row
    assert "`close`" in row


def test_authorize_errors_table_has_internal_error() -> None:
    """contrato_autorizacion_asesores R10: la tabla de errores tiene 500 internal_error."""
    assert ("500", "internal_error") in _error_rows(_subsection(AUTHORIZE_ROUTE, "Errores"))


def test_authorize_section_documents_path_id() -> None:
    """contrato_autorizacion_asesores R11: {id} es el case_id (1–64)."""
    assert "`{id}` es el `case_id` (identificador, 1–64 caracteres)" in _route(
        AUTHORIZE_ROUTE
    )


def test_authorize_section_documents_allowed_true_or_forbidden() -> None:
    """contrato_autorizacion_asesores R12: 200 allowed=true o 403 forbidden, nunca false."""
    section = _route(AUTHORIZE_ROUTE)
    for fragment in (
        "`200`",
        "`allowed` = `true`",
        "`403`",
        "`forbidden`",
        "`allowed` = `false`",
        "S12",
    ):
        assert fragment in section, fragment


def test_authorize_section_documents_closed_case() -> None:
    """contrato_autorizacion_asesores R13: caso closed → 409 case_closed."""
    section = _route(AUTHORIZE_ROUTE)
    for fragment in ("`closed`", "`409`", "`case_closed`"):
        assert fragment in section, fragment


def test_common_rules_forbidden_row_cites_case_routes() -> None:
    """contrato_autorizacion_asesores R14: la fila 403 cita las cuatro rutas de casos."""
    rules = _section(_doc(), "Reglas comunes", 2)
    match = re.search(r"^\| 403\s+\| `forbidden`\s+\|(.*)$", rules, re.MULTILINE)
    assert match, "falta la fila 403 forbidden en Reglas comunes"
    for route in (
        "/cases/{id}/authorize",
        "/cases/{id}/reply",
        "/cases/{id}/close",
        "/cases/{id}/assign",
    ):
        assert route in match.group(1), route


CASE_ROUTES_WITH_FORBIDDEN = [
    "POST /cases/{id}/reply",
    "POST /cases/{id}/close",
    "POST /cases/{id}/assign",
]

PREVIOUS_ERROR_ROWS: dict[str, set[tuple[str, str]]] = {
    "POST /cases/{id}/reply": {
        ("401", "unauthorized"),
        ("422", "validation_error"),
        ("404", "not_found"),
        ("502", "upstream_error"),
        ("500", "internal_error"),
    },
    "POST /cases/{id}/close": {
        ("401", "unauthorized"),
        ("422", "validation_error"),
        ("404", "not_found"),
        ("500", "internal_error"),
    },
    "POST /cases/{id}/assign": {
        ("401", "unauthorized"),
        ("422", "validation_error"),
        ("404", "not_found"),
        ("409", "case_closed"),
        ("500", "internal_error"),
    },
}


@pytest.mark.parametrize("route", CASE_ROUTES_WITH_FORBIDDEN)
def test_existing_case_routes_document_forbidden(route: str) -> None:
    """contrato_autorizacion_asesores R15-R17: las rutas existentes documentan 403."""
    assert ("403", "forbidden") in _error_rows(_subsection(route, "Errores"))


@pytest.mark.parametrize("route", CASE_ROUTES_WITH_FORBIDDEN)
def test_existing_case_routes_keep_their_error_rows(route: str) -> None:
    """contrato_autorizacion_asesores R18: las filas previas se conservan y se añade 403."""
    rows = _error_rows(_subsection(route, "Errores"))
    assert PREVIOUS_ERROR_ROWS[route] | {("403", "forbidden")} <= rows


def test_assumptions_s12_defines_who_is_advisor() -> None:
    """contrato_autorizacion_asesores R19: S12 define quién es asesor y el 403."""
    row = _assumption_row("S12")
    for fragment in (
        "`POST /cases/{id}/authorize`",
        "`ADVISOR_CHAT_IDS`",
        "`403`",
        "`forbidden`",
    ):
        assert fragment in row, fragment


def test_assumptions_s12_reply_rules() -> None:
    """contrato_autorizacion_asesores R20: S12 recoge la regla de responder."""
    row = _assumption_row("S12")
    for fragment in (
        "`reply`",
        "`open`",
        "`timed_out`",
        "la primera respuesta lo asigna",
        "`assigned`",
        "solo lo responde el asesor asignado",
    ):
        assert fragment in row, fragment


def test_assumptions_s12_close_rules() -> None:
    """contrato_autorizacion_asesores R21: S12 recoge la regla de cerrar."""
    row = _assumption_row("S12")
    for fragment in (
        "`close`",
        "lo cierra cualquier asesor registrado",
        "solo lo cierra el asesor asignado",
    ):
        assert fragment in row, fragment


def test_assumptions_s12_no_reassignment_nor_supervisor() -> None:
    """contrato_autorizacion_asesores R22: S12 niega reasignación y rol supervisor."""
    row = _assumption_row("S12")
    assert "Sin reasignación" in row
    assert "supervisor" in row


def test_assumptions_s12_fails_closed() -> None:
    """contrato_autorizacion_asesores R23: S12 recoge el fallo cerrado 502."""
    row = _assumption_row("S12")
    for fragment in ("falla cerrado", "no envía", "`502`", "`upstream_error`"):
        assert fragment in row, fragment


def test_assumptions_s12_applies_to_existing_routes() -> None:
    """contrato_autorizacion_asesores R24: S12 aplica a reply, close y assign."""
    row = _assumption_row("S12")
    for fragment in (
        "`POST /cases/{id}/reply`",
        "sin enviar nada al cliente",
        "`POST /cases/{id}/close`",
        "`POST /cases/{id}/assign`",
        "sin modificar el caso",
    ):
        assert fragment in row, fragment


def test_assumptions_s12_identity_limitation() -> None:
    """contrato_autorizacion_asesores R25: S12 recoge la limitación de identidad."""
    row = _assumption_row("S12")
    for fragment in ("`SERVICE_TOKEN`", "suplante", "`advisor_id`"):
        assert fragment in row, fragment


def test_assumptions_s12_limits_s11_to_assigned_advisor() -> None:
    """contrato_autorizacion_asesores R26: S11 solo da 200 al asesor asignado."""
    row = _assumption_row("S12")
    for fragment in ("(S11)", "al asesor asignado", "otro asesor recibe `403`"):
        assert fragment in row, fragment


def test_assumptions_s12_error_precedence() -> None:
    """contrato_autorizacion_asesores R43: S12 fija la precedencia de errores."""
    row = _assumption_row("S12")
    for fragment in (
        "Precedencia de errores",
        "`POST /cases/{id}/authorize`",
        "`POST /cases/{id}/close`",
        "`POST /cases/{id}/assign`",
        (
            "`403` (asesor no registrado) → `404` (caso inexistente) → `409` "
            "(caso `closed`; en `POST /cases/{id}/close`, `200` sin cambios por S8) "
            "→ `403` (caso asignado a otro asesor)"
        ),
    ):
        assert fragment in row, fragment


def test_assumptions_s12_close_on_closed_keeps_s8() -> None:
    """contrato_autorizacion_asesores R44: close sobre closed sigue S8; authorize da 409."""
    row = _assumption_row("S12")
    for fragment in (
        "`POST /cases/{id}/close` sobre un caso `closed` sigue S8",
        "`200` sin cambios para cualquier asesor registrado",
        "`action` = `close` sobre un caso `closed` responde `409`",
    ):
        assert fragment in row, fragment


def test_assumptions_s12_fail_closed_reuses_reply_502() -> None:
    """contrato_autorizacion_asesores R45: el 502 reutiliza la fila publicada de reply."""
    row = _assumption_row("S12")
    assert (
        "la fila `502 upstream_error` ya publicada de `POST /cases/{id}/reply`" in row
    )
    assert ("502", "upstream_error") in _error_rows(
        _subsection("POST /cases/{id}/reply", "Errores")
    )


def test_assumptions_s12_reply_on_closed_is_case_closed() -> None:
    """contrato_autorizacion_asesores R46: reply sobre closed → 409 case_closed."""
    row = _assumption_row("S12")
    for fragment in (
        "`POST /cases/{id}/reply` sobre un caso `closed` responde `409` con "
        "`error` = `case_closed`, sin enviar nada al cliente",
        "el orquestador propaga el `409` de `authorize`",
    ):
        assert fragment in row, fragment


def test_assumptions_s12_reply_authorizes_before_case_lookup() -> None:
    """contrato_autorizacion_asesores R47: reply autoriza antes de buscar el caso."""
    row = _assumption_row("S12")
    for fragment in (
        "En `POST /cases/{id}/reply` el orquestador autoriza antes de comprobar si "
        "el caso existe",
        "un `advisor_id` no registrado recibe `403` con `error` = `forbidden` "
        "aunque el caso no exista",
    ):
        assert fragment in row, fragment


def test_reply_errors_table_has_case_closed() -> None:
    """contrato_autorizacion_asesores R48: la tabla de reply tiene 409 case_closed."""
    assert ("409", "case_closed") in _error_rows(
        _subsection("POST /cases/{id}/reply", "Errores")
    )


def test_common_rules_case_closed_row_cites_reply() -> None:
    """contrato_autorizacion_asesores R49: la fila común 409 cita assign y reply."""
    rules = _section(_doc(), "Reglas comunes", 2)
    match = re.search(r"^\| 409\s+\| `case_closed`\s+\|(.*)$", rules, re.MULTILINE)
    assert match, "falta la fila 409 case_closed en Reglas comunes"
    assert "/cases/{id}/reply" in match.group(1)
    assert "/cases/{id}/assign" in match.group(1)


def test_assumptions_s11_other_advisor_gets_forbidden() -> None:
    """contrato_autorizacion_asesores R50: otro asesor recibe 403 al asignar."""
    row = _assumption_row("S11")
    for fragment in (
        "sin cambiar el asesor asignado cuando quien asigna es el asesor asignado",
        "si es otro asesor, responde `403` con `error` = `forbidden`",
        "(S12, cambio de la #13)",
    ):
        assert fragment in row, fragment


def test_assumptions_s12_documents_s11_change() -> None:
    """contrato_autorizacion_asesores R51: S12 documenta el cambio frente a S11."""
    row = _assumption_row("S12")
    for fragment in (
        "Esto cambia el `200` sin cambios que S11 daba en la #9 a cualquier asesor",
        "el asesor asignado sigue recibiendo `200` sin cambios",
    ):
        assert fragment in row, fragment


def test_authorize_route_caller_mentions_cerrar_command() -> None:
    """contrato_autorizacion_asesores R53: la línea Llama cita /cerrar y close."""
    llamada = _bullet(AUTHORIZE_ROUTE, "Llama")
    assert "`/cerrar`" in llamada
    assert "`POST /cases/{id}/close`" in llamada


# ── contrato_cierre_casos_huerfanos (feature #17) ────────────────────────────


def test_assumptions_s12_defines_orphan_case() -> None:
    """contrato_cierre_casos_huerfanos R1: S12 define el caso huérfano, incluido el nulo."""
    row = _assumption_row("S12")
    fragment = (
        "Caso huérfano: un caso `assigned` cuyo `advisor_id` es nulo o ya no está en "
        "`ADVISOR_CHAT_IDS`"
    )
    assert fragment in row, fragment


def test_assumptions_s12_orphan_close_by_any_registered_advisor() -> None:
    """contrato_cierre_casos_huerfanos R2: cualquier asesor registrado cierra un huérfano."""
    row = _assumption_row("S12")
    for fragment in (
        "Un caso huérfano lo cierra cualquier asesor registrado",
        "`POST /cases/{id}/close` lo pasa a `closed`",
    ):
        assert fragment in row, fragment


def test_assumptions_s12_orphan_authorize_close_allowed() -> None:
    """contrato_cierre_casos_huerfanos R3: authorize(close) sobre un huérfano da 200."""
    row = _assumption_row("S12")
    fragment = "`authorize` con `action` = `close` responde `200` con `allowed` = `true`"
    assert fragment in row, fragment


def test_assumptions_s12_orphan_close_is_not_reassignment() -> None:
    """contrato_cierre_casos_huerfanos R4: cerrar un huérfano no es reasignarlo."""
    row = _assumption_row("S12")
    fragment = "cerrarlo no es reasignarlo"
    assert fragment in row, fragment


def test_assumptions_s12_assigned_close_rule_has_orphan_exception() -> None:
    """contrato_cierre_casos_huerfanos R5: un assigned solo lo cierra el asignado, salvo huérfano."""
    row = _assumption_row("S12")
    fragment = "un caso `assigned` solo lo cierra el asesor asignado, salvo un caso huérfano"
    assert fragment in row, fragment


def test_assumptions_s12_orphan_reply_forbidden() -> None:
    """contrato_cierre_casos_huerfanos R6: otro asesor no puede responder un huérfano."""
    row = _assumption_row("S12")
    for fragment in (
        "Un caso huérfano no lo responde ni lo asigna ningún otro asesor",
        (
            "`POST /cases/{id}/reply` y `authorize` con `action` = `reply` responden "
            "`403` con `error` = `forbidden`"
        ),
    ):
        assert fragment in row, fragment


def test_assumptions_s12_orphan_assign_forbidden() -> None:
    """contrato_cierre_casos_huerfanos R7: otro asesor no puede asignar un huérfano."""
    row = _assumption_row("S12")
    for fragment in (
        "Un caso huérfano no lo responde ni lo asigna ningún otro asesor",
        "`POST /cases/{id}/assign` responde `403` con `error` = `forbidden` sin modificar el caso",
    ):
        assert fragment in row, fragment


def test_assumptions_s12_precedence_other_advisor_step_skips_orphan_close() -> None:
    """contrato_cierre_casos_huerfanos R8: el escalón 403 de otro asesor no aplica a close."""
    row = _assumption_row("S12")
    fragment = (
        "→ `403` (caso asignado a otro asesor), escalón que no se aplica a "
        "`POST /cases/{id}/close` ni a `authorize` con `action` = `close` sobre un caso "
        "huérfano"
    )
    assert fragment in row, fragment


def test_assumptions_s12_precedence_orphan_close_allowed_after_first_steps() -> None:
    """contrato_cierre_casos_huerfanos R9: superados los tres primeros escalones, se cierra."""
    row = _assumption_row("S12")
    for fragment in (
        "superados los tres primeros escalones, el cierre está permitido",
        (
            "`403` (asesor no registrado) → `404` (caso inexistente) → `409` "
            "(caso `closed`; en `POST /cases/{id}/close`, `200` sin cambios por S8)"
        ),
    ):
        assert fragment in row, fragment


def test_assumptions_s12_documents_advisor_retirement_procedure() -> None:
    """contrato_cierre_casos_huerfanos R10: el asesor cierra sus casos antes de retirarse."""
    row = _assumption_row("S12")
    fragment = "antes de quitar su chat_id de `ADVISOR_CHAT_IDS`, el asesor cierra sus casos"
    assert fragment in row, fragment


def test_assumptions_s12_documents_orphan_count_at_startup() -> None:
    """contrato_cierre_casos_huerfanos R11: handover registra cuántos huérfanos hay al arrancar."""
    row = _assumption_row("S12")
    fragment = "al arrancar, handover registra cuántos casos huérfanos hay, sin sus ids"
    assert fragment in row, fragment


# ── contrato_conversacion_caso (feature #15) ─────────────────────────────────

CLIENT_MESSAGE_ROUTE = "POST /cases/{id}/client-message"


def test_client_message_route_is_called_by_orchestrator() -> None:
    """contrato_conversacion_caso R3: '- **Llama:**' de la ruta cita orchestrator."""
    assert "orchestrator" in _bullet(CLIENT_MESSAGE_ROUTE, "Llama")


def test_client_message_errors_table_has_internal_error() -> None:
    """contrato_conversacion_caso R9: '#### Errores' de la ruta tiene 500 internal_error."""
    assert ("500", "internal_error") in _error_rows(
        _subsection(CLIENT_MESSAGE_ROUTE, "Errores")
    )


def test_client_message_section_documents_path_id() -> None:
    """contrato_conversacion_caso R10: la ruta indica que {id} es el case_id (1–64)."""
    assert "`{id}` es el `case_id` (identificador, 1–64 caracteres)" in _route(
        CLIENT_MESSAGE_ROUTE
    )


def test_client_message_section_documents_statuses() -> None:
    """contrato_conversacion_caso R11: la ruta describe assigned → forwarded y not_assigned."""
    section = _route(CLIENT_MESSAGE_ROUTE).split("#### Request")[0]
    for fragment in (
        "`assigned`",
        "`200`",
        "`forwarded`",
        "`not_assigned`",
        "asesor asignado",
        "sin enviar nada",
        "S13",
    ):
        assert fragment in section, fragment


def test_client_message_upstream_error_row_mentions_advisor() -> None:
    """contrato_conversacion_caso R12: la fila 502 upstream_error cita el envío al asesor."""
    table = _subsection(CLIENT_MESSAGE_ROUTE, "Errores")
    match = re.search(r"^\| 502 \| upstream_error \|(.*)$", table, re.MULTILINE)
    assert match, "falta la fila 502 upstream_error"
    assert "envío al asesor" in match.group(1)


def test_client_message_error_codes_are_declared_in_common_rules() -> None:
    """contrato_conversacion_caso R13: los errores de la ruta ya están en Reglas comunes."""
    rows = _error_rows(_subsection(CLIENT_MESSAGE_ROUTE, "Errores"))
    rules = _section(_doc(), "Reglas comunes", 2)
    declared = set(re.findall(r"^\| (\d{3})\s+\| `([a-z_]+)`", rules, re.MULTILINE))
    assert rows <= declared


def test_close_route_is_also_called_by_orchestrator() -> None:
    """contrato_conversacion_caso R14: close cita orchestrator y conserva el llamador previo."""
    llamada = _bullet("POST /cases/{id}/close", "Llama")
    assert "orchestrator" in llamada
    assert "asesor (herramienta interna con token; panel en el futuro)" in llamada


def test_assumptions_include_client_message_forwarding() -> None:
    """contrato_conversacion_caso R15: S13 recoge cuándo se reenvía el mensaje al asesor."""
    row = _assumption_row("S13")
    for fragment in (
        "`POST /cases/{id}/client-message`",
        "`assigned`",
        "`open`",
        "`not_assigned`",
        "`404`",
        "flujo actual",
    ):
        assert fragment in row, fragment


def test_assumptions_s13_forward_failure_does_not_fall_back_to_rag() -> None:
    """contrato_conversacion_caso R16: S13 recoge el 502 sin volver al RAG."""
    row = _assumption_row("S13")
    for fragment in ("`502`", "texto fijo", "no se vuelve al RAG"):
        assert fragment in row, fragment


def test_assumptions_s13_advisor_commands_use_messages_route() -> None:
    """contrato_conversacion_caso R17: S13 recoge los comandos por POST /messages."""
    row = _assumption_row("S13")
    for fragment in (
        "`/responder <case_id> <texto>`",
        "`/cerrar <case_id>`",
        "`POST /messages`",
        "no cambia",
    ):
        assert fragment in row, fragment


def test_assumptions_s13_advisor_id_is_telegram_sender() -> None:
    """contrato_conversacion_caso R18: S13 fija advisor_id = remitente del webhook."""
    row = _assumption_row("S13")
    for fragment in (
        "`advisor_id`",
        "`telegram_user_id`",
        "`TELEGRAM_WEBHOOK_SECRET`",
        "nunca un id escrito en el texto",
    ):
        assert fragment in row, fragment


def test_assumptions_s13_non_command_advisor_message_follows_current_flow() -> None:
    """contrato_conversacion_caso R36: un mensaje de asesor que no es comando sigue el flujo."""
    row = _assumption_row("S13")
    for fragment in (
        "un mensaje de un asesor que no es `/responder` ni `/cerrar` sigue el flujo actual",
        "como el de cualquier cliente",
    ):
        assert fragment in row, fragment


def test_assumptions_s13_advisor_commands_follow_s12() -> None:
    """contrato_conversacion_caso R38: S13 autoriza los comandos con las reglas de S12."""
    row = _assumption_row("S13")
    assert "se autorizan con las reglas de S12" in row
    assert _assumption_row("S12") != ""


def test_assumptions_s13_advisor_list_matches_sender_user_id() -> None:
    """contrato_conversacion_caso R37: ADVISOR_CHAT_IDS se compara con telegram_user_id."""
    row = _assumption_row("S13")
    for fragment in (
        "`ADVISOR_CHAT_IDS`",
        "se comprueba con ese `telegram_user_id`",
        "no con el `chat_id`",
    ):
        assert fragment in row, fragment


def test_assumptions_s13_group_ids_cannot_use_commands() -> None:
    """contrato_conversacion_caso R39: un id de grupo no puede usar los comandos."""
    row = _assumption_row("S13")
    for fragment in ("id de grupo (negativo)", "no puede usar los comandos"):
        assert fragment in row, fragment


# ── edicion_fragmentos (feature #19) ─────────────────────────────────────────

CHUNK_UPDATE_ROUTE = "PATCH /chunks/{id}"


def test_chunk_update_route_is_exposed_by_rag() -> None:
    """edicion_fragmentos R1: la ruta la expone rag y documenta sus modelos."""
    assert _bullet(CHUNK_UPDATE_ROUTE, "Expone") == "rag"
    names = re.findall(r"`([A-Za-z]+)`", _bullet(CHUNK_UPDATE_ROUTE, "Modelos"))
    assert names[:2] == ["ChunkUpdateRequest", "ChunkUpdateResponse"]


def test_chunk_update_errors_table_has_all_documented_codes() -> None:
    """edicion_fragmentos R1: la tabla de errores documenta 401, 404, 422 y 500."""
    rows = _error_rows(_subsection(CHUNK_UPDATE_ROUTE, "Errores"))
    assert {
        ("401", "unauthorized"),
        ("404", "not_found"),
        ("422", "validation_error"),
        ("500", "internal_error"),
    } <= rows


def test_chunk_update_request_table_lists_text() -> None:
    """edicion_fragmentos R1: la tabla de request lista el campo text."""
    assert "`text`" in _subsection(CHUNK_UPDATE_ROUTE, "Request")
    assert "text" in _first_column_cells(_subsection(CHUNK_UPDATE_ROUTE, "Request"))


def test_chunk_update_section_documents_preserved_metadata() -> None:
    """edicion_fragmentos R1, R7: la ruta documenta los metadatos que conserva."""
    section = _route(CHUNK_UPDATE_ROUTE)
    for fragment in ("`chunk_id`", "`manual_id`", "manual", "orden", "estado activo"):
        assert fragment in section, fragment

