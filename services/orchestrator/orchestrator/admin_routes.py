"""Router HTTP del panel administrativo (HTML renderizado en el servidor)."""
from __future__ import annotations

import hmac
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, quote

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from lazaro_contracts import ChunkActiveRequest, ChunkUpdateRequest, ManualUploadRequest
from pydantic import ValidationError
from starlette.datastructures import UploadFile as StarletteUploadFile

from . import admin, advisor_panel
from .accounts import ROLES, USERNAME_PATTERN, hash_token
from .administration import (
    OPERATIONAL_SETTINGS,
    OPERATIONAL_SETTINGS_BY_KEY,
    resolve_operational_settings,
)
from .classifier import parse_threshold, validate_category_fields
from .config import Settings
from .domain import (
    Adapters,
    CategoryCodeTaken,
    ClientNotFound,
    CredentialRevoked,
    DomainError,
    CategoryNotFound,
    LastAdmin,
    LoginThrottled,
    NoticeVersionRequired,
    ProfileNotFound,
    RagRejected,
    ServiceUnavailable,
    SettingsInvalid,
    TemplateExists,
    TemplateNotFound,
    TemplateTransitionInvalid,
    UsernameTaken,
    admin_metrics,
    authenticate_admin,
    change_role,
    change_template_status,
    classifier_threshold,
    conversation_texts,
    create_client,
    create_profile,
    create_query_category,
    create_template,
    execute_suppression_from_panel,
    issue_link_token,
    list_clients_admin,
    list_profiles,
    list_query_categories,
    operational_settings,
    recent_events,
    record_panel_audit,
    renew_credential,
    revoke_credential,
    close_client_session,
    save_operational_settings,
    set_classifier_threshold,
    set_query_category_active,
    suppression_queue,
    text_history,
    update_conversation_texts,
    update_query_category,
    update_template,
)
from .privacy import CONVERSATION_TEXT_FIELDS, ConversationTexts

SESSION_COOKIE = "admin_session"
LOGIN_ERROR = "Usuario o contraseña incorrectos."


class LoginRequired(Exception):
    """La petición a /admin no trae una sesión válida (R3)."""


class CsrfInvalid(Exception):
    """El POST protegido no trae el csrf_token de la sesión (R4)."""


def client_ip(request: Request, settings: Settings) -> str:
    if settings.admin_trust_proxy_headers:
        first = request.headers.get("x-forwarded-for", "").split(",")[0].strip()
        if first:
            return first
    return request.client.host if request.client is not None else ""


async def _form(request: Request) -> dict[str, str]:
    body = await request.body()
    parsed = parse_qs(body.decode("utf-8"), keep_blank_values=True)
    return {key: values[-1] for key, values in parsed.items()}


def _require_session(request: Request, adapters: Adapters):
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        raise LoginRequired()
    session = adapters.repository.get_session(hash_token(token), adapters.clock())
    if session is None:
        raise LoginRequired()
    return session


def _require_csrf(session, form: dict[str, str]) -> None:
    provided = form.get("csrf_token", "")
    if not provided or not hmac.compare_digest(provided, session.csrf_token):
        raise CsrfInvalid()


def _html(content: str, status_code: int = 200) -> HTMLResponse:
    return HTMLResponse(
        content=content, status_code=status_code, headers=admin.security_headers()
    )


def _redirect(url: str, status_code: int = 303) -> RedirectResponse:
    return RedirectResponse(
        url=url, status_code=status_code, headers=admin.security_headers()
    )


def _rag_error(exc: RagRejected, csrf: str | None) -> HTMLResponse:
    return _html(
        admin.render_error(exc.status_code, exc.code, csrf), status_code=exc.status_code
    )


def _upstream_error(csrf: str | None) -> HTMLResponse:
    return _html(
        admin.render_error(502, "upstream_error", csrf), status_code=502
    )


def _validate_profile_fields(
    username: str, role: str, password: str, settings: Settings
) -> str | None:
    normalized = username.lower()
    if not USERNAME_PATTERN.fullmatch(normalized):
        return "El usuario debe tener de 3 a 64 caracteres: letras minúsculas, números, . _ -"
    if role not in ROLES:
        return "El rol debe ser admin, asesor o cliente."
    if len(password) < settings.profile_password_min_length:
        return "La contraseña es demasiado corta."
    return None


MAX_CONVERSATION_TEXT_LENGTH = 4096


def _conversation_texts_from_form(
    form: dict[str, str],
) -> ConversationTexts | None:
    values = {field: form.get(field, "") for field in CONVERSATION_TEXT_FIELDS}
    if any(len(value) > MAX_CONVERSATION_TEXT_LENGTH for value in values.values()):
        return None
    if not values["notice_text"].strip() or not values["notice_version"].strip():
        return None
    return ConversationTexts(**values)


def _audit(profile, action: str, result: str, adapters: Adapters, **kwargs) -> None:
    try:
        record_panel_audit(profile, action, result, adapters, **kwargs)
    except Exception:
        pass


def _actor(session, adapters: Adapters):
    return adapters.repository.get_profile(session.profile_id)


def _form_date(raw: str, utc_offset_minutes: int) -> datetime | None:
    """R3, R4, S9: AAAA-MM-DD a medianoche local; vacío significa no enviado."""
    value = raw.strip()
    if not value:
        return None
    try:
        parsed = datetime.strptime(value, "%Y-%m-%d")
    except ValueError:
        raise ValueError("fecha") from None
    return (parsed.replace(tzinfo=timezone.utc) - timedelta(
        minutes=utc_offset_minutes
    ))


def _effective_setting_value(key: str, operational) -> str:
    if key.startswith("identity."):
        field = {
            "identity.link_ttl_minutes": "link_ttl_minutes",
            "identity.session_idle_minutes": "session_idle_minutes",
            "identity.login_max_attempts": "login_max_attempts",
            "identity.lockout_minutes": "lockout_minutes",
            "identity.validity_days": "validity_days",
            "identity.expiry_notice_days": "expiry_notice_days",
        }[key]
        return str(getattr(operational.identity, field))
    if key == "expiry_notice.enabled":
        return "true" if operational.expiry_notice_enabled else "false"
    if key == "business_hours.enabled":
        return "true" if operational.hours.enabled else "false"
    if key == "business_hours.start":
        return operational.hours.start.strftime("%H:%M")
    if key == "business_hours.end":
        return operational.hours.end.strftime("%H:%M")
    if key == "business_hours.days":
        return ",".join(str(day) for day in sorted(operational.hours.days))
    if key == "business_hours.utc_offset_minutes":
        return str(operational.hours.utc_offset_minutes)
    if key == "suppression.deadline_business_days":
        return str(operational.suppression_deadline_business_days)
    return str(operational.suppression_due_soon_business_days)


def _default_setting_value(spec, settings: Settings) -> str:
    value = getattr(settings, spec.default_attr)
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _setting_range(spec) -> str:
    if spec.kind == "bool":
        return "true | false"
    if spec.kind == "time":
        return "HH:MM"
    if spec.kind == "days":
        return "1-7 separados por comas"
    return f"{spec.minimum}..{spec.maximum}"


def _settings_view(settings: Settings, adapters: Adapters) -> list[dict[str, str]]:
    overrides = adapters.repository.get_app_settings(("identity.", "expiry_notice.", "business_hours.", "suppression."))
    operational = resolve_operational_settings(settings, overrides)
    rows = []
    for spec in OPERATIONAL_SETTINGS:
        raw = overrides.get(spec.key)
        effective = _effective_setting_value(spec.key, operational)
        origin = "entorno"
        if raw is not None and raw.strip() and _raw_matches_effective(spec, raw, effective):
            origin = "panel"
        rows.append(
            {
                "key": spec.key,
                "effective": effective,
                "default": _default_setting_value(spec, settings),
                "origin": origin,
                "range": _setting_range(spec),
            }
        )
    return rows


def _raw_matches_effective(spec, raw: str, effective: str) -> bool:
    value = raw.strip()
    if spec.kind == "bool":
        return value.lower() == effective
    if spec.kind == "days":
        return (
            ",".join(token.strip() for token in value.split(",") if token.strip())
            == ",".join(sorted(effective.split(","), key=int))
        )
    try:
        return str(int(value)) == effective
    except ValueError:
        return value == effective


def create_admin_router(settings: Settings, adapters: Adapters) -> APIRouter:
    # Sin `prefix`: las rutas se registran en la app con su ruta completa. La
    # versión de FastAPI instalada envuelve `include_router` en un objeto sin
    # `path`, y el test de superficie exige ver las rutas como `APIRoute`.
    router = APIRouter()

    def _category_page(session, status_code: int = 200, error: str | None = None):
        threshold = classifier_threshold(settings, adapters)
        return _html(
            admin.render_categories(
                list_query_categories(adapters), threshold, session.csrf_token, error
            ),
            status_code=status_code,
        )

    @router.get("/admin/static/admin.css")
    async def admin_css() -> Response:
        return Response(
            content=admin.ADMIN_CSS,
            media_type="text/css",
            headers=admin.security_headers(),
        )

    @router.get("/admin/login")
    async def login_page() -> HTMLResponse:
        return _html(admin.render_login())

    @router.post("/admin/login")
    async def login(request: Request) -> Response:
        form = await _form(request)
        try:
            token = authenticate_admin(
                form.get("username", ""),
                form.get("password", ""),
                client_ip(request, settings),
                settings,
                adapters,
            )
        except LoginThrottled:
            return _html(admin.render_login(LOGIN_ERROR), status_code=429)
        if token is None:
            return _html(admin.render_login(LOGIN_ERROR), status_code=401)
        response = _redirect("/admin")
        response.set_cookie(
            key=SESSION_COOKIE,
            value=token,
            max_age=settings.admin_session_ttl_minutes * 60,
            path="/admin",
            httponly=True,
            samesite="strict",
            secure=settings.admin_cookie_secure,
        )
        return response

    @router.post("/admin/logout")
    async def logout(request: Request) -> Response:
        session = _require_session(request, adapters)
        form = await _form(request)
        _require_csrf(session, form)
        adapters.repository.delete_session(session.token_hash)
        response = _redirect("/admin/login")
        response.delete_cookie(key=SESSION_COOKIE, path="/admin")
        return response

    @router.get("/admin")
    async def home(request: Request) -> HTMLResponse:
        session = _require_session(request, adapters)
        return _html(admin.render_home(session.csrf_token))

    @router.get("/admin/profiles")
    async def profiles_page(request: Request) -> HTMLResponse:
        session = _require_session(request, adapters)
        return _html(
            admin.render_profiles(list_profiles(adapters), session.csrf_token)
        )

    @router.post("/admin/profiles")
    async def create_profile_page(request: Request) -> Response:
        session = _require_session(request, adapters)
        form = await _form(request)
        _require_csrf(session, form)
        username = form.get("username", "")
        role = form.get("role", "")
        password = form.get("password", "")
        error = _validate_profile_fields(username, role, password, settings)
        if error is not None:
            return _html(
                admin.render_profiles(
                    list_profiles(adapters), session.csrf_token, error
                ),
                status_code=422,
            )
        try:
            create_profile(username.lower(), role, password, settings, adapters)
        except UsernameTaken:
            return _html(
                admin.render_profiles(
                    list_profiles(adapters), session.csrf_token, "username_taken"
                ),
                status_code=409,
            )
        return _redirect("/admin/profiles")

    @router.post("/admin/profiles/{profile_id}/role")
    async def change_profile_role(profile_id: str, request: Request) -> Response:
        session = _require_session(request, adapters)
        form = await _form(request)
        _require_csrf(session, form)
        role = form.get("role", "")
        if role not in ROLES:
            return _html(
                admin.render_profiles(
                    list_profiles(adapters), session.csrf_token, "Rol inválido."
                ),
                status_code=422,
            )
        try:
            change_role(profile_id, role, adapters)
        except ProfileNotFound:
            return _html(
                admin.render_message(
                    "Perfil no encontrado", "profile_not_found", session.csrf_token
                ),
                status_code=404,
            )
        except LastAdmin:
            return _html(
                admin.render_profiles(
                    list_profiles(adapters), session.csrf_token, "last_admin"
                ),
                status_code=409,
            )
        return _redirect("/admin/profiles")

    @router.post("/admin/profiles/{profile_id}/link-token")
    async def create_link_token(profile_id: str, request: Request) -> Response:
        session = _require_session(request, adapters)
        form = await _form(request)
        _require_csrf(session, form)
        try:
            issued = issue_link_token(profile_id, settings, adapters)
        except ProfileNotFound:
            return _html(
                admin.render_message(
                    "Perfil no encontrado", "profile_not_found", session.csrf_token
                ),
                status_code=404,
            )
        link = None
        if settings.telegram_bot_username:
            link = (
                f"https://t.me/{settings.telegram_bot_username}"
                f"?start={issued.token}"
            )
        return _html(
            admin.render_link(
                issued.token, link, issued.expires_at, session.csrf_token
            )
        )

    @router.get("/admin/events")
    async def events_page(request: Request) -> HTMLResponse:
        session = _require_session(request, adapters)
        events = recent_events(settings.admin_events_limit, adapters)
        return _html(admin.render_events(events, session.csrf_token))

    @router.get("/admin/manuals")
    async def manuals_page(request: Request) -> HTMLResponse:
        session = _require_session(request, adapters)
        try:
            manuals = adapters.rag.list_manuals()
        except RagRejected as exc:
            return _rag_error(exc, session.csrf_token)
        except ServiceUnavailable:
            return _upstream_error(session.csrf_token)
        return _html(admin.render_manuals(manuals, session.csrf_token))

    @router.post("/admin/manuals")
    async def upload_manual(request: Request) -> Response:
        session = _require_session(request, adapters)
        form = await request.form()
        csrf_value = form.get("csrf_token")
        _require_csrf(
            session,
            {"csrf_token": csrf_value if isinstance(csrf_value, str) else ""},
        )
        name_value = form.get("name")
        file_value = form.get("file")
        name = name_value if isinstance(name_value, str) else ""
        if not isinstance(file_value, StarletteUploadFile):
            return _html(
                admin.render_manuals(
                    None, session.csrf_token, "Faltan el nombre o el archivo del manual."
                ),
                status_code=422,
            )
        try:
            ManualUploadRequest(name=name)
        except ValidationError:
            return _html(
                admin.render_manuals(
                    None, session.csrf_token, "El nombre del manual no es válido."
                ),
                status_code=422,
            )
        content = await file_value.read(settings.admin_manual_max_bytes + 1)
        if len(content) > settings.admin_manual_max_bytes:
            return _html(
                admin.render_manuals(
                    None,
                    session.csrf_token,
                    "El archivo supera el tamaño máximo permitido.",
                ),
                status_code=413,
            )
        try:
            created = adapters.rag.upload_manual(
                name,
                file_value.filename or "manual",
                content,
                file_value.content_type or "application/octet-stream",
            )
        except RagRejected as exc:
            return _rag_error(exc, session.csrf_token)
        except ServiceUnavailable:
            return _upstream_error(session.csrf_token)
        return _redirect(
            f"/admin/manuals/{quote(created.manual_id, safe='')}"
        )

    @router.get("/admin/manuals/{manual_id}")
    async def manual_chunks_page(manual_id: str, request: Request) -> HTMLResponse:
        session = _require_session(request, adapters)
        try:
            chunks = adapters.rag.list_chunks(manual_id)
        except RagRejected as exc:
            return _rag_error(exc, session.csrf_token)
        except ServiceUnavailable:
            return _upstream_error(session.csrf_token)
        return _html(
            admin.render_manual_chunks(manual_id, chunks, session.csrf_token)
        )

    @router.post("/admin/chunks/{chunk_id}")
    async def edit_chunk(chunk_id: str, request: Request) -> Response:
        session = _require_session(request, adapters)
        form = await _form(request)
        _require_csrf(session, form)
        text = form.get("text", "")
        try:
            ChunkUpdateRequest(text=text)
        except ValidationError:
            return _html(
                admin.render_error(422, "validation_error", session.csrf_token),
                status_code=422,
            )
        try:
            updated = adapters.rag.update_chunk(chunk_id, text)
        except RagRejected as exc:
            return _rag_error(exc, session.csrf_token)
        except ServiceUnavailable:
            return _upstream_error(session.csrf_token)
        return _redirect(
            f"/admin/manuals/{quote(updated.manual_id, safe='')}"
        )

    @router.post("/admin/chunks/{chunk_id}/active")
    async def change_chunk_active(chunk_id: str, request: Request) -> Response:
        session = _require_session(request, adapters)
        form = await _form(request)
        _require_csrf(session, form)
        active_value = form.get("active", "")
        if active_value not in ("true", "false"):
            return _html(
                admin.render_error(422, "validation_error", session.csrf_token),
                status_code=422,
            )
        try:
            ChunkActiveRequest(active=active_value == "true")
            updated = adapters.rag.set_chunk_active(
                chunk_id, active_value == "true"
            )
        except ValidationError:
            return _html(
                admin.render_error(422, "validation_error", session.csrf_token),
                status_code=422,
            )
        except RagRejected as exc:
            return _rag_error(exc, session.csrf_token)
        except ServiceUnavailable:
            return _upstream_error(session.csrf_token)
        return _redirect(
            f"/admin/manuals/{quote(updated.manual_id, safe='')}"
        )

    @router.get("/admin/categories")
    async def categories_page(request: Request) -> HTMLResponse:
        session = _require_session(request, adapters)
        return _category_page(session)

    @router.post("/admin/categories")
    async def create_category(request: Request) -> Response:
        session = _require_session(request, adapters)
        form = await _form(request)
        _require_csrf(session, form)
        try:
            code, name, keywords = validate_category_fields(
                form.get("code", ""), form.get("name", ""), form.get("keywords", "")
            )
        except ValueError:
            return _category_page(
                session, 422, "Los datos de la categoría no son válidos."
            )
        try:
            create_query_category(code or "", name, keywords, adapters)
        except CategoryCodeTaken:
            return _category_page(session, 409, "category_code_taken")
        return _redirect("/admin/categories")

    # Esta ruta va antes que /admin/categories/{category_id} para que "threshold"
    # no se interprete como un id.
    @router.post("/admin/categories/threshold")
    async def update_threshold(request: Request) -> Response:
        session = _require_session(request, adapters)
        form = await _form(request)
        _require_csrf(session, form)
        try:
            value = parse_threshold(form.get("threshold", ""))
        except ValueError:
            return _category_page(session, 422, "El umbral debe estar entre 0 y 1.")
        set_classifier_threshold(value, adapters)
        return _redirect("/admin/categories")

    @router.post("/admin/categories/{category_id}")
    async def edit_category(category_id: str, request: Request) -> Response:
        session = _require_session(request, adapters)
        form = await _form(request)
        _require_csrf(session, form)
        try:
            _, name, keywords = validate_category_fields(
                None, form.get("name", ""), form.get("keywords", "")
            )
        except ValueError:
            return _category_page(
                session, 422, "Los datos de la categoría no son válidos."
            )
        try:
            update_query_category(category_id, name, keywords, adapters)
        except CategoryNotFound:
            return _category_page(session, 404, "category_not_found")
        return _redirect("/admin/categories")

    @router.get("/admin/texts")
    async def texts_page(request: Request) -> HTMLResponse:
        session = _require_session(request, adapters)
        return _html(
            admin.render_conversation_texts(
                conversation_texts(settings, adapters),
                session.csrf_token,
                versions=adapters.repository.current_text_versions(),
            )
        )

    @router.get("/admin/texts/{field}/historial")
    async def text_history_page(field: str, request: Request) -> HTMLResponse:
        session = _require_session(request, adapters)
        if field not in CONVERSATION_TEXT_FIELDS:
            return _html(
                admin.render_error(404, "not_found", session.csrf_token),
                status_code=404,
            )
        return _html(
            admin.render_text_history(
                field,
                text_history(field, settings, adapters),
                session.csrf_token,
            )
        )

    @router.post("/admin/texts")
    async def save_texts(request: Request) -> Response:
        session = _require_session(request, adapters)
        form = await _form(request)
        _require_csrf(session, form)
        actor = _actor(session, adapters)
        texts = _conversation_texts_from_form(form)
        if texts is None:
            return _html(
                admin.render_conversation_texts(
                    conversation_texts(settings, adapters),
                    session.csrf_token,
                    "El texto legal y su versión son obligatorios (máx. 4096).",
                    versions=adapters.repository.current_text_versions(),
                ),
                status_code=422,
            )
        current = conversation_texts(settings, adapters)
        changed_fields = [
            field
            for field in CONVERSATION_TEXT_FIELDS
            if getattr(texts, field) != getattr(current, field)
        ]
        try:
            update_conversation_texts(
                texts, session.profile_id, settings, adapters
            )
        except NoticeVersionRequired:
            _audit(actor, "texts_update", "notice_version_required", adapters)
            return _html(
                admin.render_conversation_texts(
                    conversation_texts(settings, adapters),
                    session.csrf_token,
                    "Debes indicar una versión nueva al cambiar el texto legal.",
                    versions=adapters.repository.current_text_versions(),
                ),
                status_code=422,
            )
        for field in changed_fields:
            _audit(actor, "texts_update", "ok", adapters, target=field)
        if not changed_fields:
            _audit(actor, "texts_update", "ok", adapters)
        return _redirect("/admin/texts")

    @router.get("/admin/supresiones")
    async def suppression_list(request: Request) -> HTMLResponse:
        session = _require_session(request, adapters)
        profile = adapters.repository.get_profile(session.profile_id)
        if profile is None:
            return _html(
                admin.render_error(403, "forbidden", session.csrf_token),
                status_code=403,
            )
        try:
            rows = suppression_queue(profile, settings, adapters)
        except DomainError as exc:
            _audit(profile, "suppression_queue_viewed", exc.code, adapters)
            return _html(
                admin.render_error(exc.status_code, exc.code, session.csrf_token),
                status_code=exc.status_code,
            )
        _audit(profile, "suppression_queue_viewed", "ok", adapters)
        return _html(
            advisor_panel.render_suppression_queue(
                rows, session.csrf_token, "/admin/supresiones"
            )
        )

    @router.post("/admin/supresiones/{request_id}/execute")
    async def suppression_execute(request_id: str, request: Request) -> Response:
        session = _require_session(request, adapters)
        form = await _form(request)
        _require_csrf(session, form)
        profile = adapters.repository.get_profile(session.profile_id)
        if profile is None:
            return _html(
                admin.render_error(403, "forbidden", session.csrf_token),
                status_code=403,
            )
        try:
            execute_suppression_from_panel(
                request_id, profile, form.get("note", ""), settings, adapters
            )
        except DomainError as exc:
            _audit(
                profile, "suppression_execute", exc.code, adapters,
                request_id=request_id,
            )
            return _html(
                admin.render_error(exc.status_code, exc.code, session.csrf_token),
                status_code=exc.status_code,
            )
        _audit(
            profile, "suppression_execute", "ok", adapters, request_id=request_id
        )
        return _redirect("/admin/supresiones")

    @router.post("/admin/categories/{category_id}/active")
    async def toggle_category(category_id: str, request: Request) -> Response:
        session = _require_session(request, adapters)
        form = await _form(request)
        _require_csrf(session, form)
        active_value = form.get("active", "")
        if active_value not in ("true", "false"):
            return _category_page(session, 422, "El estado debe ser true o false.")
        try:
            set_query_category_active(category_id, active_value == "true", adapters)
        except CategoryNotFound:
            return _category_page(session, 404, "category_not_found")
        return _redirect("/admin/categories")

    def _clients_page(session, status_code: int = 200, error: str | None = None):
        return _html(
            admin.render_clients(
                list_clients_admin(settings, adapters), session.csrf_token, error
            ),
            status_code=status_code,
        )

    @router.get("/admin/clientes")
    async def clients_page(request: Request) -> HTMLResponse:
        session = _require_session(request, adapters)
        return _clients_page(session)

    @router.post("/admin/clientes")
    async def create_client_page(request: Request) -> Response:
        session = _require_session(request, adapters)
        form = await _form(request)
        _require_csrf(session, form)
        actor = _actor(session, adapters)
        username = form.get("username", "")
        password = form.get("password", "")
        if (
            not USERNAME_PATTERN.fullmatch(username.lower())
            or len(password) < settings.profile_password_min_length
        ):
            _audit(actor, "client_create", "validation_error", adapters)
            return _clients_page(session, 422, "Datos del cliente no válidos.")
        offset = operational_settings(settings, adapters).hours.utc_offset_minutes
        try:
            valid_from = _form_date(form.get("valid_from", ""), offset)
            valid_until = _form_date(form.get("valid_until", ""), offset)
        except ValueError:
            _audit(actor, "client_create", "validation_error", adapters)
            return _clients_page(session, 422, "Las fechas no son válidas.")
        if (
            valid_from is not None
            and valid_until is not None
            and valid_until <= valid_from
        ):
            _audit(actor, "client_create", "validation_error", adapters)
            return _clients_page(
                session, 422, "La fecha final debe ser posterior a la inicial."
            )
        try:
            created = create_client(
                username, password, valid_from, valid_until, settings, adapters
            )
        except UsernameTaken:
            _audit(actor, "client_create", "username_taken", adapters)
            return _clients_page(session, 409, "username_taken")
        _audit(actor, "client_create", "ok", adapters, target=created.profile_id)
        return _redirect("/admin/clientes")

    @router.post("/admin/clientes/{profile_id}/renovar")
    async def renew_client(profile_id: str, request: Request) -> Response:
        session = _require_session(request, adapters)
        form = await _form(request)
        _require_csrf(session, form)
        actor = _actor(session, adapters)
        try:
            renew_credential(profile_id, settings, adapters)
        except ClientNotFound:
            _audit(actor, "client_renew", "client_not_found", adapters, target=profile_id)
            return _clients_page(session, 404, "client_not_found")
        except CredentialRevoked:
            _audit(actor, "client_renew", "credential_revoked", adapters, target=profile_id)
            return _clients_page(session, 409, "credential_revoked")
        _audit(actor, "client_renew", "ok", adapters, target=profile_id)
        return _redirect("/admin/clientes")

    @router.post("/admin/clientes/{profile_id}/revocar")
    async def revoke_client(profile_id: str, request: Request) -> Response:
        session = _require_session(request, adapters)
        form = await _form(request)
        _require_csrf(session, form)
        actor = _actor(session, adapters)
        try:
            revoke_credential(profile_id, settings, adapters)
        except ClientNotFound:
            _audit(actor, "client_revoke", "client_not_found", adapters, target=profile_id)
            return _clients_page(session, 404, "client_not_found")
        _audit(actor, "client_revoke", "ok", adapters, target=profile_id)
        return _redirect("/admin/clientes")

    @router.post("/admin/clientes/{profile_id}/cerrar-sesion")
    async def close_client(profile_id: str, request: Request) -> Response:
        session = _require_session(request, adapters)
        form = await _form(request)
        _require_csrf(session, form)
        actor = _actor(session, adapters)
        try:
            close_client_session(profile_id, settings, adapters)
        except ClientNotFound:
            _audit(
                actor, "client_close_session", "client_not_found", adapters,
                target=profile_id,
            )
            return _clients_page(session, 404, "client_not_found")
        _audit(actor, "client_close_session", "ok", adapters, target=profile_id)
        return _redirect("/admin/clientes")

    def _templates_page(session, status_code: int = 200, error: str | None = None):
        return _html(
            admin.render_templates(
                adapters.repository.list_whatsapp_templates(),
                session.csrf_token,
                error,
            ),
            status_code=status_code,
        )

    @router.get("/admin/plantillas")
    async def templates_page(request: Request) -> HTMLResponse:
        session = _require_session(request, adapters)
        return _templates_page(session)

    @router.post("/admin/plantillas")
    async def create_template_page(request: Request) -> Response:
        session = _require_session(request, adapters)
        form = await _form(request)
        _require_csrf(session, form)
        actor = _actor(session, adapters)
        try:
            create_template(
                form.get("name", ""),
                form.get("purpose", ""),
                form.get("language", ""),
                form.get("variables", ""),
                form.get("body", ""),
                actor,
                adapters,
            )
        except ValueError:
            _audit(actor, "template_create", "validation_error", adapters)
            return _templates_page(session, 422, "Datos de plantilla no válidos.")
        except TemplateExists:
            _audit(actor, "template_create", "template_exists", adapters)
            return _templates_page(session, 409, "template_exists")
        _audit(
            actor, "template_create", "ok", adapters,
            target=form.get("name", ""),
        )
        return _redirect("/admin/plantillas")

    @router.post("/admin/plantillas/{name}")
    async def update_template_page(name: str, request: Request) -> Response:
        session = _require_session(request, adapters)
        form = await _form(request)
        _require_csrf(session, form)
        actor = _actor(session, adapters)
        try:
            update_template(
                name,
                form.get("language", ""),
                form.get("variables", ""),
                form.get("body", ""),
                actor,
                adapters,
            )
        except TemplateNotFound:
            _audit(actor, "template_update", "template_not_found", adapters, target=name)
            return _templates_page(session, 404, "template_not_found")
        except ValueError:
            _audit(actor, "template_update", "validation_error", adapters, target=name)
            return _templates_page(session, 422, "Datos de plantilla no válidos.")
        _audit(actor, "template_update", "ok", adapters, target=name)
        return _redirect("/admin/plantillas")

    @router.post("/admin/plantillas/{name}/estado")
    async def template_status_page(name: str, request: Request) -> Response:
        session = _require_session(request, adapters)
        form = await _form(request)
        _require_csrf(session, form)
        actor = _actor(session, adapters)
        try:
            change_template_status(
                name, form.get("status", ""), actor, adapters
            )
        except TemplateNotFound:
            _audit(actor, "template_status", "template_not_found", adapters, target=name)
            return _templates_page(session, 404, "template_not_found")
        except TemplateTransitionInvalid:
            _audit(actor, "template_status", "invalid_transition", adapters, target=name)
            return _templates_page(session, 409, "invalid_transition")
        _audit(actor, "template_status", "ok", adapters, target=name)
        return _redirect("/admin/plantillas")

    def _settings_page(session, status_code: int = 200, error: str | None = None):
        return _html(
            admin.render_settings(
                _settings_view(settings, adapters), session.csrf_token, error
            ),
            status_code=status_code,
        )

    @router.get("/admin/ajustes")
    async def settings_page(request: Request) -> HTMLResponse:
        session = _require_session(request, adapters)
        return _settings_page(session)

    @router.post("/admin/ajustes")
    async def save_settings(request: Request) -> Response:
        session = _require_session(request, adapters)
        form = await _form(request)
        _require_csrf(session, form)
        actor = _actor(session, adapters)
        before = adapters.repository.get_app_settings(
            ("identity.", "expiry_notice.", "business_hours.", "suppression.")
        )
        try:
            save_operational_settings(form, actor, settings, adapters)
        except SettingsInvalid:
            _audit(actor, "settings_update", "validation_error", adapters)
            return _settings_page(session, 422, "Algún ajuste no es válido.")
        for spec in OPERATIONAL_SETTINGS:
            raw = form.get(spec.key, "").strip()
            previous = before.get(spec.key, "")
            if raw == previous:
                continue
            _audit(actor, "settings_update", "ok", adapters, target=spec.key)
        return _redirect("/admin/ajustes")

    @router.get("/admin/metricas")
    async def metrics_page(request: Request) -> HTMLResponse:
        session = _require_session(request, adapters)
        raw_days = request.query_params.get("dias", "7")
        try:
            days = int(raw_days)
        except (TypeError, ValueError):
            days = 0
        if days < 1 or days > 90:
            return _html(
                admin.render_error(422, "validation_error", session.csrf_token),
                status_code=422,
            )
        actor = _actor(session, adapters)
        metrics = admin_metrics(days, settings, adapters)
        _audit(actor, "metrics_viewed", "ok", adapters, target=str(days))
        return _html(admin.render_metrics(metrics, session.csrf_token))

    return router
