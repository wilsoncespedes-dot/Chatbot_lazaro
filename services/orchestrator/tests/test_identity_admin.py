"""Funciones administrativas de clientes y credenciales (#38, T18)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from orchestrator.domain import (
    ConversationState,
    CredentialNotEnabled,
    CredentialRevoked,
    active_client_id,
    close_client_session,
    create_client,
    get_client_status,
    issue_login_link,
    login_client,
    renew_credential,
    revoke_credential,
)

NOW = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
BASE = "https://orchestrator.example"
KEY = "k" * 32
PASSWORD = "clave-segura-123"


def _env(env_factory):
    return env_factory(
        identity_login_required=True,
        identity_public_base_url=BASE,
        identity_link_signing_key=KEY,
        password_scrypt_n=16384,
    )


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
    env.repo.add_privacy_consent(
        user, env.settings.privacy_notice_version, "sha", NOW
    )
    return env.repo.get_or_create_contact(user, chat, NOW)


def _logged(env):
    profile = _client(env)
    contact = _contact(env)
    url = issue_login_link(contact, env.settings, env.adapters)
    login_client(
        url.split("t=", 1)[1], "cliente1", PASSWORD, "1.1.1.1", env.settings, env.adapters
    )
    return contact, profile


# --- R38, R45 ---------------------------------------------------------------------


def test_create_client_hashes_password_and_reports_status(env_factory):
    """R38, R45: hash scrypt, sin exponerlo y estado calculado."""
    env = _env(env_factory)
    status = _client(env)

    credential = env.repo.get_client_credential(status.profile_id)
    stored = env.repo.profiles[status.profile_id].password_hash
    assert stored.startswith("scrypt$")
    assert PASSWORD not in stored
    assert status.status in ("vigente", "por_vencer")
    assert status.valid_from == NOW - timedelta(days=1)
    assert status.valid_until == NOW + timedelta(days=30)
    assert status.days_remaining == 30
    assert status.has_active_session is False


def test_status_reflects_credential_and_session(env_factory):
    """R45: estado, días restantes y sesión activa."""
    env = _env(env_factory)
    contact, profile = _logged(env)

    status = get_client_status(profile.profile_id, env.settings, env.adapters)

    assert status.has_active_session is True
    assert active_client_id(contact.id, env.adapters) == profile.profile_id


# --- R39, R40, R46 ----------------------------------------------------------------


def test_renew_adds_days_from_the_later_of_valid_until_and_now(env_factory):
    """R39: la renovación se calcula desde `max(valid_until, now)`."""
    env = _env(env_factory)
    profile = _client(env)
    original = env.repo.get_client_credential(profile.profile_id).valid_until

    renew_credential(profile.profile_id, env.settings, env.adapters)
    renewed = env.repo.get_client_credential(profile.profile_id).valid_until
    assert renewed == original + timedelta(days=30)

    later = renewed + timedelta(days=10)
    env.adapters.clock = lambda: later
    renew_credential(profile.profile_id, env.settings, env.adapters)
    assert env.repo.get_client_credential(profile.profile_id).valid_until == (
        later + timedelta(days=30)
    )


def test_renewal_reactivates_no_access_contact_with_session(env_factory):
    """R40: si el contacto está en `no_access` con sesión, renovar lo reactiva."""
    env = _env(env_factory)
    contact, profile = _logged(env)
    env.repo.set_conversation_state(contact.id, ConversationState.NO_ACCESS, NOW)

    renew_credential(profile.profile_id, env.settings, env.adapters)

    assert env.repo.get_conversation_state(contact.id) == ConversationState.ACTIVE
    assert env.gateway.sent[-1] == (
        100,
        env.repo.get_conversation_texts().active_welcome,
    )


def test_renewing_a_revoked_credential_returns_conflict(env_factory):
    """R46: renovar una revocada lanza `CredentialRevoked` sin cambiar fechas."""
    env = _env(env_factory)
    profile = _client(env)
    revoke_credential(profile.profile_id, env.settings, env.adapters)
    before = env.repo.get_client_credential(profile.profile_id).valid_until

    with pytest.raises(CredentialRevoked):
        renew_credential(profile.profile_id, env.settings, env.adapters)

    assert env.repo.get_client_credential(profile.profile_id).valid_until == before


# --- R37, R42 ---------------------------------------------------------------------


def test_revoke_ends_the_session_and_notifies(env_factory):
    """R37, R42: revocar cierra con `revoked`, pasa a esperar login y audita."""
    env = _env(env_factory)
    contact, profile = _logged(env)

    status = revoke_credential(profile.profile_id, env.settings, env.adapters)

    assert status.status == "revocada"
    assert env.repo.get_active_session_by_contact(contact.id) is None
    session = next(iter(env.repo.client_sessions.values()))
    assert session.end_reason == "revoked"
    assert env.repo.get_conversation_state(contact.id) == ConversationState.AWAITING_LOGIN
    assert env.gateway.sent[-1] == (
        100,
        env.repo.get_conversation_texts().session_closed_reply,
    )
    assert any(audit.action == "revoke" for audit in env.repo.identity_audits)


def test_admin_close_session_ends_with_admin_closed_reason(env_factory):
    """R42: cerrar sesión desde administración usa motivo `admin_closed`."""
    env = _env(env_factory)
    contact, profile = _logged(env)

    close_client_session(profile.profile_id, env.settings, env.adapters)

    assert env.repo.get_active_session_by_contact(contact.id) is None
    session = next(iter(env.repo.client_sessions.values()))
    assert session.end_reason == "admin_closed"
    assert env.repo.get_conversation_state(contact.id) == ConversationState.AWAITING_LOGIN


def test_login_after_revoke_returns_403(env_factory):
    """R36, R42: tras revocar, un enlace nuevo no habilita el acceso."""
    env = _env(env_factory)
    contact, profile = _logged(env)
    revoke_credential(profile.profile_id, env.settings, env.adapters)
    url = issue_login_link(contact, env.settings, env.adapters)

    with pytest.raises(CredentialNotEnabled):
        login_client(
            url.split("t=", 1)[1],
            "cliente1",
            PASSWORD,
            "1.1.1.1",
            env.settings,
            env.adapters,
        )
