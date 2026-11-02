"""Router HTTP del panel de asesores (HTML renderizado en el servidor)."""
from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from lazaro_contracts import CaseReplyRequest, Identifier
from pydantic import TypeAdapter, ValidationError

from . import admin, advisor_panel
from .accounts import hash_token
from .admin_routes import (
    LOGIN_ERROR,
    LoginRequired,
    _form,
    _require_csrf,
    client_ip,
)
from .config import Settings
from .domain import (
    Adapters,
    DomainError,
    LoginThrottled,
    ServiceUnavailable,
    assign_case,
    authenticate_profile,
    close_case,
    reply_to_case,
)

ADVISOR_SESSION_COOKIE = "advisor_session"
_IDENTIFIER = TypeAdapter(Identifier)


class TelegramNotLinked(Exception):
    """El perfil de la sesión no tiene telegram_user_id vinculado (R9)."""


def _html(content: str, status_code: int = 200) -> HTMLResponse:
    return HTMLResponse(
        content=content, status_code=status_code, headers=admin.security_headers()
    )


def _redirect(url: str, status_code: int = 303) -> RedirectResponse:
    return RedirectResponse(
        url=url, status_code=status_code, headers=admin.security_headers()
    )


def _require_session(request: Request, adapters: Adapters):
    token = request.cookies.get(ADVISOR_SESSION_COOKIE)
    if not token:
        raise LoginRequired()
    session = adapters.repository.get_session_for_role(
        hash_token(token), adapters.clock(), "asesor"
    )
    if session is None:
        raise LoginRequired()
    return session


def _current_profile(session, adapters: Adapters):
    profile = adapters.repository.get_profile(session.profile_id)
    if profile is None or profile.role != "asesor":
        raise LoginRequired()
    return profile


def _advisor_id(session, adapters: Adapters) -> str:
    profile = _current_profile(session, adapters)
    if profile.telegram_user_id is None:
        raise TelegramNotLinked()
    return str(profile.telegram_user_id)


def _valid_case_id(value: str) -> bool:
    try:
        _IDENTIFIER.validate_python(value)
    except ValidationError:
        return False
    return True


def _error_page(status: int, code: str, csrf: str | None) -> HTMLResponse:
    return _html(
        advisor_panel.render_advisor_error(status, code, csrf), status_code=status
    )


def _domain_error(exc: DomainError, csrf: str | None) -> HTMLResponse:
    return _error_page(exc.status_code, exc.code, csrf)


def create_advisor_router(settings: Settings, adapters: Adapters) -> APIRouter:
    router = APIRouter()

    @router.get("/asesor/login")
    async def login_page() -> HTMLResponse:
        return _html(advisor_panel.render_advisor_login())

    @router.post("/asesor/login")
    async def login(request: Request) -> Response:
        form = await _form(request)
        try:
            token = authenticate_profile(
                form.get("username", ""),
                form.get("password", ""),
                client_ip(request, settings),
                "asesor",
                settings,
                adapters,
            )
        except LoginThrottled:
            return _html(advisor_panel.render_advisor_login(LOGIN_ERROR), status_code=429)
        if token is None:
            return _html(advisor_panel.render_advisor_login(LOGIN_ERROR), status_code=401)
        response = _redirect("/asesor")
        response.set_cookie(
            key=ADVISOR_SESSION_COOKIE,
            value=token,
            max_age=settings.admin_session_ttl_minutes * 60,
            path="/asesor",
            httponly=True,
            samesite="strict",
            secure=settings.admin_cookie_secure,
        )
        return response

    @router.post("/asesor/logout")
    async def logout(request: Request) -> Response:
        session = _require_session(request, adapters)
        form = await _form(request)
        _require_csrf(session, form)
        adapters.repository.delete_session(session.token_hash)
        response = _redirect("/asesor/login")
        response.delete_cookie(key=ADVISOR_SESSION_COOKIE, path="/asesor")
        return response

    @router.get("/asesor")
    async def home(request: Request) -> HTMLResponse:
        session = _require_session(request, adapters)
        profile = _current_profile(session, adapters)
        return _html(
            advisor_panel.render_advisor_home(
                session.csrf_token,
                request.query_params.get("ok"),
                profile.telegram_user_id is not None,
            )
        )

    @router.get("/asesor/cases")
    async def cases_page(request: Request) -> HTMLResponse:
        session = _require_session(request, adapters)
        try:
            advisor_id = _advisor_id(session, adapters)
        except TelegramNotLinked:
            return _error_page(403, "telegram_not_linked", session.csrf_token)
        try:
            listed = adapters.handover.list_cases(advisor_id)
        except ServiceUnavailable:
            return _error_page(502, "upstream_error", session.csrf_token)
        return _html(
            advisor_panel.render_advisor_cases(listed.root, session.csrf_token)
        )

    @router.post("/asesor/reply")
    async def reply(request: Request) -> Response:
        session = _require_session(request, adapters)
        form = await _form(request)
        _require_csrf(session, form)
        try:
            advisor_id = _advisor_id(session, adapters)
        except TelegramNotLinked:
            return _error_page(403, "telegram_not_linked", session.csrf_token)
        case_id = form.get("case_id", "")
        text = form.get("text", "")
        if not _valid_case_id(case_id):
            return _error_page(422, "validation_error", session.csrf_token)
        try:
            CaseReplyRequest(advisor_id=advisor_id, text=text)
        except ValidationError:
            return _error_page(422, "validation_error", session.csrf_token)
        try:
            reply_to_case(
                case_id,
                CaseReplyRequest(advisor_id=advisor_id, text=text),
                settings,
                adapters,
            )
        except DomainError as exc:
            return _domain_error(exc, session.csrf_token)
        return _redirect("/asesor?ok=reply")

    @router.post("/asesor/assign")
    async def assign(request: Request) -> Response:
        session = _require_session(request, adapters)
        form = await _form(request)
        _require_csrf(session, form)
        try:
            advisor_id = _advisor_id(session, adapters)
        except TelegramNotLinked:
            return _error_page(403, "telegram_not_linked", session.csrf_token)
        case_id = form.get("case_id", "")
        if not _valid_case_id(case_id):
            return _error_page(422, "validation_error", session.csrf_token)
        try:
            assign_case(case_id, advisor_id, adapters)
        except DomainError as exc:
            return _domain_error(exc, session.csrf_token)
        return _redirect("/asesor?ok=assign")

    @router.post("/asesor/close")
    async def close(request: Request) -> Response:
        session = _require_session(request, adapters)
        form = await _form(request)
        _require_csrf(session, form)
        try:
            advisor_id = _advisor_id(session, adapters)
        except TelegramNotLinked:
            return _error_page(403, "telegram_not_linked", session.csrf_token)
        case_id = form.get("case_id", "")
        if not _valid_case_id(case_id):
            return _error_page(422, "validation_error", session.csrf_token)
        try:
            close_case(case_id, advisor_id, settings, adapters)
        except DomainError as exc:
            return _domain_error(exc, session.csrf_token)
        return _redirect("/asesor?ok=close")

    return router
