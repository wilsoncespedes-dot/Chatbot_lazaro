"""R1, R2: contratos y documentación del canal simulado (#63)."""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from pydantic import ValidationError

import lazaro_contracts as contracts
from lazaro_contracts import (
    MailboxEntry,
    MailboxResponse,
    SimulatedInboundRequest,
    SimulatedInboundResponse,
)

DOC_PATH = Path(__file__).resolve().parent.parent / "CONTRATOS.md"
SECTION_NAME = "Canal simulado"
CHANNEL = "tiktok-simulado"
ENTRY = {
    "id": 1,
    "channel": CHANNEL,
    "destination": "cliente-demo",
    "kind": "client",
    "text": "Hola",
    "created_at": "2026-11-21T15:00:00Z",
}
INBOUND = {"external_user_id": "cliente-demo", "text": "Hola"}
RESPONSE = {"status": "accepted", "forwarded": True}


def _section(text: str, heading: str, level: int) -> str:
    lines = text.splitlines()
    marker = "#" * level + " " + heading
    start = lines.index(marker)
    body = []
    for line in lines[start + 1 :]:
        match = re.match(r"^(#+) ", line)
        if match and len(match.group(1)) <= level:
            break
        body.append(line)
    return "\n".join(body)


def _doc() -> str:
    return DOC_PATH.read_text(encoding="utf-8")


def _section_text() -> str:
    return _section(_doc(), SECTION_NAME, 2)


def _route_section(route: str) -> str:
    return _section(_section_text(), route, 3)


def _json_example(section: str, heading: str) -> dict:
    content = _section(section, heading, 4)
    match = re.search(r"```json\n(.*?)\n```", content, re.DOTALL)
    assert match, f"falta ejemplo JSON en {heading}"
    return json.loads(match.group(1))


def _bad(model, payload: dict) -> bool:
    with pytest.raises(ValidationError):
        model.model_validate(payload)
    return True


def test_simulator_models_are_exported():
    """R1: los cuatro modelos públicos están en __all__."""
    names = {
        "MailboxEntry",
        "MailboxResponse",
        "SimulatedInboundRequest",
        "SimulatedInboundResponse",
    }
    assert names <= set(contracts.__all__)
    assert all(hasattr(contracts, name) for name in names)


@pytest.mark.parametrize(
    "model,payload",
    [
        (MailboxEntry, ENTRY),
        (MailboxResponse, {"channel": CHANNEL, "entries": [ENTRY]}),
        (SimulatedInboundRequest, INBOUND),
        (SimulatedInboundResponse, RESPONSE),
    ],
)
def test_simulator_models_forbid_extra_fields(model, payload):
    """R1: todos los modelos heredan extra=forbid."""
    assert _bad(model, {**payload, "unexpected": "value"})


@pytest.mark.parametrize(
    "payload",
    [
        {**ENTRY, "id": 0},
        {**ENTRY, "kind": "otro"},
        {**ENTRY, "text": ""},
        {**ENTRY, "text": "x" * 4097},
        {**ENTRY, "destination": ""},
        {**ENTRY, "created_at": "sin-zona"},
    ],
)
def test_mailbox_entry_rejects_values_outside_limits(payload):
    """R1: id, tipo, texto, destino y fecha se validan."""
    assert _bad(MailboxEntry, payload)


@pytest.mark.parametrize(
    "external_user_id",
    ["", "x" * 65, "con espacios", "acentué", "a/b", "!cliente"],
)
def test_simulated_request_rejects_invalid_external_ids(external_user_id):
    """R1: el id externo de prueba cumple [A-Za-z0-9_.:-]{1,64}."""
    assert _bad(
        SimulatedInboundRequest,
        {"external_user_id": external_user_id, "text": "Hola"},
    )


@pytest.mark.parametrize("text", ["", "x" * 4097])
def test_simulated_request_rejects_invalid_text(text):
    """R1: el texto del mensaje simulado va de 1 a MAX_TEXT_LENGTH."""
    assert _bad(
        SimulatedInboundRequest,
        {"external_user_id": "cliente-demo", "text": text},
    )


@pytest.mark.parametrize(
    "payload",
    [
        {"status": "otro", "forwarded": True},
        {"status": "accepted"},
        {"status": "accepted", "forwarded": True, "reason": "x" * 201},
    ],
)
def test_simulated_response_rejects_invalid_status_or_reason(payload):
    """R1: status y el motivo acotado a 200 caracteres."""
    assert _bad(SimulatedInboundResponse, payload)


@pytest.mark.parametrize(
    "external_user_id",
    ["cliente-demo", "A.b_c:d-1", "x" * 64, "1234567890"],
)
def test_simulated_request_accepts_valid_external_ids(external_user_id):
    """R1: letras, dígitos y _ . : - hasta 64 caracteres son válidos."""
    request = SimulatedInboundRequest(
        external_user_id=external_user_id, text="Hola"
    )
    assert request.external_user_id == external_user_id


def test_contract_documents_routes_examples_errors_settings_and_rejection():
    """R2: secciones, errores, ajustes, capacidades y nota de #65."""
    section = _section_text()
    for route in (
        "GET /channels/{channel_id}/mailbox",
        "POST /channels/{channel_id}/simulate",
    ):
        route_section = _route_section(route)
        assert "- **Expone:** telegram_gateway (desde #63)" in route_section
        assert "- **Llama:**" in route_section
        assert "#### Request" in route_section
        assert "#### Respuesta" in route_section
        assert "#### Errores" in route_section
        errors = set(re.findall(r"^\| (\d{3}) \| `?([a-z_]+)`? \|", route_section, re.M))
        assert {("401", "unauthorized"), ("404", "not_found")} <= errors
        assert {("422", "validation_error"), ("503", "channel_store_unavailable")} <= errors
    assert ("422", "channel_inactive") in set(
        re.findall(
            r"^\| (\d{3}) \| `?([a-z_]+)`? \|",
            _route_section("POST /channels/{channel_id}/simulate"),
            re.M,
        )
    )
    for fragment in (
        "SIMULATED_MAILBOX_RETENTION_SECONDS",
        "SIMULATED_MAILBOX_MAX_ENTRIES",
        "capabilities",
        "supports_images",
        "requires_template",
        "SIMULADO",
        "Desde #65",
        "rejected",
        "solo de pruebas",
    ):
        assert fragment in section, fragment


def test_documented_json_examples_validate_against_the_models():
    """R2: los ejemplos del documento validan contra los modelos de R1."""
    mailbox = _route_section("GET /channels/{channel_id}/mailbox")
    MailboxResponse.model_validate(_json_example(mailbox, "Respuesta"))

    simulate = _route_section("POST /channels/{channel_id}/simulate")
    SimulatedInboundRequest.model_validate(_json_example(simulate, "Request"))
    SimulatedInboundResponse.model_validate(_json_example(simulate, "Respuesta"))
