"""Herramientas puras del servidor MCP (#74): solo lectura y DEMOSTRACIÓN."""
from __future__ import annotations

import pytest

from mcp_lectura import schema
from mcp_lectura.adapters import FakeDemoOffers, FakeRagSearch, PostgresDemoOffers
from mcp_lectura.tools import (
    FORBIDDEN_INPUT_FIELDS,
    READ_ONLY_TOOLS,
    TOOL_ANNOTATIONS,
    TOOL_SPECS,
    DEMO_LABEL,
    buscar_manuales,
    ofertas_demo,
)


def test_lists_only_two_tools():
    """R1: el servidor expone exactamente `buscar_manuales` y `ofertas_demo`."""
    assert READ_ONLY_TOOLS == ("buscar_manuales", "ofertas_demo")
    assert tuple(spec.name for spec in TOOL_SPECS) == READ_ONLY_TOOLS
    assert len(TOOL_SPECS) == 2


def test_all_tools_read_only_hint():
    """R2: cada herramienta se declara con `readOnlyHint=True`."""
    assert dict(TOOL_ANNOTATIONS) == {"readOnlyHint": True}
    assert all(spec.read_only_hint is True for spec in TOOL_SPECS)


def test_buscar_manuales_only_calls_search():
    """R4: `buscar_manuales` solo usa `search` del RAG."""
    rag = FakeRagSearch(results=[{"chunk_id": "c1", "text": "hola"}])

    result = buscar_manuales(" cómo instalo ", rag, 5)

    assert rag.calls == [("cómo instalo", 5)]
    assert result.rows == [{"chunk_id": "c1", "text": "hola"}]
    assert result.demo is False


def test_no_identity_field_in_schemas():
    """R5: ningún esquema de entrada declara identidad."""
    for spec in TOOL_SPECS:
        properties = set(spec.input_schema.get("properties", {}))
        assert properties.isdisjoint(FORBIDDEN_INPUT_FIELDS)
        assert "cliente_id" not in properties


def test_demo_rows_marked():
    """R12: cada fila devuelta lleva `es_demo=true` y la etiqueta visible."""
    store = FakeDemoOffers(
        rows=[
            {
                "id": "demo-1",
                "destino": "Melgar",
                "titulo": "Oferta ficticia",
                "es_demo": False,
                "etiqueta": "otra",
            }
        ]
    )

    result = ofertas_demo("Melgar", None, None, store, 20)

    assert result.demo is True
    assert result.rows[0]["es_demo"] is True
    assert result.rows[0]["etiqueta"] == DEMO_LABEL


def test_demo_ddl_enforces_marker():
    """R13: el esquema obliga a que toda fila sea de demostración."""
    ddl = "\n".join(schema.DDL)
    assert "CREATE TABLE IF NOT EXISTS demo_ofertas" in ddl
    assert "es_demo BOOLEAN NOT NULL DEFAULT TRUE" in ddl
    assert "CHECK (es_demo)" in ddl
    assert "etiqueta TEXT NOT NULL" in ddl
    assert "CREATE TABLE IF NOT EXISTS mcp_auditoria" in ddl


class _FakeCursor:
    def __init__(self, log):
        self.log = log
        self.description = None
        self._rows: list[tuple] = []

    def execute(self, sql, params=()):
        self.log.append((sql, tuple(params)))
        if sql.strip().upper().startswith("SELECT"):
            self.description = [
                ("id",),
                ("destino",),
                ("titulo",),
                ("precio_cop",),
                ("valido_desde",),
                ("valido_hasta",),
                ("es_demo",),
                ("etiqueta",),
            ]
            self._rows = [
                (
                    "demo-1",
                    "Melgar",
                    "Oferta de demostración",
                    350000,
                    "2026-01-01",
                    "2026-12-31",
                    True,
                    DEMO_LABEL,
                )
            ]

    def fetchall(self):
        return list(self._rows)


class _FakeConnection:
    def __init__(self):
        self.log: list[tuple[str, tuple]] = []

    def cursor(self):
        return _FakeCursor(self.log)

    def commit(self):
        pass

    def close(self):
        pass


def test_demo_query_is_select_read_only():
    """R3: `ofertas_demo` usa un SELECT parametrizado en transacción READ ONLY."""
    from datetime import date

    connection = _FakeConnection()
    store = PostgresDemoOffers("postgresql://x", connect=lambda: connection)

    rows = store.buscar("Melgar", date(2026, 1, 1), date(2026, 12, 31), 20)

    statements = [sql.strip() for sql, _ in connection.log]
    assert statements[0] == "SET TRANSACTION READ ONLY"
    assert any(statement.upper().startswith("SELECT") for statement in statements)
    assert not any(
        statement.upper().startswith(("INSERT", "UPDATE", "DELETE", "CREATE", "DROP"))
        for statement in statements
    )
    assert statements[-1] == "ROLLBACK"

    select_sql, params = next(
        (sql, params)
        for sql, params in connection.log
        if sql.strip().upper().startswith("SELECT")
    )
    assert "%s" in select_sql
    assert "Melgar" not in select_sql
    assert params == ("%Melgar%", date(2026, 1, 1), date(2026, 12, 31), 20)
    assert rows[0]["etiqueta"] == DEMO_LABEL


@pytest.mark.parametrize("destino", ["", "   "])
def test_demo_rejects_empty_destination(destino):
    """R3, R12: sin destino no se consulta la base."""
    store = FakeDemoOffers()
    with pytest.raises(Exception):
        ofertas_demo(destino, None, None, store, 20)
    assert store.calls == []
