"""Documentación del canal genérico firmado y de los campos nuevos (#60)."""
from __future__ import annotations

import hashlib
import hmac
import json
import re
from pathlib import Path

import pytest

from lazaro_contracts import (
    Attachment,
    ChannelCapabilities,
    NormalizedMessage,
)

DOC_PATH = Path(__file__).resolve().parent.parent / "CONTRATOS.md"
GENERIC_SECTION = "Canal genérico (webhook firmado)"


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


def _base() -> str:
    return _section(_doc(), "Mensaje normalizado y respuesta abstracta", 2)


def _generic() -> str:
    return _section(_doc(), GENERIC_SECTION, 2)


def _first_column_cells(table_text: str) -> set[str]:
    return set(re.findall(r"^\| `([a-z_]+)` \|", table_text, re.MULTILINE))


def _error_rows(table_text: str) -> set[tuple[str, str]]:
    return set(
        re.findall(r"^\| (\d{3})\s+\| `?([a-z_]+)`? \|", table_text, re.MULTILINE)
    )


def _blocks(section: str) -> list[tuple[str, str]]:
    return re.findall(r"```(json|http)\n(.*?)\n```", section, re.DOTALL)


def _http_parts(block: str) -> tuple[str, dict[str, str], str]:
    lines = block.splitlines()
    route = lines[0]
    headers: dict[str, str] = {}
    for line in lines[1:-1]:
        if ":" in line:
            name, _, value = line.partition(":")
            headers[name.strip().lower()] = value.strip()
    return route, headers, lines[-1]


# ── R28, R29 ────────────────────────────────────────────────────────────────


def test_normalized_message_table_lists_all_fields():
    """R28: la tabla de NormalizedMessage lista todos los campos del modelo."""
    table = _section(_base(), "NormalizedMessage", 3)
    assert "| Campo | Tipo | Obligatorio | Descripción |" in table
    assert set(NormalizedMessage.model_fields) <= _first_column_cells(table)


def test_attachment_table_lists_all_fields():
    """R28: la tabla de Attachment lista todos los campos del modelo."""
    table = _section(_base(), "Attachment", 3)
    assert "| Campo | Tipo | Obligatorio | Descripción |" in table
    assert set(Attachment.model_fields) <= _first_column_cells(table)
    assert "nunca el binario" in table


def test_response_blocks_table_lists_image_block():
    """R29: ResponseBlocks documenta ImageBlock con type image."""
    table = _section(_base(), "ResponseBlocks", 3)
    assert "`ImageBlock`" in table
    assert "`image`" in table


def test_capabilities_table_lists_all_fields_with_defaults():
    """R29: ChannelCapabilities documenta los diez campos y sus valores por defecto."""
    table = _section(_base(), "ChannelCapabilities", 3)
    assert set(ChannelCapabilities.model_fields) <= _first_column_cells(table)
    for field, default in (
        ("supports_buttons", "true"),
        ("supports_images", "false"),
        ("supports_files", "false"),
        ("supports_audio", "false"),
    ):
        row = re.search(rf"^\| `{field}` \|(.*)$", table, re.MULTILINE)
        assert row, f"falta la fila {field}"
        assert f"por defecto `{default}`" in row.group(1)


# ── R30-R35: webhook genérico ───────────────────────────────────────────────


def test_generic_webhook_route_is_documented():
    """R30: la ruta del webhook genérico, su servicio, modelos y errores."""
    webhook = _section(_generic(), "POST /webhooks/{canal_id}", 3)
    assert "telegram_gateway" in webhook
    assert "#62" in webhook
    match = re.search(r"^- \*\*Llama:\*\* (.*)$", webhook, re.MULTILINE)
    assert match and match.group(1).strip()
    models = re.search(r"^- \*\*Modelos:\*\* (.*)$", webhook, re.MULTILINE)
    assert models
    assert "`NormalizedMessage`" in models.group(1)
    assert "`MessageResponse`" in models.group(1)
    assert "`200 OK`" in webhook
    rows = _error_rows(_section(webhook, "Errores", 4))
    assert {
        ("401", "unauthorized"),
        ("404", "not_found"),
        ("422", "validation_error"),
        ("500", "internal_error"),
    } <= rows


def test_generic_section_json_examples_validate():
    """R31: los ejemplos de entrada y callback validan como NormalizedMessage."""
    parsed: list[NormalizedMessage] = []
    for language, block in _blocks(_generic()):
        if language == "json":
            parsed.append(NormalizedMessage.model_validate_json(block))
        else:
            _, _, body = _http_parts(block)
            parsed.append(NormalizedMessage.model_validate_json(body))
    assert any(
        message.direction == "inbound"
        and message.attachments
        and message.metadata
        for message in parsed
    )
    assert any(message.direction == "outbound" for message in parsed)


def test_signature_rules_are_documented():
    """R32: encabezados, algoritmo, ventana, comparación constante y 401."""
    section = _section(_generic(), "Firma y ventana anti-repetición", 3)
    for fragment in (
        "`X-Lazaro-Timestamp`",
        "segundos Unix",
        "`X-Lazaro-Signature`",
        "HMAC-SHA256",
        "64 caracteres hexadecimales en minúsculas",
        "<timestamp>.<cuerpo>",
        "300",
        "`DEFAULT_SIGNATURE_WINDOW_SECONDS`",
        "tiempo constante",
        "`401`",
    ):
        assert fragment in section, fragment


def test_signed_examples_are_verifiable():
    """R33: las firmas documentadas coinciden con el secreto de ejemplo."""
    section = _generic()
    secret_match = re.search(r"secreto de ejemplo `([^`]+)`", section)
    assert secret_match
    secret = secret_match.group(1)
    http_blocks = [block for language, block in _blocks(section) if language == "http"]
    assert len(http_blocks) == 2
    inbound_route: str | None = None
    inbound_body: str | None = None
    for block in http_blocks:
        route, headers, body = _http_parts(block)
        timestamp = headers["x-lazaro-timestamp"]
        signature = headers["x-lazaro-signature"]
        assert len(signature) == 64
        assert signature == signature.lower()
        expected = hmac.new(
            secret.encode(),
            f"{timestamp}.".encode() + body.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        assert signature == expected
        path = route.split()[1]
        if path.startswith("/webhooks/"):
            inbound_route = path.removeprefix("/webhooks/")
            inbound_body = body
    assert inbound_route is not None and inbound_body is not None
    assert json.loads(inbound_body)["channel"] == inbound_route


def test_callback_is_documented():
    """R34: callback saliente, firma, entrega 2xx, deduplicación y #62."""
    section = _section(_generic(), "Callback saliente", 3)
    for fragment in (
        "config.callback_url",
        "https",
        "`direction` = `outbound`",
        "mismos encabezados de firma",
        "2xx",
        "envío fallido",
        "deduplica",
        "`external_message_id`",
        "#62",
    ):
        assert fragment in section, fragment


def test_equivalence_table_maps_assignment_names():
    """R35: la tabla del encargo asocia los nueve nombres a campos del contrato."""
    table = _section(_generic(), "Equivalencia con los nombres del encargo", 3)
    pairs = [
        ("canalId", "channel"),
        ("idExternoUsuario", "external_user_id"),
        ("idExternoMensaje", "external_message_id"),
        ("direccion", "direction"),
        ("tipo", "kind"),
        ("contenido", "text"),
        ("adjuntos", "attachments"),
        ("timestamp", "received_at"),
        ("metadata", "metadata"),
    ]
    for source, target in pairs:
        row = re.search(rf"^\| `{source}` \| `{target}` \|", table, re.MULTILINE)
        assert row, f"falta la pareja {source} -> {target}"
        assert target in NormalizedMessage.model_fields


# ── R36-R38 ─────────────────────────────────────────────────────────────────


def test_authentication_lists_generic_webhook():
    """R36: Autenticación exceptúa el webhook genérico protegido por firma."""
    section = _section(_section(_doc(), "Reglas comunes", 2), "Autenticación", 3)
    assert "`POST /webhooks/{canal_id}`" in section
    assert "`X-Service-Token`" in section
    assert "`X-Lazaro-Signature`" in section


def test_send_and_messages_document_channel_registry_behaviors():
    """R37: /send usa el registro; POST /messages conserva su rechazo temporal."""
    variant = _section(_base(), "Variante canónica de POST /send", 3)
    for fragment in (
        "`ChannelRegistry`",
        "no existe una fila",
        "`422 validation_error`",
        "`422 channel_inactive`",
        "`502 upstream_error`",
        "`503 channel_store_unavailable`",
        "`503 channel_secrets_unavailable`",
        "degrada los bloques",
    ):
        assert fragment in variant, fragment

    send_errors = _section(_section(_doc(), "POST /send", 3), "Errores", 4)
    rows = _error_rows(send_errors)
    assert {
        ("422", "validation_error"),
        ("422", "channel_inactive"),
        ("502", "upstream_error"),
        ("503", "channel_store_unavailable"),
        ("503", "channel_secrets_unavailable"),
    } <= rows

    messages_errors = _section(_section(_doc(), "POST /messages", 3), "Errores", 4)
    messages_422 = re.search(r"^\| 422 \|(.*)$", messages_errors, re.MULTILINE)
    assert messages_422
    for fragment in ("no es un canal atendido", "`outbound`"):
        assert fragment in messages_422.group(1), fragment


def test_assumption_s17_documents_limits_and_text_only():
    """R38: S17 recoge formato, límites, binario, «solo texto» y rechazo temporal."""
    assumptions = _section(_doc(), "Supuestos a confirmar", 2)
    row = re.search(r"^\| S17 \|(.*)$", assumptions, re.MULTILINE)
    assert row
    for fragment in (
        "channel",
        "2 a 32",
        "10 adjuntos",
        "4096 bytes",
        "profundidad 5",
        "2048",
        "1024",
        "255",
        "2 GiB",
        "nunca el binario",
        "unsupported_reply",
        "422",
        "#61",
    ):
        assert fragment in row.group(1), fragment
