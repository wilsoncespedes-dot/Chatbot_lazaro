"""Login de clientes, credenciales y sesiones únicas (#38, T13-T15)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from orchestrator.accounts import hash_password_scrypt, hash_token
from orchestrator.domain import (
    ClientLoginFailed,
    ConversationEvent,
    ConversationState,
    CredentialNotEnabled,
    LoginLinkInvalid,
    LoginThrottled,
    SessionConflict,
    create_client,
    issue_login_link,
    login_client,
)
from orchestrator.identity import sign_login_token

NOW = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
BASE = "https://orchestrator.example"
KEY = "k" * 32
PASSWORD = "clave-segura-123"


def _env(env_factory, **overrides):
    values = {
        "identity_login_required": True,
        "identity_public_base_url": BASE,
        "identity_link_signing_key": KEY,
        "password_scrypt_n": 16384,
    }
    values.update(overrides)
    return env_factory(**values)


def _client(
    env,
    username: str = "cliente1",
    valid_from: datetime | None = None,
    valid_until: datetime | None = None,
):
    return create_client(
        username,
        PASSWORD,
        valid_from or NOW - timedelta(days=1),
        valid_until or NOW + timedelta(days=30),
        env.settings,
        env.adapters,
    )


def _link(env, user: str = "10", chat: str = "100", channel: str = "telegram"):
    contact = env.repo.get_or_create_channel_contact(channel, user, chat, NOW)
    url = issue_login_link(contact, env.settings, env.adapters)
    assert url is not None
    return contact, url.split("t=", 1)[1]


def _login(env, token: str, username: str = "cliente1", password: str = PASSWORD, ip: str = "1.1.1.1"):
    return login_client(token, username, password, ip, env.settings, env.adapters)


# --- Éxito y estados de credencial ------------------------------------------------


def test_valid_credential_creates_session_and_activates_contact(env_factory):
    """R14, R15, R16: sesión, enlace consumido, LOGIN_VALID y bienvenida."""
    env = _env(env_factory)
    profile = _client(env)
    contact, token = _link(env)

    outcome = _login(env, token)

    assert outcome.status == "ok"
    session = env.repo.get_active_session_by_contact(contact.id)
    assert session is not None
    assert session.profile_id == profile.profile_id
    assert env.repo.get_login_link(hash_token(token), NOW) is None
    assert env.repo.get_conversation_state(contact.id) == ConversationState.ACTIVE
    assert env.gateway.sent[-1] == (100, env.repo.get_conversation_texts().active_welcome)
    assert any(audit.action == "login" for audit in env.repo.identity_audits)


def test_expiring_credential_still_activates(env_factory):
    """R14: `por_vencer` cuenta como vigente para el acceso."""
    env = _env(env_factory)
    profile = _client(env, valid_until=NOW + timedelta(days=3))
    contact = env.repo.get_or_create_channel_contact("telegram", "10", "100", NOW)
    url = issue_login_link(contact, env.settings, env.adapters)
    outcome = _login(env, url.split("t=", 1)[1])

    assert outcome.status == "ok"
    assert env.repo.get_conversation_state(contact.id) == ConversationState.ACTIVE
    assert env.repo.get_client_credential(profile.profile_id).valid_until == NOW + timedelta(days=3)


def test_expired_credential_creates_session_but_denies_access(env_factory):
    """R34: vencida → LOGIN_EXPIRED, `no_access` y aviso de suspensión."""
    env = _env(env_factory)
    _client(env, valid_from=NOW - timedelta(days=60), valid_until=NOW - timedelta(days=1))
    contact, token = _link(env)

    outcome = _login(env, token)

    assert outcome.status == "ok_no_access"
    assert env.repo.get_active_session_by_contact(contact.id) is not None
    assert env.repo.get_conversation_state(contact.id) == ConversationState.NO_ACCESS
    assert env.gateway.sent[-1] == (
        100,
        env.repo.get_conversation_texts().suspended_reply,
    )


@pytest.mark.parametrize("mode", ["revoked", "not_started", "no_credential"])
def test_revoked_not_started_or_missing_credential_is_403(env_factory, mode):
    """R36, R37: revocada, no iniciada o sin fila → 403 sin sesión y con auditoría."""
    env = _env(env_factory)
    if mode == "no_credential":
        env.repo.create_profile(
            "cliente1",
            "cliente",
            hash_password_scrypt(PASSWORD, 16384),
            NOW,
        )
    elif mode == "revoked":
        profile = _client(env)
        env.repo.revoke_client_credential(profile.profile_id, NOW)
    else:
        _client(env, valid_from=NOW + timedelta(days=1), valid_until=NOW + timedelta(days=30))
    contact, token = _link(env)

    with pytest.raises(CredentialNotEnabled):
        _login(env, token)

    assert env.repo.get_active_session_by_contact(contact.id) is None
    assert env.repo.get_login_link(hash_token(token), NOW) is not None
    assert any(audit.action == "login_denied" for audit in env.repo.identity_audits)


# --- Credenciales incorrectas y bloqueo ------------------------------------------


def test_unknown_user_wrong_password_and_staff_profile_share_401(env_factory):
    """R21, R22, R48: mismo 401, intento registrado y token sin consumir."""
    env = _env(env_factory)
    env.repo.create_profile(
        "asesor1", "asesor", hash_password_scrypt(PASSWORD, 16384), NOW
    )
    contact, token = _link(env)

    for username, password in (
        ("noexiste", PASSWORD),
        ("asesor1", PASSWORD),
    ):
        with pytest.raises(ClientLoginFailed):
            _login(env, token, username=username, password=password)
        assert env.repo.get_login_link(hash_token(token), NOW) is not None

    assert len(env.repo.identity_login_attempts) == 2


def test_wrong_password_also_records_failure_and_fake_verification(env_factory, monkeypatch):
    """R22, R48: usuario inexistente ejecuta una verificación ficticia."""
    env = _env(env_factory)
    calls: list[str] = []
    import orchestrator.domain as domain_module

    original = domain_module.verify_password

    def spy(password, stored):
        calls.append(stored)
        return original(password, stored)

    monkeypatch.setattr(domain_module, "verify_password", spy)
    _, token = _link(env)

    with pytest.raises(ClientLoginFailed):
        _login(env, token, username="noexiste")

    assert calls and calls[0].startswith("scrypt$")
    assert len(env.repo.identity_login_attempts) == 1


def test_five_failures_lock_even_a_correct_password(env_factory):
    """R23: al alcanzar el máximo responde 429 sin verificar la contraseña."""
    env = _env(env_factory)
    _client(env)
    _, token = _link(env)
    for _ in range(5):
        with pytest.raises(ClientLoginFailed):
            _login(env, token, password="incorrecta")

    with pytest.raises(LoginThrottled):
        _login(env, token)


def test_success_clears_failed_attempts(env_factory):
    """R24: un login correcto borra los intentos del usuario."""
    env = _env(env_factory)
    _client(env)
    _, token = _link(env)
    env.repo.record_identity_login_failure(
        "cliente1", "1.1.1.1", NOW, NOW - timedelta(minutes=15)
    )
    assert env.repo.identity_login_attempts

    _login(env, token)

    assert env.repo.identity_login_attempts == []


# --- Enlaces inválidos ------------------------------------------------------------


def test_reused_expired_or_tampered_link_is_400(env_factory):
    """R12, R13: token reutilizado/vencido/firma mala sin tocar el repositorio."""
    env = _env(env_factory)
    _client(env)
    _, token = _link(env)
    _login(env, token)
    with pytest.raises(LoginLinkInvalid):
        _login(env, token)

    env2 = _env(env_factory)
    _client(env2)
    _, expired = _link(env2)
    env2.adapters.clock = lambda: NOW + timedelta(minutes=16)
    with pytest.raises(LoginLinkInvalid):
        _login(env2, expired)

    env3 = _env(env_factory)
    _client(env3)

    def boom(*args, **kwargs):
        raise AssertionError("no debe consultar el repositorio")

    env3.repo.get_login_link = boom
    with pytest.raises(LoginLinkInvalid):
        _login(env3, sign_login_token("otra-clave") + ".x" * 0)


def test_invalid_signature_does_not_consult_repository(env_factory):
    """R13: la firma se valida antes de cualquier consulta."""
    env = _env(env_factory)
    _client(env)

    def boom(*args, **kwargs):
        raise AssertionError("no debe consultar el repositorio")

    env.repo.get_login_link = boom
    with pytest.raises(LoginLinkInvalid):
        _login(env, "nonce.firma-invalida")


# --- Sesión única y caducidad por inactividad ------------------------------------


def test_second_login_for_same_credential_returns_409_and_keeps_token(env_factory):
    """R26, R27: segunda sesión activa → 409, token sin consumir y auditoría."""
    env = _env(env_factory)
    _client(env)
    first_contact, first_token = _link(env, "10", "100")
    second_contact, second_token = _link(env, "11", "101")
    _login(env, first_token)

    with pytest.raises(SessionConflict):
        _login(env, second_token)

    assert env.repo.get_active_session_by_contact(second_contact.id) is None
    assert env.repo.get_login_link(hash_token(second_token), NOW) is not None
    assert any(audit.action == "login_conflict" for audit in env.repo.identity_audits)


def test_idle_session_is_closed_and_second_login_succeeds(env_factory):
    """R30: una sesión inactiva se cierra con `idle` y la nueva entra."""
    env = _env(env_factory)
    _client(env)
    first_contact, first_token = _link(env, "10", "100")
    _login(env, first_token)

    later = NOW + timedelta(minutes=61)
    env.adapters.clock = lambda: later
    second_contact, second_token = _link(env, "11", "101")
    outcome = _login(env, second_token)

    assert outcome.status == "ok"
    old = env.repo.client_sessions[
        next(
            session.id
            for session in env.repo.client_sessions.values()
            if session.contact_id == first_contact.id
        )
    ]
    assert old.end_reason == "idle" and old.ended_at == later
    assert env.repo.get_conversation_state(first_contact.id) == ConversationState.AWAITING_LOGIN
    assert env.repo.get_active_session_by_contact(second_contact.id) is not None


def test_with_advisor_session_is_not_treated_as_idle_on_login(env_factory):
    """R30: la sesión de un contacto con asesor no expira; segundo login 409."""
    env = _env(env_factory)
    _client(env)
    first_contact, first_token = _link(env, "10", "100")
    _login(env, first_token)
    env.repo.set_conversation_state(
        first_contact.id, ConversationState.WITH_ADVISOR, NOW
    )

    later = NOW + timedelta(minutes=61)
    env.adapters.clock = lambda: later
    second_contact, second_token = _link(env, "11", "101")

    with pytest.raises(SessionConflict):
        _login(env, second_token)

    assert env.repo.get_active_session_by_contact(first_contact.id) is not None
    assert env.repo.get_active_session_by_contact(second_contact.id) is None
    assert env.repo.get_login_link(hash_token(second_token), later) is not None
    assert any(audit.action == "login_conflict" for audit in env.repo.identity_audits)


def test_contact_is_taken_from_the_link_without_profile_channel_id(env_factory, monkeypatch):
    """R17, R18: sin comparar ni escribir ids de canal; contacto del enlace."""
    env = _env(env_factory)
    profile = _client(env)
    contact, token = _link(env, "57300", "chat-57300", channel="whatsapp")

    def boom(*args, **kwargs):
        raise AssertionError("el login no debe buscar por telegram_user_id")

    monkeypatch.setattr(env.repo, "get_profile_by_telegram_user_id", boom)
    _login(env, token)

    assert env.repo.get_profile(profile.profile_id).telegram_user_id is None
    session = env.repo.get_active_session_by_contact(contact.id)
    assert session is not None and session.profile_id == profile.profile_id


def test_telegram_profile_without_telegram_user_id_can_login(env_factory):
    """R18: un perfil sin `telegram_user_id` se asocia solo por el enlace."""
    env = _env(env_factory)
    profile = _client(env)
    contact, token = _link(env)

    _login(env, token)

    assert env.repo.get_profile(profile.profile_id).telegram_user_id is None
    assert env.repo.get_active_session_by_contact(contact.id).profile_id == profile.profile_id
