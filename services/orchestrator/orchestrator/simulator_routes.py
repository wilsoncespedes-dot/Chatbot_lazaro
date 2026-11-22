"""Rutas del panel para el canal SIMULADO (admin y supervisor, #63)."""
from __future__ import annotations

import re
from urllib.parse import quote

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from . import admin, advisor_panel, simulator_page
from .adapters.simulator import SIMULATED_ADAPTER_TYPE, SimulatorUnavailable
from .admin_routes import _form, _require_any_session, _require_csrf
from .advisor_routes import SUPERVISOR_ROLES, _require_session
from .config import Settings
from .domain import Adapters

PAGE_TITLE = "Simulador [SIMULADO]"
ADMIN_PATH = "/admin/simulador"
ADVISOR_PATH = "/asesor/simulador"
ADMIN_ROLES = frozenset({"admin"})
EXTERNAL_ID = re.compile(r"^[A-Za-z0-9_.:-]{1,64}$")
MAX_TEXT = 4096
UNAVAILABLE = "El gateway de canales no está disponible. Inténtalo de nuevo más tarde."


def _html_admin(content: str, status_code: int = 200, csrf: str | None = None):
    return HTMLResponse(
        content=admin.render_page(PAGE_TITLE, content, csrf, ADMIN_PATH),
        status_code=status_code,
        headers=admin.security_headers(),
    )


def _html_advisor(content: str, status_code: int = 200, csrf: str | None = None):
    return HTMLResponse(
        content=advisor_panel._page(
            PAGE_TITLE, content, csrf, current_path=ADVISOR_PATH
        ),
        status_code=status_code,
        headers=admin.panel_security_headers(),
    )


def _unavailable(csrf: str, render) -> HTMLResponse:
    body = f'<p class="error" role="alert">{admin._esc(UNAVAILABLE)}</p>'
    return render(body, 503, csrf)


def _valid_fields(usuario: str, texto: str) -> str | None:
    if not usuario or EXTERNAL_ID.fullmatch(usuario) is None:
        return (
            "El id externo de prueba debe tener de 1 a 64 caracteres: letras, "
            "números, punto, guion, dos puntos o guion bajo."
        )
    if not 1 <= len(texto) <= MAX_TEXT:
        return "El texto debe tener entre 1 y 4096 caracteres."
    return None


def _load_channels(adapters: Adapters):
    simulator = adapters.simulator
    if simulator is None:
        raise SimulatorUnavailable("sin cliente")
    return [
        channel
        for channel in simulator.list_channels()
        if channel.adapter_type == SIMULATED_ADAPTER_TYPE
    ]


def _render_get(adapters: Adapters, request: Request, csrf: str, base_path: str):
    simulator = adapters.simulator
    if simulator is None:
        return None
    channels = _load_channels(adapters)
    ids = {channel.id for channel in channels}
    selected = request.query_params.get("canal") or None
    user_id = (request.query_params.get("usuario") or "").strip() or None
    entries = []
    if (
        selected in ids
        and user_id
        and EXTERNAL_ID.fullmatch(user_id) is not None
    ):
        entries = simulator.mailbox(selected, user_id).entries
    return simulator_page.render_simulator(
        channels,
        selected if selected in ids else None,
        user_id,
        entries,
        csrf,
        base_path,
    )


def _render_error(
    channels, selected, usuario, error: str, csrf: str, base_path: str
) -> str:
    return simulator_page.render_simulator(
        channels, selected, usuario, [], csrf, base_path, error=error
    )


def create_simulator_router(settings: Settings, adapters: Adapters) -> APIRouter:
    router = APIRouter()

    @router.get(ADMIN_PATH)
    async def admin_page(request: Request) -> HTMLResponse:
        session, _profile = _require_any_session(request, adapters, ADMIN_ROLES)
        try:
            body = _render_get(
                adapters, request, session.csrf_token, ADMIN_PATH
            )
        except SimulatorUnavailable:
            return _unavailable(session.csrf_token, _html_admin)
        if body is None:
            return _unavailable(session.csrf_token, _html_admin)
        return _html_admin(body, csrf=session.csrf_token)

    @router.post(ADMIN_PATH)
    async def admin_send(request: Request) -> Response:
        session, _profile = _require_any_session(request, adapters, ADMIN_ROLES)
        form = await _form(request)
        _require_csrf(session, form)
        usuario = form.get("usuario", "").strip()
        texto = form.get("texto", "")
        canal = form.get("canal", "").strip()
        error = _valid_fields(usuario, texto)
        if error:
            body = _render_error(
                [], canal or None, usuario, error, session.csrf_token, ADMIN_PATH
            )
            return _html_admin(body, 422, session.csrf_token)
        try:
            channels = _load_channels(adapters)
        except SimulatorUnavailable:
            return _unavailable(session.csrf_token, _html_admin)
        if canal not in {channel.id for channel in channels}:
            body = _render_error(
                channels,
                canal or None,
                usuario,
                "El canal no está en la lista de canales simulados.",
                session.csrf_token,
                ADMIN_PATH,
            )
            return _html_admin(body, 422, session.csrf_token)
        try:
            adapters.simulator.simulate(canal, usuario, texto)
        except SimulatorUnavailable:
            return _unavailable(session.csrf_token, _html_admin)
        query = f"canal={quote(canal, safe='')}&usuario={quote(usuario, safe='')}"
        return RedirectResponse(
            f"{ADMIN_PATH}?{query}",
            status_code=303,
            headers=admin.security_headers(),
        )

    @router.get(ADVISOR_PATH)
    async def advisor_page(request: Request) -> HTMLResponse:
        session = _require_session(request, adapters, SUPERVISOR_ROLES)
        try:
            body = _render_get(
                adapters, request, session.csrf_token, ADVISOR_PATH
            )
        except SimulatorUnavailable:
            return _unavailable(session.csrf_token, _html_advisor)
        if body is None:
            return _unavailable(session.csrf_token, _html_advisor)
        return _html_advisor(body, csrf=session.csrf_token)

    @router.post(ADVISOR_PATH)
    async def advisor_send(request: Request) -> Response:
        session = _require_session(request, adapters, SUPERVISOR_ROLES)
        form = await _form(request)
        _require_csrf(session, form)
        usuario = form.get("usuario", "").strip()
        texto = form.get("texto", "")
        canal = form.get("canal", "").strip()
        error = _valid_fields(usuario, texto)
        if error:
            body = _render_error(
                [], canal or None, usuario, error, session.csrf_token, ADVISOR_PATH
            )
            return _html_advisor(body, 422, session.csrf_token)
        try:
            channels = _load_channels(adapters)
        except SimulatorUnavailable:
            return _unavailable(session.csrf_token, _html_advisor)
        if canal not in {channel.id for channel in channels}:
            body = _render_error(
                channels,
                canal or None,
                usuario,
                "El canal no está en la lista de canales simulados.",
                session.csrf_token,
                ADVISOR_PATH,
            )
            return _html_advisor(body, 422, session.csrf_token)
        try:
            adapters.simulator.simulate(canal, usuario, texto)
        except SimulatorUnavailable:
            return _unavailable(session.csrf_token, _html_advisor)
        query = f"canal={quote(canal, safe='')}&usuario={quote(usuario, safe='')}"
        return RedirectResponse(
            f"{ADVISOR_PATH}?{query}",
            status_code=303,
            headers=admin.panel_security_headers(),
        )

    return router
