"""Textos versionados, cierre y bienvenida (#42)."""
from __future__ import annotations

from dataclasses import replace
from datetime import timedelta

import pytest
from lazaro_contracts import NormalizedMessage

from orchestrator.accounts import hash_password_scrypt, hash_token
from orchestrator.domain import (
    _active_welcome_text,
    close_case,
    login_client,
    process_channel_message,
)
from orchestrator.identity import sign_login_token

PASSWORD = "clave-segura-123"
CSRF = "csrf-token"


@pytest.fixture()
def env(env_factory, panel):
    env = env_factory(admin_cookie_secure=False, password_hash_iterations=100000)
    panel.login_admin(env)
    return env


def _form(env, **changes):
    texts = env.repo.get_conversation_texts()
    values = {field: getattr(texts, field) for field in texts.__dataclass_fields__}
    values.update(changes)
    values["csrf_token"] = CSRF
    return values


def test_changed_field_creates_one_version_and_unchanged_none(env):
    """R16, R17: solo el campo cambiado recibe versión nueva."""
    before = env.repo.current_text_versions()
    response = env.client.post(
        "/admin/texts",
        data=_form(env, active_welcome="Bienvenida nueva"),
        follow_redirects=False,
    )
    assert response.status_code == 303
    after = env.repo.current_text_versions()
    assert after["active_welcome"] == before["active_welcome"] + 1
    assert after["greeting"] == before["greeting"]


def test_changing_notice_with_same_version_is_422_and_rolls_back(env):
    """R18: cambiar el aviso sin cambiar la versión no guarda ningún campo."""
    before_texts = env.repo.get_conversation_texts()
    before_versions = env.repo.current_text_versions()
    response = env.client.post(
        "/admin/texts",
        data=_form(
            env,
            notice_text="Aviso cambiado",
            greeting="Saludo que tampoco debe guardarse",
        ),
        follow_redirects=False,
    )
    assert response.status_code == 422
    assert env.repo.get_conversation_texts() == before_texts
    assert env.repo.current_text_versions() == before_versions


def test_version_and_history_are_visible_ordered_limited_and_escaped(env):
    """R19, R20: versión vigente, historial descendente, límite y escape."""
    env.settings.admin_text_history_limit = 2
    for value in ("<b>uno</b>", "<b>dos</b>", "<b>tres</b>"):
        env.repo.save_conversation_texts(
            replace(env.repo.get_conversation_texts(), greeting=value),
            "admin-1",
            env.adapters.clock(),
        )
    page = env.client.get("/admin/texts")
    assert "Versión vigente" in page.text
    history = env.client.get("/admin/texts/greeting/historial")
    assert history.status_code == 200
    assert "<b>tres</b>" not in history.text
    assert "&lt;b&gt;tres&lt;/b&gt;" in history.text
    assert "&lt;b&gt;dos&lt;/b&gt;" in history.text
    assert "&lt;b&gt;uno&lt;/b&gt;" not in history.text


def test_unknown_text_field_history_returns_404(env):
    """R21: un campo fuera de CONVERSATION_TEXT_FIELDS responde 404."""
    response = env.client.get("/admin/texts/desconocido/historial")
    assert response.status_code == 404


def test_next_message_uses_new_text_without_restart(env):
    """R22: el siguiente mensaje usa el texto guardado sin reiniciar el proceso."""
    env.client.post(
        "/admin/texts",
        data=_form(env, greeting="Saludo recién guardado"),
        follow_redirects=False,
    )
    message = NormalizedMessage(
        channel="telegram",
        external_user_id="10",
        external_chat_id="100",
        external_message_id="m1",
        kind="text",
        text="hola",
        received_at=env.adapters.clock(),
    )
    process_channel_message(message, env.settings, env.adapters)
    assert "Saludo recién guardado" in env.gateway.channel_sent[-1][2]


def test_closing_reply_replaces_case_closed_reply(env):
    """R23: con closing_reply configurado se envía al cerrar el caso."""
    env.repo.save_conversation_texts(
        replace(
            env.repo.get_conversation_texts(),
            closing_reply="Cierre configurado desde el panel",
        ),
        "admin-1",
        env.adapters.clock(),
    )
    contact = env.repo.get_or_create_channel_contact("telegram", "10", "100", env.adapters.clock())
    env.repo.link_case("case-1", contact.id, env.adapters.clock())
    close_case("case-1", "700", env.settings, env.adapters)
    assert env.gateway.sent[-1] == (100, "Cierre configurado desde el panel")


def test_topics_list_is_added_to_active_welcome(env):
    """R24: la bienvenida activa incluye topics_list en el login válido."""
    env.settings.identity_link_signing_key = "k" * 32
    contact = env.repo.get_or_create_channel_contact(
        "telegram", "10", "100", env.adapters.clock()
    )
    profile = env.repo.create_client_credential(
        "cliente1",
        hash_password_scrypt(PASSWORD, env.settings.password_scrypt_n),
        env.adapters.clock() - timedelta(days=1),
        env.adapters.clock() + timedelta(days=10),
        env.adapters.clock(),
    )
    token = sign_login_token(env.settings.identity_link_signing_key)
    env.repo.add_login_link(
        hash_token(token),
        contact.id,
        "telegram",
        "100",
        env.adapters.clock(),
        env.adapters.clock() + timedelta(minutes=15),
    )
    texts = replace(
        env.repo.get_conversation_texts(),
        active_welcome="Bienvenida activa",
        topics_list="Tema A\nTema B",
    )
    env.repo.save_conversation_texts(texts, "admin-1", env.adapters.clock())
    login_client(token, "cliente1", PASSWORD, "ip", env.settings, env.adapters)
    assert env.gateway.sent[-1][1] == _active_welcome_text(texts)
    assert "Tema A" in env.gateway.sent[-1][1]


def test_texts_update_is_audited_without_values(env):
    """R44: texts_update se audita sin copiar valores de textos."""
    secret_value = "texto-secreto-no-auditado"
    env.client.post(
        "/admin/texts",
        data=_form(env, greeting=secret_value),
        follow_redirects=False,
    )
    rows = [row for row in env.repo.panel_audit if row.action == "texts_update"]
    assert rows
    assert all(secret_value not in (row.target or "") for row in rows)
