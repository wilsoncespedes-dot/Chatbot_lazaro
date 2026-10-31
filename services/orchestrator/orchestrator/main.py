"""Aplicación FastAPI del servicio orchestrator: mensajes, respuestas de asesores y /health."""
from __future__ import annotations

import hmac
import logging
import uuid
from datetime import datetime, timezone

from fastapi import BackgroundTasks, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from lazaro_contracts import (
    SERVICE_TOKEN_HEADER,
    CaseReplyRequest,
    CaseReplyResponse,
    ErrorResponse,
    HealthResponse,
    MessageRequest,
    MessageResponse,
)
from starlette.exceptions import HTTPException as StarletteHTTPException

from .adapters.gateway import HttpGatewayClient
from .adapters.handover import HttpHandoverClient
from .adapters.llm import HttpLLMClient
from .adapters.rag import HttpRagClient
from .adapters.repository import PostgresRepository
from .config import Settings
from .domain import Adapters, DomainError, process_message, reply_to_case

logger = logging.getLogger(__name__)

SERVICE_NAME = "orchestrator"
PUBLIC_PATHS: frozenset[str] = frozenset({"/health"})


def _error(status_code: int, error: str, message: str) -> JSONResponse:
    body = ErrorResponse(error=error, message=message).model_dump()
    return JSONResponse(status_code=status_code, content=body)


def build_default_adapters(settings: Settings) -> Adapters:
    """Adaptadores reales; ninguno abre conexiones hasta su primer uso."""
    timeout = settings.http_timeout_seconds
    return Adapters(
        repository=PostgresRepository(settings.database_url),
        rag=HttpRagClient(settings.rag_url, settings.service_token, timeout),
        llm=HttpLLMClient(
            settings.llm_base_url, settings.llm_api_key, settings.llm_model, timeout
        ),
        gateway=HttpGatewayClient(settings.telegram_gateway_url, settings.service_token, timeout),
        handover=HttpHandoverClient(settings.handover_url, settings.service_token, timeout),
        clock=lambda: datetime.now(timezone.utc),
        new_id=lambda: uuid.uuid4().hex,
    )


def create_app(settings: Settings | None = None, adapters: Adapters | None = None) -> FastAPI:
    settings = settings or Settings()
    adapters = adapters or build_default_adapters(settings)
    app = FastAPI(title=SERVICE_NAME)

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

    def _process(message: MessageRequest) -> None:
        try:
            process_message(message, settings, adapters)
        except Exception as exc:
            logger.error(
                "process_message_failed update_id=%s code=%s",
                message.update_id,
                type(exc).__name__,
            )

    @app.post("/messages", status_code=202, response_model=MessageResponse)
    def post_message(body: MessageRequest, background: BackgroundTasks) -> MessageResponse:
        if not adapters.repository.mark_update_if_new(body.update_id):
            return MessageResponse(status="duplicate")
        background.add_task(_process, body)
        return MessageResponse(status="accepted")

    @app.post("/cases/{case_id}/reply", response_model=CaseReplyResponse)
    def post_case_reply(case_id: str, body: CaseReplyRequest) -> CaseReplyResponse:
        return reply_to_case(case_id, body, settings, adapters)

    return app


app = create_app()
