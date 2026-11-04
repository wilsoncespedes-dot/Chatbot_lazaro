"""Aplicación FastAPI del servicio telegram_gateway: token de servicio, errores y /health."""
from __future__ import annotations

import hmac
import json
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone

import httpx
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, PlainTextResponse
from lazaro_contracts import (
    SERVICE_TOKEN_HEADER,
    ChannelSendRequest,
    ErrorResponse,
    HealthResponse,
    SendRequest,
    SendResponse,
    TextBlock,
)
from pydantic import BaseModel, ConfigDict, StrictInt, ValidationError
from starlette.concurrency import run_in_threadpool
from starlette.exceptions import HTTPException as StarletteHTTPException

from . import grouping
from .adapters.dedup import RedisDedupStore
from .adapters.message_buffer import RedisMessageBuffer
from .adapters.orchestrator import HttpOrchestratorClient
from .adapters.telegram import HttpTelegramClient, TelegramChannelAdapter
from .adapters.whatsapp_cloud import WhatsAppCloudAdapter, WhatsAppCloudConfig
from .adapters.whatsapp_window import RedisWhatsAppWindowStore
from .config import Settings
from .domain import (
    Adapters,
    ChannelNotConfigured,
    ChannelSendFailed,
    DomainError,
    OrchestratorError,
    TelegramError,
    WebhookForbidden,
    build_message_request,
    extract_callback,
    extract_incoming,
    normalize_callback,
    normalize_incoming,
    send_response,
)
from .grouping import GroupingWorker
from .whatsapp_cloud import (
    SIGNATURE_HEADER,
    parse_webhook,
    to_delivery_status,
    verify_signature,
    verify_subscription,
)

logger = logging.getLogger(__name__)

SERVICE_NAME = "telegram_gateway"
WEBHOOK_PATH = "/telegram/webhook"
WHATSAPP_WEBHOOK_PATH = "/whatsapp/webhook"
WEBHOOK_SECRET_HEADER = "X-Telegram-Bot-Api-Secret-Token"
# Los webhooks no usan X-Service-Token: se protegen con su propio secreto/firma.
PUBLIC_PATHS: frozenset[str] = frozenset(
    {"/health", WEBHOOK_PATH, WHATSAPP_WEBHOOK_PATH}
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class TelegramUpdate(BaseModel):
    model_config = ConfigDict(extra="allow")

    update_id: StrictInt


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
        telegram=HttpTelegramClient(settings.telegram_bot_token, settings.http_timeout_seconds),
        dedup=RedisDedupStore(settings.redis_url),
        orchestrator=HttpOrchestratorClient(
            settings.orchestrator_url, settings.service_token, settings.http_timeout_seconds
        ),
        buffer=buffer,
        whatsapp=whatsapp,
        whatsapp_window=whatsapp_window,
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
        raw = update.model_dump()
        callback = extract_callback(raw)
        if callback is not None:
            try:
                normalized_button = normalize_callback(
                    callback, adapters.clock()
                )
            except ValidationError:
                logger.error(
                    "callback_invalido update_id=%s", callback.update_id
                )
                return {"ok": True}
            try:
                is_new = adapters.dedup.mark_message_if_new(
                    "telegram",
                    callback.callback_id,
                    settings.dedup_ttl_seconds,
                )
            except Exception as exc:
                logger.error(
                    "Fallo de Redis al deduplicar callback id=%s (%s); se trata como nuevo",
                    callback.callback_id,
                    type(exc).__name__,
                )
                is_new = True
            if not is_new:
                return {"ok": True}
            try:
                adapters.orchestrator.post_message(normalized_button)
            except (OrchestratorError, ValidationError) as exc:
                logger.error(
                    "Fallo al reenviar botón callback id=%s (%s): %s",
                    callback.callback_id,
                    type(exc).__name__,
                    exc if isinstance(exc, OrchestratorError) else "botón no válido",
                )
            return {"ok": True}
        incoming = extract_incoming(raw)
        if incoming is None:
            return {"ok": True}
        try:
            normalized = normalize_incoming(incoming, adapters.clock())
        except ValidationError:
            # Un update fuera de contrato (p. ej. texto de más de 4096) conserva
            # la rama legacy: se deduplica y el flujo lo descarta sin reenviarlo.
            channel = "telegram"
            external_message_id = str(incoming.update_id)
        else:
            channel = normalized.channel
            external_message_id = normalized.external_message_id
        try:
            is_new = adapters.dedup.mark_message_if_new(
                channel,
                external_message_id,
                settings.dedup_ttl_seconds,
            )
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
    async def whatsapp_webhook(request: Request):
        if not settings.whatsapp_enabled:
            raise StarletteHTTPException(status_code=404, detail="not_found")
        body = await request.body()
        if not verify_signature(
            settings.whatsapp_app_secret.get_secret_value(),
            body,
            request.headers.get(SIGNATURE_HEADER),
        ):
            return _error(
                401, "unauthorized", "Firma del webhook ausente o no válida."
            )
        try:
            payload = json.loads(body)
        except (json.JSONDecodeError, UnicodeDecodeError):
            payload = None
        if not isinstance(payload, dict) or payload.get("object") != "whatsapp_business_account":
            return {"ok": True}

        def process() -> None:
            received_at = adapters.clock()
            parsed = parse_webhook(
                payload, settings.whatsapp_phone_number_id, received_at
            )
            if adapters.whatsapp_window is not None:
                for wa_id in parsed.inbound_wa_ids:
                    try:
                        adapters.whatsapp_window.record_inbound(wa_id, received_at)
                    except Exception as exc:  # noqa: BLE001 - R27 no debe romper el lote
                        logger.warning(
                            "No se pudo registrar la ventana de WhatsApp (%s)",
                            type(exc).__name__,
                        )
            for message in parsed.messages:
                try:
                    is_new = adapters.dedup.mark_message_if_new(
                        "whatsapp",
                        message.external_message_id,
                        settings.dedup_ttl_seconds,
                    )
                except Exception as exc:  # noqa: BLE001 - R25 se trata como nuevo
                    logger.error(
                        "Fallo de Redis al deduplicar WhatsApp wamid=%s (%s); se trata como nuevo",
                        message.external_message_id,
                        type(exc).__name__,
                    )
                    is_new = True
                if not is_new:
                    continue
                try:
                    adapters.orchestrator.post_message(message)
                except (OrchestratorError, ValidationError) as exc:
                    logger.error(
                        "Fallo al reenviar WhatsApp wamid=%s (%s): %s",
                        message.external_message_id,
                        type(exc).__name__,
                        exc
                        if isinstance(exc, OrchestratorError)
                        else "mensaje no válido",
                    )
            for status in parsed.statuses:
                logger.info(
                    "whatsapp_status wamid=%s status=%s codes=%s",
                    status.wamid,
                    to_delivery_status(status.status),
                    list(status.error_codes),
                )

        try:
            await run_in_threadpool(process)
        except Exception:  # noqa: BLE001 - Meta no debe reintentar en bucle
            logger.exception("Fallo procesando el webhook de WhatsApp")
        return {"ok": True}

    @app.post("/send", response_model=SendResponse)
    def send(body: SendRequest | ChannelSendRequest) -> SendResponse:
        if isinstance(body, SendRequest):
            status = send_response(
                TelegramChannelAdapter(adapters.telegram),
                str(body.chat_id),
                [TextBlock(type="text", text=body.text)],
            )
            if status == "failed":
                raise ChannelSendFailed("El canal informó que el envío falló.")
            return SendResponse(sent=True)
        if body.channel == "whatsapp":
            adapter = adapters.whatsapp
        else:
            adapter = TelegramChannelAdapter(adapters.telegram)
        if adapter is None:
            raise ChannelNotConfigured(
                "El canal WhatsApp no está configurado en este servicio."
            )
        status = send_response(adapter, body.destination, body.blocks)
        if status == "failed":
            raise ChannelSendFailed("El canal informó que el envío falló.")
        return SendResponse(sent=True)

    return app


app = create_app()
