"""Websocket del panel en tiempo real (#53): handshake y ciclo de vida."""
from __future__ import annotations

from datetime import timedelta

import pytest
from starlette.websockets import WebSocketDisconnect

from orchestrator.accounts import hash_token

WS_SETTINGS = {
    "panel_ws_allowed_origins": "http://testserver",
    "panel_events_poll_seconds": 1,
}


def _ws(env, path: str = "/asesor/ws", origin: str | None = "http://testserver"):
    headers = {"host": "testserver"}
    if origin is not None:
        headers["origin"] = origin
    return env.client.websocket_connect(path, headers=headers)


def _rejected(env, path: str = "/asesor/ws", origin: str | None = "http://testserver"):
    with pytest.raises(WebSocketDisconnect):
        with _ws(env, path, origin) as ws:
            ws.receive_json()


def _login_non_panel(env, panel, role: str = "admin"):
    profile = panel.make_profile(env, "otro1", role, telegram_user_id=None)
    env.repo.create_session(
        hash_token("asesor-session"),
        profile.id,
        panel.CSRF,
        panel.NOW + timedelta(hours=1),
    )
    env.client.cookies.set("advisor_session", "asesor-session")
    return profile


def test_ws_rejects_without_session(env_factory):
    """R2: sin cookie de sesión se rechaza el handshake."""
    env = env_factory(**WS_SETTINGS)
    _rejected(env)


def test_ws_rejects_expired_session(env_factory, panel):
    """R2: una sesión expirada no abre el websocket."""
    env = env_factory(**WS_SETTINGS)
    profile = panel.make_profile(env, "asesor1", "asesor", 700)
    env.repo.create_session(
        hash_token("expired-session"),
        profile.id,
        panel.CSRF,
        panel.NOW - timedelta(minutes=1),
    )
    env.client.cookies.set("advisor_session", "expired-session")
    _rejected(env)


def test_ws_rejects_non_panel_role(env_factory, panel):
    """R2: un perfil sin rol de asesor ni supervisor se rechaza."""
    env = env_factory(**WS_SETTINGS)
    _login_non_panel(env, panel, "admin")
    _rejected(env)


def test_ws_rejects_missing_origin(env_factory, panel):
    """R3: sin cabecera `Origin` no se acepta el handshake."""
    env = env_factory(**WS_SETTINGS)
    panel.login(env)
    _rejected(env, origin=None)


def test_ws_rejects_foreign_origin(env_factory, panel):
    """R3, R4: un `Origin` que no está en la lista se rechaza aunque haya sesión."""
    env = env_factory(**WS_SETTINGS)
    panel.login(env)
    _rejected(env, origin="http://evil.test")


def test_ws_accepts_configured_origin(env_factory, panel):
    """R1, R4: con un `Origin` exacto de la lista el handshake se acepta."""
    env = env_factory(**WS_SETTINGS)
    panel.login(env)
    with _ws(env) as ws:
        assert ws.receive_json()["type"] == "hello"


def test_ws_scope_all_rejected_for_asesor(env_factory, panel):
    """R7: `scope=all` exige rol supervisor."""
    env = env_factory(**WS_SETTINGS)
    panel.login(env)
    _rejected(env, path="/asesor/ws?scope=all")


def test_ws_does_not_touch_presence(env_factory, panel):
    """R8: abrir el websocket no renueva la presencia del asesor."""
    env = env_factory(**WS_SETTINGS)
    panel.login(env)
    with _ws(env) as ws:
        ws.receive_json()
        assert env.repo.advisor_presence == {}


def test_ws_connection_limit_per_profile(env_factory, panel):
    """R9: el perfil no puede exceder el máximo de conexiones de la instancia."""
    env = env_factory(**WS_SETTINGS, panel_ws_max_connections_per_profile=1)
    panel.login(env)
    with _ws(env) as ws:
        ws.receive_json()
        _rejected(env)


def test_ws_closes_4401_after_logout(env_factory, panel):
    """R6: al invalidarse la sesión la conexión se cierra con 4401."""
    env = env_factory(**WS_SETTINGS)
    panel.login(env)
    with _ws(env) as ws:
        ws.receive_json()
        env.repo.delete_session(hash_token("asesor-session"))
        with pytest.raises(WebSocketDisconnect) as info:
            ws.receive_json()
    assert info.value.code == 4401


def test_ws_client_message_closes_1003(env_factory, panel):
    """R10: cualquier mensaje del cliente cierra con 1003 sin ejecutar nada."""
    env = env_factory(**WS_SETTINGS)
    panel.login(env)
    with _ws(env) as ws:
        ws.receive_json()
        ws.send_text("hola")
        with pytest.raises(WebSocketDisconnect) as info:
            ws.receive_json()
    assert info.value.code == 1003


def test_ws_first_message_is_hello_with_cursor(env_factory, panel):
    """R14: el primer mensaje es `hello` con el id del último evento existente."""
    env = env_factory(**WS_SETTINGS)
    panel.login(env)
    env.repo.publish_panel_event("case-1", "case_created", panel.NOW)
    with _ws(env) as ws:
        hello = ws.receive_json()
    assert hello == {"type": "hello", "cursor": 1}


def test_ws_disabled_rejects_handshake(env_factory, panel):
    """R35: con `PANEL_LIVE_ENABLED=false` el handshake se rechaza."""
    env = env_factory(panel_live_enabled=False, **WS_SETTINGS)
    panel.login(env)
    _rejected(env)
