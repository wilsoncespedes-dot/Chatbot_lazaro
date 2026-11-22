"""ID de cliente en el chat: login, comando e imposibilidad de identificación (#73)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fakes import drain_queues
from orchestrator.domain import ConversationState, create_client, issue_login_link, login_client
from orchestrator.identity import is_client_id_command

NOW = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
BASE = "https://orchestrator.example"
KEY = "k" * 32
PASSWORD = "clave-segura-123"


def _env(env_factory):
    env = env_factory(
        identity_login_required=True,
        identity_public_base_url=BASE,
        identity_link_signing_key=KEY,
        password_scrypt_n=16384,
    )
    return env


def _client(env, username: str = "cliente1", *, expired: bool = False):
    end = NOW - timedelta(days=1) if expired else NOW + timedelta(days=30)
    return create_client(
        username,
        PASSWORD,
        NOW - timedelta(days=10),
        end,
        env.settings,
        env.adapters,
    )


def _contact(env, user: int = 10, chat: int = 100):
    env.repo.add_privacy_consent(
        user, env.settings.privacy_notice_version, "sha", NOW
    )
    return env.repo.get_or_create_contact(user, chat, NOW)


def _login(env, username: str = "cliente1", user: int = 10, chat: int = 100):
    contact = _contact(env, user, chat)
    url = issue_login_link(contact, env.settings, env.adapters)
    assert url is not None
    outcome = login_client(
        url.split("t=", 1)[1],
        username,
        PASSWORD,
        "1.1.1.1",
        env.settings,
        env.adapters,
    )
    drain_queues(env.settings, env.adapters)
    return contact, outcome


def test_login_sends_the_public_id_as_its_own_message(env_factory):
    """R9: tras la bienvenida, un mensaje con exactamente el ID."""
    env = _env(env_factory)
    status = _client(env)
    _contact, outcome = _login(env)

    assert outcome.status == "ok"
    texts = [text for _channel, _destination, text in env.gateway.channel_sent]
    assert texts[-1] == status.public_id
    assert env.settings.conversation_active_welcome in texts[-2]


def test_login_without_access_still_sends_the_public_id(env_factory):
    """R9: con credencial vencida se envía la suspensión y después el ID."""
    env = _env(env_factory)
    status = _client(env, expired=True)
    _contact, outcome = _login(env)

    assert outcome.status == "ok_no_access"
    texts = [text for _channel, _destination, text in env.gateway.channel_sent]
    assert texts[-1] == status.public_id
    assert env.repo.get_conversation_texts().suspended_reply in texts[-2]


def test_client_id_command_answers_with_intro_and_id(env_factory):
    """R10: con sesión activa el comando devuelve intro y el ID en otro mensaje."""
    env = _env(env_factory)
    status = _client(env)
    _login(env)

    env.post("mi id")

    texts = [text for _channel, _destination, text in env.gateway.channel_sent]
    assert texts[-2] == env.settings.conversation_client_id_intro
    assert texts[-1] == status.public_id


def test_client_id_command_requires_exact_equality():
    """R11: `mi id 5` no es el comando de ID."""
    commands = ("/id", "mi id", "mi id de cliente")
    assert is_client_id_command("mi id", commands)
    assert is_client_id_command("MI  ID", commands)
    assert not is_client_id_command("mi id 5", commands)
    assert not is_client_id_command("/id ahora", commands)


def test_client_id_command_without_session_follows_normal_flow(env_factory):
    """R12: sin sesión no se envía ningún ID; se pide el login."""
    env = _env(env_factory)
    status = _client(env)

    env.post("mi id", user=11, chat=111)

    texts = [text for _channel, _destination, text in env.gateway.channel_sent]
    assert status.public_id not in texts
    assert env.repo.get_conversation_state(
        env.repo.get_or_create_contact(11, 111, NOW).id
    ) == ConversationState.AWAITING_LOGIN


def test_writing_another_client_id_does_not_identify_or_query(env_factory, monkeypatch):
    """R13, R14: el ID escrito es dato; no cambia estado, no vincula ni consulta."""
    env = _env(env_factory)
    _client(env, "cliente1")
    other = _client(env, "cliente2")
    contact, _outcome = _login(env)
    before_state = env.repo.get_conversation_state(contact.id)
    before_identities = dict(env.repo.identidades_cliente)

    def forbidden(public_id: str):
        raise AssertionError("el flujo de chat no debe resolver IDs")

    monkeypatch.setattr(env.repo, "find_client_by_public_id", forbidden)

    env.post(f"mi id de cliente es {other.public_id}")

    assert env.repo.get_conversation_state(contact.id) == before_state
    assert dict(env.repo.identidades_cliente) == before_identities
    assert not [
        owner
        for owner, _linked_at in env.repo.identidades_cliente.values()
        if owner == other.profile_id
    ]
