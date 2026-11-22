"""Registro de herramientas en `build_mcp` con un SDK MCP simulado (#74)."""
from __future__ import annotations

import inspect
import sys
import types

from mcp_lectura.adapters import FakeAuditSink, FakeDemoOffers, FakeRagSearch
from mcp_lectura.server import McpDeps, build_mcp
from mcp_lectura.tools import FORBIDDEN_INPUT_FIELDS


def _install_fake_sdk(monkeypatch, registered: list[tuple]) -> None:
    class FakeAnnotations:
        def __init__(self, **kwargs) -> None:
            self.kwargs = kwargs

    class FakeFastMCP:
        def __init__(self, name: str) -> None:
            self.name = name
            self.registered = registered

        def tool(self, *, name=None, description=None, annotations=None):
            def decorator(function):
                self.registered.append((name, description, annotations, function))
                return function

            return decorator

    class FakeToolError(Exception):
        pass

    fastmcp = types.ModuleType("mcp.server.fastmcp")
    fastmcp.FastMCP = FakeFastMCP
    exceptions = types.ModuleType("mcp.server.fastmcp.exceptions")
    exceptions.ToolError = FakeToolError
    types_module = types.ModuleType("mcp.types")
    types_module.ToolAnnotations = FakeAnnotations
    server = types.ModuleType("mcp.server")
    server.fastmcp = fastmcp
    root = types.ModuleType("mcp")
    root.server = server
    fastmcp.exceptions = exceptions
    for name, module in {
        "mcp": root,
        "mcp.server": server,
        "mcp.server.fastmcp": fastmcp,
        "mcp.server.fastmcp.exceptions": exceptions,
        "mcp.types": types_module,
    }.items():
        monkeypatch.setitem(sys.modules, name, module)


def test_build_mcp_registers_exactly_two_read_only_tools(monkeypatch):
    """R1, R2, R5: dos herramientas, `readOnlyHint` y sin identidad en el esquema."""
    registered: list[tuple] = []
    _install_fake_sdk(monkeypatch, registered)
    deps = McpDeps(
        rag=FakeRagSearch(), offers=FakeDemoOffers(), audit=FakeAuditSink()
    )

    mcp = build_mcp(deps)

    assert mcp.name == "mcp_lectura"
    assert [item[0] for item in registered] == ["buscar_manuales", "ofertas_demo"]
    for name, description, annotations, function in registered:
        assert description
        assert annotations.kwargs == {"readOnlyHint": True}
        assert set(inspect.signature(function).parameters).isdisjoint(
            FORBIDDEN_INPUT_FIELDS
        )
