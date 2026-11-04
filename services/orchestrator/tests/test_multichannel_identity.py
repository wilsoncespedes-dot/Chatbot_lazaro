"""Identidad y consentimiento por canal en el orquestador (#36, R13-R21)."""
from __future__ import annotations

from datetime import datetime, timezone

from orchestrator.domain import Contact
from orchestrator.privacy import (
    PRIVACY_ACCEPT_BUTTON,
    consent_button_proof,
    notice_sha256,
)

SERVICE_TOKEN = "svc-token"
HEADERS = {"X-Service-Token": SERVICE_TOKEN}
RECEIVED_AT = "2026-11-03T16:05:12Z"
FIXED_NOW = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)


def _consent(env, channel: str, external_user_id: str) -> None:
    env.repo.add_channel_privacy_consent(
        channel,
        external_user_id,
        env.settings.privacy_notice_version,
        notice_sha256(env.settings.privacy_notice_text),
        FIXED_NOW,
    )


def _canonical(external_user_id: str, external_message_id: str, **changes):
    data = {
        "channel": "whatsapp",
        "external_user_id": external_user_id,
        "external_chat_id": f"chat-{external_user_id}",
        "external_message_id": external_message_id,
        "kind": "text",
        "text": "Hola",
        "received_at": RECEIVED_AT,
    }
    data.update(changes)
    return data


def _post(env, external_user_id: str, external_message_id: str, **changes):
    return env.client.post(
        "/messages",
        json=_canonical(external_user_id, external_message_id, **changes),
        headers=HEADERS,
    )


def _button(
    env,
    external_user_id: str,
    external_message_id: str,
    button_id: str = PRIVACY_ACCEPT_BUTTON,
    **changes,
):
    challenge = env.adapters.consent_challenges.get("whatsapp", external_user_id)
    if challenge is None:
        _post(env, external_user_id, f"present-{external_message_id}")
        challenge = env.adapters.consent_challenges.get("whatsapp", external_user_id)
    assert challenge is not None
    texts = env.repo.get_conversation_texts()
    external_chat_id = changes.get("external_chat_id", f"chat-{external_user_id}")
    data = _canonical(
        external_user_id,
        external_message_id,
        kind="button",
        text=None,
        button_id=button_id,
        button_proof=consent_button_proof(
            env.settings.service_token,
            "whatsapp",
            external_user_id,
            external_chat_id,
            button_id,
            texts.notice_version,
            notice_sha256(texts.notice_text),
            challenge.nonce,
        ),
        **changes,
    )
    return env.client.post("/messages", json=data, headers=HEADERS)


def test_contact_lookup_uses_channel_and_external_user_id(env):
    """R13: tras consentir, el contacto se busca y reutiliza por la pareja."""
    _consent(env, "whatsapp", "57300")

    first = _post(env, "57300", "m1")
    second = _post(env, "57300", "m2")

    assert first.json() == {"status": "accepted"}
    assert second.json() == {"status": "accepted"}
    contact = env.repo.contacts[("whatsapp", "57300")]
    assert contact.external_user_id == "57300"
    assert {message.contact_id for message in env.repo.messages} == {contact.id}


def test_same_numeric_id_in_telegram_and_whatsapp_stays_separate(env):
    """R14: el mismo valor numérico en dos canales produce contactos distintos."""
    env.post(user=10, chat=100, update_id=1)
    _consent(env, "whatsapp", "10")
    _post(env, "10", "m1")

    telegram = env.repo.contacts[10]
    whatsapp = env.repo.contacts[("whatsapp", "10")]
    assert telegram.id != whatsapp.id
    assert telegram.channel == "telegram"
    assert whatsapp.channel == "whatsapp"
    assert whatsapp.telegram_user_id is None
    telegram_messages = {
        m.contact_id for m in env.repo.messages if m.contact_id == telegram.id
    }
    whatsapp_messages = {
        m.contact_id for m in env.repo.messages if m.contact_id == whatsapp.id
    }
    assert telegram_messages and whatsapp_messages


def test_consent_is_independent_by_channel(env):
    """R15: el consentimiento de un canal no habilita al otro con el mismo id."""
    _consent(env, "telegram", "10")

    before = _post(env, "10", "m1")

    assert before.json() == {"status": "accepted"}
    assert len(env.gateway.channel_sent) == 1
    channel, destination, prompt = env.gateway.channel_sent[0]
    assert (channel, destination) == ("whatsapp", "chat-10")
    assert env.settings.privacy_notice_text in prompt
    assert ("whatsapp", "10") not in env.repo.contacts
    assert env.repo.messages == []

    accepted = _button(env, "10", "m2")
    assert accepted.json() == {"status": "accepted"}
    assert env.gateway.channel_sent[-1] == (
        "whatsapp",
        "chat-10",
        env.settings.privacy_accepted_reply,
    )
    assert [consent.channel for consent in env.repo.privacy_consents] == [
        "telegram",
        "whatsapp",
    ]

    after = _post(env, "10", "m3")
    assert after.json() == {"status": "accepted"}
    assert env.repo.contacts[("whatsapp", "10")].telegram_user_id is None

    # La aceptación WhatsApp tampoco habilita la identidad Telegram (R15).
    # Se usa otra identidad para no reutilizar el consentimiento Telegram ya
    # aceptado al inicio de la prueba.
    _consent(env, "whatsapp", "20")
    assert not env.repo.has_privacy_consent(20, env.settings.privacy_notice_version)
    telegram = env.post(user=20, chat=200, update_id=2, consent=False)
    assert telegram.json() == {"status": "accepted"}
    assert len(env.gateway.sent) == 1
    assert env.gateway.sent[0][0] == 200
    assert env.settings.privacy_notice_text in env.gateway.sent[0][1]
    assert 20 not in env.repo.contacts


def test_before_consent_no_contact_or_personal_data_is_persisted(env):
    """R21: sin consentimiento solo se envía el aviso y no se guarda nada."""
    response = _post(env, "57300", "m1")

    assert response.json() == {"status": "accepted"}
    assert len(env.gateway.channel_sent) == 1
    channel, destination, prompt = env.gateway.channel_sent[0]
    assert (channel, destination) == ("whatsapp", "chat-57300")
    assert env.settings.privacy_notice_text in prompt
    assert env.repo.contacts == {}
    assert env.repo.messages == []
    assert env.repo.events == []
    assert env.repo.privacy_consents == []
    assert env.repo.processed_messages == set()
    assert env.repo.processed == set()
    assert env.rag.calls == []


def test_canonical_telegram_before_consent_does_not_persist_message_id(env):
    """R21: el payload canónico de Telegram tampoco persiste la clave antes de consentir."""
    response = env.client.post(
        "/messages",
        json=_canonical(
            "10", "m1", channel="telegram", external_chat_id="100"
        ),
        headers=HEADERS,
    )

    assert response.json() == {"status": "accepted"}
    assert len(env.gateway.sent) == 1
    assert env.gateway.sent[0][0] == 100
    assert env.settings.privacy_notice_text in env.gateway.sent[0][1]
    assert env.repo.contacts == {}
    assert env.repo.processed_messages == set()
    assert env.repo.processed == set()


def test_canonical_telegram_numeric_before_consent_does_not_persist_message_id(env):
    """R21, R23: el canónico Telegram numérico no escribe deduplicación antes de consentir."""
    response = env.client.post(
        "/messages",
        json=_canonical("10", "1", channel="telegram", external_chat_id="100"),
        headers=HEADERS,
    )

    assert response.json() == {"status": "accepted"}
    assert len(env.gateway.sent) == 1
    assert env.gateway.sent[0][0] == 100
    assert env.settings.privacy_notice_text in env.gateway.sent[0][1]
    assert env.repo.contacts == {}
    assert env.repo.processed_messages == set()
    assert env.repo.processed == set()


def test_legacy_telegram_before_consent_only_persists_update_id(env):
    """R22: el endpoint legacy conserva solo `processed_updates(update_id)`."""
    response = env.post(consent=False, update_id=1)

    assert response.json() == {"status": "accepted"}
    assert env.repo.processed == {1}
    assert env.repo.processed_messages == set()
    assert env.repo.contacts == {}
    assert env.repo.messages == []


def test_request_without_privacy_config_does_not_persist_message_id(env_factory):
    """R23: sin aviso configurado no se guarda la clave ni en canónico ni en legacy."""
    env = env_factory(
        privacy_notice_text="",
        privacy_notice_version="",
        privacy_accept_phrase="",
        privacy_accepted_reply="",
        privacy_retention_days="",
    )

    canonical = env.client.post(
        "/messages", json=_canonical("57300", "m1"), headers=HEADERS
    )
    legacy = env.post(consent=False, update_id=2)

    assert canonical.json() == {"status": "accepted"}
    assert legacy.json() == {"status": "accepted"}
    assert env.repo.processed_messages == set()
    assert env.repo.contacts == {}
    assert env.repo.messages == []
    assert env.repo.processed == {2}


def test_button_acceptance_writes_evidence_and_opens_login_state(env):
    """R4, R21, R26: el botón crea la evidencia y después el contacto consentido."""
    response = _button(env, "57300", "m1")

    assert response.json() == {"status": "accepted"}
    assert env.repo.messages == []
    assert env.repo.events == []
    assert env.repo.processed_messages == set()
    assert env.repo.processed == set()
    [consent] = env.repo.privacy_consents
    assert (consent.channel, consent.external_user_id) == ("whatsapp", "57300")
    assert consent.telegram_user_id is None
    assert consent.external_message_id == "m1"
    assert consent.button_id == PRIVACY_ACCEPT_BUTTON
    contact = env.repo.contacts[("whatsapp", "57300")]
    assert env.repo.conversation_states[contact.id][0].value == "awaiting_login"


def test_persistent_dedup_starts_after_channel_consent(env):
    """R5, R21: tras consentir, la clave compuesta vuelve a ser la barrera persistente."""
    _consent(env, "whatsapp", "57300")

    first = _post(env, "57300", "m2")
    second = _post(env, "57300", "m2")

    assert first.json() == {"status": "accepted"}
    assert second.json() == {"status": "duplicate"}
    assert ("whatsapp", "m2") in env.repo.processed_messages


def test_whatsapp_identity_never_uses_the_telegram_column(env):
    """R16: el id externo de WhatsApp no se guarda ni consulta como telegram_user_id."""
    _consent(env, "whatsapp", "57300")
    _post(env, "57300", "m1")

    contact = env.repo.contacts[("whatsapp", "57300")]
    assert contact.telegram_user_id is None
    assert env.repo.get_or_create_contact(57300, 57300, FIXED_NOW).id != contact.id
    assert all(
        not (
            consent.channel == "whatsapp"
            and consent.telegram_user_id is not None
        )
        for consent in env.repo.privacy_consents
    )


def test_contacts_have_no_client_id_and_channels_are_not_linked(env):
    """R19: sin login verificado no se crea ni comparte `client_id`."""
    assert "client_id" not in Contact.model_fields

    env.post(user=10, chat=100, update_id=1)
    _consent(env, "whatsapp", "10")
    _post(env, "10", "m1")

    telegram = env.repo.contacts[10]
    whatsapp = env.repo.contacts[("whatsapp", "10")]
    assert telegram.id != whatsapp.id
    assert not hasattr(telegram, "client_id")
    assert not hasattr(whatsapp, "client_id")


def test_legacy_telegram_contact_gets_channel_and_external_ids(env):
    """R17: el alta Telegram histórica usa la pareja y conserva su id."""
    first = env.repo.get_or_create_contact(10, 100, FIXED_NOW)
    second = env.repo.get_or_create_contact(10, 100, FIXED_NOW)

    assert first.id == second.id
    assert first.channel == "telegram"
    assert first.external_user_id == "10"
    assert first.external_chat_id == "100"
    assert (first.telegram_user_id, first.chat_id) == (10, 100)
