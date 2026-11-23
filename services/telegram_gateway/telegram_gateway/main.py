"""Aplicación FastAPI del servicio telegram_gateway: token de servicio, errores y /health."""
from __future__ import annotations

import hmac
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from functools import partial
from uuid import uuid4

import httpx
from lazaro_contracts.production import require_service_token
from fastapi import FastAPI, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, PlainTextResponse
from lazaro_contracts import (
    SERVICE_TOKEN_HEADER,
    ChannelActiveRequest,
    ChannelCreateRequest,
    ChannelCreateResponse,
    ChannelInfo,
    ChannelListResponse,
    ChannelSecretResponse,
    ChannelSendRequest,
    ChannelUpdateRequest,
    ErrorResponse,
    HealthResponse,
    MailboxResponse,
    MessageResponse,
    NormalizedMessage,
    SendRequest,
    SendResponse,
    SimulatedInboundRequest,
    SimulatedInboundResponse,
    TextBlock,
)
from starlette.concurrency import run_in_threadpool
from starlette.exceptions import HTTPException as StarletteHTTPException

from .adapters import channels as registered_channels
from .adapters.callback import FakeCallbackClient, HttpCallbackClient
from .adapters.channel_repository import (
    ChannelRepository,
    FakeChannelRepository,
    PostgresChannelRepository,
)
from .adapters.dedup import RedisDedupStore
from .adapters.inbound_retry import FakeInboundRetryStore, PostgresInboundRetryStore
from .adapters.mailbox import FakeMailboxRepository, PostgresMailboxRepository
from .adapters.message_buffer import RedisMessageBuffer
from .adapters.orchestrator import HttpOrchestratorClient
from .adapters.telegram import HttpTelegramClient
from .adapters.whatsapp_cloud import WhatsAppCloudAdapter, WhatsAppCloudConfig
from .adapters.whatsapp_window import RedisWhatsAppWindowStore
from .config import Settings
from .channel_service import ChannelService
from .domain import (
    Adapters,
    ChannelStoreUnavailable,
    ChannelSendFailed,
    DomainError,
    WebhookForbidden,
    send_through_channel,
)
from .grouping import GroupingWorker
from .inbound import InboundRetryWorker
from .registry import CHANNEL_REGISTRY, ChannelContext, ChannelRegistry
from .secret_cipher import SecretCipher
from .webhook_service import WebhookService
from .whatsapp_cloud import verify_subscription

logger = logging.getLogger(__name__)

SERVICE_NAME = "telegram_gateway"
LEGACY_SEND_CHANNEL = "telegram"
WEBHOOK_PATH = "/telegram/webhook"
WHATSAPP_WEBHOOK_PATH = "/whatsapp/webhook"
# Fase 2: las URLs históricas entran por el webhook común con estos canales.
TELEGRAM_CHANNEL_ID = "telegram"
WHATSAPP_CHANNEL_ID = "whatsapp"
# Los webhooks no usan X-Service-Token: se protegen con su propio secreto/firma.
PUBLIC_PATHS: frozenset[str] = frozenset(
    {"/health", WEBHOOK_PATH, WHATSAPP_WEBHOOK_PATH}
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def build_default_adapters(settings: Settings) -> Adapters:
    buffer = (
        RedisMessageBuffer(settings.redis_url)
        if settings.message_grouping_enabled
        else None
    )
    whatsapp: WhatsAppCloudAdapter | None = None
    whatsapp_window = None
    if settings.whatsapp_enabled:
        whatsapp_window = RedisWhatsAppWindowStore(
            settings.redis_url, settings.whatsapp_window_hours * 3600
        )
        whatsapp = WhatsAppCloudAdapter(
            WhatsAppCloudConfig(
                access_token=settings.whatsapp_access_token.get_secret_value(),
                phone_number_id=settings.whatsapp_phone_number_id,
                graph_base_url=settings.whatsapp_graph_base_url,
                api_version=settings.whatsapp_graph_api_version,
                template_language=settings.whatsapp_template_language,
                interactive_body_text=settings.whatsapp_interactive_body_text,
                window_hours=settings.whatsapp_window_hours,
            ),
            httpx.Client(timeout=settings.http_timeout_seconds),
            whatsapp_window,
            _utcnow,
        )
    return Adapters(
        telegram=HttpTelegramClient(
            settings.telegram_bot_token,
            settings.http_timeout_seconds,
            settings.telegram_answer_callback_timeout_seconds,
        ),
        dedup=RedisDedupStore(settings.redis_url),
        orchestrator=HttpOrchestratorClient(
            settings.orchestrator_url, settings.service_token, settings.http_timeout_seconds
        ),
        buffer=buffer,
        whatsapp=whatsapp,
        whatsapp_window=whatsapp_window,
        channels=PostgresChannelRepository(settings.database_url),
        callback=HttpCallbackClient(
            settings.http_timeout_seconds,
            settings.webhook_allow_private_callbacks,
        ),
        mailbox=PostgresMailboxRepository(
            settings.database_url,
            settings.simulated_mailbox_retention_seconds,
            settings.simulated_mailbox_max_entries,
        ),
        inbound_retry=PostgresInboundRetryStore(settings.database_url),
    )


def _error(status_code: int, error: str, message: str) -> JSONResponse:
    body = ErrorResponse(error=error, message=message).model_dump()
    return JSONResponse(status_code=status_code, content=body)


def create_app(settings: Settings | None = None, adapters: Adapters | None = None) -> FastAPI:
    settings = settings or Settings()
    adapters = adapters or build_default_adapters(settings)
    channel_repository: ChannelRepository = adapters.channels or FakeChannelRepository()
    channel_registry: ChannelRegistry = adapters.channel_registry or CHANNEL_REGISTRY
    adapters.channels = channel_repository
    adapters.channel_registry = channel_registry
    if adapters.callback is None:
        adapters.callback = FakeCallbackClient()
    if adapters.mailbox is None:
        adapters.mailbox = FakeMailboxRepository(
            settings.simulated_mailbox_retention_seconds,
            settings.simulated_mailbox_max_entries,
        )
    if adapters.inbound_retry is None:
        adapters.inbound_retry = FakeInboundRetryStore()
    channel_context = ChannelContext(settings=settings, adapters=adapters)
    cipher = SecretCipher(settings.channel_secrets_key.get_secret_value())
    channel_service = ChannelService(
        channel_repository, channel_registry, cipher, channel_context
    )
    webhook_service = WebhookService(channel_service, settings, adapters)
    if not cipher.available:
        logger.warning("channel_secrets_key_unavailable reason=%s", cipher.status)
    grouping_worker: GroupingWorker | None = None
    retry_worker: InboundRetryWorker | None = None

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        nonlocal grouping_worker, retry_worker
        require_service_token(settings.service_token)
        if settings.message_grouping_enabled and adapters.buffer is not None:
            grouping_worker = GroupingWorker(settings, adapters)
            grouping_worker.start()
        retry_worker = InboundRetryWorker(settings, adapters)
        retry_worker.start()
        try:
            channel_service.ensure_seeded()
        except ChannelStoreUnavailable as exc:
            logger.warning("channels_seed_deferred code=%s", type(exc).__name__)
        try:
            yield
        finally:
            if grouping_worker is not None:
                grouping_worker.stop()
                grouping_worker = None
            retry_worker.stop()
            retry_worker = None

    app = FastAPI(title=SERVICE_NAME, lifespan=lifespan)

    @app.middleware("http")
    async def verify_service_token(request: Request, call_next):
        # Los webhooks los autentica su adaptador dentro de WebhookService.
        if request.url.path in PUBLIC_PATHS:
            return await call_next(request)
        if request.url.path.startswith("/webhooks/"):
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

    @app.get("/health", response_model=HealthResponse, response_model_exclude_none=True)
    async def health() -> HealthResponse | JSONResponse:
        dependencies: dict[str, str] = {}
        try:
            healthy = await run_in_threadpool(
                adapters.dedup.ping, settings.healthcheck_timeout_seconds
            )
        except Exception as exc:  # noqa: BLE001 - cualquier fallo es unhealthy
            logger.warning(
                "healthcheck_redis_unavailable code=%s", type(exc).__name__
            )
            healthy = False
        if not healthy:
            dependencies["redis"] = "unavailable"
        try:
            await run_in_threadpool(
                channel_repository.health_check,
                settings.healthcheck_timeout_seconds,
            )
        except Exception as exc:  # noqa: BLE001 - toda falla es unhealthy
            logger.warning(
                "healthcheck_postgres_unavailable code=%s", type(exc).__name__
            )
            dependencies["postgres"] = "unavailable"
        if dependencies:
            return JSONResponse(
                status_code=503,
                content=HealthResponse(
                    status="unhealthy",
                    service=SERVICE_NAME,
                    dependencies=dependencies,
                ).model_dump(exclude_none=True),
            )
        return HealthResponse(status="ok", service=SERVICE_NAME)

    async def _receive(channel_id: str, request: Request, own_route: bool = False):
        body = await request.body()
        return await run_in_threadpool(
            partial(webhook_service.receive, own_route=own_route),
            channel_id,
            request.headers,
            body,
        )

    @app.post(WEBHOOK_PATH)
    async def telegram_webhook(request: Request) -> dict:
        """URL histórica de Telegram; entra por el webhook común (fase 2)."""
        await _receive(TELEGRAM_CHANNEL_ID, request, own_route=True)
        return {"ok": True}

    @app.get(WHATSAPP_WEBHOOK_PATH)
    def whatsapp_verify(request: Request):
        if not settings.whatsapp_enabled:
            raise StarletteHTTPException(status_code=404, detail="not_found")
        challenge = verify_subscription(
            request.query_params,
            settings.whatsapp_verify_token.get_secret_value(),
        )
        if challenge is None:
            raise WebhookForbidden("Verificación del webhook de WhatsApp rechazada.")
        return PlainTextResponse(
            challenge,
            media_type="text/plain",
            headers={"Content-Type": "text/plain"},
        )

    @app.post(WHATSAPP_WEBHOOK_PATH)
    async def whatsapp_webhook(request: Request) -> dict:
        """URL histórica de WhatsApp; entra por el webhook común (fase 2)."""
        await _receive(WHATSAPP_CHANNEL_ID, request, own_route=True)
        return {"ok": True}

    @app.post("/webhooks/{canal_id}", response_model=MessageResponse)
    async def generic_webhook(canal_id: str, request: Request) -> MessageResponse:
        result = await _receive(canal_id, request)
        return MessageResponse(status=result.status)

    @app.get("/channels", response_model=ChannelListResponse)
    def list_channels() -> ChannelListResponse:
        return channel_service.list_channels()

    @app.post("/channels", response_model=ChannelCreateResponse, status_code=201)
    def create_channel(body: ChannelCreateRequest) -> ChannelCreateResponse:
        return channel_service.create(body)

    @app.patch("/channels/{channel_id}", response_model=ChannelInfo)
    def update_channel(channel_id: str, body: ChannelUpdateRequest) -> ChannelInfo:
        return channel_service.update(channel_id, body)

    @app.patch("/channels/{channel_id}/active", response_model=ChannelInfo)
    def set_channel_active(
        channel_id: str, body: ChannelActiveRequest
    ) -> ChannelInfo:
        return channel_service.set_active(channel_id, body)

    @app.post("/channels/{channel_id}/secret", response_model=ChannelSecretResponse)
    def regenerate_channel_secret(channel_id: str) -> ChannelSecretResponse:
        return channel_service.regenerate_secret(channel_id)

    @app.get("/channels/{channel_id}/secret", response_model=ChannelSecretResponse)
    def reveal_channel_secret(channel_id: str) -> ChannelSecretResponse:
        return channel_service.reveal_secret(channel_id)

    @app.get("/channels/{channel_id}/mailbox", response_model=MailboxResponse)
    def read_channel_mailbox(
        channel_id: str,
        destination: str | None = None,
        after: int = Query(0, ge=0),
        limit: int = Query(100, ge=1, le=500),
    ) -> MailboxResponse:
        channel_service.mailbox_channel(channel_id)
        mailbox = adapters.mailbox
        if mailbox is None:
            raise ChannelStoreUnavailable("El buzón no está disponible.")
        try:
            entries = mailbox.list(
                channel_id, destination, after, limit, adapters.clock()
            )
        except Exception as exc:  # noqa: BLE001 - R19 responde 503 sin detalles
            logger.error(
                "mailbox_list_failed channel_id=%s code=%s",
                channel_id,
                type(exc).__name__,
            )
            raise ChannelStoreUnavailable("El buzón no está disponible.") from None
        return MailboxResponse(channel=channel_id, entries=entries)

    @app.post(
        "/channels/{channel_id}/simulate",
        response_model=SimulatedInboundResponse,
        response_model_exclude_none=True,
    )
    def simulate_channel(
        channel_id: str, body: SimulatedInboundRequest
    ) -> SimulatedInboundResponse:
        canal = channel_service.active_mailbox_channel(channel_id)
        message = NormalizedMessage(
            channel=channel_id,
            external_user_id=body.external_user_id,
            external_chat_id=body.external_user_id,
            external_message_id=f"sim-{uuid4().hex}",
            kind="text",
            text=body.text,
            received_at=adapters.clock(),
        )
        result = webhook_service.inject(channel_id, canal, message)
        return SimulatedInboundResponse(
            status=result.status,
            forwarded=result.forwarded,
            reason=result.reason,
        )

    @app.post("/send", response_model=SendResponse)
    def send(body: SendRequest | ChannelSendRequest) -> SendResponse:
        if isinstance(body, SendRequest):
            channel_id = LEGACY_SEND_CHANNEL
            destination = str(body.chat_id)
            blocks = [TextBlock(type="text", text=body.text)]
        else:
            channel_id = body.channel
            destination = body.destination
            blocks = body.blocks
        channel = channel_service.resolve(channel_id)
        status = send_through_channel(channel, destination, blocks)
        if status == "failed":
            raise ChannelSendFailed("El canal informó que el envío falló.")
        return SendResponse(sent=True)

    return app


app = create_app()
