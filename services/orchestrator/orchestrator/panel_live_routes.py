"""Rutas del panel de asesores en tiempo real (#53): websocket y fragmentos."""
from __future__ import annotations

import asyncio
import logging
from contextlib import suppress
from datetime import timedelta

from fastapi import APIRouter, Request, WebSocket
from fastapi.responses import HTMLResponse, Response
from starlette.concurrency import run_in_threadpool

from . import admin, advisor_panel
from .accounts import hash_token
from .advisor_routes import (
    ADVISOR_ROLES,
    ADVISOR_SESSION_COOKIE,
    PANEL_ROLES,
    AdvisorAccessDenied,
    _advisor_id,
    _domain_error,
    _error_page,
    _html,
    _require_session,
    _valid_case_id,
)
from .config import Settings
from .domain import (
    Adapters,
    DomainError,
    advisor_all_cases,
    advisor_case_history,
    advisor_inbox,
    advisor_reassign_targets,
    visible_case_ids,
)
from .panel_live import (
    PANEL_EVENTS_BATCH_LIMIT,
    PANEL_EVENT_OVERLAP_SECONDS,
    dedupe_new_events,
    event_payload,
    origin_allowed,
)
from .panel_live_js import PANEL_LIVE_JS

logger = logging.getLogger(__name__)

SCOPE_MINE = "mine"
SCOPE_ALL = "all"
_WS_REJECTED = 1008
_WS_POLICY = 1003
_WS_SESSION_INVALID = 4401


def create_panel_live_router(settings: Settings, adapters: Adapters) -> APIRouter:
    router = APIRouter()
    connection_counts: dict[str, int] = {}

    async def _reject(websocket: WebSocket) -> None:
        await websocket.close(code=_WS_REJECTED)

    def _session_profile(websocket: WebSocket):
        token = websocket.cookies.get(ADVISOR_SESSION_COOKIE)
        if not token:
            return None, None
        session = adapters.repository.get_session_for_roles(
            hash_token(token), adapters.clock(), PANEL_ROLES
        )
        if session is None:
            return None, None
        profile = adapters.repository.get_profile(session.profile_id)
        return session, profile

    @router.websocket("/asesor/ws")
    async def panel_ws(websocket: WebSocket) -> None:
        if not settings.panel_live_enabled:
            await _reject(websocket)
            return
        if not origin_allowed(
            websocket.headers.get("origin"),
            websocket.headers.get("host"),
            settings.panel_ws_allowed_origin_list,
        ):
            await _reject(websocket)
            return
        session, profile = _session_profile(websocket)
        if (
            session is None
            or profile is None
            or profile.role not in ADVISOR_ROLES
        ):
            await _reject(websocket)
            return
        scope = websocket.query_params.get("scope") or SCOPE_MINE
        if scope not in (SCOPE_MINE, SCOPE_ALL):
            await _reject(websocket)
            return
        if scope == SCOPE_ALL and profile.role != "supervisor":
            await _reject(websocket)
            return
        profile_key = str(profile.id)
        current = connection_counts.get(profile_key, 0)
        if current >= settings.panel_ws_max_connections_per_profile:
            await _reject(websocket)
            return
        connection_counts[profile_key] = current + 1

        receive_task: asyncio.Task | None = None
        try:
            await websocket.accept()
            repository = adapters.repository
            cursor = await run_in_threadpool(repository.panel_events_cursor)
            since = adapters.clock() - timedelta(
                seconds=PANEL_EVENT_OVERLAP_SECONDS
            )
            baseline = await run_in_threadpool(
                repository.panel_events_since,
                cursor,
                since,
                PANEL_EVENTS_BATCH_LIMIT,
            )
            seen = {event.id for event in baseline if event.id <= cursor}
            last_id = cursor
            # R14: `hello` siempre es el primer mensaje de la conexión.
            await websocket.send_json({"type": "hello", "cursor": cursor})
            receive_task = asyncio.create_task(websocket.receive())
            while True:
                done, _ = await asyncio.wait(
                    {receive_task},
                    timeout=settings.panel_events_poll_seconds,
                )
                if receive_task in done:
                    message = receive_task.result()
                    if message.get("type") == "websocket.disconnect":
                        return
                    # R10: el websocket es de solo lectura.
                    await websocket.close(code=_WS_POLICY)
                    return

                still = await run_in_threadpool(
                    repository.get_session_for_roles,
                    session.token_hash,
                    adapters.clock(),
                    ADVISOR_ROLES,
                )
                if still is None:
                    # R6: logout, expiración o pérdida del rol de panel.
                    await websocket.close(code=_WS_SESSION_INVALID)
                    return

                since = adapters.clock() - timedelta(
                    seconds=PANEL_EVENT_OVERLAP_SECONDS
                )
                events = await run_in_threadpool(
                    repository.panel_events_since,
                    last_id,
                    since,
                    PANEL_EVENTS_BATCH_LIMIT,
                )
                new_events = dedupe_new_events(events, seen)
                if events:
                    last_id = max(last_id, max(event.id for event in events))
                # La ventana de solape es corta; se conserva un conjunto acotado.
                if len(seen) > PANEL_EVENTS_BATCH_LIMIT:
                    seen.intersection_update(
                        sorted(seen)[-PANEL_EVENTS_BATCH_LIMIT:]
                    )
                if not new_events:
                    continue
                try:
                    # R11, R12: una sola consulta por lote y fallo cerrado.
                    allowed = await run_in_threadpool(
                        visible_case_ids, profile, scope, adapters
                    )
                except Exception:
                    logger.error("panel_events_visibility_failed")
                    continue
                for event in new_events:
                    if event.case_id in allowed:
                        await websocket.send_json(event_payload(event))
        finally:
            connection_counts[profile_key] = (
                connection_counts.get(profile_key, 1) - 1
            )
            if connection_counts[profile_key] <= 0:
                connection_counts.pop(profile_key, None)
            if receive_task is not None:
                receive_task.cancel()
                with suppress(asyncio.CancelledError, Exception):
                    await receive_task

    @router.get("/asesor/live/inbox")
    async def live_inbox(request: Request) -> HTMLResponse:
        session = _require_session(request, adapters, ADVISOR_ROLES)
        profile = adapters.repository.get_profile(session.profile_id)
        if profile is None:
            raise AdvisorAccessDenied()
        scope = request.query_params.get("scope") or SCOPE_MINE
        if scope not in (SCOPE_MINE, SCOPE_ALL):
            return _error_page(422, "validation_error", session.csrf_token)
        channel = request.query_params.get("canal")
        assignment = request.query_params.get("asignacion")
        tag = request.query_params.get("tag") or None
        try:
            if scope == SCOPE_ALL:
                rows = advisor_all_cases(
                    profile, channel, assignment, settings, adapters, tag=tag
                )
                targets = advisor_reassign_targets(profile, settings, adapters)
                show_advisor = True
            else:
                rows = advisor_inbox(
                    _advisor_id(session, adapters),
                    channel,
                    assignment,
                    settings,
                    adapters,
                    tag=tag,
                )
                targets = ()
                show_advisor = False
        except DomainError as exc:
            return _domain_error(exc, session.csrf_token)
        table = advisor_panel.render_inbox_table(
            rows,
            session.csrf_token,
            show_advisor=show_advisor,
            all_view=scope == SCOPE_ALL,
            reassign_targets=targets,
        )
        return _html(table)

    @router.get("/asesor/live/cases/{case_id}")
    async def live_case(request: Request, case_id: str) -> HTMLResponse:
        session = _require_session(request, adapters, ADVISOR_ROLES)
        profile = adapters.repository.get_profile(session.profile_id)
        if profile is None:
            raise AdvisorAccessDenied()
        if not _valid_case_id(case_id):
            return _error_page(422, "validation_error", session.csrf_token)
        try:
            history = advisor_case_history(case_id, profile, settings, adapters)
        except DomainError as exc:
            return _domain_error(exc, session.csrf_token)
        return _html(advisor_panel.render_history_fragment(history))

    @router.get("/asesor/static/panel_live.js")
    async def panel_live_script() -> Response:
        return Response(
            content=PANEL_LIVE_JS,
            media_type="text/javascript",
            headers=admin.panel_security_headers(),
        )

    return router
