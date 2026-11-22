"""Panel de envíos fallidos de la cola de salida (#64)."""
from __future__ import annotations

import html

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, Response

from . import admin
from .accounts import hash_token
from .admin_routes import (
    SESSION_COOKIE,
    LoginRequired,
    _audit,
    _form,
    _html,
    _redirect,
    _require_csrf_audited,
)
from .config import Settings
from .domain import Adapters, FailedSend, mask_destination

ALLOWED_ROLES = ("admin", "supervisor")


def _esc(value: object) -> str:
    return html.escape(str(value))


def _require_panel_session(request: Request, adapters: Adapters):
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        raise LoginRequired()
    session = adapters.repository.get_session_any(
        hash_token(token), adapters.clock()
    )
    if session is None:
        raise LoginRequired()
    return session


def render_failed_sends(
    rows: list[FailedSend], csrf: str, current_path: str = "/admin/envios"
) -> str:
    """R29, R30, R41: lista sin texto ni destino completo."""
    if not rows:
        body = "<p>No hay envíos fallidos.</p>"
    else:
        cells = "".join(
            "<tr>"
            f"<td>{row.id}</td>"
            f"<td>{_esc(row.channel)}</td>"
            f"<td>{_esc(mask_destination(row.destination))}</td>"
            f"<td>{_esc(row.kind)}</td>"
            f"<td>{row.attempts}</td>"
            f"<td>{_esc(row.last_error or '')}</td>"
            f"<td>{_esc(row.created_at)}</td>"
            "<td>"
            f'<form method="post" action="/admin/envios/{row.id}/reintentar">'
            f"{admin.csrf_field(csrf)}"
            '<button type="submit">Reintentar</button>'
            "</form>"
            "</td>"
            "</tr>"
            for row in rows
        )
        body = (
            '<div class="table-wrap"><table>'
            "<thead><tr><th>Id</th><th>Canal</th><th>Destino</th><th>Tipo</th>"
            "<th>Intentos</th><th>Motivo</th><th>Creado</th><th></th></tr></thead>"
            f"<tbody>{cells}</tbody></table></div>"
        )
    return admin.render_page(
        "Envíos fallidos", body, csrf, current_path=current_path
    )


def create_envios_router(settings: Settings, adapters: Adapters) -> APIRouter:
    router = APIRouter()

    def _allowed(session):
        profile = adapters.repository.get_profile(session.profile_id)
        if profile is None or profile.role not in ALLOWED_ROLES:
            return None
        return profile

    @router.get("/admin/envios")
    async def failed_sends(request: Request) -> HTMLResponse:
        session = _require_panel_session(request, adapters)
        profile = _allowed(session)
        if profile is None:
            return _html(
                admin.render_error(403, "forbidden", session.csrf_token),
                status_code=403,
            )
        rows = adapters.repository.list_failed_outbound(settings.admin_events_limit)
        return _html(render_failed_sends(rows, session.csrf_token))

    @router.post("/admin/envios/{row_id}/reintentar")
    async def retry_failed_send(row_id: int, request: Request) -> Response:
        session = _require_panel_session(request, adapters)
        form = await _form(request)
        profile = _allowed(session)
        if profile is None:
            current = adapters.repository.get_profile(session.profile_id)
            if current is not None:
                _audit(
                    current,
                    "outbox_retry",
                    "forbidden",
                    adapters,
                    target=str(row_id),
                )
            return _html(
                admin.render_error(403, "forbidden", session.csrf_token),
                status_code=403,
            )
        _require_csrf_audited(
            session, form, profile, "outbox_retry", adapters, target=str(row_id)
        )
        result = adapters.repository.requeue_outbound(row_id, adapters.clock())
        _audit(profile, "outbox_retry", result, adapters, target=str(row_id))
        if result == "ok":
            return _redirect("/admin/envios")
        if result == "not_found":
            return _html(
                admin.render_error(404, "not_found", session.csrf_token),
                status_code=404,
            )
        return _html(
            admin.render_error(409, "not_failed", session.csrf_token),
            status_code=409,
        )

    return router
