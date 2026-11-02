"""Aplicación FastAPI del servicio handover: casos, avisos a asesores, cierre y vencimiento."""
from __future__ import annotations

import hmac
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Annotated

from fastapi import FastAPI, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from lazaro_contracts import (
    SERVICE_TOKEN_HEADER,
    CaseAssignRequest,
    CaseAssignResponse,
    CaseAuthorizeRequest,
    CaseAuthorizeResponse,
    CaseClientMessageRequest,
    CaseClientMessageResponse,
    CaseCloseRequest,
    CaseCloseResponse,
    CaseListQuery,
    CaseListResponse,
    CheckTimeoutsRequest,
    CheckTimeoutsResponse,
    ErrorResponse,
    HandoverRequest,
    HandoverResponse,
    HealthResponse,
    PrivacyPurgeRequest,
    PrivacyPurgeResponse,
)
from starlette.concurrency import run_in_threadpool
from starlette.exceptions import HTTPException as StarletteHTTPException

from .adapters.gateway import HttpGatewayClient
from .adapters.repository import PostgresCaseRepository
from .config import Settings
from .domain import (
    Adapters,
    DomainError,
    assign_case,
    authorize_case,
    check_timeouts,
    close_case,
    forward_client_message,
    list_advisor_cases,
    log_orphan_cases,
    open_case,
    purge_personal_data,
)

logger = logging.getLogger(__name__)

SERVICE_NAME = "handover"
PUBLIC_PATHS: frozenset[str] = frozenset({"/health"})
LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s %(message)s"


def configure_logging() -> None:
    """Hace visibles en stderr los registros INFO o superiores del paquete handover."""
    package_logger = logging.getLogger("handover")
    package_logger.setLevel(logging.INFO)
    if not package_logger.handlers and not logging.getLogger().handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter(LOG_FORMAT))
        package_logger.addHandler(handler)


def _error(status_code: int, error: str, message: str) -> JSONResponse:
    body = ErrorResponse(error=error, message=message).model_dump()
    return JSONResponse(status_code=status_code, content=body)


def build_default_adapters(settings: Settings) -> Adapters:
    """Adaptadores reales; ninguno abre conexiones hasta su primer uso."""
    return Adapters(
        repository=PostgresCaseRepository(settings.database_url),
        gateway=HttpGatewayClient(
            settings.telegram_gateway_url, settings.service_token, settings.http_timeout_seconds
        ),
        clock=lambda: datetime.now(timezone.utc),
    )


def create_app(settings: Settings | None = None, adapters: Adapters | None = None) -> FastAPI:
    settings = settings or Settings()
    advisor_count = len(settings.advisor_ids)
    logger.info("advisors_configured count=%d", advisor_count)
    if advisor_count == 0:
        logger.warning("no_advisors_configured")
    adapters = adapters or build_default_adapters(settings)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        await run_in_threadpool(log_orphan_cases, settings, adapters)
        yield

    app = FastAPI(title=SERVICE_NAME, lifespan=lifespan)

    @app.middleware("http")
    async def verify_service_token(request: Request, call_next):
        if request.url.path in PUBLIC_PATHS:
            return await call_next(request)
        token = request.headers.get(SERVICE_TOKEN_HEADER)
        expected = settings.service_token
        if (
            expected == ""
            or token is None
            or not hmac.compare_digest(token.encode(), expected.encode())
        ):
            return _error(401, "unauthorized", "Falta X-Service-Token o no es válido.")
        return await call_next(request)

    @app.exception_handler(DomainError)
    async def handle_domain_error(request: Request, exc: DomainError):
        return _error(exc.status_code, exc.code, str(exc) or exc.code)

    @app.exception_handler(StarletteHTTPException)
    async def handle_http_error(request: Request, exc: StarletteHTTPException):
        if exc.status_code == 404:
            code = "not_found"
        elif exc.status_code == 405:
            code = "method_not_allowed"
        else:
            code = "http_error"
        return _error(exc.status_code, code, str(exc.detail) or code)

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(request: Request, exc: RequestValidationError):
        return _error(422, "validation_error", "El cuerpo de la petición no es válido.")

    @app.exception_handler(Exception)
    async def handle_unexpected_error(request: Request, exc: Exception):
        logger.exception("Excepción no controlada")
        return _error(500, "internal_error", "Error interno.")

    @app.get("/health", response_model=HealthResponse)
    async def health() -> HealthResponse:
        return HealthResponse(status="ok", service=SERVICE_NAME)

    @app.get("/cases", response_model=CaseListResponse)
    def get_cases(query: Annotated[CaseListQuery, Query()]) -> CaseListResponse:
        return list_advisor_cases(query.advisor_id, settings, adapters)

    @app.post("/handover", response_model=HandoverResponse)
    def post_handover(body: HandoverRequest) -> HandoverResponse:
        return open_case(body, settings, adapters)

    @app.post("/cases/check-timeouts", response_model=CheckTimeoutsResponse)
    def post_check_timeouts(body: CheckTimeoutsRequest) -> CheckTimeoutsResponse:
        return check_timeouts(settings, adapters)

    @app.post("/cases/{case_id}/assign", response_model=CaseAssignResponse)
    def post_assign(case_id: str, body: CaseAssignRequest) -> CaseAssignResponse:
        return assign_case(case_id, body.advisor_id, settings, adapters)

    @app.post("/cases/{case_id}/close", response_model=CaseCloseResponse)
    def post_close(case_id: str, body: CaseCloseRequest) -> CaseCloseResponse:
        return close_case(case_id, body.advisor_id, settings, adapters)

    @app.post("/cases/{case_id}/authorize", response_model=CaseAuthorizeResponse)
    def post_authorize(case_id: str, body: CaseAuthorizeRequest) -> CaseAuthorizeResponse:
        return authorize_case(case_id, body, settings, adapters)

    @app.post("/cases/{case_id}/client-message", response_model=CaseClientMessageResponse)
    def post_client_message(
        case_id: str, body: CaseClientMessageRequest
    ) -> CaseClientMessageResponse:
        return forward_client_message(case_id, body, adapters)

    @app.post("/privacy/purge", response_model=PrivacyPurgeResponse)
    def post_privacy_purge(body: PrivacyPurgeRequest) -> PrivacyPurgeResponse:
        return purge_personal_data(settings, adapters)

    return app


configure_logging()
app = create_app()
