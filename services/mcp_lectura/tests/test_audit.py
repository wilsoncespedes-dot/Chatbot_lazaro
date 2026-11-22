"""Auditoría de herramientas MCP: hashes, sin valores y fallo cerrado (#74)."""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone

import pytest

from mcp_lectura.adapters import FakeAuditSink
from mcp_lectura.tools import (
    ToolFailure,
    ToolResult,
    args_sha256,
    run_audited,
)

NOW = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
ROWS = [{"destino": "Melgar", "titulo": "Oferta de demostración secreta"}]


def _run(sink, action, arguments=None):
    return run_audited(
        "ofertas_demo",
        arguments or {"destino": "Melgar"},
        "cliente-123",
        sink,
        action,
        lambda: NOW,
    )


def test_audit_row_fields():
    """R9: la auditoría guarda herramienta, hash, filas, estado y fecha."""
    sink = FakeAuditSink()
    rows = _run(sink, lambda: ToolResult(rows=ROWS, demo=True))

    assert rows == ROWS
    record = sink.records[0]
    assert record.herramienta == "ofertas_demo"
    assert record.args_sha256 == args_sha256({"destino": "Melgar"})
    assert record.filas == 1
    assert record.estado == "ok"
    assert record.creado_en == NOW
    assert record.cliente_sha256 == hashlib.sha256(b"cliente-123").hexdigest()


def test_audit_has_no_argument_values():
    """R10: ni los argumentos ni el contenido de las filas quedan guardados."""
    sink = FakeAuditSink()
    _run(sink, lambda: ToolResult(rows=ROWS, demo=True))

    stored = sink.records[0].model_dump_json()
    assert "Melgar" not in stored
    assert "Oferta de demostración secreta" not in stored
    assert "cliente-123" not in stored


def test_audit_failure_returns_error_without_data():
    """R11: si falla la auditoría, no se entrega lo consultado."""
    sink = FakeAuditSink(fail=True)
    with pytest.raises(ToolFailure):
        _run(sink, lambda: ToolResult(rows=ROWS, demo=True))


def test_tool_error_is_audited_and_reraised():
    """R9: un error de la herramienta deja una fila `error` con cero filas."""
    sink = FakeAuditSink()

    def boom():
        raise RuntimeError("Postgres caído")

    with pytest.raises(RuntimeError):
        _run(sink, boom)

    assert sink.records[0].estado == "error"
    assert sink.records[0].filas == 0


def test_audit_failure_on_tool_error_fails_closed():
    """R11: incluso en el camino de error, sin auditoría no hay datos."""
    sink = FakeAuditSink(fail=True)

    def boom():
        raise RuntimeError("Postgres caído")

    with pytest.raises(ToolFailure):
        _run(sink, boom)
