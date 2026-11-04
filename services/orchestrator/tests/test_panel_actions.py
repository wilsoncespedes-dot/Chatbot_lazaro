"""Transferir, resolver, devolver y presencia del panel multicanal (#41)."""
from __future__ import annotations

from datetime import timedelta

import pytest


def _post(env, path: str, data: dict):
    return env.client.post(path, data=data, follow_redirects=False)


def _transfer(env, panel, target_profile_id: str = "target"):
    return _post(
        env,
        "/asesor/transfer",
        {
            "csrf_token": panel.CSRF,
            "case_id": "case-1",
            "target_profile_id": target_profile_id,
        },
    )


def _target(env, panel, role: str = "asesor", telegram_user_id: int | None = 222,
            available: bool = True):
    profile = panel.make_profile(env, "destino", role, telegram_user_id)
    if available and telegram_user_id is not None:
        panel.set_presence(env, profile.id, "available")
    return profile


def test_transfer_success_records_handover_and_event(env_factory, panel):
    """R32, R35: transfiere al perfil disponible y registra advisor_transfer."""
    env = env_factory()
    actor = panel.login(env)
    panel.link_case(env, "case-1")
    target = _target(env, panel, available=True)

    response = _transfer(env, panel, target.id)

    assert response.status_code == 303
    assert response.headers["location"] == "/asesor?ok=transfer"
    assert env.handover.transferred == [("case-1", "700", "222")]
    assert any(
        event.type == "advisor_transfer"
        and event.reason == "case:case-1 from:700 to:222"
        for event in env.repo.events
    )
    assert target.id != actor.id


@pytest.mark.parametrize(
    "setup",
    ["missing", "client", "unlinked", "self"],
)
def test_transfer_invalid_target_is_422_without_handover(env_factory, setup, panel):
    """R33: destino inexistente, no asesor, sin Telegram o el propio actor."""
    env = env_factory()
    actor = panel.login(env)
    panel.link_case(env, "case-1")
    if setup == "missing":
        target_id = "no-existe"
    elif setup == "client":
        target_id = _target(env, panel, role="cliente").id
    elif setup == "unlinked":
        target_id = _target(env, panel, telegram_user_id=None).id
    else:
        target_id = actor.id
    response = _transfer(env, panel, target_id)
    assert response.status_code == 422
    assert 'data-code="validation_error"' in response.text
    assert env.handover.transferred == []


def test_transfer_away_target_is_409_without_handover(env_factory, panel):
    """R34: un destino con presencia `away` responde 409 advisor_unavailable."""
    env = env_factory()
    panel.login(env)
    panel.link_case(env, "case-1")
    target = _target(env, panel, available=False)
    response = _transfer(env, panel, target.id)
    assert response.status_code == 409
    assert 'data-code="advisor_unavailable"' in response.text
    assert env.handover.transferred == []


@pytest.mark.parametrize(
    ("attribute", "value", "status", "code"),
    [
        ("transfer_error", "forbidden", 403, "forbidden"),
        ("transfer_error", "not_found", 404, "not_found"),
        ("transfer_error", "case_closed", 409, "case_closed"),
        ("transfer_error", "validation_error", 422, "validation_error"),
        ("fail_transfer", True, 502, "upstream_error"),
    ],
)
def test_transfer_maps_handover_errors(env_factory, attribute, value, status, code, panel):
    """R32-R35: los errores de handover se traducen a páginas fijas."""
    env = env_factory()
    panel.login(env)
    panel.link_case(env, "case-1")
    target = _target(env, panel)
    setattr(env.handover, attribute, value)
    response = _transfer(env, panel, target.id)
    assert response.status_code == status
    assert f'data-code="{code}"' in response.text


def test_resolve_keeps_closed_reply_and_state(env_factory, panel):
    """R36: resolver conserva CASE_CLOSED_REPLY y aplica ADVISOR_RESOLVED."""
    env = env_factory()
    panel.login(env)
    contact = panel.link_case(env, "case-1")
    env.repo.set_conversation_state(contact.id, "with_advisor", panel.NOW)

    response = _post(
        env, "/asesor/close", {"csrf_token": panel.CSRF, "case_id": "case-1"}
    )

    assert response.status_code == 303
    assert env.handover.authorized[-1] == ("case-1", "700", "close")
    assert env.handover.closed == [("case-1", "700")]
    assert (contact.chat_id, env.settings.case_closed_reply) in env.gateway.sent
    assert env.repo.get_conversation_state(contact.id) == "active"


def test_return_closes_sends_return_reply_and_records_event(env_factory, panel):
    """R37, R38: devolver cierra, envía ADVISOR_RETURN_REPLY y deja evento."""
    env = env_factory()
    panel.login(env)
    contact = panel.link_case(env, "case-1")
    env.repo.set_conversation_state(contact.id, "with_advisor", panel.NOW)

    response = _post(
        env, "/asesor/return", {"csrf_token": panel.CSRF, "case_id": "case-1"}
    )

    assert response.status_code == 303
    assert env.handover.closed == [("case-1", "700")]
    assert (contact.chat_id, env.settings.advisor_return_reply) in env.gateway.sent
    assert env.repo.get_conversation_state(contact.id) == "active"
    assert any(
        event.type == "advisor_returned"
        and event.reason == "case:case-1 advisor:700"
        for event in env.repo.events
    )


@pytest.mark.parametrize("path", ["/asesor/close", "/asesor/return"])
def test_whatsapp_closed_skips_notice_but_closes_case(env_factory, path, panel):
    """R39: con WhatsApp cerrada no se envía aviso y se registra notice_skipped."""
    env = env_factory()
    panel.login(env)
    contact = panel.link_case(
        env, "case-1", channel="whatsapp", user="57300", chat="57301"
    )

    response = _post(env, path, {"csrf_token": panel.CSRF, "case_id": "case-1"})

    assert response.status_code == 303
    assert env.handover.closed == [("case-1", "700")]
    assert env.gateway.channel_sent == []
    assert any(
        event.type == "notice_skipped" and event.reason == "window_closed"
        for event in env.repo.events
    )
    assert contact.channel == "whatsapp"


@pytest.mark.parametrize("status", ["available", "away"])
def test_presence_is_stored_with_now(env_factory, status, panel):
    """R56: POST /asesor/presence guarda estado y last_seen_at."""
    env = env_factory()
    profile = panel.login(env)
    response = _post(
        env, "/asesor/presence", {"csrf_token": panel.CSRF, "status": status}
    )
    assert response.status_code == 303
    assert env.repo.advisor_presence[profile.id] == (status, panel.NOW)


def test_invalid_presence_is_422_without_changing_state(env_factory, panel):
    """R57: un estado inválido no cambia la presencia."""
    env = env_factory()
    profile = panel.login(env)
    panel.set_presence(env, profile.id, "available", panel.NOW - timedelta(minutes=1))
    response = _post(
        env, "/asesor/presence", {"csrf_token": panel.CSRF, "status": "invisible"}
    )
    assert response.status_code == 422
    assert env.repo.advisor_presence[profile.id][0] == "available"


def test_protected_request_touches_last_seen_keeping_status(env_factory, panel):
    """R58: una petición protegida actualiza last_seen sin cambiar el estado."""
    env = env_factory()
    profile = panel.login(env)
    panel.set_presence(env, profile.id, "available", panel.NOW - timedelta(hours=1))
    response = env.client.get("/asesor")
    assert response.status_code == 200
    assert env.repo.advisor_presence[profile.id] == ("available", panel.NOW)


def test_logout_sets_presence_away(env_factory, panel):
    """R59: cerrar sesión guarda la presencia como away."""
    env = env_factory()
    profile = panel.login(env)
    panel.set_presence(env, profile.id, "available")
    response = _post(env, "/asesor/logout", {"csrf_token": panel.CSRF})
    assert response.status_code == 303
    assert env.repo.advisor_presence[profile.id][0] == "away"
