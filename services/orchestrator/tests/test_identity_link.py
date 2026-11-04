"""Emisión del enlace de login y hook del botón Acepto (#38, T12)."""
from __future__ import annotations

import logging
from dataclasses import replace
from datetime import datetime, timedelta, timezone

from lazaro_contracts import LinkBlock, TextBlock

from orchestrator.accounts import hash_token
from orchestrator.domain import issue_login_link
from orchestrator.privacy import PRIVACY_ACCEPT_BUTTON, notice_sha256

NOW = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
BASE = "https://orchestrator.example"
KEY = "k" * 32


def _env(env_factory, **overrides):
    values = {
        "identity_login_required": True,
        "identity_public_base_url": BASE,
        "identity_link_signing_key": KEY,
    }
    values.update(overrides)
    return env_factory(**values)


def _contact(env, channel: str = "telegram", user: str = "10", chat: str = "100"):
    return env.repo.get_or_create_channel_contact(channel, user, chat, NOW)


def _token(url: str) -> str:
    return url.split("t=", 1)[1]


def _blocks(env):
    return env.gateway.blocks_sent[-1]


def test_issue_link_uses_base_url_and_ttl_and_stores_only_hash(env_factory):
    """R1, R4, R6: URL `/acceso?t=`, TTL del entorno y solo SHA-256 guardado."""
    env = _env(env_factory)
    contact = _contact(env)

    url = issue_login_link(contact, env.settings, env.adapters)

    assert url is not None
    assert url.startswith(f"{BASE}/acceso?t=")
    token = _token(url)
    stored = env.repo.login_links[hash_token(token)]
    assert stored.contact_id == contact.id
    assert stored.channel == "telegram"
    assert stored.external_chat_id == "100"
    assert stored.expires_at == NOW + timedelta(minutes=15)
    assert token not in env.repo.login_links


def test_issue_link_honors_policy_override(env_factory):
    """R6, R49: `identity.link_ttl_minutes` de app_settings cambia la caducidad."""
    env = _env(env_factory)
    env.repo.identity_overrides["identity.link_ttl_minutes"] = "30"

    url = issue_login_link(_contact(env), env.settings, env.adapters)

    assert env.repo.login_links[hash_token(_token(url))].expires_at == NOW + timedelta(
        minutes=30
    )


def test_missing_base_or_key_omits_link_and_stores_nothing(env_factory, caplog):
    """R7: sin URL base o clave se envía solo texto y se registra el motivo."""
    caplog.set_level(logging.WARNING)
    env = _env(env_factory, identity_public_base_url="", identity_link_signing_key="")

    assert issue_login_link(_contact(env), env.settings, env.adapters) is None
    assert env.repo.login_links == {}
    assert "identity_link_unavailable" in caplog.text


def test_missing_label_fails_closed_without_link(env_factory, caplog):
    """R9: sin `login_link_label` no se emite enlace y se registra."""
    caplog.set_level(logging.WARNING)
    env = _env(env_factory)
    texts = env.repo.get_conversation_texts()
    env.repo.save_conversation_texts(replace(texts, login_link_label=""), "admin", NOW)

    assert issue_login_link(_contact(env), env.settings, env.adapters) is None
    assert env.repo.login_links == {}
    assert "identity_texts_not_configured" in caplog.text


def test_accept_button_sends_text_and_link_to_same_channel_and_chat(env_factory):
    """R1: tras Acepto, `LinkBlock` al mismo canal/chat y mismo contacto."""
    env = _env(env_factory)
    env.present(user=10, chat=100)
    response = env.post_button(PRIVACY_ACCEPT_BUTTON, user=10, chat=100)
    assert response.status_code == 202

    channel, destination, blocks = _blocks(env)
    assert (channel, destination) == ("telegram", "100")
    assert isinstance(blocks[0], TextBlock)
    assert blocks[0].text == env.repo.get_conversation_texts().accepted_reply
    links = [block for block in blocks if isinstance(block, LinkBlock)]
    assert len(links) == 1
    assert links[0].url.startswith(f"{BASE}/acceso?t=")
    assert links[0].text == env.repo.get_conversation_texts().login_link_label
    contact = env.repo.contacts[10]
    token = _token(links[0].url)
    assert env.repo.login_links[hash_token(token)].contact_id == contact.id


def test_whatsapp_accept_uses_the_external_chat(env_factory):
    """R1: el enlace de WhatsApp se envía a su chat externo, no a Telegram."""
    env = _env(env_factory)
    env.present(user=57300, chat=57301, channel="whatsapp")
    env.post_button(
        PRIVACY_ACCEPT_BUTTON, user=57300, chat=57301, channel="whatsapp"
    )

    channel, destination, blocks = _blocks(env)
    assert (channel, destination) == ("whatsapp", "57301")
    assert any(isinstance(block, LinkBlock) for block in blocks)


def test_issue_new_link_invalidates_the_previous_one(env_factory):
    """R5: un enlace nuevo invalida el anterior del mismo contacto."""
    env = _env(env_factory)
    contact = _contact(env)
    first = issue_login_link(contact, env.settings, env.adapters)
    second = issue_login_link(contact, env.settings, env.adapters)

    assert first is not None and second is not None
    assert env.repo.get_login_link(hash_token(_token(first)), NOW) is None
    assert env.repo.get_login_link(hash_token(_token(second)), NOW) is not None


def test_link_expires_without_being_consumed(env_factory):
    """R6, R12: pasado el TTL el enlace deja de existir para el repositorio."""
    env = _env(env_factory)
    url = issue_login_link(_contact(env), env.settings, env.adapters)
    token_hash = hash_token(_token(url))

    assert env.repo.get_login_link(token_hash, NOW + timedelta(minutes=16)) is None
