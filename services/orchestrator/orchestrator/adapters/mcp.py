"""Cliente MCP del orquestador: SDK oficial, sesión corta y fakes de prueba."""
from __future__ import annotations

import asyncio
import concurrent.futures
import json
import logging
from typing import Any, Callable, Mapping, Protocol

from lazaro_contracts import SERVICE_TOKEN_HEADER
from pydantic import BaseModel, Field

from ..domain import ServiceUnavailable

logger = logging.getLogger(__name__)

CLIENTE_ID_HEADER = "X-Cliente-Id"


class McpToolSpec(BaseModel):
    name: str
    description: str = ""
    input_schema: dict[str, Any] = Field(default_factory=dict)


class McpCallResult(BaseModel):
    rows: list[dict[str, Any]] = Field(default_factory=list)
    demo: bool = False


class McpUnavailable(ServiceUnavailable):
    """Interna: el servidor MCP no respondió o devolvió un error de protocolo."""


class McpClient(Protocol):
    def list_tools(self) -> list[McpToolSpec]: ...

    def call_tool(
        self, name: str, args: Mapping[str, object], cliente_id: str
    ) -> McpCallResult: ...


def _rows_from_result(result: Any) -> list[dict[str, Any]]:
    structured = getattr(result, "structuredContent", None)
    candidates: list[Any] = []
    if isinstance(structured, dict):
        if isinstance(structured.get("rows"), list):
            return [row for row in structured["rows"] if isinstance(row, dict)]
        if isinstance(structured.get("result"), list):
            return [row for row in structured["result"] if isinstance(row, dict)]
        candidates.append(structured)
    elif isinstance(structured, list):
        candidates.append({"rows": structured})
    for item in getattr(result, "content", None) or []:
        text = getattr(item, "text", None)
        if not isinstance(text, str):
            continue
        try:
            data = json.loads(text)
        except ValueError:
            continue
        if isinstance(data, list):
            return [row for row in data if isinstance(row, dict)]
        if isinstance(data, dict):
            if isinstance(data.get("rows"), list):
                return [row for row in data["rows"] if isinstance(row, dict)]
            if isinstance(data.get("result"), list):
                return [row for row in data["result"] if isinstance(row, dict)]
            candidates.append(data)
    for candidate in candidates:
        if isinstance(candidate, dict):
            return [candidate]
    return []


class HttpMcpClient:
    """Una sesión corta por operación; headers de servicio y de sesión."""

    def __init__(
        self,
        url: str,
        service_token: str,
        timeout: float = 10,
        cliente_header: str = CLIENTE_ID_HEADER,
    ) -> None:
        self._url = url
        self._service_token = service_token
        self._timeout = timeout
        self._cliente_header = cliente_header

    def _headers(self, cliente_id: str | None) -> dict[str, str]:
        headers = {SERVICE_TOKEN_HEADER: self._service_token}
        if cliente_id is not None:
            headers[self._cliente_header] = cliente_id
        return headers

    def _run(self, operation: str, factory: Callable[[], Any]) -> Any:
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return self._run_new_loop(operation, factory)
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            return executor.submit(
                self._run_new_loop, operation, factory
            ).result()

    def _run_new_loop(self, operation: str, factory: Callable[[], Any]) -> Any:
        try:
            return asyncio.run(factory())
        except McpUnavailable:
            raise
        except Exception as exc:  # noqa: BLE001 - todo fallo externo es indisponible
            logger.error(
                "mcp_client_error operation=%s code=%s",
                operation,
                type(exc).__name__,
            )
            raise McpUnavailable("Servidor MCP no disponible.") from None

    def list_tools(self) -> list[McpToolSpec]:
        return self._run("list_tools", self._list_tools_async)

    async def _list_tools_async(self) -> list[McpToolSpec]:
        from mcp import ClientSession
        from mcp.client.streamable_http import streamablehttp_client

        async with streamablehttp_client(
            self._url,
            headers=self._headers(None),
            timeout=self._timeout,
            sse_read_timeout=self._timeout,
        ) as streams:
            read_stream, write_stream = streams[0], streams[1]
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                result = await session.list_tools()
        return [
            McpToolSpec(
                name=tool.name,
                description=getattr(tool, "description", "") or "",
                input_schema=dict(
                    getattr(tool, "inputSchema", None)
                    or getattr(tool, "input_schema", None)
                    or {}
                ),
            )
            for tool in result.tools
        ]

    def call_tool(
        self, name: str, args: Mapping[str, object], cliente_id: str
    ) -> McpCallResult:
        return self._run(
            "call_tool",
            lambda: self._call_tool_async(name, dict(args), cliente_id),
        )

    async def _call_tool_async(
        self, name: str, args: dict[str, object], cliente_id: str
    ) -> McpCallResult:
        from mcp import ClientSession
        from mcp.client.streamable_http import streamablehttp_client

        async with streamablehttp_client(
            self._url,
            headers=self._headers(cliente_id),
            timeout=self._timeout,
            sse_read_timeout=self._timeout,
        ) as streams:
            read_stream, write_stream = streams[0], streams[1]
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                result = await session.call_tool(name, arguments=args)
        if getattr(result, "isError", False):
            raise McpUnavailable("La herramienta MCP devolvió un error.")
        rows = _rows_from_result(result)
        demo = any(bool(row.get("es_demo")) for row in rows)
        return McpCallResult(rows=rows, demo=demo)


_DEFAULT_SCHEMAS: dict[str, dict[str, Any]] = {
    "buscar_manuales": {
        "type": "object",
        "properties": {
            "consulta": {"type": "string"},
            "top_k": {"type": "integer"},
        },
        "required": ["consulta"],
    },
    "ofertas_demo": {
        "type": "object",
        "properties": {
            "destino": {"type": "string"},
            "desde": {"type": "string"},
            "hasta": {"type": "string"},
        },
        "required": ["destino"],
    },
}

DEFAULT_TOOL_SPECS: tuple[McpToolSpec, ...] = (
    McpToolSpec(
        name="buscar_manuales",
        description="Busca en los manuales de soporte.",
        input_schema=_DEFAULT_SCHEMAS["buscar_manuales"],
    ),
    McpToolSpec(
        name="ofertas_demo",
        description="Ofertas de DEMOSTRACIÓN.",
        input_schema=_DEFAULT_SCHEMAS["ofertas_demo"],
    ),
)


class FakeMcpClient:
    """Fake con herramientas y resultados en memoria; registra cada llamada."""

    def __init__(
        self,
        tools: list[McpToolSpec] | None = None,
        results: dict[str, McpCallResult | Exception | Callable[..., McpCallResult]]
        | None = None,
        fail: bool = False,
    ) -> None:
        self.tools = list(tools) if tools is not None else list(DEFAULT_TOOL_SPECS)
        self.results = dict(results or {})
        self.fail = fail
        self.list_calls = 0
        self.calls: list[tuple[str, dict[str, object], str]] = []

    def list_tools(self) -> list[McpToolSpec]:
        self.list_calls += 1
        if self.fail:
            raise McpUnavailable("Servidor MCP caído.")
        return list(self.tools)

    def call_tool(
        self, name: str, args: Mapping[str, object], cliente_id: str
    ) -> McpCallResult:
        self.calls.append((name, dict(args), cliente_id))
        if self.fail:
            raise McpUnavailable("Servidor MCP caído.")
        result = self.results.get(name, McpCallResult())
        if isinstance(result, Exception):
            raise result
        if callable(result):
            return result(name, dict(args), cliente_id)
        return result
