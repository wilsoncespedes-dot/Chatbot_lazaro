"""Aplicación FastAPI del servicio orchestrator: mensajes, respuestas de asesores y /health."""
from __future__ import annotations

import hmac
import logging
import uuid
from datetime import datetime, timezone
from typing import Literal

from fastapi import BackgroundTasks, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from lazaro_contracts import (
    SERVICE_TOKEN_HEADER,
    CaseReplyRequest,
    CaseReplyResponse,
    ErrorResponse,
    HealthResponse,
    MessageRequest,
    MessageResponse,
    PrivacyPurgeRequest,
    PrivacyPurgeResponse,
)
from pydantic import BaseModel, ConfigDict, field_validator
from starlette.exceptions import HTTPException as StarletteHTTPException

from . import admin
from .accounts import USERNAME_PATTERN
from .adapters.db_query import PostgresReadOnlyQuery, UnavailableDbQuery
from .adapters.gateway import HttpGatewayClient
from .adapters.handover import HttpHandoverClient
from .adapters.llm import HttpLLMClient
from .adapters.rag import HttpRagClient
from .adapters.repository import PostgresRepository
from .admin_routes import CsrfInvalid, LoginRequired, create_admin_router
from .config import Settings
from .domain import (
    Adapters,
    DomainError,
    create_profile,
    issue_link_token,
    privacy_acceptance_pending,
    process_message,
    purge_personal_data,
    reply_to_case,
)

logger = logging.getLogger(__name__)

SERVICE_NAME = "orchestrator"
PUBLIC_PATHS: frozenset[str] = frozenset({"/health"})

Role = Literal["admin", "asesor", "cliente"]


class ProfileCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: str
    role: Role
    password: str

    @field_validator("username")
    @classmethod
    def _normalize_username(cls, value: str) -> str:
        normalized = value.lower()
        if not USERNAME_PATTERN.fullmatch(normalized):
            raise ValueError("username inválido")
        return normalized


class ProfileResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    username: str
    role: Role
    linked: bool


class LinkTokenResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    token: str
    link: str | None
    expires_at: datetime


def _error(status_code: int, error: str, message: str) -> JSONResponse:
    body = ErrorResponse(error=error, message=message).model_dump()
    return JSONResponse(status_code=status_code, content=body)


def build_default_adapters(settings: Settings) -> Adapters:
    """Adaptadores reales; ninguno abre conexiones hasta su primer uso."""
    timeout = settings.http_timeout_seconds
    if settings.db_query_enabled:
        db_query = PostgresReadOnlyQuery(
            settings.db_query_database_url, settings.db_query_allowlist_map
        )
    else:
        db_query = UnavailableDbQuery()
    return Adapters(
        repository=PostgresRepository(settings.database_url),
        rag=HttpRagClient(settings.rag_url, settings.service_token, timeout),
        llm=HttpLLMClient(
            settings.llm_base_url, settings.llm_api_key, settings.llm_model, timeout
        ),
        gateway=HttpGatewayClient(settings.telegram_gateway_url, settings.service_token, timeout),
        handover=HttpHandoverClient(settings.handover_url, settings.service_token, timeout),
        db_query=db_query,
        clock=lambda: datetime.now(timezone.utc),
        new_id=lambda: uuid.uuid4().hex,
    )


def create_app(settings: Settings | None = None, adapters: Adapters | None = None) -> FastAPI:
    settings = settings or Settings()
    adapters = adapters or build_default_adapters(settings)
    app = FastAPI(title=SERVICE_NAME)

    @app.middleware("http")
    async def verify_service_token(request: Request, call_next):
        path = request.url.path
        if path in PUBLIC_PATHS or path == "/admin" or path.startswith("/admin/"):
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

    @app.exception_handler(LoginRequired)
    async def handle_login_required(request: Request, exc: LoginRequired):
        return RedirectResponse(
            url="/admin/login", status_code=303, headers=admin.security_headers()
        )

    @app.exception_handler(CsrfInvalid)
    async def handle_csrf_invalid(request: Request, exc: CsrfInvalid):
        return HTMLResponse(
            content=admin.render_message("Acceso denegado", "Token CSRF inválido."),
            status_code=403,
            headers=admin.security_headers(),
        )

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

    # Registrar las rutas del panel una a una: con la versión instalada,
    # `include_router` las deja dentro de un objeto sin `path` en `app.routes`.
    app.router.routes.extend(create_admin_router(settings, adapters).routes)

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
        if privacy_acceptance_pending(body, settings, adapters):
            process_message(body, settings, adapters)
        else:
            background.add_task(_process, body)
        return MessageResponse(status="accepted")

    @app.post("/privacy/purge", response_model=PrivacyPurgeResponse)
    def post_privacy_purge(body: PrivacyPurgeRequest) -> PrivacyPurgeResponse:
        return purge_personal_data(settings, adapters)

    @app.post("/cases/{case_id}/reply", response_model=CaseReplyResponse)
    def post_case_reply(case_id: str, body: CaseReplyRequest) -> CaseReplyResponse:
        return reply_to_case(case_id, body, settings, adapters)

    @app.post("/profiles", status_code=201, response_model=ProfileResponse)
    def post_profile(body: ProfileCreateRequest) -> ProfileResponse:
        if len(body.password) < settings.profile_password_min_length:
            raise RequestValidationError([])
        profile = create_profile(body.username, body.role, body.password, settings, adapters)
        return ProfileResponse(
            id=profile.id,
            username=profile.username,
            role=profile.role,
            linked=profile.telegram_user_id is not None,
        )

    @app.post(
        "/profiles/{profile_id}/link-token",
        status_code=201,
        response_model=LinkTokenResponse,
    )
    def post_profile_link_token(profile_id: str) -> LinkTokenResponse:
        issued = issue_link_token(profile_id, settings, adapters)
        link = None
        if settings.telegram_bot_username:
            link = (
                f"https://t.me/{settings.telegram_bot_username}?start={issued.token}"
            )
        return LinkTokenResponse(
            token=issued.token, link=link, expires_at=issued.expires_at
        )

    return app


app = create_app()
