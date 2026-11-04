"""Rutas públicas del login de clientes (`GET/POST /acceso`)."""
from __future__ import annotations

from urllib.parse import parse_qs

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from . import admin, identity_page
from .accounts import hash_token
from .admin_routes import client_ip
from .config import Settings
from .domain import (
    Adapters,
    ClientLoginFailed,
    CredentialNotEnabled,
    LoginLinkInvalid,
    LoginThrottled,
    SessionConflict,
    login_client,
)
from .identity import verify_login_token_signature

_HEADERS = {**admin.security_headers(), "Referrer-Policy": "no-referrer"}


def _html(content: str, status_code: int = 200) -> HTMLResponse:
    return HTMLResponse(content=content, status_code=status_code, headers=_HEADERS)


def _form(body: bytes) -> dict[str, str]:
    parsed = parse_qs(body.decode("utf-8"), keep_blank_values=True)
    return {key: values[-1] for key, values in parsed.items()}


def _link_is_valid(token: str, settings: Settings, adapters: Adapters) -> bool:
    if not verify_login_token_signature(
        token, settings.identity_link_signing_key.strip()
    ):
        return False
    return (
        adapters.repository.get_login_link(hash_token(token), adapters.clock())
        is not None
    )


def create_identity_router(settings: Settings, adapters: Adapters) -> APIRouter:
    router = APIRouter()

    @router.get("/acceso")
    async def login_page(request: Request) -> HTMLResponse:
        token = request.query_params.get("t", "")
        if not _link_is_valid(token, settings, adapters):
            return _html(identity_page.render_error(400), status_code=400)
        return _html(identity_page.render_login_form(token))

    @router.post("/acceso")
    async def login(request: Request) -> HTMLResponse:
        form = _form(await request.body())
        try:
            login_client(
                form.get("t", ""),
                form.get("username", ""),
                form.get("password", ""),
                client_ip(request, settings),
                settings,
                adapters,
            )
        except LoginLinkInvalid:
            return _html(identity_page.render_error(400), status_code=400)
        except ClientLoginFailed:
            return _html(identity_page.render_error(401), status_code=401)
        except CredentialNotEnabled:
            return _html(identity_page.render_error(403), status_code=403)
        except SessionConflict:
            return _html(identity_page.render_error(409), status_code=409)
        except LoginThrottled:
            return _html(identity_page.render_error(429), status_code=429)
        return _html(identity_page.render_success())

    return router
