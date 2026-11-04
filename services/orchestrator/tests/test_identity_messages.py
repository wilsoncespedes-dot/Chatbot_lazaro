"""Compuerta de identidad dentro del flujo de mensajes (#38, T16-T17)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from lazaro_contracts import LinkBlock, TextBlock

from orchestrator.accounts import hash_token
from orchestrator.domain import (
    ConversationState,
    create_client,
    issue_login_link,
    login_client,
)

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


def _contact(env, user: int = 10, chat: int = 100):
    env.repo.add_privacy_consent(
        user,
        env.settings.privacy_notice_version,
        "sha",
        NOW,
    )
    return env.repo.get_or_create_contact(user, chat, NOW)


def _logged(env, user: int = 10, chat: int = 100):
    profile = create_client(
        "cliente1",
        PASSWORD,
        NOW - timedelta(days=1),
        NOW + timedelta(days=30),
        env.settings,
        env.adapters,
    )
    contact = _contact(env, user, chat)
    url = issue_login_link(contact, env.settings, env.adapters)
    login_client(
        url.split("t=", 1)[1], "cliente1", PASSWORD, "1.1.1.1", env.settings, env.adapters
    )
    return contact, profile


def _state(env, contact_id: str) -> ConversationState | None:
    return env.repo.get_conversation_state(contact_id)


def _last_blocks(env):
    return env.gateway.blocks_sent[-1]


def _last_text(env) -> str:
    _channel, _destination, blocks = _last_blocks(env)
    return next(block.text for block in blocks if isinstance(block, TextBlock))


def test_awaiting_login_sends_reminder_and_new_link(env_factory):
    """R2, R5: recordatorio con LinkBlock nuevo e invalidación del anterior."""
    env = _env(env_factory)
    contact = _contact(env)
    env.repo.set_conversation_state(contact.id, ConversationState.AWAITING_LOGIN, NOW)
    previous = issue_login_link(contact, env.settings, env.adapters)

    response = env.post(text="hola", update_id=1)

    assert response.status_code == 202
    assert _last_text(env) == env.repo.get_conversation_texts().login_reminder
    _channel, _destination, blocks = _last_blocks(env)
    links = [block for block in blocks if isinstance(block, LinkBlock)]
    assert len(links) == 1 and links[0].url.startswith(f"{BASE}/acceso?t=")
    assert env.repo.get_login_link(hash_token(previous.split("t=", 1)[1]), NOW) is None
    assert env.rag.calls == [] and env.llm.calls == []


def test_missing_state_is_treated_as_awaiting_login(env_factory):
    """R47: consentido sin fila de estado → recordatorio, no RAG."""
    env = _env(env_factory)
    contact = _contact(env)

    env.post(text="hola", update_id=1)

    assert _state(env, contact.id) == ConversationState.AWAITING_LOGIN
    _channel, _destination, blocks = _last_blocks(env)
    assert any(isinstance(block, LinkBlock) for block in blocks)
    assert env.rag.calls == []


def test_message_with_session_updates_last_activity(env_factory):
    """R28: cada mensaje del contacto con sesión activa actualiza la actividad."""
    env = _env(env_factory)
    contact, _profile = _logged(env)
    later = NOW + timedelta(minutes=5)
    env.adapters.clock = lambda: later

    env.post(text="hola", update_id=1)

    session = env.repo.get_active_session_by_contact(contact.id)
    assert session is not None and session.last_activity_at == later


def test_inactivity_ends_session_and_does_not_call_rag(env_factory):
    """R30, R31: sesión inactiva → `idle`, recordatorio y sin RAG/LLM."""
    env = _env(env_factory)
    contact, _profile = _logged(env)
    env.adapters.clock = lambda: NOW + timedelta(minutes=61)

    env.post(text="hola", update_id=1)

    session = env.repo.get_active_session_by_contact(contact.id)
    assert session is None
    assert _state(env, contact.id) == ConversationState.AWAITING_LOGIN
    assert _last_text(env) == env.repo.get_conversation_texts().login_reminder
    assert env.rag.calls == [] and env.llm.calls == []


def test_with_advisor_session_does_not_expire(env_factory):
    """R28, R30: no expira con asesor, pero la actividad sí avanza."""
    env = _env(env_factory)
    contact, _profile = _logged(env)
    env.repo.set_conversation_state(contact.id, ConversationState.WITH_ADVISOR, NOW)
    later = NOW + timedelta(minutes=61)
    env.adapters.clock = lambda: later

    env.post(text="sigo esperando", update_id=1)

    session = env.repo.get_active_session_by_contact(contact.id)
    assert session is not None
    assert session.last_activity_at == later
    assert _state(env, contact.id) == ConversationState.WITH_ADVISOR


def test_active_without_session_returns_to_login(env_factory):
    """R33: `active` sin sesión aplica SESSION_CLOSED y pide login."""
    env = _env(env_factory)
    contact = _contact(env)
    env.repo.set_conversation_state(contact.id, ConversationState.ACTIVE, NOW)

    env.post(text="hola", update_id=1)

    assert _state(env, contact.id) == ConversationState.AWAITING_LOGIN
    assert _last_text(env) == env.repo.get_conversation_texts().login_reminder
    assert env.rag.calls == []


def test_logout_command_ends_session_and_keeps_privacy_consents(env_factory):
    """R29, R32: `/salir` cierra sesión, avisa con enlace y no toca consentimientos."""
    env = _env(env_factory)
    contact, _profile = _logged(env)
    consents_before = list(env.repo.privacy_consents)

    env.post(text="/salir", update_id=1, consent=False)

    assert env.repo.get_active_session_by_contact(contact.id) is None
    assert _state(env, contact.id) == ConversationState.AWAITING_LOGIN
    assert _last_text(env) == env.repo.get_conversation_texts().session_closed_reply
    _channel, _destination, blocks = _last_blocks(env)
    assert any(isinstance(block, LinkBlock) for block in blocks)
    assert env.repo.privacy_consents == consents_before


def test_expired_credential_on_active_contact_denies_access(env_factory):
    """R35: credencial vencida en `active` → `no_access`, aviso y sin RAG."""
    env = _env(env_factory)
    contact, profile = _logged(env)
    env.repo.get_client_credential(profile.profile_id).valid_until = NOW - timedelta(days=1)

    env.post(text="hola", update_id=1)

    assert _state(env, contact.id) == ConversationState.NO_ACCESS
    assert env.gateway.sent[-1] == (
        100,
        env.repo.get_conversation_texts().suspended_reply,
    )
    assert env.rag.calls == [] and env.llm.calls == []


def test_no_access_with_renewed_credential_is_reactivated_before_routing(env_factory):
    """R41: `no_access` con credencial vigente vuelve a `active` y sigue al RAG."""
    env = _env(env_factory)
    contact, _profile = _logged(env)
    env.repo.set_conversation_state(contact.id, ConversationState.NO_ACCESS, NOW)

    env.post(text="¿Cómo instalo el módulo?", update_id=1)

    assert _state(env, contact.id) == ConversationState.ACTIVE
    assert env.rag.calls == [("¿Cómo instalo el módulo?", env.settings.rag_top_k)]


def test_login_disabled_keeps_the_historic_flow(env_factory):
    """R44: con `IDENTITY_LOGIN_REQUIRED=false` el mismo texto llega al RAG."""
    env = env_factory()
    assert env.settings.identity_login_required is False
    contact = _contact(env)
    env.repo.set_conversation_state(contact.id, ConversationState.ACTIVE, NOW)

    env.post(text="¿Cómo instalo el módulo?", update_id=1)

    assert env.rag.calls == [("¿Cómo instalo el módulo?", env.settings.rag_top_k)]


def test_login_required_blocks_the_same_message(env_factory):
    """R44, R47: con login exigido, el texto no llega a RAG sin sesión."""
    env = _env(env_factory)
    contact = _contact(env)

    env.post(text="¿Cómo instalo el módulo?", update_id=1)

    assert _state(env, contact.id) == ConversationState.AWAITING_LOGIN
    assert env.rag.calls == []


def test_route_never_looks_up_profiles_by_telegram_id(env_factory, monkeypatch):
    """R18, R25: el flujo de mensajes no llama a `get_profile_by_telegram_user_id`."""
    env = _env(env_factory)
    _contact(env)

    def boom(*args, **kwargs):
        raise AssertionError("no debe buscar perfiles por id de Telegram")

    monkeypatch.setattr(env.repo, "get_profile_by_telegram_user_id", boom)
    env.post(text="hola", update_id=1)
