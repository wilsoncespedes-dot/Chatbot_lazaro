"""Servidor MCP (SDK oficial) con dos herramientas de solo lectura."""
from __future__ import annotations

import logging
from contextvars import ContextVar, Token
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Any, Callable

from .tools import (
    TOOL_ANNOTATIONS,
    TOOL_SPECS,
    ToolFailure,
    buscar_manuales as _buscar_manuales,
    ofertas_demo as _ofertas_demo,
    run_audited,
)

logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class McpDeps:
    rag: Any
    offers: Any
    audit: Any
    max_rows: int = 20
    clock: Callable[[], datetime] = field(default_factory=lambda: _utcnow)
    initialize: Callable[[], None] | None = None


_CLIENTE_ID: ContextVar[str] = ContextVar("mcp_cliente_id", default="")


def set_cliente_id(value: str) -> Token:
    return _CLIENTE_ID.set(value or "")


def reset_cliente_id(token: Token) -> None:
    try:
        _CLIENTE_ID.reset(token)
    except ValueError:
        # Otra tarea del mismo contexto ya lo restauró; no hay nada que hacer.
        pass


def current_cliente_id() -> str:
    return _CLIENTE_ID.get()


def _parse_date(value: str | None) -> date | None:
    if value is None or not value.strip():
        return None
    return date.fromisoformat(value.strip())


def build_mcp(deps: McpDeps):
    """Registra exactamente las dos herramientas con `readOnlyHint=True`."""
    from mcp.server.fastmcp import FastMCP
    from mcp.server.fastmcp.exceptions import ToolError
    from mcp.types import ToolAnnotations

    mcp = FastMCP("mcp_lectura")
    annotations = ToolAnnotations(**dict(TOOL_ANNOTATIONS))
    descriptions = {spec.name: spec.description for spec in TOOL_SPECS}

    def _execute(
        name: str, arguments: dict[str, Any], action: Callable[[], Any]
    ) -> list[dict[str, Any]]:
        try:
            return run_audited(
                name,
                arguments,
                current_cliente_id(),
                deps.audit,
                action,
                deps.clock,
            )
        except ToolFailure as exc:
            logger.warning("mcp_tool_failed name=%s reason=%s", name, exc)
            raise ToolError("La herramienta no pudo completarse.") from None

    @mcp.tool(
        name="buscar_manuales",
        description=descriptions["buscar_manuales"],
        annotations=annotations,
    )
    def buscar_manuales(consulta: str, top_k: int = 5) -> list[dict[str, Any]]:
        arguments = {"consulta": consulta, "top_k": top_k}
        return _execute(
            "buscar_manuales",
            arguments,
            lambda: _buscar_manuales(consulta, deps.rag, top_k),
        )

    @mcp.tool(
        name="ofertas_demo",
        description=descriptions["ofertas_demo"],
        annotations=annotations,
    )
    def ofertas_demo(
        destino: str,
        desde: str | None = None,
        hasta: str | None = None,
    ) -> list[dict[str, Any]]:
        arguments: dict[str, Any] = {"destino": destino}
        if desde is not None:
            arguments["desde"] = desde
        if hasta is not None:
            arguments["hasta"] = hasta

        def action():
            start = _parse_date(desde) or deps.clock().date()
            end = _parse_date(hasta) or (start + timedelta(days=7))
            return _ofertas_demo(destino, start, end, deps.offers, deps.max_rows)

        return _execute("ofertas_demo", arguments, action)

    return mcp
