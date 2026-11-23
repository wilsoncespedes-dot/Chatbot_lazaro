"""App ASGI del servidor MCP: token de servicio, `/health` y montaje del SDK."""
from __future__ import annotations

import hmac
import logging
from contextlib import asynccontextmanager
from typing import Any

from lazaro_contracts import SERVICE_TOKEN_HEADER
from lazaro_contracts.production import require_service_token
from starlette.applications import Starlette
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import Headers
from starlette.responses import JSONResponse
from starlette.routing import Route

from .adapters import (
    HttpRagSearch,
    PostgresAuditSink,
    PostgresDemoOffers,
    pg_connect,
)
from .config import Settings
from .schema import initialize as initialize_schema
from .server import McpDeps, reset_cliente_id, set_cliente_id

logger = logging.getLogger(__name__)

SERVICE_NAME = "mcp_lectura"


async def _health(_: Any) -> JSONResponse:
    return JSONResponse({"status": "ok", "service": SERVICE_NAME})


class ServiceTokenMiddleware:
    """R6: exige `X-Service-Token` en todo salvo `GET /health`."""

    def __init__(self, app: Any, settings: Settings) -> None:
        self.app = app
        self.settings = settings

    async def __call__(self, scope: dict, receive: Any, send: Any) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return
        if scope.get("path") == "/health":
            await self.app(scope, receive, send)
            return
        headers = Headers(scope=scope)
        token = headers.get(SERVICE_TOKEN_HEADER)
        expected = self.settings.service_token
        if (
            expected == ""
            or token is None
            or not hmac.compare_digest(token.encode(), expected.encode())
        ):
            response = JSONResponse(
                status_code=401,
                content={
                    "error": "unauthorized",
                    "message": "Falta X-Service-Token o no es válido.",
                },
            )
            await response(scope, receive, send)
            return
        context_token = set_cliente_id(headers.get("X-Cliente-Id", ""))
        try:
            await self.app(scope, receive, send)
        finally:
            reset_cliente_id(context_token)


def build_dependencies(settings: Settings) -> McpDeps:
    database_url = settings.effective_database_url
    initialize = None
    if database_url:
        initialize = lambda: initialize_schema(  # noqa: E731 - cierre mínimo
            lambda: pg_connect(database_url), settings.mcp_demo_seed
        )
    return McpDeps(
        rag=HttpRagSearch(
            settings.rag_url,
            settings.service_token,
            settings.http_timeout_seconds,
        ),
        offers=PostgresDemoOffers(database_url),
        audit=PostgresAuditSink(database_url),
        max_rows=settings.mcp_max_rows,
        initialize=initialize,
    )


def create_app(
    settings: Settings, deps: McpDeps, mcp_app: Starlette | None = None
) -> Starlette:
    """Starlette con el servidor MCP, `/health` y el middleware de token."""
    if mcp_app is None:
        from .server import build_mcp

        mcp_app = build_mcp(deps).streamable_http_app()

    mcp_app.router.routes.insert(0, Route("/health", _health, methods=["GET"]))
    mcp_app.add_middleware(ServiceTokenMiddleware, settings=settings)

    original_lifespan = mcp_app.router.lifespan_context

    @asynccontextmanager
    async def lifespan(app: Any):
        require_service_token(settings.service_token)
        if deps.initialize is not None:
            try:
                await run_in_threadpool(deps.initialize)
            except Exception:  # noqa: BLE001 - el arranque no se cae por el esquema
                logger.error("mcp_schema_init_failed")
        async with original_lifespan(app):
            yield

    mcp_app.router.lifespan_context = lifespan
    return mcp_app


class _LazyApp:
    """Construye la app real al primer evento; importar el módulo no exige el SDK."""

    def __init__(self) -> None:
        self._app: Starlette | None = None

    async def __call__(self, scope: dict, receive: Any, send: Any) -> None:
        if self._app is None:
            settings = Settings()
            self._app = create_app(settings, build_dependencies(settings))
        await self._app(scope, receive, send)


app = _LazyApp()
