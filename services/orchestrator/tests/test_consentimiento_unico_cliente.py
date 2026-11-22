"""Consentimiento único por cliente en todos sus canales vinculados (#72)."""
from __future__ import annotations

import logging
from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.routing import APIRoute
from lazaro_contracts import LinkBlock, TextBlock

from orchestrator.adapters.repository import PostgresRepository
from orchestrator.config import Settings
from orchestrator.domain import (
    ClientHistoryMessage,
    ClientLoginFailed,
    ClientSession,
    CredentialNotEnabled,
    LoginLinkInvalid,
    LoginThrottled,
    SessionConflict,
    client_history,
    create_client,
    execute_suppression,
    issue_login_link,
    login_client,
    purge_personal_data,
)
from orchestrator.privacy import notice_sha256

from fakes import drain_queues

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


def _client(env, username: str = "cliente1"):
    return create_client(
        username,
        PASSWORD,
        NOW - timedelta(days=1),
        NOW + timedelta(days=30),
        env.settings,
        env.adapters,
    )


def _link(env, channel: str = "telegram", user: str = "10", chat: str = "100"):
    contact = env.repo.get_or_create_channel_contact(channel, user, chat, NOW)
    url = issue_login_link(contact, env.settings, env.adapters)
    assert url is not None
    return contact, url.split("t=", 1)[1]


def _login(env, token: str, username: str = "cliente1"):
    outcome = login_client(token, username, PASSWORD, "1.1.1.1", env.settings, env.adapters)
    drain_queues(env.settings, env.adapters)
    return outcome


def _accept_evidence(env, channel: str, user: str, version: str | None = None) -> None:
    env.repo.add_channel_privacy_consent(
        channel,
        user,
        version or env.repo.get_conversation_texts().notice_version,
        notice_sha256(env.settings.privacy_notice_text),
        NOW,
    )


def _ensure_client(env, username: str = "cliente1"):
    if env.repo.get_client_credentials_by_username(username) is None:
        _client(env, username)


def _login_contact(
    env,
    channel: str = "telegram",
    user: str = "10",
    chat: str = "100",
    username: str = "cliente1",
):
    _ensure_client(env, username)
    contact, token = _link(env, channel, user, chat)
    _accept_evidence(env, channel, user)
    outcome = _login(env, token, username)
    assert outcome.status == "ok"
    return contact


def _end_session(env, contact) -> None:
    session = env.repo.get_active_session_by_contact(contact.id)
    if session is not None:
        env.repo.end_client_session(session.id, "logout", NOW)


def _texts(blocks: list) -> str:
    return "\n".join(block.text for block in blocks if isinstance(block, TextBlock))


def _links(blocks: list) -> list[LinkBlock]:
    return [block for block in blocks if isinstance(block, LinkBlock)]


def _sent_blocks(env, channel: str, destination: str) -> list:
    for sent_channel, sent_destination, blocks in reversed(env.gateway.blocks_sent):
        if sent_channel == channel and sent_destination == destination:
            return blocks
    return []


def test_login_registers_client_consent_and_identity(env_factory):
    """R1, R2, R13: copia la evidencia a consentimientos_cliente sin tocarla."""
    env = _env(env_factory)
    client = _client(env)
    contact = env.repo.get_or_create_channel_contact("telegram", "10", "100", NOW)
    _accept_evidence(env, "telegram", "10")
    url = issue_login_link(contact, env.settings, env.adapters)
    assert url is not None

    outcome = _login(env, url.split("t=", 1)[1])

    assert outcome.status == "ok"
    row = env.repo.consentimientos_cliente[(client.profile_id, "v1")]
    assert row["canal_id"] == "telegram"
    assert row["aceptado_en"] == NOW
    assert row["notice_sha256"] == notice_sha256(env.settings.privacy_notice_text)
    assert [
        (consent.channel, consent.external_user_id)
        for consent in env.repo.privacy_consents
    ] == [("telegram", "10")]
    assert env.repo.identidades_cliente[("telegram", "10")] == (client.profile_id, NOW)


def test_login_keeps_original_client_consent_row(env_factory):
    """R3: un segundo login desde otro canal no reescribe fecha ni canal."""
    env = _env(env_factory)
    client = _client(env)
    telegram = _login_contact(env)
    _end_session(env, telegram)
    whatsapp, token = _link(env, "whatsapp", "57300", "57301")
    _accept_evidence(env, "whatsapp", "57300")
    assert _login(env, token).status == "ok"

    row = env.repo.consentimientos_cliente[(client.profile_id, "v1")]
    assert row["aceptado_en"] == NOW
    assert row["canal_id"] == "telegram"
    assert ("whatsapp", "57300") in env.repo.identidades_cliente
    assert whatsapp.channel == "whatsapp"


def test_linked_identity_on_other_channel_not_asked_notice(env_factory):
    """R4: el canal B vinculado sin fila propia recibe el flujo de login, no el aviso."""
    env = _env(env_factory)
    telegram = _login_contact(env)
    _end_session(env, telegram)
    whatsapp, token = _link(env, "whatsapp", "57300", "57301")
    assert _login(env, token).status == "ok"
    assert not any(
        consent.channel == "whatsapp" for consent in env.repo.privacy_consents
    )
    _end_session(env, whatsapp)

    env.present(user=57300, chat=57301, channel="whatsapp")

    contact = env.repo.find_channel_contact("whatsapp", "57300")
    assert contact is not None
    assert env.repo.get_conversation_state(contact.id) == "awaiting_login"
    blocks = _sent_blocks(env, "whatsapp", "57301")
    texts = env.repo.get_conversation_texts()
    assert texts.notice_text not in _texts(blocks)
    assert texts.greeting not in _texts(blocks)
    assert _links(blocks)


def test_not_asked_after_logout(env_factory):
    """R5, R18: tras cerrar sesión el texto vuelve al login, no al aviso."""
    env = _env(env_factory)
    contact = _login_contact(env)

    env.post(text="/salir", update_id=2, user=10, chat=100, consent=False)
    assert env.repo.get_active_session_by_contact(contact.id) is None
    env.post(text="Hola de nuevo", update_id=3, user=10, chat=100, consent=False)

    blocks = _sent_blocks(env, "telegram", "100")
    texts = env.repo.get_conversation_texts()
    assert texts.notice_text not in _texts(blocks)
    assert texts.greeting not in _texts(blocks)
    assert _links(blocks)
    assert env.llm.calls == []


def test_new_version_asks_once_and_covers_all_channels(env_factory):
    """R7, R8, R9: la versión nueva se pide en A y cubre al canal B."""
    env = _env(env_factory)
    client = _client(env)
    telegram = _login_contact(env)
    _end_session(env, telegram)
    whatsapp, token = _link(env, "whatsapp", "57300", "57301")
    _accept_evidence(env, "whatsapp", "57300")
    assert _login(env, token).status == "ok"
    _end_session(env, whatsapp)

    texts = env.repo.get_conversation_texts()
    env.repo.save_conversation_texts(replace(texts, notice_version="v2"), "admin", NOW)

    env.present(user=10, chat=100)
    blocks_a = _sent_blocks(env, "telegram", "100")
    assert texts.notice_text in _texts(blocks_a)
    env.post(
        text=env.settings.consent_accept_phrase,
        update_id=2,
        user=10,
        chat=100,
        consent=False,
    )
    row = env.repo.consentimientos_cliente[(client.profile_id, "v2")]
    assert row["canal_id"] == "telegram"

    env.present(user=57300, chat=57301, channel="whatsapp")
    blocks_b = _sent_blocks(env, "whatsapp", "57301")
    assert texts.notice_text not in _texts(blocks_b)
    assert _links(blocks_b)
    assert [
        key for key in env.repo.consentimientos_cliente
        if key[0] == client.profile_id and key[1] == "v2"
    ] == [(client.profile_id, "v2")]


def test_unlinked_identity_still_gets_notice(env_factory):
    """R10: una identidad nunca vinculada recibe el aviso aunque el cliente aceptó."""
    env = _env(env_factory)
    _login_contact(env)

    env.present(user=99, chat=990)

    blocks = _sent_blocks(env, "telegram", "990")
    assert env.repo.get_conversation_texts().notice_text in _texts(blocks)
    assert env.repo.find_channel_contact("telegram", "99") is None


def test_unlinked_identity_stores_no_data(env_factory):
    """R11: sin aceptación propia no se crea contacto, mensaje ni estado."""
    env = _env(env_factory)

    env.present(user=99, chat=990)

    assert env.repo.find_channel_contact("telegram", "99") is None
    assert env.repo.messages == []
    assert env.repo.conversation_states == {}
    assert env.repo.privacy_consents == []


@pytest.mark.parametrize(
    "mode", ["bad_credentials", "invalid_link", "revoked", "locked", "conflict"]
)
def test_failed_login_does_not_link(env_factory, mode):
    """R14: ningún fallo de login inserta filas en identidades_cliente."""
    env = _env(env_factory)
    client = _client(env)
    contact, token = _link(env)
    username, password = "cliente1", PASSWORD
    if mode == "bad_credentials":
        password = "incorrecta"
    elif mode == "invalid_link":
        token = "invalido"
    elif mode == "revoked":
        env.repo.revoke_client_credential(client.profile_id, NOW)
    elif mode == "locked":
        for _ in range(5):
            env.repo.record_identity_login_failure(
                username, "1.1.1.1", NOW, NOW - timedelta(minutes=15)
            )
    else:
        env.repo.client_sessions["s-1"] = ClientSession(
            id="s-1",
            profile_id=client.profile_id,
            contact_id=contact.id,
            started_at=NOW - timedelta(minutes=10),
            last_activity_at=NOW,
        )

    expected = {
        "bad_credentials": ClientLoginFailed,
        "invalid_link": LoginLinkInvalid,
        "revoked": CredentialNotEnabled,
        "locked": LoginThrottled,
        "conflict": SessionConflict,
    }[mode]
    with pytest.raises(expected):
        login_client(token, username, password, "1.1.1.1", env.settings, env.adapters)

    assert env.repo.identidades_cliente == {}
    assert env.repo.consentimientos_cliente == {}


def test_login_reassigns_identity_to_new_client(env_factory):
    """R15: el login de otro cliente reasigna la identidad y actualiza la fecha."""
    env = _env(env_factory)
    first = _client(env, "cliente1")
    second = _client(env, "cliente2")
    contact = _login_contact(env, username="cliente1")
    assert env.repo.identidades_cliente[("telegram", "10")][0] == first.profile_id

    _end_session(env, contact)
    _, token = _link(env)
    _accept_evidence(env, "telegram", "10")
    assert _login(env, token, "cliente2").status == "ok"

    assert env.repo.identidades_cliente[("telegram", "10")] == (
        second.profile_id,
        NOW,
    )


def test_client_history_merges_identities_with_channel(env_factory):
    """R16: el historial une los mensajes de todas las identidades con su canal."""
    env = _env(env_factory)
    telegram = env.repo.get_or_create_channel_contact("telegram", "10", "100", NOW)
    whatsapp = env.repo.get_or_create_channel_contact("whatsapp", "57300", "57301", NOW)
    env.repo.add_message(telegram.id, "user", "uno", NOW - timedelta(hours=2))
    env.repo.add_message(whatsapp.id, "user", "dos", NOW - timedelta(hours=1))
    env.repo.add_message(telegram.id, "bot", "tres", NOW)
    env.repo.identidades_cliente[("telegram", "10")] = ("cliente-1", NOW)
    env.repo.identidades_cliente[("whatsapp", "57300")] = ("cliente-1", NOW)

    history = client_history("cliente-1", 10, env.adapters)

    assert history == [
        ClientHistoryMessage(channel="telegram", role="user", text="uno", at=NOW - timedelta(hours=2)),
        ClientHistoryMessage(channel="whatsapp", role="user", text="dos", at=NOW - timedelta(hours=1)),
        ClientHistoryMessage(channel="telegram", role="bot", text="tres", at=NOW),
    ]
    assert client_history("cliente-1", 1, env.adapters) == [history[-1]]


def test_link_failure_does_not_break_login_and_asks_again(env_factory, caplog):
    """R17: si falla la vinculación el login termina y el aviso se pide de nuevo."""
    caplog.set_level(logging.WARNING)
    env = _env(env_factory)
    _client(env)
    _, token = _link(env)
    env.repo.fail_client_link = True

    assert _login(env, token).status == "ok"
    assert env.repo.identidades_cliente == {}
    assert "client_consent_link_failed" in caplog.text
    assert "cliente1" not in caplog.text

    env.present(user=10, chat=100)
    blocks = _sent_blocks(env, "telegram", "100")
    assert env.repo.get_conversation_texts().notice_text in _texts(blocks)


def test_login_still_required_for_covered_identity(env_factory):
    """R18: la cobertura por cliente no exime del login verificado."""
    env = _env(env_factory)
    contact = _login_contact(env)
    _end_session(env, contact)

    env.post(text="¿Cómo instalo el módulo?", update_id=2, consent=False)

    blocks = _sent_blocks(env, "telegram", "100")
    assert _links(blocks)
    assert env.repo.get_conversation_state(contact.id) == "awaiting_login"
    assert env.llm.calls == [] and env.rag.calls == []


def test_no_alternative_identification_routes(env_factory):
    """R19: no hay ruta ni ajuste de identificación alternativa por canal."""
    env = _env(env_factory)
    paths = {route.path for route in env.client.app.routes if isinstance(route, APIRoute)}
    for fragment in ("verif", "codigo", "otp", "identify", "identificar"):
        assert not any(fragment in path for path in paths), fragment
    fields = set(Settings.model_fields)
    for fragment in ("verification_code", "otp", "channel_code", "identify"):
        assert not any(fragment in field for field in fields), fragment


class _LogCursor:
    def __init__(self, log: list) -> None:
        self.log = log
        self.sql = ""

    def execute(self, sql, params=()):
        self.sql = sql
        self.log.append((sql, tuple(params)))

    def fetchall(self):
        return []


class _LogConn:
    def __init__(self, log: list) -> None:
        self.log = log

    def cursor(self):
        return _LogCursor(self.log)

    def commit(self):
        pass

    def rollback(self):
        pass


def test_postgres_client_consent_sql_is_parameterized():
    """R1, R4, R8, R13, R15, R16: consultas parametrizadas y upserts idempotentes."""
    log: list = []
    repo = PostgresRepository(
        "postgresql://x", connect=lambda: _LogConn(log), new_id=lambda: "n"
    )

    repo.register_client_login("c1", "telegram", "10", "v1", NOW)
    repo.register_client_acceptance_if_linked("telegram", "10", "v1", "sha", NOW)
    repo.has_client_consent_for_identity(
        "telegram", "10", "v1", NOW - timedelta(days=30)
    )
    repo.client_history("c1", 10)

    statements = [(sql, params) for sql, params in log if not sql.startswith("CREATE")]
    joined = " ".join(sql for sql, _ in statements)
    assert "ON CONFLICT (canal_id, id_externo) DO UPDATE" in joined
    assert "ON CONFLICT (cliente_id, notice_version) DO NOTHING" in joined
    assert "c.aceptado_en >= %s" in joined
    assert "JOIN identidades_cliente i" in joined
    for sql, params in statements:
        assert sql.count("%s") == len(params), sql


def test_client_consent_kept_without_retention(env_factory):
    """R20: sin CLIENT_CONSENT_RETENTION_DAYS la purga no borra la aceptación."""
    env = _env(env_factory)
    old = NOW - timedelta(days=90)
    env.repo.consentimientos_cliente[("cliente-1", "v1")] = {
        "notice_sha256": "sha",
        "aceptado_en": old,
        "canal_id": "telegram",
    }
    env.repo.identidades_cliente[("telegram", "10")] = ("cliente-1", old)

    response = purge_personal_data(env.settings, env.adapters)

    assert ("cliente-1", "v1") in env.repo.consentimientos_cliente
    assert ("telegram", "10") in env.repo.identidades_cliente
    assert "consentimientos_cliente" not in response.deleted


def test_client_consent_purged_after_configured_days(env_factory):
    """R21: con plazo, la aceptación vencida se borra y deja de cubrir."""
    env = _env(env_factory, client_consent_retention_days="30")
    old = NOW - timedelta(days=31)
    boundary = NOW - timedelta(days=30)
    env.repo.identidades_cliente[("telegram", "10")] = ("cliente-1", old)
    env.repo.consentimientos_cliente[("cliente-1", "vieja")] = {
        "notice_sha256": "sha",
        "aceptado_en": old,
        "canal_id": "telegram",
    }
    env.repo.consentimientos_cliente[("cliente-1", "nueva")] = {
        "notice_sha256": "sha",
        "aceptado_en": boundary,
        "canal_id": "telegram",
    }

    response = purge_personal_data(env.settings, env.adapters)

    assert response.deleted["consentimientos_cliente"] == 1
    assert ("cliente-1", "vieja") not in env.repo.consentimientos_cliente
    assert ("cliente-1", "nueva") in env.repo.consentimientos_cliente
    assert ("telegram", "10") in env.repo.identidades_cliente
    assert not env.repo.has_client_consent_for_identity(
        "telegram", "10", "vieja", boundary
    )
    assert env.repo.has_client_consent_for_identity(
        "telegram", "10", "nueva", boundary
    )


def _suppression_setup(env):
    client = env.repo.create_client_credential(
        "cliente1", "hash", NOW - timedelta(days=1), NOW + timedelta(days=30), NOW
    )
    admin = env.repo.create_profile("admin1", "admin", "hash", NOW)
    telegram = env.repo.get_or_create_channel_contact("telegram", "10", "100", NOW)
    whatsapp = env.repo.get_or_create_channel_contact("whatsapp", "57300", "57301", NOW)
    env.repo.client_sessions["s-telegram"] = ClientSession(
        id="s-telegram",
        profile_id=client.id,
        contact_id=telegram.id,
        started_at=NOW - timedelta(minutes=10),
        last_activity_at=NOW - timedelta(minutes=1),
        ended_at=NOW,
    )
    request_id, created = env.repo.create_or_get_pending_suppression(
        "req-1", client.id, telegram.id, "telegram", NOW
    )
    assert created
    env.repo.identidades_cliente[("telegram", "10")] = (client.id, NOW)
    env.repo.identidades_cliente[("whatsapp", "57300")] = (client.id, NOW)
    env.repo.consentimientos_cliente[(client.id, "v1")] = {
        "notice_sha256": "sha",
        "aceptado_en": NOW,
        "canal_id": "telegram",
    }
    _accept_evidence(env, "telegram", "10")
    _accept_evidence(env, "whatsapp", "57300")
    return client, admin, telegram, whatsapp, request_id


def test_suppression_removes_client_consent_and_identities(env_factory):
    """R23, R24: la supresión borra las tablas nuevas y la evidencia de toda identidad."""
    env = _env(env_factory)
    client, admin, _telegram, _whatsapp, request_id = _suppression_setup(env)

    execution = execute_suppression(request_id, admin.id, env.settings, env.adapters)

    assert execution.deleted["consentimientos_cliente"] == 1
    assert execution.deleted["identidades_cliente"] == 2
    assert execution.deleted["privacy_consents"] == 2
    assert not [
        key for key in env.repo.consentimientos_cliente if key[0] == client.id
    ]
    assert not [
        key for key in env.repo.identidades_cliente if key[1] in ("10", "57300")
    ]
    request = env.repo.suppression_requests[request_id]
    assert request.removed_counts["consentimientos_cliente"] == 1
    assert request.removed_counts["identidades_cliente"] == 2


def test_suppression_removes_privacy_consents_of_all_linked_identities(env_factory):
    """R24: la evidencia del canal sin sesión también se borra si está vinculado."""
    env = _env(env_factory)
    _client, admin, _telegram, _whatsapp, request_id = _suppression_setup(env)

    execution = execute_suppression(request_id, admin.id, env.settings, env.adapters)

    assert execution.deleted["privacy_consents"] == 2
    assert env.repo.privacy_consents == []


def test_suppressed_client_identity_gets_notice_again(env_factory):
    """R25: tras la supresión la identidad vuelve a ser no vinculada y recibe aviso."""
    env = _env(env_factory)
    _client, admin, _telegram, _whatsapp, request_id = _suppression_setup(env)
    execute_suppression(request_id, admin.id, env.settings, env.adapters)

    env.present(user=10, chat=100)

    blocks = _sent_blocks(env, "telegram", "100")
    assert env.repo.get_conversation_texts().notice_text in _texts(blocks)
    assert not env.repo.has_client_consent_for_identity(
        "telegram", "10", "v1", None
    )
