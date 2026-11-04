"""Rutas `/acceso` y `/clients` de identidad (#38, T19-T21)."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from orchestrator.accounts import hash_token
from orchestrator.domain import create_client, issue_login_link

NOW = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
BASE = "https://orchestrator.example"
KEY = "k" * 32
PASSWORD = "clave-segura-123"
SERVICE_TOKEN = "svc-token"
HEADERS = {"X-Service-Token": SERVICE_TOKEN}


def _env(env_factory, **overrides):
    values = {
        "identity_login_required": True,
        "identity_public_base_url": BASE,
        "identity_link_signing_key": KEY,
        "password_scrypt_n": 16384,
    }
    values.update(overrides)
    return env_factory(**values)


def _client(env, username: str = "cliente1"):
    return create_client(
        username,
        PASSWORD,
        NOW - timedelta(days=1),
        NOW + timedelta(days=30),
        env.settings,
        env.adapters,
    )


def _contact(env, user: int = 10, chat: int = 100):
    return env.repo.get_or_create_contact(user, chat, NOW)


def _link(env, user: int = 10, chat: int = 100) -> str:
    contact = _contact(env, user, chat)
    url = issue_login_link(contact, env.settings, env.adapters)
    return url.split("t=", 1)[1]


def _post_login(env, token: str, username: str = "cliente1", password: str = PASSWORD, **extra):
    data = {"t": token, "username": username, "password": password, **extra}
    return env.client.post("/acceso", data=data)


# --- R10, R11, R12 ---------------------------------------------------------------


def test_get_with_valid_token_shows_form_without_consuming_it(env_factory):
    """R10, R11: formulario con `t` oculto, token intacto y encabezados seguros."""
    env = _env(env_factory)
    _client(env)
    token = _link(env)

    response = env.client.get("/acceso", params={"t": token})

    assert response.status_code == 200
    assert f'name="t" value="{token}"' in response.text
    assert 'name="username"' in response.text
    assert 'name="password"' in response.text
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["referrer-policy"] == "no-referrer"
    assert "default-src 'self'" in response.headers["content-security-policy"]
    assert env.repo.get_login_link(hash_token(token), NOW) is not None


def test_login_page_has_no_external_resources(env_factory):
    """R10: HTML propio, sin CDN ni recursos de dominios externos."""
    env = _env(env_factory)
    _client(env)
    token = _link(env)

    text = env.client.get("/acceso", params={"t": token}).text

    assert "http://" not in text and "https://" not in text
    assert "<script" not in text


def test_invalid_or_used_token_returns_400_without_credentials(env_factory):
    """R12: enlace inválido o usado → 400 genérico y sin validar credenciales."""
    env = _env(env_factory)
    _client(env)
    token = _link(env)
    _post_login(env, token)
    consumed = env.client.get("/acceso", params={"t": token})
    unknown = env.client.get("/acceso", params={"t": "nonce.firma"})

    assert consumed.status_code == 400
    assert unknown.status_code == 400
    assert "no es válido" in consumed.text and PASSWORD not in consumed.text


def test_acceso_is_public_but_similar_paths_require_service_token(env_factory):
    """R11: `/acceso` no exige token interno; `/acceso/otra` sí."""
    env = _env(env_factory)
    _client(env)
    token = _link(env)

    assert env.client.get("/acceso", params={"t": token}).status_code == 200
    assert env.client.get("/acceso/otra").status_code == 401


# --- R14, R17, R18 ----------------------------------------------------------------


def test_post_success_creates_session_from_the_link_contact(env_factory):
    """R14, R17, R18: campos extra ignorados y contacto tomado del enlace."""
    env = _env(env_factory)
    profile = _client(env)
    contact = _contact(env, 10, 100)
    token = _link(env)

    response = _post_login(
        env,
        token,
        contact_id="otro",
        external_chat_id="999",
        telegram_user_id="777",
    )

    assert response.status_code == 200
    session = env.repo.get_active_session_by_contact(contact.id)
    assert session is not None and session.profile_id == profile.profile_id
    assert env.repo.get_active_session_by_contact("otro") is None
    assert env.repo.get_profile(profile.profile_id).telegram_user_id is None
    assert env.repo.get_login_link(hash_token(token), NOW) is None


def test_whatsapp_login_associates_the_whatsapp_contact(env_factory):
    """R14, R18: un contacto WhatsApp se asocia sin usar columnas de Telegram."""
    env = _env(env_factory)
    profile = _client(env)
    contact = env.repo.get_or_create_channel_contact("whatsapp", "57300", "chat-57300", NOW)
    token = issue_login_link(contact, env.settings, env.adapters).split("t=", 1)[1]

    response = _post_login(env, token)

    assert response.status_code == 200
    assert env.repo.get_active_session_by_contact(contact.id).profile_id == profile.profile_id
    assert contact.telegram_user_id is None


# --- R21, R23, R26, R36 -----------------------------------------------------------


def test_error_status_mapping_and_no_password_echo(env_factory):
    """R12, R21, R26, R36: 401/403/409 con HTML genérico sin eco de la clave."""
    env = _env(env_factory)
    profile = _client(env)
    token = _link(env)

    wrong = _post_login(env, token, password="incorrecta")
    assert wrong.status_code == 401
    assert PASSWORD not in wrong.text and "incorrecta" not in wrong.text

    env.repo.revoke_client_credential(profile.profile_id, NOW)
    denied = _post_login(env, token)
    assert denied.status_code == 403

    env = _env(env_factory)
    _client(env)
    first_token = _link(env, 10, 100)
    second_token = _link(env, 11, 101)
    assert _post_login(env, first_token).status_code == 200
    conflict = _post_login(env, second_token)
    assert conflict.status_code == 409
    assert "sesión activa" in conflict.text


def test_five_failures_return_429_even_with_correct_password(env_factory):
    """R23: el bloqueo responde 429 antes de verificar la contraseña."""
    env = _env(env_factory)
    _client(env)
    token = _link(env)
    for _ in range(5):
        assert _post_login(env, token, password="incorrecta").status_code == 401

    throttled = _post_login(env, token)

    assert throttled.status_code == 429
    assert env.repo.get_login_link(hash_token(token), NOW) is not None


# --- R38, R39, R42, R45, R46: /clients -------------------------------------------


def test_clients_routes_require_service_token(env_factory):
    """R38: las rutas internas responden 401 sin X-Service-Token."""
    env = _env(env_factory)
    response = env.client.post(
        "/clients",
        json={"username": "cliente1", "password": PASSWORD},
    )
    assert response.status_code == 401


def test_post_clients_returns_201_without_hash_or_password(env_factory):
    """R38, R45: respuesta de estado sin hash y hash scrypt guardado."""
    env = _env(env_factory)
    response = env.client.post(
        "/clients",
        json={"username": "Cliente1", "password": PASSWORD},
        headers=HEADERS,
    )

    assert response.status_code == 201
    body = response.json()
    assert body["username"] == "cliente1"
    assert body["status"] in ("vigente", "por_vencer")
    assert set(body) == {
        "profile_id",
        "username",
        "status",
        "valid_from",
        "valid_until",
        "days_remaining",
        "has_active_session",
    }
    assert PASSWORD not in response.text and "scrypt$" not in response.text
    assert env.repo.profiles[body["profile_id"]].password_hash.startswith("scrypt$")


def test_get_renew_revoke_and_close_session(env_factory):
    """R39, R42, R45, R46: estado, renovación, revocación y cierre."""
    env = _env(env_factory)
    created = env.client.post(
        "/clients",
        json={"username": "cliente1", "password": PASSWORD},
        headers=HEADERS,
    ).json()
    profile_id = created["profile_id"]

    status = env.client.get(f"/clients/{profile_id}", headers=HEADERS)
    assert status.status_code == 200
    assert status.json()["days_remaining"] >= 0

    renewed = env.client.post(f"/clients/{profile_id}/renew", headers=HEADERS)
    assert renewed.status_code == 200

    revoked = env.client.post(f"/clients/{profile_id}/revoke", headers=HEADERS)
    assert revoked.status_code == 200
    assert revoked.json()["status"] == "revocada"

    conflict = env.client.post(f"/clients/{profile_id}/renew", headers=HEADERS)
    assert conflict.status_code == 409
    assert conflict.json()["error"] == "credential_revoked"

    closed = env.client.post(
        f"/clients/{profile_id}/close-session", headers=HEADERS
    )
    assert closed.status_code == 200


def test_short_client_password_returns_422(env_factory):
    """R38: la contraseña mínima del perfil se aplica al cliente."""
    env = _env(env_factory)
    response = env.client.post(
        "/clients",
        json={"username": "cliente1", "password": "corta"},
        headers=HEADERS,
    )
    assert response.status_code == 422
    assert env.repo.client_credentials == {}


# --- R25: no filtración -----------------------------------------------------------


def test_password_and_token_never_leak(env_factory, caplog):
    """R25: la clave y el token no aparecen en logs, envíos, eventos ni auditoría."""
    caplog.set_level(logging.DEBUG)
    env = _env(env_factory)
    created = env.client.post(
        "/clients",
        json={"username": "cliente1", "password": PASSWORD},
        headers=HEADERS,
    )
    assert created.status_code == 201
    token = _link(env)
    _post_login(env, token, password="incorrecta")
    assert _post_login(env, token).status_code == 200
    env.client.post(f"/clients/{created.json()['profile_id']}/revoke", headers=HEADERS)

    assert PASSWORD not in caplog.text
    assert token not in caplog.text
    assert all(PASSWORD not in text for _chat, text in env.gateway.sent)
    assert all(token not in text for _chat, text in env.gateway.sent)
    assert all(PASSWORD not in event.reason for event in env.repo.events)
    assert all(token not in event.reason for event in env.repo.events)
    assert all(PASSWORD not in audit.reason for audit in env.repo.identity_audits)
    assert all(token not in audit.reason for audit in env.repo.identity_audits)


def test_uvicorn_access_log_redacts_the_t_query_value():
    """R25: el filtro de `uvicorn.access` convierte `t=<token>` en `t=***`."""
    from orchestrator.main import install_access_log_redaction

    install_access_log_redaction()
    logger = logging.getLogger("uvicorn.access")
    token = "tok3n-secreto"
    record = logging.LogRecord(
        name="uvicorn.access",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg='%s - "%s %s HTTP/%s" %d',
        args=("1.2.3.4", "GET", f"/acceso?t={token}", "1.1", 200),
        exc_info=None,
    )
    for item in logger.filters:
        item.filter(record)

    message = record.getMessage()
    assert token not in message
    assert "t=***" in message
