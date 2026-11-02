"""Aplicación FastAPI del servicio telegram_gateway: token de servicio, errores y /health."""
from __future__ import annotations

import hmac
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from lazaro_contracts import (
    SERVICE_TOKEN_HEADER,
    ErrorResponse,
    HealthResponse,
    SendRequest,
    SendResponse,
)
from pydantic import BaseModel, ConfigDict, StrictInt, ValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from . import grouping
from .adapters.dedup import RedisDedupStore
from .adapters.message_buffer import RedisMessageBuffer
from .adapters.orchestrator import HttpOrchestratorClient
from .adapters.telegram import HttpTelegramClient
from .config import Settings
from .domain import (
    Adapters,
    DomainError,
    OrchestratorError,
    TelegramError,
    build_message_request,
    extract_incoming,
)
from .grouping import GroupingWorker

logger = logging.getLogger(__name__)

SERVICE_NAME = "telegram_gateway"
WEBHOOK_PATH = "/telegram/webhook"
WEBHOOK_SECRET_HEADER = "X-Telegram-Bot-Api-Secret-Token"
# El webhook no usa X-Service-Token: se protege con su propio secreto.
PUBLIC_PATHS: frozenset[str] = frozenset({"/health", WEBHOOK_PATH})


class TelegramUpdate(BaseModel):
    model_config = ConfigDict(extra="allow")

    update_id: StrictInt


def build_default_adapters(settings: Settings) -> Adapters:
    buffer = (
        RedisMessageBuffer(settings.redis_url)
        if settings.message_grouping_enabled
        else None
    )
    return Adapters(
        telegram=HttpTelegramClient(settings.telegram_bot_token, settings.http_timeout_seconds),
        dedup=RedisDedupStore(settings.redis_url),
        orchestrator=HttpOrchestratorClient(
            settings.orchestrator_url, settings.service_token, settings.http_timeout_seconds
        ),
        buffer=buffer,
    )


def _error(status_code: int, error: str, message: str) -> JSONResponse:
    body = ErrorResponse(error=error, message=message).model_dump()
    return JSONResponse(status_code=status_code, content=body)


def create_app(settings: Settings | None = None, adapters: Adapters | None = None) -> FastAPI:
    settings = settings or Settings()
    adapters = adapters or build_default_adapters(settings)
    grouping_worker: GroupingWorker | None = None

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        nonlocal grouping_worker
        if settings.message_grouping_enabled and adapters.buffer is not None:
            grouping_worker = GroupingWorker(settings, adapters)
            grouping_worker.start()
        try:
            yield
        finally:
            if grouping_worker is not None:
                grouping_worker.stop()
                grouping_worker = None

    app = FastAPI(title=SERVICE_NAME, lifespan=lifespan)

    @app.middleware("http")
    async def verify_service_token(request: Request, call_next):
        if request.url.path == WEBHOOK_PATH:
            secret = request.headers.get(WEBHOOK_SECRET_HEADER)
            expected_secret = settings.telegram_webhook_secret
            if (
                expected_secret == ""
                or secret is None
                or not hmac.compare_digest(secret.encode(), expected_secret.encode())
            ):
                return _error(401, "unauthorized", "Secreto del webhook ausente o no válido.")
            return await call_next(request)
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

    @app.post(WEBHOOK_PATH)
    def webhook(update: TelegramUpdate) -> dict:
        incoming = extract_incoming(update.model_dump())
        if incoming is None:
            return {"ok": True}
        try:
            is_new = adapters.dedup.mark_if_new(incoming.update_id, settings.dedup_ttl_seconds)
        except Exception as exc:
            logger.error(
                "Fallo de Redis al deduplicar update_id=%s (%s); se trata como nuevo",
                incoming.update_id,
                type(exc).__name__,
            )
            is_new = True
        if not is_new:
            return {"ok": True}
        if incoming.text is None:
            try:
                adapters.telegram.send_message(incoming.chat_id, settings.non_text_reply)
            except TelegramError as exc:
                logger.error(
                    "No se pudo enviar NON_TEXT_REPLY (update_id=%s): %s", incoming.update_id, exc
                )
            return {"ok": True}
        if settings.message_grouping_enabled and adapters.buffer is not None:
            grouping.enqueue_text(incoming, settings, adapters)
            return {"ok": True}
        try:
            message = build_message_request(incoming, adapters.clock())
            adapters.orchestrator.post_message(message)
        except (OrchestratorError, ValidationError) as exc:
            logger.error(
                "Fallo al reenviar al orquestador update_id=%s (%s): %s",
                incoming.update_id,
                type(exc).__name__,
                exc if isinstance(exc, OrchestratorError) else "mensaje no válido",
            )
        return {"ok": True}

    @app.post("/send", response_model=SendResponse)
    def send(body: SendRequest) -> SendResponse:
        adapters.telegram.send_message(body.chat_id, body.text)
        return SendResponse(sent=True)

    return app


app = create_app()
