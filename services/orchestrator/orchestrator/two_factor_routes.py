"""Rutas HTTP del registro del segundo factor en los paneles admin y asesor."""
from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from . import admin, two_factor_page
from .accounts import hash_token
from .admin_routes import CsrfInvalid, LoginRequired, _form, _require_csrf
from .config import Settings
from .domain import (
    Adapters,
    DomainError,
    TwoFactorAlreadyEnabled,
    TwoFactorCodeInvalid,
    TwoFactorNotEnabled,
    TwoFactorUnavailable,
    begin_two_factor_enrollment,
    confirm_two_factor_enrollment,
)

PANEL_ROLES = {
    "admin": frozenset({"admin"}),
    "asesor": frozenset({"asesor", "supervisor", "responsable_datos"}),
}
PANEL_COOKIES = {"admin": "admin_session", "asesor": "advisor_session"}


def _headers(panel: str) -> dict[str, str]:
    if panel == "admin":
        return admin.security_headers()
    return admin.panel_security_headers()


def _html(content: str, panel: str, status_code: int = 200) -> HTMLResponse:
    return HTMLResponse(
        content=content, status_code=status_code, headers=_headers(panel)
    )


def create_two_factor_router(
    settings: Settings, adapters: Adapters, panel: str
) -> APIRouter:
    if panel not in PANEL_ROLES:
        raise ValueError("panel debe ser admin o asesor")
    router = APIRouter()
    allowed_roles = PANEL_ROLES[panel]
    cookie = PANEL_COOKIES[panel]

    def _require_any_session(request: Request):
        token = request.cookies.get(cookie)
        if not token:
            raise LoginRequired()
        session = adapters.repository.get_session_any(
            hash_token(token), adapters.clock()
        )
        if session is None:
            raise LoginRequired()
        profile = adapters.repository.get_profile(session.profile_id)
        if profile is None or profile.role not in allowed_roles:
            raise LoginRequired()
        return session, profile

    def _status_page(
        profile,
        csrf: str,
        status_code: int = 200,
        error: str | None = None,
        error_code: str | None = None,
    ) -> HTMLResponse:
        record = adapters.repository.get_two_factor(profile.id)
        enabled = record is not None and record.enabled_at is not None
        pending = record is not None and record.enabled_at is None
        return _html(
            two_factor_page.render_status(
                panel,
                csrf,
                enabled=enabled,
                pending=pending,
                error=error,
                error_code=error_code,
            ),
            panel,
            status_code,
        )

    @router.get(f"/{panel}/2fa")
    async def two_factor_status(request: Request) -> HTMLResponse:
        """R9, R28, R30: solo muestra el estado, nunca el secreto."""
        session, profile = _require_any_session(request)
        return _status_page(profile, session.csrf_token)

    @router.post(f"/{panel}/2fa/start")
    async def two_factor_start(request: Request) -> HTMLResponse:
        """R5, R8, R40: inicia el registro y muestra el secreto una sola vez."""
        session, profile = _require_any_session(request)
        form = await _form(request)
        try:
            _require_csrf(session, form)
        except CsrfInvalid:
            raise
        try:
            enrollment = begin_two_factor_enrollment(profile, settings, adapters)
        except TwoFactorAlreadyEnabled:
            return _status_page(
                profile,
                session.csrf_token,
                409,
                "El segundo factor ya está activo.",
                "two_factor_already_enabled",
            )
        except TwoFactorUnavailable:
            return _status_page(
                profile,
                session.csrf_token,
                503,
                "El segundo factor no está disponible.",
                "two_factor_unavailable",
            )
        return _html(
            two_factor_page.render_enrollment(
                panel,
                session.csrf_token,
                enrollment.secret_base32,
                enrollment.provisioning_uri,
            ),
            panel,
        )

    @router.post(f"/{panel}/2fa/confirm")
    async def two_factor_confirm(request: Request) -> HTMLResponse:
        """R6, R7, R25, R40: activa el factor y muestra los códigos una sola vez."""
        session, profile = _require_any_session(request)
        form = await _form(request)
        try:
            _require_csrf(session, form)
        except CsrfInvalid:
            raise
        try:
            codes = confirm_two_factor_enrollment(
                profile,
                form.get("code", ""),
                settings,
                adapters,
                session.token_hash,
            )
        except TwoFactorCodeInvalid:
            return _status_page(
                profile,
                session.csrf_token,
                401,
                "Código de verificación incorrecto.",
                "two_factor_invalid",
            )
        except TwoFactorAlreadyEnabled:
            return _status_page(
                profile,
                session.csrf_token,
                409,
                "El segundo factor ya está activo.",
                "two_factor_already_enabled",
            )
        except TwoFactorNotEnabled:
            return _status_page(
                profile,
                session.csrf_token,
                409,
                "El segundo factor no está pendiente.",
                "two_factor_not_enabled",
            )
        except TwoFactorUnavailable:
            return _status_page(
                profile,
                session.csrf_token,
                503,
                "El segundo factor no está disponible.",
                "two_factor_unavailable",
            )
        except DomainError as exc:
            return _status_page(
                profile,
                session.csrf_token,
                exc.status_code,
                str(exc),
                exc.code,
            )
        return _html(
            two_factor_page.render_recovery(panel, session.csrf_token, codes),
            panel,
        )

    return router
