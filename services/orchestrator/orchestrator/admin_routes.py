"""Router HTTP del panel administrativo (HTML renderizado en el servidor)."""
from __future__ import annotations

import hmac
from urllib.parse import parse_qs, quote

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from lazaro_contracts import ChunkActiveRequest, ChunkUpdateRequest, ManualUploadRequest
from pydantic import ValidationError
from starlette.datastructures import UploadFile as StarletteUploadFile

from . import admin
from .accounts import ROLES, USERNAME_PATTERN, hash_token
from .classifier import parse_threshold, validate_category_fields
from .config import Settings
from .domain import (
    Adapters,
    CategoryCodeTaken,
    CategoryNotFound,
    LastAdmin,
    LoginThrottled,
    ProfileNotFound,
    RagRejected,
    ServiceUnavailable,
    UsernameTaken,
    authenticate_admin,
    change_role,
    classifier_threshold,
    create_profile,
    create_query_category,
    issue_link_token,
    list_profiles,
    list_query_categories,
    recent_events,
    set_classifier_threshold,
    set_query_category_active,
    update_query_category,
)

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

    return router
