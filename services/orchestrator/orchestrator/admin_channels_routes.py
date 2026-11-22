"""Panel `/admin/canales`: alta, edición, activación y secretos de canales (#66).

Solo admin. Todo cambio pasa por el gateway (`ChannelAdminClient`); el
orquestador no guarda canales ni registra secretos o credenciales.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, Response
from lazaro_contracts import (
    CHANNEL_ICONS,
    ChannelCreateRequest,
    ChannelInfo,
    ChannelUpdateRequest,
)
from pydantic import ValidationError

from . import admin
from .adapters.channel_admin import ChannelAdminError, ChannelAdminUnavailable
from .admin_channels import ChannelFormError, channel_form, icon_glyph, webhook_url
from .admin_routes import (
    _actor,
    _audit,
    _form,
    _html,
    _require_csrf_audited,
    _require_session,
    _upstream_error,
)
from .config import Settings
from .domain import Adapters

logger = logging.getLogger(__name__)

ERROR_TEXT = {
    "channel_exists": "Ya existe un canal con ese id.",
    "channel_managed_by_environment": "El canal lo gestiona la configuración del entorno.",
    "channel_secrets_unavailable": "El gateway no puede cifrar o descifrar secretos.",
    "not_found": "El canal no existe.",
    "validation_error": "El gateway rechazó los datos del canal.",
}


def create_admin_channels_router(settings: Settings, adapters: Adapters) -> APIRouter:
    router = APIRouter()
    def client():
        return adapters.channel_admin

    def _page(
        session,
        status_code: int = 200,
        error: str | None = None,
        revealed: tuple[str, str] | None = None,
        revealed_title: str = "Secreto del canal",
    ) -> HTMLResponse:
        try:
            listing = client().list()
        except ChannelAdminUnavailable:
            return _upstream_error(session.csrf_token)
        return _html(
            admin.render_channels(
                listing,
                session.csrf_token,
                icons=CHANNEL_ICONS,
                glyph_for=icon_glyph,
                webhook_for=lambda channel_id: webhook_url(
                    settings.gateway_public_base_url, channel_id
                ),
                error=error,
                revealed=revealed,
                revealed_title=revealed_title,
            ),
            status_code=status_code,
        )

    def _gateway_error(session, actor, action: str, exc: ChannelAdminError, target: str):
        _audit(actor, action, exc.code, adapters, target=target)
        return _page(session, exc.status, ERROR_TEXT.get(exc.code, exc.code))

    def _changed() -> None:
        # R29: la próxima decisión del núcleo relee GET /channels.
        try:
            adapters.channels.invalidate()
        except Exception:  # noqa: BLE001 - invalidar nunca hace fallar el panel
            logger.warning("channel_directory_invalidate_failed")

    def _find(channel_id: str) -> ChannelInfo | None:
        for info in client().list().channels:
            if info.id == channel_id:
                return info
        return None

    async def _start(request: Request, action: str, target: str | None = None):
        session = _require_session(request, adapters)
        form = await _form(request)
        actor = _actor(session, adapters)
        kwargs = {"target": target} if target is not None else {}
        _require_csrf_audited(session, form, actor, action, adapters, **kwargs)
        return session, form, actor

    @router.get("/admin/static/canales.js")
    async def channels_js() -> Response:
        return Response(
            content=admin.CHANNELS_JS,
            media_type="text/javascript",
            headers=admin.security_headers(),
        )

    @router.get("/admin/canales")
    async def channels_page(request: Request) -> HTMLResponse:
        session = _require_session(request, adapters)
        return _page(session)

    @router.post("/admin/canales")
    async def create_channel(request: Request) -> Response:
        session, form, actor = await _start(request, "channel_create")
        try:
            data = channel_form(form, creating=True)
            body = ChannelCreateRequest(
                id=data.channel_id,
                name=data.name,
                adapter_type=data.adapter_type,
                icon=data.icon,
                color=data.color,
                config=data.config,
                credentials=data.credentials or {},
            )
        except ChannelFormError as exc:
            _audit(actor, "channel_create", "validation_error", adapters)
            return _page(session, 422, str(exc))
        except ValidationError:
            _audit(actor, "channel_create", "validation_error", adapters)
            return _page(session, 422, "Los datos del canal no son válidos.")
        try:
            created = client().create(body)
        except ChannelAdminError as exc:
            return _gateway_error(session, actor, "channel_create", exc, body.id)
        except ChannelAdminUnavailable:
            _audit(actor, "channel_create", "upstream_error", adapters, target=body.id)
            return _upstream_error(session.csrf_token)
        _changed()
        _audit(actor, "channel_create", "ok", adapters, target=body.id)
        return _page(
            session,
            revealed=(created.channel.id, created.secret),
            revealed_title="Canal creado. Secreto",
        )

    @router.post("/admin/canales/{channel_id}")
    async def update_channel(channel_id: str, request: Request) -> Response:
        session, form, actor = await _start(request, "channel_update", channel_id)
        try:
            current = _find(channel_id)
        except ChannelAdminUnavailable:
            return _upstream_error(session.csrf_token)
        if current is None:
            _audit(actor, "channel_update", "not_found", adapters, target=channel_id)
            return _page(session, 404, ERROR_TEXT["not_found"])
        try:
            data = channel_form(
                form,
                creating=False,
                current_config=dict(current.config),
                managed=current.managed_by_environment,
            )
            values: dict = {
                "name": data.name,
                "icon": data.icon,
                "color": data.color,
                "config": data.config,
            }
            if data.credentials is not None:
                values["credentials"] = data.credentials
            body = ChannelUpdateRequest(**values)
        except ChannelFormError as exc:
            _audit(actor, "channel_update", "validation_error", adapters, target=channel_id)
            return _page(session, 422, str(exc))
        except ValidationError:
            _audit(actor, "channel_update", "validation_error", adapters, target=channel_id)
            return _page(session, 422, "Los datos del canal no son válidos.")
        try:
            client().update(channel_id, body)
        except ChannelAdminError as exc:
            return _gateway_error(session, actor, "channel_update", exc, channel_id)
        except ChannelAdminUnavailable:
            _audit(actor, "channel_update", "upstream_error", adapters, target=channel_id)
            return _upstream_error(session.csrf_token)
        _changed()
        _audit(actor, "channel_update", "ok", adapters, target=channel_id)
        return _page(session)

    @router.post("/admin/canales/{channel_id}/activo")
    async def toggle_channel(channel_id: str, request: Request) -> Response:
        session, form, actor = await _start(request, "channel_active", channel_id)
        raw = form.get("active", "")
        if raw not in ("true", "false"):
            _audit(actor, "channel_active", "validation_error", adapters, target=channel_id)
            return _page(session, 422, "El estado no es válido.")
        try:
            client().set_active(channel_id, raw == "true")
        except ChannelAdminError as exc:
            return _gateway_error(session, actor, "channel_active", exc, channel_id)
        except ChannelAdminUnavailable:
            _audit(actor, "channel_active", "upstream_error", adapters, target=channel_id)
            return _upstream_error(session.csrf_token)
        _changed()
        _audit(actor, "channel_active", "ok", adapters, target=f"{channel_id}:{raw}")
        return _page(session)

    @router.post("/admin/canales/{channel_id}/secreto")
    async def reveal_secret(channel_id: str, request: Request) -> Response:
        session, _, actor = await _start(request, "channel_secret_reveal", channel_id)
        try:
            revealed = client().reveal_secret(channel_id)
        except ChannelAdminError as exc:
            return _gateway_error(session, actor, "channel_secret_reveal", exc, channel_id)
        except ChannelAdminUnavailable:
            _audit(actor, "channel_secret_reveal", "upstream_error", adapters, target=channel_id)
            return _upstream_error(session.csrf_token)
        _audit(actor, "channel_secret_reveal", "ok", adapters, target=channel_id)
        return _page(session, revealed=(revealed.channel_id, revealed.secret))

    @router.post("/admin/canales/{channel_id}/secreto/regenerar")
    async def regenerate_secret(channel_id: str, request: Request) -> Response:
        session, form, actor = await _start(request, "channel_secret_regenerate", channel_id)
        if form.get("confirmar") != "si":
            _audit(
                actor, "channel_secret_regenerate", "validation_error", adapters,
                target=channel_id,
            )
            return _page(session, 422, "Confirma que quieres invalidar el secreto actual.")
        try:
            regenerated = client().regenerate_secret(channel_id)
        except ChannelAdminError as exc:
            return _gateway_error(session, actor, "channel_secret_regenerate", exc, channel_id)
        except ChannelAdminUnavailable:
            _audit(
                actor, "channel_secret_regenerate", "upstream_error", adapters,
                target=channel_id,
            )
            return _upstream_error(session.csrf_token)
        _audit(actor, "channel_secret_regenerate", "ok", adapters, target=channel_id)
        return _page(
            session,
            revealed=(regenerated.channel_id, regenerated.secret),
            revealed_title="Secreto nuevo (el anterior ya no sirve)",
        )

    return router
