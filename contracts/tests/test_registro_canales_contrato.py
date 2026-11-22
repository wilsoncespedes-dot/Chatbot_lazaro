"""R1–R4: contratos públicos, validación y documentación del registro de canales."""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from pydantic import ValidationError

import lazaro_contracts as contracts
from lazaro_contracts import (
    ChannelActiveRequest,
    ChannelCreateRequest,
    ChannelCreateResponse,
    ChannelInfo,
    ChannelListResponse,
    ChannelSecretResponse,
    ChannelUpdateRequest,
)

DOC_PATH = Path(__file__).resolve().parent.parent / "CONTRATOS.md"
CHANNEL_SECTION = "Canales (registro del gateway)"
CHANNEL_ID = "canal-prueba"
CHANNEL_INFO = {
    "id": CHANNEL_ID,
    "name": "Canal de prueba",
    "adapter_type": "simulado",
    "icon": "chat",
    "color": "#1B6FA8",
    "config": {},
    "active": True,
    "configured": True,
    "has_secrets": True,
    "managed_by_environment": False,
    "created_at": "2026-11-21T12:00:00Z",
}
SECRET = "A" * 43


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


def _channel_section() -> str:
    return _section(DOC_PATH.read_text(encoding="utf-8"), CHANNEL_SECTION, 2)


def _route_section(route: str) -> str:
    return _section(_channel_section(), route, 3)


def _json_example(section: str, heading: str) -> dict:
    content = _section(section, heading, 4)
    match = re.search(r"```json\n(.*?)\n```", content, re.DOTALL)
    assert match, f"falta ejemplo JSON en {heading}"
    return json.loads(match.group(1))


def _bad(model, payload: dict) -> bool:
    with pytest.raises(ValidationError):
        model.model_validate(payload)
    return True


def test_channel_registry_models_are_exported():
    """R1: los siete modelos públicos están en __all__."""
    names = {
        "ChannelInfo",
        "ChannelListResponse",
        "ChannelCreateRequest",
        "ChannelCreateResponse",
        "ChannelUpdateRequest",
        "ChannelActiveRequest",
        "ChannelSecretResponse",
    }
    assert names <= set(contracts.__all__)
    assert all(hasattr(contracts, name) for name in names)


@pytest.mark.parametrize(
    "model,payload",
    [
        (ChannelInfo, CHANNEL_INFO),
        (ChannelListResponse, {"channels": [CHANNEL_INFO], "adapter_types": ["simulado"]}),
        (
            ChannelCreateRequest,
            {
                "id": CHANNEL_ID,
                "name": "Canal de prueba",
                "adapter_type": "simulado",
                "icon": "chat",
                "color": "#1B6FA8",
            },
        ),
        (ChannelCreateResponse, {"channel": CHANNEL_INFO, "secret": SECRET}),
        (ChannelUpdateRequest, {"name": "Nuevo nombre"}),
        (ChannelActiveRequest, {"active": False}),
        (ChannelSecretResponse, {"channel_id": CHANNEL_ID, "secret": SECRET}),
    ],
)
def test_channel_models_forbid_extra_fields(model, payload):
    """R1: todos los modelos del registro heredan extra=forbid."""
    assert _bad(model, {**payload, "unexpected": "value"})


def _create_payload(**changes) -> dict:
    payload = {
        "id": CHANNEL_ID,
        "name": "Canal de prueba",
        "adapter_type": "simulado",
        "icon": "chat",
        "color": "#1B6FA8",
    }
    payload.update(changes)
    return payload


@pytest.mark.parametrize(
    "payload",
    [
        _create_payload(id="x"),
        _create_payload(id="Xx"),
        _create_payload(name=""),
        _create_payload(name=" " * 4),
        _create_payload(name="nombre\x00canal"),
        _create_payload(name="n" * 61),
        _create_payload(icon=""),
        _create_payload(icon="i" * 33),
        _create_payload(icon="chat\x7f"),
        _create_payload(color="1B6FA8"),
        _create_payload(color="#12345G"),
        _create_payload(config={"x": "v" * 4096}),
        _create_payload(config={"a": {"b": {"c": {"d": {"e": {}}}}}}),
        _create_payload(credentials={f"key_{i}": "v" for i in range(21)}),
        _create_payload(credentials={"Bad": "value"}),
        _create_payload(credentials={"good": ""}),
        _create_payload(credentials={"good": "v" * 4097}),
        _create_payload(active="true"),
    ],
)
def test_channel_create_rejects_values_outside_limits(payload):
    """R2: los límites de id, visuales, config, credenciales y active son estrictos."""
    assert _bad(ChannelCreateRequest, payload)


@pytest.mark.parametrize(
    "payload",
    [
        {"name": "x" * 61},
        {"name": "a\n"},
        {"icon": "i" * 33},
        {"icon": "x\x01"},
        {"color": "#abc"},
        {"config": {"a": {"b": {"c": {"d": {"e": {}}}}}}},
        {"credentials": {f"key_{i}": "v" for i in range(21)}},
        {"credentials": {"1bad": "value"}},
        {"credentials": {"a" * 65: "value"}},
        {"credentials": {"valid": "v" * 4097}},
        {"credentials": {"valid": ""}},
        {"name": None},
        {"config": None},
        {"credentials": None},
    ],
)
def test_channel_update_rejects_invalid_or_empty_updates(payload):
    """R2: PATCH exige campos válidos y no acepta una actualización vacía/null."""
    assert _bad(ChannelUpdateRequest, payload)


@pytest.mark.parametrize("value", ["true", 1, 0, None])
def test_active_requires_a_boolean(value):
    """R2: active usa StrictBool y rechaza coerciones."""
    assert _bad(ChannelActiveRequest, {"active": value})


@pytest.mark.parametrize("value", ["short", "x" * 42, "x" * 44, "a" * 42 + "+"])
def test_channel_secret_requires_43_url_safe_characters(value):
    """R2: secret debe cumplir ^[A-Za-z0-9_-]{43}$."""
    assert _bad(ChannelSecretResponse, {"channel_id": CHANNEL_ID, "secret": value})


def test_channel_contract_document_lists_route_models_fields_and_errors():
    """R3: las seis rutas siguen el formato común y enumeran request/response/errors."""
    cases = {
        "GET /channels": ("ChannelListResponse", {("503", "channel_store_unavailable")}),
        "POST /channels": (
            "ChannelCreateResponse",
            {
                ("409", "channel_exists"),
                ("503", "channel_secrets_unavailable"),
                ("503", "channel_store_unavailable"),
            },
        ),
        "PATCH /channels/{channel_id}": (
            "ChannelInfo",
            {
                ("404", "not_found"),
                ("409", "channel_managed_by_environment"),
                ("503", "channel_secrets_unavailable"),
                ("503", "channel_store_unavailable"),
            },
        ),
        "PATCH /channels/{channel_id}/active": (
            "ChannelInfo",
            {("404", "not_found"), ("503", "channel_store_unavailable")},
        ),
        "POST /channels/{channel_id}/secret": (
            "ChannelSecretResponse",
            {
                ("404", "not_found"),
                ("409", "channel_managed_by_environment"),
                ("503", "channel_secrets_unavailable"),
                ("503", "channel_store_unavailable"),
            },
        ),
        "GET /channels/{channel_id}/secret": (
            "ChannelSecretResponse",
            {
                ("404", "not_found"),
                ("409", "channel_managed_by_environment"),
                ("503", "channel_secrets_unavailable"),
                ("503", "channel_store_unavailable"),
            },
        ),
    }
    for route, (response_model, own_errors) in cases.items():
        section = _route_section(route)
        assert "- **Expone:** `telegram_gateway`" in section
        assert "- **Llama:**" in section
        assert f"`{response_model}`" in section
        assert "#### Request" in section
        assert "#### Respuesta" in section
        assert "#### Errores" in section
        errors = set(re.findall(r"^\| (\d{3}) \| `?([a-z_]+)`? \|", section, re.M))
        assert {("401", "unauthorized"), ("422", "validation_error")} <= errors
        assert own_errors <= errors


@pytest.mark.parametrize(
    "route,request_model,response_model",
    [
        ("GET /channels", None, ChannelListResponse),
        ("POST /channels", ChannelCreateRequest, ChannelCreateResponse),
        ("PATCH /channels/{channel_id}", ChannelUpdateRequest, ChannelInfo),
        (
            "PATCH /channels/{channel_id}/active",
            ChannelActiveRequest,
            ChannelInfo,
        ),
        ("POST /channels/{channel_id}/secret", None, ChannelSecretResponse),
        ("GET /channels/{channel_id}/secret", None, ChannelSecretResponse),
    ],
)
def test_channel_route_json_examples_validate(route, request_model, response_model):
    """R3: cada ejemplo JSON documentado valida contra su modelo de contrato."""
    section = _route_section(route)
    if request_model is not None:
        request = _json_example(section, "Request")
        request_model.model_validate(request)
    response = _json_example(section, "Respuesta")
    response_model.model_validate(response)


def test_channel_contract_documents_column_mapping_and_registry_behavior():
    """R3, R4: columnas, errores, degradación, salud y estados actuales documentados."""
    doc = DOC_PATH.read_text(encoding="utf-8")
    section = _channel_section()
    for source, target in (
        ("name", "nombre"),
        ("adapter_type", "tipo_adaptador"),
        ("icon", "icono"),
        ("active", "activo"),
        ("created_at", "creado_en"),
        ("credentials` y `secret", "config_secreta"),
    ):
        assert f"| `{source}` | `{target}`" in section
    for fragment in (
        "channel_secrets_unavailable",
        "channel_store_unavailable",
        "`configured`",
        "`has_secrets`",
        "`managed_by_environment`",
    ):
        assert fragment in section
    errors = _section(doc, "Errores", 3)
    for code in (
        "channel_exists",
        "channel_managed_by_environment",
        "channel_inactive",
        "channel_secrets_unavailable",
        "channel_store_unavailable",
    ):
        assert f"`{code}`" in errors
    send = _section(doc, "Variante canónica de POST /send", 3)
    for fragment in (
        "no existe una fila",
        "`422 validation_error`",
        "`422 channel_inactive`",
        "`502 upstream_error`",
        "`503 channel_store_unavailable`",
        "`503 channel_secrets_unavailable`",
    ):
        assert fragment in send
    base = _section(doc, "Mensaje normalizado y respuesta abstracta", 2)
    assert "### Degradación por capacidades" in base
    degradation = _section(base, "Degradación por capacidades", 3)
    for block in ("OptionsBlock", "ListBlock", "ImageBlock", "LinkBlock"):
        assert block in degradation
    image_row = re.search(r"^\| `ImageBlock` \|(.*)$", doc, re.M)
    assert image_row and "422" not in image_row.group(1)
    health = _section(_section(doc, "Reglas comunes", 2), "Salud", 3)
    assert "desde #61" in health and "PostgreSQL" in health
    s17 = re.search(r"^\| S17 \|(.*)$", _section(doc, "Supuestos a confirmar", 2), re.M)
    assert s17 and "#61" in s17.group(1) and "degrada" in s17.group(1)
