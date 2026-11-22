"""#66: panel /admin/canales (alta, edición, activación, secretos)."""
from __future__ import annotations

import json
import logging

import httpx
import pytest
from fakes import channel_info
from lazaro_contracts import CHANNEL_ICONS, CaseListItem, ChannelCreateRequest

from orchestrator.adapters.channel_admin import (
    ChannelAdminError,
    ChannelAdminUnavailable,
    FakeChannelAdminClient,
    HttpChannelAdminClient,
)
from orchestrator.adapters.channels import FakeChannelDirectory
from orchestrator.admin_channels import contrast_ratio, valid_color, webhook_url

CSRF = "csrf-token"
CREDS = "token=abcdefgh1234\nphone_id=99887766"


@pytest.fixture()
def admin_env(env_factory, panel):
    def build(channels=None, adapter_types=("simulado", "whatsapp_cloud"), **settings):
        env = env_factory(**settings)
        fake = FakeChannelAdminClient(
            list(channels if channels is not None else [channel_info("simulado")]),
            adapter_types=list(adapter_types),
        )
        env.adapters.channel_admin = fake
        panel.login_admin(env)
        return env, fake

    return build


def _create_form(**overrides):
    form = {
        "csrf_token": CSRF,
        "id": "tienda",
        "name": "Tienda",
        "adapter_type": "simulado",
        "icon": "tienda",
        "color": "#1B6FA8",
        "consent_mode": "boton",
        "callback_url": "https://cliente.example/cb",
        "credentials": CREDS,
    }
    form.update(overrides)
    return form


def _edit_form(**overrides):
    form = {
        "csrf_token": CSRF,
        "name": "Simulado 2",
        "icon": "web",
        "color": "#1B6FA8",
        "consent_mode": "texto",
    }
    form.update(overrides)
    return form


def _audits(env, action=None):
    return [a for a in env.repo.panel_audit if action is None or a.action == action]


def _mutations(fake):
    return [c for c in fake.calls if c[0] != "list"]


# ── R7–R9: acceso, CSRF y navegación ─────────────────────────────────────────


@pytest.mark.parametrize(
    "method,path",
    [
        ("get", "/admin/canales"),
        ("post", "/admin/canales"),
        ("post", "/admin/canales/simulado"),
        ("post", "/admin/canales/simulado/activo"),
        ("post", "/admin/canales/simulado/secreto"),
        ("post", "/admin/canales/simulado/secreto/regenerar"),
    ],
)
def test_without_admin_session_redirects_without_gateway(env, method, path):
    """R7"""
    fake = FakeChannelAdminClient([channel_info("simulado")], adapter_types=["simulado"])
    env.adapters.channel_admin = fake
    kwargs = {"data": {"csrf_token": CSRF}} if method == "post" else {}
    response = getattr(env.client, method)(path, follow_redirects=False, **kwargs)
    assert response.status_code in (302, 303)
    assert "/admin/login" in response.headers["location"]
    assert fake.calls == []


def test_advisor_session_cannot_open_channels(env, panel):
    """R7: un asesor no es admin."""
    fake = FakeChannelAdminClient([channel_info("simulado")])
    env.adapters.channel_admin = fake
    panel.login(env, "asesor")
    response = env.client.get("/admin/canales", follow_redirects=False)
    assert response.status_code in (302, 303)
    assert fake.calls == []


@pytest.mark.parametrize(
    "path",
    [
        "/admin/canales",
        "/admin/canales/simulado",
        "/admin/canales/simulado/activo",
        "/admin/canales/simulado/secreto",
        "/admin/canales/simulado/secreto/regenerar",
    ],
)
@pytest.mark.parametrize("token", [None, "malo"])
def test_bad_csrf_is_403_without_gateway(admin_env, path, token):
    """R8"""
    env, fake = admin_env()
    data = _create_form() | {"active": "false", "confirmar": "si"}
    data.pop("csrf_token")
    if token is not None:
        data["csrf_token"] = token
    response = env.client.post(path, data=data, follow_redirects=False)
    assert response.status_code == 403
    assert fake.calls == []


def test_nav_shows_channels(admin_env):
    """R9"""
    env, _ = admin_env()
    response = env.client.get("/admin")
    assert 'href="/admin/canales"' in response.text
    assert "Canales" in response.text


# ── R10–R17: listar, crear, editar y validar ─────────────────────────────────


def test_listing_shows_fields_and_hints_without_secret(admin_env):
    """R10, R21, R31"""
    info = channel_info("simulado", name="Pruebas").model_copy(
        update={"credential_hints": {"token": "…1234"}, "icon": "tienda"}
    )
    env, fake = admin_env([info])
    fake.secrets["simulado"] = "S9" + "z" * 41
    response = env.client.get("/admin/canales")
    assert response.status_code == 200
    text = response.text
    for piece in ("Pruebas", "simulado", "Activo", "texto", "token …1234"):
        assert piece in text
    assert CHANNEL_ICONS["tienda"] in text
    assert 'fill="#1B6FA8"' in text and 'fill="#FFFFFF"' in text
    assert fake.secrets["simulado"] not in text
    assert response.headers["cache-control"] == "no-store"


def test_create_offers_only_gateway_adapter_types(admin_env):
    """R11"""
    env, _ = admin_env(adapter_types=["simulado"])
    text = env.client.get("/admin/canales").text
    assert '<option value="simulado">' in text
    assert '<option value="whatsapp_cloud">' not in text


def test_create_sends_request_and_shows_secret_once(admin_env):
    """R12, R25, R29, R32"""
    env, fake = admin_env()
    response = env.client.post("/admin/canales", data=_create_form())
    assert response.status_code == 200
    (call,) = _mutations(fake)
    request: ChannelCreateRequest = call[1]
    assert (request.id, request.name, request.adapter_type, request.icon) == (
        "tienda", "Tienda", "simulado", "tienda",
    )
    assert request.config == {
        "consent_mode": "boton",
        "callback_url": "https://cliente.example/cb",
    }
    assert request.credentials == {"token": "abcdefgh1234", "phone_id": "99887766"}
    secret = fake.secrets["tienda"]
    assert response.text.count(secret) == 1
    assert 'data-copy="secreto-revelado"' in response.text
    assert response.headers["cache-control"] == "no-store"
    assert env.adapters.channels.invalidations == 1
    (audit,) = _audits(env, "channel_create")
    assert (audit.target, audit.result) == ("tienda", "ok")
    # El listado posterior ya no muestra el secreto.
    assert secret not in env.client.get("/admin/canales").text


def test_edit_sends_patch_and_keeps_credentials_when_empty(admin_env):
    """R13, R29, R32"""
    env, fake = admin_env()
    response = env.client.post("/admin/canales/simulado", data=_edit_form())
    assert response.status_code == 200
    (call,) = _mutations(fake)
    assert call[0] == "update" and call[1] == "simulado"
    body = call[2]
    assert "credentials" not in body.model_fields_set
    assert (body.name, body.icon, body.config["consent_mode"]) == ("Simulado 2", "web", "texto")
    assert env.adapters.channels.invalidations == 1
    (audit,) = _audits(env, "channel_update")
    assert (audit.target, audit.result) == ("simulado", "ok")


def test_edit_with_credentials_sends_them_and_shows_hints(admin_env):
    """R13, R10"""
    env, fake = admin_env()
    response = env.client.post(
        "/admin/canales/simulado", data=_edit_form(credentials=CREDS)
    )
    assert response.status_code == 200
    body = _mutations(fake)[0][2]
    assert body.credentials == {"token": "abcdefgh1234", "phone_id": "99887766"}
    assert "token …1234" in response.text
    assert "abcdefgh1234" not in response.text


def test_edit_can_clear_callback_url(admin_env):
    """R12: la URL de callback es opcional y se puede quitar."""
    info = channel_info("simulado").model_copy(
        update={"config": {"consent_mode": "texto", "callback_url": "https://x.example/cb"}}
    )
    env, fake = admin_env([info])
    env.client.post("/admin/canales/simulado", data=_edit_form(clear_callback_url="si"))
    assert "callback_url" not in _mutations(fake)[0][2].config


def test_managed_channel_offers_no_credentials_secret_or_webhook(admin_env):
    """R14"""
    managed = channel_info("telegram", name="Telegram").model_copy(
        update={"managed_by_environment": True}
    )
    env, fake = admin_env([managed])
    text = env.client.get("/admin/canales").text
    assert 'name="credentials"' not in text.split("Nuevo canal")[0]
    assert "/admin/canales/telegram/secreto" not in text
    assert "/webhooks/telegram" not in text
    response = env.client.post(
        "/admin/canales/telegram", data=_edit_form(credentials=CREDS)
    )
    assert response.status_code == 200
    assert "credentials" not in _mutations(fake)[0][2].model_fields_set


@pytest.mark.parametrize(
    "overrides",
    [
        {"icon": "cohete"},  # R15
        {"color": "rojo"},  # R16
        {"color": "#FFFF00"},  # R16: contraste insuficiente con blanco
        {"credentials": "sin_igual"},  # R17
        {"credentials": "Mayus=valor"},  # R17
        {"credentials": "a=1\na=2"},  # R17
        {"callback_url": "http://inseguro.example"},
        {"name": ""},
        {"id": "X"},
    ],
)
def test_invalid_create_is_422_without_gateway(admin_env, overrides):
    """R15, R16, R17"""
    env, fake = admin_env()
    response = env.client.post("/admin/canales", data=_create_form(**overrides))
    assert response.status_code == 422
    assert 'role="alert"' in response.text
    assert _mutations(fake) == []
    assert env.adapters.channels.invalidations == 0
    (audit,) = _audits(env, "channel_create")
    assert audit.result == "validation_error"


def test_invalid_edit_is_422_without_gateway(admin_env):
    """R15"""
    env, fake = admin_env()
    response = env.client.post("/admin/canales/simulado", data=_edit_form(icon="nope"))
    assert response.status_code == 422
    assert _mutations(fake) == []


def test_edit_unknown_channel_is_404(admin_env):
    env, fake = admin_env()
    response = env.client.post("/admin/canales/otro", data=_edit_form())
    assert response.status_code == 404
    assert _mutations(fake) == []


def test_contrast_rule():
    """R16"""
    assert contrast_ratio("#FFFFFF", "#000000") == pytest.approx(21, rel=1e-3)
    assert valid_color("#1B6FA8")
    assert not valid_color("#FFFF00")
    assert not valid_color("#12345")


# ── R18–R19: errores del gateway ─────────────────────────────────────────────


@pytest.mark.parametrize(
    "status,code", [(409, "channel_exists"), (422, "validation_error")]
)
def test_gateway_rejection_passes_status(admin_env, status, code):
    """R18"""
    env, fake = admin_env()
    fake.error = ChannelAdminError(status, code)
    response = env.client.post("/admin/canales", data=_create_form())
    assert response.status_code == status
    assert 'role="alert"' in response.text
    assert env.adapters.channels.invalidations == 0
    (audit,) = _audits(env, "channel_create")
    assert audit.result == code


def test_duplicate_id_is_409(admin_env):
    """R18"""
    env, _ = admin_env()
    response = env.client.post("/admin/canales", data=_create_form(id="simulado"))
    assert response.status_code == 409
    assert "Ya existe un canal" in response.text


@pytest.mark.parametrize(
    "path,data",
    [
        ("/admin/canales", {}),
        ("/admin/canales/simulado/activo", {"active": "false"}),
        ("/admin/canales/simulado/secreto", {}),
        ("/admin/canales/simulado/secreto/regenerar", {"confirmar": "si"}),
    ],
)
def test_gateway_unavailable_is_502(admin_env, path, data):
    """R19"""
    env, fake = admin_env()
    fake.fail = True
    form = (_create_form() if path == "/admin/canales" else {"csrf_token": CSRF}) | data
    response = env.client.post(path, data=form)
    assert response.status_code == 502


def test_listing_unavailable_is_502(admin_env):
    """R19"""
    env, fake = admin_env()
    fake.fail = True
    assert env.client.get("/admin/canales").status_code == 502


# ── R20–R25: webhook y secreto ───────────────────────────────────────────────


def test_webhook_url_with_public_base(admin_env):
    """R20, R30"""
    env, _ = admin_env(gateway_public_base_url="https://gw.example/")
    text = env.client.get("/admin/canales").text
    assert 'value="https://gw.example/webhooks/simulado"' in text
    assert 'data-copy="webhook-simulado"' in text
    assert "Configura GATEWAY_PUBLIC_BASE_URL" not in text
    assert '<script src="/admin/static/canales.js" defer></script>' in text
    assert "<script>" not in text


def test_webhook_url_without_base_shows_notice(admin_env):
    """R20"""
    env, _ = admin_env()
    text = env.client.get("/admin/canales").text
    assert 'value="/webhooks/simulado"' in text
    assert "Configura GATEWAY_PUBLIC_BASE_URL" in text


def test_webhook_url_helper():
    """R20"""
    assert webhook_url("https://a.example", "x1") == ("https://a.example/webhooks/x1", True)
    assert webhook_url("", "x1") == ("/webhooks/x1", False)
    assert webhook_url("http://a.example", "x1") == ("/webhooks/x1", False)


def test_reveal_secret_shows_it_and_audits_without_value(admin_env, caplog):
    """R22, R24, R25"""
    env, fake = admin_env()
    fake.secrets["simulado"] = "S7" + "q" * 41
    caplog.set_level(logging.DEBUG)
    response = env.client.post("/admin/canales/simulado/secreto", data={"csrf_token": CSRF})
    assert response.status_code == 200
    assert fake.secrets["simulado"] in response.text
    assert 'data-copy="secreto-revelado"' in response.text
    assert response.headers["cache-control"] == "no-store"
    (audit,) = _audits(env, "channel_secret_reveal")
    assert (audit.target, audit.result) == ("simulado", "ok")
    assert fake.secrets["simulado"] not in repr(env.repo.panel_audit)
    assert fake.secrets["simulado"] not in caplog.text
    assert env.adapters.channels.invalidations == 0


def test_regenerate_requires_confirmation(admin_env):
    """R23"""
    env, fake = admin_env()
    response = env.client.post(
        "/admin/canales/simulado/secreto/regenerar", data={"csrf_token": CSRF}
    )
    assert response.status_code == 422
    assert _mutations(fake) == []


def test_regenerate_shows_new_secret_and_audits(admin_env, caplog):
    """R23, R24"""
    env, fake = admin_env()
    caplog.set_level(logging.DEBUG)
    response = env.client.post(
        "/admin/canales/simulado/secreto/regenerar",
        data={"csrf_token": CSRF, "confirmar": "si"},
    )
    assert response.status_code == 200
    secret = fake.secrets["simulado"]
    assert secret in response.text
    (audit,) = _audits(env, "channel_secret_regenerate")
    assert (audit.target, audit.result) == ("simulado", "ok")
    assert secret not in repr(env.repo.panel_audit)
    assert secret not in caplog.text


def test_credentials_never_in_audit_or_logs(admin_env, caplog):
    """R24"""
    env, _ = admin_env()
    caplog.set_level(logging.DEBUG)
    env.client.post("/admin/canales", data=_create_form())
    env.client.post("/admin/canales/simulado", data=_edit_form(credentials=CREDS))
    for value in ("abcdefgh1234", "99887766"):
        assert value not in repr(env.repo.panel_audit)
        assert value not in caplog.text


# ── R26–R29: activar y desactivar ────────────────────────────────────────────


def test_toggle_active_calls_gateway_and_audits(admin_env):
    """R26, R29, R32"""
    env, fake = admin_env()
    response = env.client.post(
        "/admin/canales/simulado/activo", data={"csrf_token": CSRF, "active": "false"}
    )
    assert response.status_code == 200
    assert _mutations(fake) == [("set_active", "simulado", False)]
    assert "Inactivo" in response.text and "Activar" in response.text
    assert env.adapters.channels.invalidations == 1
    (audit,) = _audits(env, "channel_active")
    assert audit.result == "ok" and audit.target.startswith("simulado")


def test_toggle_rejects_invalid_state(admin_env):
    """R26"""
    env, fake = admin_env()
    response = env.client.post(
        "/admin/canales/simulado/activo", data={"csrf_token": CSRF, "active": "tal vez"}
    )
    assert response.status_code == 422
    assert _mutations(fake) == []


def test_inbox_keeps_cases_of_inactive_channel(env, panel):
    """R28"""
    infos = [channel_info("telegram", name="Telegram", active=False)]
    env.adapters.channels.set_infos(infos)
    panel.login(env, "asesor")
    panel.link_case(env, "case-1", channel="telegram")
    env.handover.case_list = [
        CaseListItem(
            case_id="case-1",
            status="open",
            created_at=env.adapters.clock(),
            actions=["reply", "assign", "close"],
        )
    ]
    response = env.client.get("/asesor/cases")
    assert response.status_code == 200
    assert "case-1" in response.text


def test_invalidate_failure_does_not_break_panel(admin_env):
    """R29: invalidar nunca hace fallar la operación."""
    env, _ = admin_env()

    class Boom(FakeChannelDirectory):
        def invalidate(self):
            raise RuntimeError("x")

    env.adapters.channels = Boom()
    response = env.client.post(
        "/admin/canales/simulado/activo", data={"csrf_token": CSRF, "active": "false"}
    )
    assert response.status_code == 200


# ── R30: script propio ───────────────────────────────────────────────────────


def test_copy_script_served_same_origin(env):
    """R30"""
    response = env.client.get("/admin/static/canales.js")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/javascript")
    assert "data-copy" in response.text
    assert "default-src 'self'" in response.headers["content-security-policy"]


# ── Cliente HTTP ─────────────────────────────────────────────────────────────


def _http_client(handler):
    return HttpChannelAdminClient(
        "http://gw", "tok", transport=httpx.MockTransport(handler)
    )


def _info_json(channel_id="simulado"):
    return json.loads(channel_info(channel_id).model_dump_json())


def test_http_client_sends_token_and_parses():
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(200, json={"channels": [_info_json()], "adapter_types": ["simulado"]})

    listing = _http_client(handler).list()
    assert listing.channels[0].id == "simulado"
    assert seen[0].headers["x-service-token"] == "tok"
    assert seen[0].url.path == "/channels"


def test_http_client_set_active_patch():
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(200, json=_info_json())

    _http_client(handler).set_active("simulado", False)
    assert seen[0].method == "PATCH"
    assert seen[0].url.path == "/channels/simulado/active"
    assert json.loads(seen[0].content) == {"active": False}


def test_http_client_maps_4xx_to_error():
    def handler(request):
        return httpx.Response(409, json={"error": "channel_exists"})

    with pytest.raises(ChannelAdminError) as caught:
        _http_client(handler).reveal_secret("simulado")
    assert (caught.value.status, caught.value.code) == (409, "channel_exists")


@pytest.mark.parametrize("status", [401, 500, 503])
def test_http_client_maps_5xx_and_401_to_unavailable(status):
    def handler(request):
        return httpx.Response(status, json={"error": "x"})

    with pytest.raises(ChannelAdminUnavailable):
        _http_client(handler).list()


def test_http_client_network_error_is_unavailable():
    def handler(request):
        raise httpx.ConnectError("caído")

    with pytest.raises(ChannelAdminUnavailable):
        _http_client(handler).regenerate_secret("simulado")


def test_http_client_invalid_body_is_unavailable():
    def handler(request):
        return httpx.Response(200, json={"nada": 1})

    with pytest.raises(ChannelAdminUnavailable):
        _http_client(handler).list()
