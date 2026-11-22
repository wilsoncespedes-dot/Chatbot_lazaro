"""Aplicación FastAPI del servicio orchestrator: mensajes, respuestas de asesores y /health."""
from __future__ import annotations

import hmac
import logging
import re
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Literal

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from lazaro_contracts import (
    SERVICE_TOKEN_HEADER,
    CaseReplyRequest,
    CaseReplyResponse,
    ErrorResponse,
    ExpiryNoticeRunRequest,
    ExpiryNoticeRunResponse,
    HealthResponse,
    MessageRequest,
    MessageResponse,
    NormalizedMessage,
    PrivacyPurgeRequest,
    PrivacyPurgeResponse,
    normalize_legacy_message,
)
from pydantic import AwareDatetime, BaseModel, ConfigDict, field_validator
from starlette.concurrency import run_in_threadpool
from starlette.exceptions import HTTPException as StarletteHTTPException

from . import admin, advisor_panel
from .accounts import USERNAME_PATTERN
from .adapters.client_data import PostgresClientDataQuery, UnavailableClientData
from .adapters.db_query import PostgresReadOnlyQuery, UnavailableDbQuery
from .adapters.gateway import HttpGatewayClient
from .adapters.handover import HttpHandoverClient
from .adapters.llm import HttpLLMClient
from .adapters.rag import HttpRagClient
from .adapters.repository import PostgresRepository
from .adapters.simulator import HttpSimulatorClient
from .adapters.channels import HttpChannelDirectory
from .admin_routes import CsrfInvalid, LoginRequired, create_admin_router
from .advisor_routes import AdvisorAccessDenied, create_advisor_router
from .config import Settings
from .envios_routes import create_envios_router
from .domain import (
    Adapters,
    DedupKey,
    DomainError,
    InboundEntry,
    ServiceUnavailable,
    UpstreamError,
    _has_current_consent,
    close_client_session,
    consent_button_pending,
    consent_configured,
    consent_text_pending,
    conversation_key,
    conversation_texts,
    create_client,
    create_profile,
    get_client_status,
    issue_link_token,
    process_channel_message,
    process_message,
    publish_advisor_roster,
    purge_personal_data,
    renew_credential,
    reply_to_case,
    revoke_credential,
    send_expiry_notices,
)
from .identity_routes import create_identity_router
from .legacy import LEGACY_CHANNEL, legacy_from_normalized
from .panel_live_routes import create_panel_live_router
from .simulator_routes import create_simulator_router

logger = logging.getLogger(__name__)

SERVICE_NAME = "orchestrator"
PUBLIC_PATHS: frozenset[str] = frozenset({"/health"})

Role = Literal["admin", "supervisor", "asesor", "responsable_datos", "cliente"]


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


class ClientCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: str
    password: str
    valid_from: AwareDatetime | None = None
    valid_until: AwareDatetime | None = None

    @field_validator("username")
    @classmethod
    def _normalize_username(cls, value: str) -> str:
        normalized = value.lower()
        if not USERNAME_PATTERN.fullmatch(normalized):
            raise ValueError("username inválido")
        return normalized


class ClientStatusResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    profile_id: str
    username: str
    status: str
    valid_from: datetime
    valid_until: datetime
    days_remaining: int
    has_active_session: bool


_TOKEN_QUERY_RE = re.compile(r"([?&]t=)[^&\s\"]+")


def _redact_access_text(value: object) -> object:
    if isinstance(value, str):
        return _TOKEN_QUERY_RE.sub(r"\1***", value)
    return value


class _AccessTokenRedactionFilter(logging.Filter):
    """R25: oculta el valor de `t=` en el log de acceso de uvicorn."""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.args, tuple):
            record.args = tuple(_redact_access_text(arg) for arg in record.args)
        elif isinstance(record.args, dict):
            record.args = {
                key: _redact_access_text(value)
                for key, value in record.args.items()
            }
        record.msg = _redact_access_text(record.msg)
        return True


def install_access_log_redaction() -> None:
    target = logging.getLogger("uvicorn.access")
    if any(isinstance(item, _AccessTokenRedactionFilter) for item in target.filters):
        return
    target.addFilter(_AccessTokenRedactionFilter())


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
    if settings.client_data_enabled:
        client_data = PostgresClientDataQuery(
            settings.client_data_database_url,
            settings.client_data_allowlist_map,
            settings.client_data_rls_setting,
        )
    else:
        client_data = UnavailableClientData()
    repository = PostgresRepository(
        settings.database_url,
        panel_events_retention_hours=settings.panel_events_retention_hours,
    )
    return Adapters(
        repository=repository,
        rag=HttpRagClient(settings.rag_url, settings.service_token, timeout),
        llm=HttpLLMClient(
            settings.llm_base_url,
            settings.llm_api_key,
            settings.llm_model,
            settings.llm_timeout_seconds,
            session_header=settings.llm_session_header,
        ),
        gateway=HttpGatewayClient(settings.telegram_gateway_url, settings.service_token, timeout),
        handover=HttpHandoverClient(
            settings.handover_url,
            settings.service_token,
            timeout,
            generation_provider=lambda: repository.get_advisor_roster_state()[0],
        ),
        db_query=db_query,
        client_data=client_data,
        simulator=HttpSimulatorClient(
            settings.telegram_gateway_url, settings.service_token, timeout
        ),
        channels=HttpChannelDirectory(
            settings.telegram_gateway_url,
            settings.service_token,
            settings.channel_directory_ttl_seconds,
            timeout,
        ),
        clock=lambda: datetime.now(timezone.utc),
        new_id=lambda: uuid.uuid4().hex,
    )


def create_app(settings: Settings | None = None, adapters: Adapters | None = None) -> FastAPI:
    settings = settings or Settings()
    adapters = adapters or build_default_adapters(settings)
    install_access_log_redaction()

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        await run_in_threadpool(publish_advisor_roster, adapters)
        yield

    app = FastAPI(title=SERVICE_NAME, lifespan=lifespan)

    @app.middleware("http")
    async def verify_service_token(request: Request, call_next):
        path = request.url.path
        if (
            path in PUBLIC_PATHS
            or path == "/acceso"
            or path == "/admin"
            or path.startswith("/admin/")
            or path == "/asesor"
            or path.startswith("/asesor/")
        ):
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
        is_advisor = (
            request.url.path == "/asesor"
            or request.url.path.startswith("/asesor/")
        )
        target = "/asesor/login" if is_advisor else "/admin/login"
        headers = (
            admin.panel_security_headers()
            if is_advisor
            else admin.security_headers()
        )
        return RedirectResponse(url=target, status_code=303, headers=headers)

    @app.exception_handler(AdvisorAccessDenied)
    async def handle_advisor_access_denied(
        request: Request, exc: AdvisorAccessDenied
    ):
        return HTMLResponse(
            content=advisor_panel.render_advisor_error(403, "forbidden"),
            status_code=403,
            headers=admin.panel_security_headers(),
        )

    @app.exception_handler(CsrfInvalid)
    async def handle_csrf_invalid(request: Request, exc: CsrfInvalid):
        if request.url.path == "/asesor" or request.url.path.startswith("/asesor/"):
            content = advisor_panel.render_advisor_error(403, "forbidden")
            headers = admin.panel_security_headers()
        else:
            content = admin.render_message("Acceso denegado", "Token CSRF inválido.")
            headers = admin.security_headers()
        return HTMLResponse(
            content=content,
            status_code=403,
            headers=headers,
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

    @app.get("/health", response_model=HealthResponse, response_model_exclude_none=True)
    async def health() -> HealthResponse | JSONResponse:
        try:
            await run_in_threadpool(
                adapters.repository.health_check,
                settings.healthcheck_timeout_seconds,
            )
        except Exception as exc:  # noqa: BLE001 - cualquier fallo es unhealthy
            logger.warning(
                "healthcheck_postgres_unavailable code=%s", type(exc).__name__
            )
            return JSONResponse(
                status_code=503,
                content=HealthResponse(
                    status="unhealthy",
                    service=SERVICE_NAME,
                    dependencies={"postgres": "unavailable"},
                ).model_dump(exclude_none=True),
            )
        return HealthResponse(status="ok", service=SERVICE_NAME)

    # Registrar las rutas del panel una a una: con la versión instalada,
    # `include_router` las deja dentro de un objeto sin `path` en `app.routes`.
    app.router.routes.extend(create_admin_router(settings, adapters).routes)
    app.router.routes.extend(create_advisor_router(settings, adapters).routes)
    app.router.routes.extend(create_panel_live_router(settings, adapters).routes)
    app.router.routes.extend(create_simulator_router(settings, adapters).routes)
    app.router.routes.extend(create_identity_router(settings, adapters).routes)
    app.router.routes.extend(create_envios_router(settings, adapters).routes)

    def _mark_dedup(dedup: DedupKey) -> bool:
        if dedup.kind == "update":
            return adapters.repository.mark_update_if_new(dedup.update_id)
        return adapters.repository.mark_message_if_new(
            dedup.channel, dedup.external_message_id
        )

    def _text_pending(message: NormalizedMessage) -> bool:
        # #65 R18: sin directorio de canales se falla cerrado con upstream_error
        # y el mensaje no se encola (el gateway reintenta).
        try:
            return consent_text_pending(message, settings, adapters)
        except ServiceUnavailable:
            logger.error("channel_directory_unavailable")
            raise UpstreamError("No se pudo consultar el directorio de canales.") from None

    @app.post("/messages", status_code=202, response_model=MessageResponse)
    def post_message(body: MessageRequest | NormalizedMessage):
        # #65 R28-R30: cualquier canal válido; solo se rechaza lo no entrante.
        if isinstance(body, NormalizedMessage) and body.direction != "inbound":
            raise RequestValidationError([])
        if isinstance(body, NormalizedMessage):
            normalized = body
            try:
                legacy = legacy_from_normalized(body)
            except (TypeError, ValueError):
                # Los ids canónicos son texto: si no se pueden representar en el
                # flujo histórico de Telegram, se procesa con identidad de canal
                # sin convertirlos ni inventar un `update_id`.
                legacy = None
            direct = (
                (lambda: process_message(legacy, settings, adapters))
                if legacy is not None
                else (lambda: process_channel_message(body, settings, adapters))
            )
            # R4/R5: el botón de consentimiento se procesa en la petición HTTP
            # para que un fallo al guardar la evidencia responda 500 (R18 de #35).
            # R7: sin consentimiento vigente no se persiste la clave del mensaje;
            # el gateway ya deduplica con TTL. Tras consentir, la clave compuesta
            # vuelve a ser la barrera persistente.
            consent_ready = (
                consent_configured(settings, adapters)
                and adapters.repository.has_channel_privacy_consent(
                    normalized.channel,
                    normalized.external_user_id,
                    conversation_texts(settings, adapters).notice_version,
                )
            )
            # R46 R16, #65 R24: la frase de un canal en modo `texto` se procesa igual.
            pending = consent_button_pending(body) or (
                not consent_ready and _text_pending(body)
            )
            dedup = (
                DedupKey(
                    kind="message",
                    channel=normalized.channel,
                    external_message_id=normalized.external_message_id,
                )
                if consent_ready
                else None
            )
            entry = InboundEntry(
                conversation_key=conversation_key(
                    normalized.channel, normalized.external_user_id
                ),
                channel=normalized.channel,
                external_user_id=normalized.external_user_id,
                payload_kind="channel",
                payload=body.model_dump(mode="json"),
            )
        else:
            legacy = body
            normalized = normalize_legacy_message(body)
            direct = lambda: process_message(legacy, settings, adapters)
            pending = (
                not _has_current_consent(
                    LEGACY_CHANNEL,
                    str(legacy.telegram_user_id),
                    settings,
                    adapters,
                )
                and _text_pending(normalized)
            )
            # R22: la excepción aprobada de #35 conserva únicamente el
            # `update_id` en `processed_updates`, sin identidad ni payload.
            dedup = DedupKey(kind="update", update_id=legacy.update_id)
            entry = InboundEntry(
                conversation_key=conversation_key(
                    LEGACY_CHANNEL, str(legacy.telegram_user_id)
                ),
                channel=LEGACY_CHANNEL,
                external_user_id=str(legacy.telegram_user_id),
                payload_kind="legacy",
                payload=body.model_dump(mode="json"),
            )
        if pending:
            # R6: la aceptación de consentimiento se procesa en la petición.
            if dedup is not None and not _mark_dedup(dedup):
                return MessageResponse(status="duplicate")
            direct()
            return MessageResponse(status="accepted")
        try:
            inserted = adapters.repository.enqueue_inbound(entry, dedup)
        except Exception as exc:  # noqa: BLE001 - R5: revierte dedup + INSERT
            logger.error("inbox_enqueue_failed code=%s", type(exc).__name__)
            return _error(500, "internal_error", "Error interno.")
        if not inserted:
            return MessageResponse(status="duplicate")
        return MessageResponse(status="accepted")

    @app.post("/privacy/purge", response_model=PrivacyPurgeResponse)
    def post_privacy_purge(body: PrivacyPurgeRequest) -> PrivacyPurgeResponse:
        return purge_personal_data(settings, adapters)

    @app.post(
        "/credentials/expiry-notices",
        response_model=ExpiryNoticeRunResponse,
    )
    def post_expiry_notices(
        body: ExpiryNoticeRunRequest,
    ) -> ExpiryNoticeRunResponse:
        return send_expiry_notices(settings, adapters)

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

    def _client_status_response(status) -> ClientStatusResponse:
        return ClientStatusResponse(
            profile_id=status.profile_id,
            username=status.username,
            status=status.status,
            valid_from=status.valid_from,
            valid_until=status.valid_until,
            days_remaining=status.days_remaining,
            has_active_session=status.has_active_session,
        )

    @app.post("/clients", status_code=201, response_model=ClientStatusResponse)
    def post_client(body: ClientCreateRequest) -> ClientStatusResponse:
        if len(body.password) < settings.profile_password_min_length:
            raise RequestValidationError([])
        return _client_status_response(
            create_client(
                body.username,
                body.password,
                body.valid_from,
                body.valid_until,
                settings,
                adapters,
            )
        )

    @app.get("/clients/{profile_id}", response_model=ClientStatusResponse)
    def get_client(profile_id: str) -> ClientStatusResponse:
        return _client_status_response(
            get_client_status(profile_id, settings, adapters)
        )

    @app.post("/clients/{profile_id}/renew", response_model=ClientStatusResponse)
    def post_client_renew(profile_id: str) -> ClientStatusResponse:
        return _client_status_response(
            renew_credential(profile_id, settings, adapters)
        )

    @app.post("/clients/{profile_id}/revoke", response_model=ClientStatusResponse)
    def post_client_revoke(profile_id: str) -> ClientStatusResponse:
        return _client_status_response(
            revoke_credential(profile_id, settings, adapters)
        )

    @app.post(
        "/clients/{profile_id}/close-session",
        response_model=ClientStatusResponse,
    )
    def post_client_close_session(profile_id: str) -> ClientStatusResponse:
        return _client_status_response(
            close_client_session(profile_id, settings, adapters)
        )

    return app


app = create_app()
