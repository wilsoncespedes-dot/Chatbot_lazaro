"""Router de respuestas rápidas del bot (#71): administración y media público."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from starlette.datastructures import UploadFile as StarletteUploadFile

from . import admin
from .accounts import ROLES, hash_token
from .admin_routes import (
    CsrfInvalid,
    LoginRequired,
    _form,
    _require_csrf,
)
from .config import Settings
from .domain import (
    Adapters,
    DomainError,
    create_quick_reply,
    list_quick_replies,
    record_panel_audit,
    set_quick_reply_active,
    update_quick_reply,
)
from .quick_replies import QuickReplyForm, image_id_valid

SESSION_COOKIE = "admin_session"


def _html(content: str, status_code: int = 200) -> HTMLResponse:
    return HTMLResponse(
        content=content, status_code=status_code, headers=admin.security_headers()
    )


def _redirect(url: str) -> RedirectResponse:
    return RedirectResponse(
        url=url, status_code=303, headers=admin.security_headers()
    )


def create_quick_replies_router(settings: Settings, adapters: Adapters) -> APIRouter:
    router = APIRouter()

    def _session(request: Request):
        token = request.cookies.get(SESSION_COOKIE)
        if not token:
            raise LoginRequired()
        session = adapters.repository.get_session_for_roles(
            hash_token(token), adapters.clock(), ROLES
        )
        if session is None:
            raise LoginRequired()
        return session

    def _profile(session):
        return adapters.repository.get_profile(session.profile_id)

    def _audit(profile, action: str, result: str, **kwargs) -> None:
        if profile is None:
            return
        try:
            record_panel_audit(profile, action, result, adapters, **kwargs)
        except Exception:
            pass

    def _page(session, status_code: int = 200, error: str | None = None):
        return _html(
            admin.render_quick_replies(
                list_quick_replies(adapters),
                session.csrf_token,
                error,
                settings.quick_reply_image_max_bytes,
            ),
            status_code=status_code,
        )

    async def _form_and_image(request: Request):
        form = await request.form()
        values: dict[str, str] = {}
        upload: StarletteUploadFile | None = None
        for key, value in form.multi_items():
            if isinstance(value, StarletteUploadFile):
                if key == "image_file" and value.filename:
                    upload = value
            else:
                values[key] = value
        image: bytes | None = None
        if upload is not None:
            image = await upload.read(settings.quick_reply_image_max_bytes + 1)
        return values, image

    @router.get("/admin/respuestas-rapidas")
    async def quick_replies_page(request: Request) -> HTMLResponse:
        session = _session(request)
        profile = _profile(session)
        if profile is None or profile.role != "admin":
            _audit(profile, "quick_reply_viewed", "forbidden")
            return _html(
                admin.render_error(403, "forbidden", session.csrf_token),
                status_code=403,
            )
        _audit(profile, "quick_reply_viewed", "ok")
        return _page(session)

    @router.post("/admin/respuestas-rapidas")
    async def create_quick_reply_page(request: Request) -> Response:
        session = _session(request)
        profile = _profile(session)
        values, image = await _form_and_image(request)
        try:
            _require_csrf(session, values)
        except CsrfInvalid:
            _audit(profile, "quick_reply_created", "forbidden")
            raise
        if profile is None or profile.role != "admin":
            _audit(profile, "quick_reply_created", "forbidden")
            return _html(
                admin.render_error(403, "forbidden", session.csrf_token),
                status_code=403,
            )
        try:
            reply = create_quick_reply(
                QuickReplyForm.from_mapping(values), image, settings, adapters
            )
        except DomainError as exc:
            _audit(profile, "quick_reply_created", exc.code)
            return _page(session, exc.status_code, exc.code)
        _audit(profile, "quick_reply_created", "ok", target=reply.id)
        return _redirect("/admin/respuestas-rapidas")

    @router.post("/admin/respuestas-rapidas/{reply_id}")
    async def update_quick_reply_page(
        reply_id: str, request: Request
    ) -> Response:
        session = _session(request)
        profile = _profile(session)
        values, image = await _form_and_image(request)
        try:
            _require_csrf(session, values)
        except CsrfInvalid:
            _audit(
                profile, "quick_reply_updated", "forbidden", target=reply_id
            )
            raise
        if profile is None or profile.role != "admin":
            _audit(
                profile, "quick_reply_updated", "forbidden", target=reply_id
            )
            return _html(
                admin.render_error(403, "forbidden", session.csrf_token),
                status_code=403,
            )
        try:
            update_quick_reply(
                reply_id,
                QuickReplyForm.from_mapping(values),
                image,
                values.get("remove_image", "") in ("1", "on", "true", "si", "sí"),
                settings,
                adapters,
            )
        except DomainError as exc:
            _audit(profile, "quick_reply_updated", exc.code, target=reply_id)
            return _page(session, exc.status_code, exc.code)
        _audit(profile, "quick_reply_updated", "ok", target=reply_id)
        return _redirect("/admin/respuestas-rapidas")

    @router.post("/admin/respuestas-rapidas/{reply_id}/activa")
    async def change_quick_reply_active(
        reply_id: str, request: Request
    ) -> Response:
        session = _session(request)
        profile = _profile(session)
        form = await _form(request)
        try:
            _require_csrf(session, form)
        except CsrfInvalid:
            _audit(
                profile,
                "quick_reply_active_changed",
                "forbidden",
                target=reply_id,
            )
            raise
        if profile is None or profile.role != "admin":
            _audit(
                profile,
                "quick_reply_active_changed",
                "forbidden",
                target=reply_id,
            )
            return _html(
                admin.render_error(403, "forbidden", session.csrf_token),
                status_code=403,
            )
        active_value = form.get("active", "")
        if active_value not in ("0", "1"):
            _audit(
                profile,
                "quick_reply_active_changed",
                "validation_error",
                target=reply_id,
            )
            return _page(session, 422, "El estado debe ser 0 o 1.")
        try:
            set_quick_reply_active(reply_id, active_value == "1", adapters)
        except DomainError as exc:
            _audit(
                profile,
                "quick_reply_active_changed",
                exc.code,
                target=reply_id,
            )
            return _page(session, exc.status_code, exc.code)
        _audit(
            profile, "quick_reply_active_changed", "ok", target=reply_id
        )
        return _redirect("/admin/respuestas-rapidas")

    @router.get("/media/respuestas/{image_id}")
    async def quick_reply_media(image_id: str) -> Response:
        if not image_id_valid(image_id):
            raise HTTPException(status_code=404, detail="not_found")
        image = adapters.repository.get_quick_reply_image(image_id)
        if image is None:
            raise HTTPException(status_code=404, detail="not_found")
        return Response(
            content=image.data,
            media_type=image.content_type,
            headers={
                "X-Content-Type-Options": "nosniff",
                "Cache-Control": "public, max-age=3600",
            },
        )

    return router
