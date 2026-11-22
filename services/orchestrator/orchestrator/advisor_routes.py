"""Router HTTP del panel de asesores (HTML renderizado en el servidor)."""
from __future__ import annotations

import logging
from urllib.parse import quote

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from lazaro_contracts import CaseReplyRequest, Identifier
from pydantic import TypeAdapter, ValidationError

from . import admin, advisor_panel
from .accounts import hash_token
from .client_id import normalize_public_id
from .admin_routes import (
    LOGIN_ERROR,
    CsrfInvalid,
    LoginRequired,
    _form,
    _require_csrf,
    client_ip,
)
from .config import Settings
from .domain import (
    inbox_channel_options,
    Adapters,
    AdvisorForbidden,
    AdvisorUnavailable,
    CaseClosed,
    CaseNotFound,
    ChannelWindowClosed,
    DomainError,
    channel_labels,
    channel_dashboard,
    LoginThrottled,
    PanelValidationError,
    ServiceUnavailable,
    UpstreamError,
    add_case_note,
    admin_metrics,
    advisor_all_cases,
    advisor_case_view,
    advisor_client_memory,
    advisor_inbox,
    advisor_reassign_targets,
    advisor_send_template,
    assign_case,
    assign_case_tag,
    conversation_view,
    delete_case_note,
    list_case_tags,
    panel_conversations,
    remove_case_tag,
    authenticate_profile,
    close_case,
    execute_suppression_from_panel,
    parse_dashboard_query,
    reassign_case,
    record_panel_audit,
    reply_to_case,
    return_case,
    search_client_by_public_id,
    set_advisor_presence,
    suppression_queue,
    take_conversation,
    transfer_case,
)

logger = logging.getLogger(__name__)

ADVISOR_SESSION_COOKIE = "advisor_session"
_IDENTIFIER = TypeAdapter(Identifier)
PANEL_ROLES = frozenset({"asesor", "supervisor", "responsable_datos"})
ADVISOR_ROLES = frozenset({"asesor", "supervisor"})
SUPERVISOR_ROLES = frozenset({"supervisor"})


class AdvisorAccessDenied(Exception):
    """La sesión es válida pero su rol no permite la ruta (R22, R25, R26)."""


def _html(content: str, status_code: int = 200) -> HTMLResponse:
    return HTMLResponse(
        content=content,
        status_code=status_code,
        headers=admin.panel_security_headers(),
    )


def _redirect(url: str, status_code: int = 303) -> RedirectResponse:
    return RedirectResponse(
        url=url, status_code=status_code, headers=admin.panel_security_headers()
    )


def _require_session(
    request: Request, adapters: Adapters, allowed_roles: frozenset[str]
):
    token = request.cookies.get(ADVISOR_SESSION_COOKIE)
    if not token:
        raise LoginRequired()
    session = adapters.repository.get_session_for_roles(
        hash_token(token), adapters.clock(), PANEL_ROLES
    )
    if session is None:
        raise LoginRequired()
    profile = adapters.repository.get_profile(session.profile_id)
    if profile is None:
        raise LoginRequired()
    # #60: el menú lateral depende del rol de la sesión.
    advisor_panel.set_panel_role(profile.role)
    if profile.role not in allowed_roles:
        raise AdvisorAccessDenied()
    if profile.role in ADVISOR_ROLES:
        try:
            adapters.repository.touch_advisor_presence(
                session.profile_id, adapters.clock()
            )
        except Exception:
            logger.error("presence_touch_failed profile_id=%s", session.profile_id)
    return session


def _current_profile(session, adapters: Adapters):
    profile = adapters.repository.get_profile(session.profile_id)
    if profile is None or profile.role not in PANEL_ROLES:
        raise LoginRequired()
    return profile


def _advisor_id(session, adapters: Adapters) -> str:
    """R4, R5: la identidad del asesor es el `profile_id` de la sesión."""
    profile = _current_profile(session, adapters)
    return str(profile.id)


def _valid_case_id(value: str) -> bool:
    try:
        _IDENTIFIER.validate_python(value)
    except ValidationError:
        return False
    return True


def _valid_contact_id(value: str) -> bool:
    return _valid_case_id(value)


def _error_page(status: int, code: str, csrf: str | None) -> HTMLResponse:
    return _html(
        advisor_panel.render_advisor_error(status, code, csrf), status_code=status
    )


def _domain_error(exc: DomainError, csrf: str | None) -> HTMLResponse:
    return _error_page(exc.status_code, exc.code, csrf)


def _audit(actor, action: str, result: str, adapters: Adapters, **kwargs) -> None:
    try:
        record_panel_audit(actor, action, result, adapters, **kwargs)
    except Exception:
        logger.error("panel_audit_failed action=%s", action)


def _audit_error(actor, action: str, exc: DomainError, adapters: Adapters, **kwargs) -> None:
    _audit(actor, action, exc.code, adapters, **kwargs)


def _require_csrf_audited(
    session, form: dict[str, str], actor, action: str, adapters: Adapters, **kwargs
) -> None:
    """R34: un fallo CSRF también queda auditado con su código (`forbidden`)."""
    try:
        _require_csrf(session, form)
    except CsrfInvalid:
        _audit(actor, action, "forbidden", adapters, **kwargs)
        raise


def _case_channel_ids(view) -> set[str]:
    ids = {view.client.channel}
    ids.update(item.channel for item in view.history)
    ids.update(summary.channel for summary in view.memory.summaries)
    return ids


def _presence_state(profile_id: str, settings: Settings, adapters: Adapters) -> str:
    from .panel import effective_presence

    stored = adapters.repository.get_advisor_presence([profile_id]).get(profile_id)
    return effective_presence(
        stored[0] if stored is not None else None,
        stored[1] if stored is not None else None,
        adapters.clock(),
        settings.advisor_presence_ttl_minutes,
    )


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
                ("asesor", "supervisor", "responsable_datos"),
                settings,
                adapters,
            )
        except LoginThrottled:
            return _html(advisor_panel.render_advisor_login(LOGIN_ERROR), status_code=429)
        if token is None:
            return _html(advisor_panel.render_advisor_login(LOGIN_ERROR), status_code=401)
        session = adapters.repository.get_session_any(
            hash_token(token), adapters.clock()
        )
        profile = (
            adapters.repository.get_profile(session.profile_id)
            if session is not None
            else None
        )
        target = (
            "/asesor/supresiones"
            if profile is not None and profile.role == "responsable_datos"
            else "/asesor"
        )
        response = _redirect(target)
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
        token = request.cookies.get(ADVISOR_SESSION_COOKIE)
        if not token:
            raise LoginRequired()
        session = adapters.repository.get_session_any(
            hash_token(token), adapters.clock()
        )
        if session is None:
            raise LoginRequired()
        profile = _current_profile(session, adapters)
        form = await _form(request)
        _require_csrf(session, form)
        if profile.role in ADVISOR_ROLES:
            try:
                set_advisor_presence(session.profile_id, "away", adapters)
            except Exception:
                logger.error(
                    "presence_logout_failed profile_id=%s", session.profile_id
                )
        adapters.repository.delete_session(session.token_hash)
        response = _redirect("/asesor/login")
        response.delete_cookie(key=ADVISOR_SESSION_COOKIE, path="/asesor")
        return response

    @router.get("/asesor")
    async def home(request: Request) -> HTMLResponse:
        session = _require_session(request, adapters, PANEL_ROLES)
        profile = _current_profile(session, adapters)
        if profile.role == "responsable_datos":
            return _redirect("/asesor/supresiones")
        return _html(
            advisor_panel.render_advisor_home(
                session.csrf_token,
                request.query_params.get("ok"),
                _presence_state(profile.id, settings, adapters),
                profile.role,
            )
        )

    @router.get("/asesor/clientes")
    async def client_search_page(request: Request) -> HTMLResponse:
        session = _require_session(request, adapters, ADVISOR_ROLES)
        profile = _current_profile(session, adapters)
        raw = request.query_params.get("q", "")
        if not raw.strip():
            return _html(advisor_panel.render_client_search(None, session.csrf_token))
        normalized = normalize_public_id(raw)
        if normalized is None:
            _audit(profile, "client_search", "invalid", adapters)
            return _html(
                advisor_panel.render_client_search(
                    None, session.csrf_token, "ID no válido", query=raw
                )
            )
        view = search_client_by_public_id(normalized, settings, adapters)
        if view is None:
            _audit(profile, "client_search", "not_found", adapters)
            return _html(
                advisor_panel.render_client_search(
                    None, session.csrf_token, "Sin resultados", query=raw
                )
            )
        labels = channel_labels(adapters, {item[1] for item in view.conversations})
        _audit(profile, "client_search", "ok", adapters)
        return _html(
            advisor_panel.render_client_search(
                view, session.csrf_token, labels=labels, query=raw
            )
        )

    @router.get("/asesor/conversaciones")
    async def conversations_page(request: Request) -> HTMLResponse:
        session = _require_session(request, adapters, ADVISOR_ROLES)
        profile = _current_profile(session, adapters)
        channel = request.query_params.get("canal")
        status = request.query_params.get("estado")
        try:
            rows = panel_conversations(
                profile, channel, status, settings, adapters
            )
            try:
                channel_choices = tuple(inbox_channel_options(adapters))
            except UpstreamError:
                channel_choices = ()
            labels = channel_labels(adapters, {row.channel for row in rows})
        except DomainError as exc:
            _audit_error(profile, "conversation_inbox_viewed", exc, adapters)
            return _domain_error(exc, session.csrf_token)
        _audit(profile, "conversation_inbox_viewed", "ok", adapters)
        return _html(
            advisor_panel.render_conversations_page(
                rows,
                session.csrf_token,
                labels=labels,
                selected_channel=channel,
                selected_status=status,
                channel_choices=channel_choices,
                refresh=settings.advisor_inbox_refresh_seconds,
                live_enabled=settings.panel_live_enabled,
            )
        )

    @router.get("/asesor/conversaciones/{contact_id}")
    async def conversation_page(request: Request, contact_id: str) -> HTMLResponse:
        session = _require_session(request, adapters, ADVISOR_ROLES)
        profile = _current_profile(session, adapters)
        target = f"conversation:{contact_id}"
        if not _valid_contact_id(contact_id):
            _audit(
                profile,
                "conversation_read",
                "not_found",
                adapters,
                target=target,
            )
            return _error_page(404, "not_found", session.csrf_token)
        try:
            view = conversation_view(contact_id, profile, settings, adapters)
        except DomainError as exc:
            _audit_error(
                profile, "conversation_read", exc, adapters, target=target
            )
            return _domain_error(exc, session.csrf_token)
        _audit(profile, "conversation_read", "ok", adapters, target=target)
        if (
            view.status == "atendida_por_asesor"
            and view.assigned_to_me
            and view.case_id is not None
        ):
            return _redirect(f"/asesor/cases/{quote(view.case_id, safe='')}")
        channel_ids = {view.client.channel}
        channel_ids.update(item.channel for item in view.history)
        labels = channel_labels(adapters, channel_ids)
        return _html(
            advisor_panel.render_conversation_read(
                view, session.csrf_token, labels=labels
            )
        )

    @router.post("/asesor/conversaciones/{contact_id}/tomar")
    async def take_conversation_action(
        request: Request, contact_id: str
    ) -> Response:
        session = _require_session(request, adapters, ADVISOR_ROLES)
        profile = _current_profile(session, adapters)
        form = await _form(request)
        valid = _valid_contact_id(contact_id)
        target = f"conversation:{contact_id}" if valid else None
        _require_csrf_audited(
            session,
            form,
            profile,
            "conversation_take",
            adapters,
            target=target,
        )
        if not valid:
            _audit(
                profile,
                "conversation_take",
                "not_found",
                adapters,
                target=None,
            )
            return _error_page(404, "not_found", session.csrf_token)
        try:
            case_id = take_conversation(contact_id, profile, settings, adapters)
        except DomainError as exc:
            _audit_error(
                profile, "conversation_take", exc, adapters, target=target
            )
            return _domain_error(exc, session.csrf_token)
        _audit(profile, "conversation_take", "ok", adapters, target=target)
        return _redirect(f"/asesor/cases/{quote(case_id, safe='')}")

    @router.get("/asesor/cases")
    async def cases_page(request: Request) -> HTMLResponse:
        session = _require_session(request, adapters, ADVISOR_ROLES)
        profile = _current_profile(session, adapters)
        advisor_id = _advisor_id(session, adapters)
        channel = request.query_params.get("canal")
        assignment = request.query_params.get("asignacion")
        tag = request.query_params.get("tag") or None
        try:
            rows = advisor_inbox(
                advisor_id, channel, assignment, settings, adapters, tag=tag
            )
            tags = list_case_tags(adapters, only_active=True)
            try:
                channel_choices = tuple(inbox_channel_options(adapters))
            except UpstreamError:
                channel_choices = ()
            labels = channel_labels(adapters, {row.channel for row in rows})
        except DomainError as exc:
            _audit_error(profile, "inbox_viewed", exc, adapters)
            return _domain_error(exc, session.csrf_token)
        _audit(profile, "inbox_viewed", "ok", adapters)
        return _html(
            advisor_panel.render_advisor_cases(
                rows,
                session.csrf_token,
                settings.advisor_inbox_refresh_seconds,
                tags=tags,
                selected_channel=channel,
                selected_assignment=assignment,
                selected_tag=tag,
                live_enabled=settings.panel_live_enabled,
                channel_choices=channel_choices,
                labels=labels,
            )
        )

    @router.get("/asesor/cases/{case_id}")
    async def case_page(request: Request, case_id: str) -> HTMLResponse:
        session = _require_session(request, adapters, ADVISOR_ROLES)
        profile = _current_profile(session, adapters)
        _advisor_id(session, adapters)
        if not _valid_case_id(case_id):
            return _error_page(422, "validation_error", session.csrf_token)
        reply_id = request.query_params.get("respuesta") or None
        try:
            view = advisor_case_view(
                case_id, profile, settings, adapters, reply_id=reply_id
            )
        except DomainError as exc:
            _audit_error(profile, "case_viewed", exc, adapters, case_id=case_id)
            return _domain_error(exc, session.csrf_token)
        _audit(profile, "case_viewed", "ok", adapters, case_id=case_id)
        _audit(profile, "memory_viewed", "ok", adapters, case_id=case_id)
        labels = channel_labels(adapters, _case_channel_ids(view))
        return _html(
            advisor_panel.render_advisor_case(
                view,
                session.csrf_token,
                can_reassign=profile.role == "supervisor",
                live_enabled=settings.panel_live_enabled,
                poll_seconds=settings.advisor_inbox_refresh_seconds,
                labels=labels,
            )
        )

    @router.get("/asesor/cases/{case_id}/memoria")
    async def case_memory(request: Request, case_id: str) -> HTMLResponse:
        session = _require_session(request, adapters, ADVISOR_ROLES)
        profile = _current_profile(session, adapters)
        advisor_id = _advisor_id(session, adapters)
        if not _valid_case_id(case_id):
            return _error_page(422, "validation_error", session.csrf_token)
        try:
            view = advisor_client_memory(
                case_id, advisor_id, settings, adapters
            )
        except DomainError as exc:
            _audit_error(profile, "memory_viewed", exc, adapters, case_id=case_id)
            return _domain_error(exc, session.csrf_token)
        _audit(profile, "memory_viewed", "ok", adapters, case_id=case_id)
        labels = channel_labels(
            adapters, {summary.channel for summary in view.summaries}
        )
        return _html(
            advisor_panel.render_advisor_memory(
                view, session.csrf_token, labels=labels
            )
        )

    @router.post("/asesor/cases/{case_id}/notes")
    async def add_note(request: Request, case_id: str) -> Response:
        session = _require_session(request, adapters, ADVISOR_ROLES)
        profile = _current_profile(session, adapters)
        form = await _form(request)
        _require_csrf_audited(
            session, form, profile, "note_added", adapters, case_id=case_id
        )
        if not _valid_case_id(case_id):
            _audit(
                profile, "note_added", "validation_error", adapters, case_id=case_id
            )
            return _error_page(422, "validation_error", session.csrf_token)
        try:
            note = add_case_note(
                case_id, profile, form.get("text", ""), settings, adapters
            )
        except DomainError as exc:
            _audit_error(profile, "note_added", exc, adapters, case_id=case_id)
            return _domain_error(exc, session.csrf_token)
        _audit(
            profile, "note_added", "ok", adapters, case_id=case_id, target=note.id
        )
        return _redirect(f"/asesor/cases/{case_id}")

    @router.post("/asesor/cases/{case_id}/notes/{note_id}/delete")
    async def delete_note(request: Request, case_id: str, note_id: str) -> Response:
        session = _require_session(request, adapters, ADVISOR_ROLES)
        profile = _current_profile(session, adapters)
        form = await _form(request)
        _require_csrf_audited(
            session,
            form,
            profile,
            "note_deleted",
            adapters,
            case_id=case_id,
            target=note_id,
        )
        if not _valid_case_id(case_id) or not _valid_case_id(note_id):
            _audit(
                profile, "note_deleted", "validation_error", adapters, case_id=case_id
            )
            return _error_page(422, "validation_error", session.csrf_token)
        try:
            delete_case_note(case_id, note_id, profile, settings, adapters)
        except DomainError as exc:
            _audit_error(
                profile,
                "note_deleted",
                exc,
                adapters,
                case_id=case_id,
                target=note_id,
            )
            return _domain_error(exc, session.csrf_token)
        _audit(
            profile,
            "note_deleted",
            "ok",
            adapters,
            case_id=case_id,
            target=note_id,
        )
        return _redirect(f"/asesor/cases/{case_id}")

    @router.post("/asesor/cases/{case_id}/tags")
    async def assign_tag(request: Request, case_id: str) -> Response:
        session = _require_session(request, adapters, ADVISOR_ROLES)
        profile = _current_profile(session, adapters)
        form = await _form(request)
        tag_id = form.get("tag_id", "")
        _require_csrf_audited(
            session,
            form,
            profile,
            "tag_assigned",
            adapters,
            case_id=case_id,
            target=tag_id or None,
        )
        if not _valid_case_id(case_id) or not _valid_case_id(tag_id):
            _audit(
                profile, "tag_assigned", "validation_error", adapters, case_id=case_id
            )
            return _error_page(422, "validation_error", session.csrf_token)
        try:
            assign_case_tag(case_id, tag_id, profile, settings, adapters)
        except DomainError as exc:
            _audit_error(
                profile,
                "tag_assigned",
                exc,
                adapters,
                case_id=case_id,
                target=tag_id,
            )
            return _domain_error(exc, session.csrf_token)
        _audit(
            profile,
            "tag_assigned",
            "ok",
            adapters,
            case_id=case_id,
            target=tag_id,
        )
        return _redirect(f"/asesor/cases/{case_id}")

    @router.post("/asesor/cases/{case_id}/tags/{tag_id}/remove")
    async def remove_tag(request: Request, case_id: str, tag_id: str) -> Response:
        session = _require_session(request, adapters, ADVISOR_ROLES)
        profile = _current_profile(session, adapters)
        form = await _form(request)
        _require_csrf_audited(
            session,
            form,
            profile,
            "tag_removed",
            adapters,
            case_id=case_id,
            target=tag_id,
        )
        if not _valid_case_id(case_id) or not _valid_case_id(tag_id):
            _audit(
                profile, "tag_removed", "validation_error", adapters, case_id=case_id
            )
            return _error_page(422, "validation_error", session.csrf_token)
        try:
            remove_case_tag(case_id, tag_id, profile, settings, adapters)
        except DomainError as exc:
            _audit_error(
                profile,
                "tag_removed",
                exc,
                adapters,
                case_id=case_id,
                target=tag_id,
            )
            return _domain_error(exc, session.csrf_token)
        _audit(
            profile,
            "tag_removed",
            "ok",
            adapters,
            case_id=case_id,
            target=tag_id,
        )
        return _redirect(f"/asesor/cases/{case_id}")

    @router.post("/asesor/reply")
    async def reply(request: Request) -> Response:
        session = _require_session(request, adapters, ADVISOR_ROLES)
        profile = _current_profile(session, adapters)
        form = await _form(request)
        _require_csrf(session, form)
        advisor_id = _advisor_id(session, adapters)
        case_id = form.get("case_id", "")
        text = form.get("text", "")
        template = form.get("template", "")
        if not _valid_case_id(case_id):
            return _error_page(422, "validation_error", session.csrf_token)
        has_text = bool(text)
        has_template = bool(template)
        if has_text == has_template:
            return _error_page(422, "validation_error", session.csrf_token)
        action = "reply" if has_text else "template"
        try:
            if has_text:
                CaseReplyRequest(advisor_id=advisor_id, text=text)
                reply_to_case(
                    case_id,
                    CaseReplyRequest(advisor_id=advisor_id, text=text),
                    settings,
                    adapters,
                )
            else:
                advisor_send_template(
                    case_id, advisor_id, template, settings, adapters
                )
        except ValidationError:
            return _error_page(422, "validation_error", session.csrf_token)
        except DomainError as exc:
            _audit_error(
                profile,
                action,
                exc,
                adapters,
                case_id=case_id,
                target=template or None,
            )
            return _domain_error(exc, session.csrf_token)
        _audit(
            profile,
            action,
            "ok",
            adapters,
            case_id=case_id,
            target=template or None,
        )
        if form.get("origen", "") == "caso":
            return _redirect(f"/asesor/cases/{quote(case_id, safe='')}")
        return _redirect("/asesor?ok=reply")

    @router.post("/asesor/assign")
    async def assign(request: Request) -> Response:
        session = _require_session(request, adapters, ADVISOR_ROLES)
        profile = _current_profile(session, adapters)
        form = await _form(request)
        _require_csrf(session, form)
        advisor_id = _advisor_id(session, adapters)
        case_id = form.get("case_id", "")
        if not _valid_case_id(case_id):
            return _error_page(422, "validation_error", session.csrf_token)
        try:
            assign_case(case_id, advisor_id, adapters)
        except DomainError as exc:
            _audit_error(profile, "assign", exc, adapters, case_id=case_id)
            return _domain_error(exc, session.csrf_token)
        _audit(profile, "assign", "ok", adapters, case_id=case_id)
        return _redirect("/asesor?ok=assign")

    @router.post("/asesor/close")
    async def close(request: Request) -> Response:
        session = _require_session(request, adapters, ADVISOR_ROLES)
        profile = _current_profile(session, adapters)
        form = await _form(request)
        _require_csrf(session, form)
        advisor_id = _advisor_id(session, adapters)
        case_id = form.get("case_id", "")
        if not _valid_case_id(case_id):
            return _error_page(422, "validation_error", session.csrf_token)
        try:
            close_case(case_id, advisor_id, settings, adapters)
        except DomainError as exc:
            _audit_error(profile, "resolve", exc, adapters, case_id=case_id)
            return _domain_error(exc, session.csrf_token)
        _audit(profile, "resolve", "ok", adapters, case_id=case_id)
        return _redirect("/asesor?ok=close")

    @router.post("/asesor/return")
    async def return_to_assistant(request: Request) -> Response:
        session = _require_session(request, adapters, ADVISOR_ROLES)
        profile = _current_profile(session, adapters)
        form = await _form(request)
        _require_csrf(session, form)
        advisor_id = _advisor_id(session, adapters)
        case_id = form.get("case_id", "")
        if not _valid_case_id(case_id):
            return _error_page(422, "validation_error", session.csrf_token)
        try:
            return_case(case_id, advisor_id, settings, adapters)
        except DomainError as exc:
            _audit_error(profile, "return", exc, adapters, case_id=case_id)
            return _domain_error(exc, session.csrf_token)
        _audit(profile, "return", "ok", adapters, case_id=case_id)
        return _redirect("/asesor?ok=return")

    @router.post("/asesor/transfer")
    async def transfer(request: Request) -> Response:
        session = _require_session(request, adapters, ADVISOR_ROLES)
        profile = _current_profile(session, adapters)
        form = await _form(request)
        _require_csrf(session, form)
        _advisor_id(session, adapters)
        case_id = form.get("case_id", "")
        target_profile_id = form.get("target_profile_id", "")
        if not _valid_case_id(case_id):
            return _error_page(422, "validation_error", session.csrf_token)
        try:
            transfer_case(
                case_id, profile, target_profile_id, settings, adapters
            )
        except DomainError as exc:
            _audit_error(
                profile,
                "transfer",
                exc,
                adapters,
                case_id=case_id,
                target=target_profile_id or None,
            )
            return _domain_error(exc, session.csrf_token)
        _audit(
            profile,
            "transfer",
            "ok",
            adapters,
            case_id=case_id,
            target=target_profile_id,
        )
        return _redirect("/asesor?ok=transfer")

    @router.post("/asesor/presence")
    async def presence(request: Request) -> Response:
        session = _require_session(request, adapters, ADVISOR_ROLES)
        profile = _current_profile(session, adapters)
        form = await _form(request)
        _require_csrf(session, form)
        status = form.get("status", "")
        try:
            set_advisor_presence(profile.id, status, adapters)
        except DomainError as exc:
            _audit_error(profile, "presence", exc, adapters)
            return _domain_error(exc, session.csrf_token)
        _audit(profile, "presence", "ok", adapters, target=status)
        return _redirect("/asesor?ok=presence")

    @router.get("/asesor/todos")
    async def all_cases_page(request: Request) -> HTMLResponse:
        session = _require_session(request, adapters, SUPERVISOR_ROLES)
        profile = _current_profile(session, adapters)
        channel = request.query_params.get("canal")
        assignment = request.query_params.get("asignacion")
        tag = request.query_params.get("tag") or None
        try:
            rows = advisor_all_cases(
                profile, channel, assignment, settings, adapters, tag=tag
            )
            reassign_targets = advisor_reassign_targets(
                profile, settings, adapters
            )
            tags = list_case_tags(adapters, only_active=True)
            try:
                channel_choices = tuple(inbox_channel_options(adapters))
            except UpstreamError:
                channel_choices = ()
            labels = channel_labels(adapters, {row.channel for row in rows})
        except DomainError as exc:
            _audit_error(profile, "all_cases_viewed", exc, adapters)
            return _domain_error(exc, session.csrf_token)
        _audit(profile, "all_cases_viewed", "ok", adapters)
        return _html(
            advisor_panel.render_advisor_cases(
                rows,
                session.csrf_token,
                settings.advisor_inbox_refresh_seconds,
                title="Todos los casos",
                show_advisor=True,
                all_view=True,
                reassign_targets=reassign_targets,
                tags=tags,
                selected_channel=channel,
                selected_assignment=assignment,
                selected_tag=tag,
                live_enabled=settings.panel_live_enabled,
                channel_choices=channel_choices,
                labels=labels,
            )
        )

    @router.post("/asesor/casos/{case_id}/reasignar")
    async def reassign(request: Request, case_id: str) -> Response:
        session = _require_session(request, adapters, SUPERVISOR_ROLES)
        profile = _current_profile(session, adapters)
        form = await _form(request)
        _require_csrf(session, form)
        if not _valid_case_id(case_id):
            return _error_page(422, "validation_error", session.csrf_token)
        target_profile_id = form.get("target_profile_id", "")
        if not _valid_case_id(target_profile_id):
            return _error_page(422, "validation_error", session.csrf_token)
        try:
            result = reassign_case(
                case_id, profile, target_profile_id, settings, adapters
            )
        except AdvisorForbidden as exc:
            _audit_error(
                profile,
                "reassign",
                exc,
                adapters,
                case_id=case_id,
                target=f"to:{target_profile_id}",
            )
            # R18: mismo contenido que cualquier 403, sin revelar el caso.
            return _error_page(403, "forbidden", None)
        except DomainError as exc:
            _audit_error(
                profile,
                "reassign",
                exc,
                adapters,
                case_id=case_id,
                target=f"to:{target_profile_id}",
            )
            return _domain_error(exc, session.csrf_token)
        _audit(
            profile,
            "reassign",
            "ok",
            adapters,
            case_id=case_id,
            target=(
                f"from:{result.previous_advisor_id} to:{result.advisor_id}"
            ),
        )
        return _redirect("/asesor/todos?ok=reassign")

    @router.get("/asesor/metricas")
    async def supervisor_metrics(request: Request) -> HTMLResponse:
        session = _require_session(request, adapters, SUPERVISOR_ROLES)
        profile = _current_profile(session, adapters)
        raw_days = request.query_params.get("dias", "7")
        try:
            days = int(raw_days)
        except (TypeError, ValueError):
            days = 0
        if days < 1 or days > 90:
            return _error_page(422, "validation_error", session.csrf_token)
        metrics = admin_metrics(days, settings, adapters)
        _audit(profile, "metrics_viewed", "ok", adapters, target=str(days))
        return _html(
            advisor_panel.render_supervisor_metrics(metrics, session.csrf_token)
        )

    @router.get("/asesor/dashboard")
    async def supervisor_dashboard(request: Request) -> HTMLResponse:
        session = _require_session(request, adapters, SUPERVISOR_ROLES)
        profile = _current_profile(session, adapters)
        try:
            days, include_simulated = parse_dashboard_query(request.query_params)
        except PanelValidationError:
            return _error_page(422, "validation_error", session.csrf_token)
        data = channel_dashboard(profile, days, include_simulated, settings, adapters)
        _audit(
            profile,
            "dashboard_viewed",
            "ok",
            adapters,
            target=f"{data.since.isoformat()}..{data.until.isoformat()}",
        )
        return _html(
            advisor_panel.render_supervisor_dashboard(data, session.csrf_token)
        )

    @router.get("/asesor/supresiones")
    async def suppression_page(request: Request) -> HTMLResponse:
        session = _require_session(
            request, adapters, frozenset(settings.suppression_executor_role_set)
        )
        profile = _current_profile(session, adapters)
        try:
            rows = suppression_queue(profile, settings, adapters)
        except DomainError as exc:
            _audit_error(profile, "suppression_queue_viewed", exc, adapters)
            return _domain_error(exc, session.csrf_token)
        _audit(profile, "suppression_queue_viewed", "ok", adapters)
        return _html(
            advisor_panel.render_suppression_queue(
                rows,
                session.csrf_token,
                "/asesor/supresiones",
                show_inbox=profile.role != "responsable_datos",
            )
        )

    @router.post("/asesor/supresiones/{request_id}/execute")
    async def suppression_execute(request: Request, request_id: str) -> Response:
        session = _require_session(
            request, adapters, frozenset(settings.suppression_executor_role_set)
        )
        profile = _current_profile(session, adapters)
        form = await _form(request)
        _require_csrf(session, form)
        note = form.get("note", "")
        try:
            execute_suppression_from_panel(
                request_id, profile, note, settings, adapters
            )
        except DomainError as exc:
            _audit_error(
                profile,
                "suppression_execute",
                exc,
                adapters,
                request_id=request_id,
            )
            return _domain_error(exc, session.csrf_token)
        _audit(
            profile,
            "suppression_execute",
            "ok",
            adapters,
            request_id=request_id,
        )
        return _redirect("/asesor?ok=suppression")

    return router
