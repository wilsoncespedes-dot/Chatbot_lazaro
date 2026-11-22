"""Consentimiento por frase de texto en Telegram (#46, R1-R32)."""
from __future__ import annotations

import threading
from dataclasses import replace
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from lazaro_contracts import LinkBlock, NormalizedMessage, OptionsBlock, TextBlock
from pydantic import ValidationError

from orchestrator.adapters.repository import PostgresRepository
from orchestrator.config import Settings
from orchestrator.domain import (
    ConversationState,
    process_channel_message as _process_channel_message,
)
from orchestrator.privacy import (
    PRIVACY_ACCEPT_BUTTON,
    PRIVACY_REJECT_BUTTON,
    ConsentChallengeStore,
    matches_consent_phrase,
    notice_sha256,
)

from fakes import drain_queues


def process_channel_message(message, settings, adapters):
    _process_channel_message(message, settings, adapters)
    drain_queues(settings, adapters)

NOW = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
RECEIVED_AT = "2026-01-02T03:04:00+00:00"
SERVICE_TOKEN = "svc-token"


def _message(
    text: str | None = None,
    *,
    channel: str = "telegram",
    user: str = "10",
    chat: str = "100",
    message_id: str = "m1",
    kind: str = "text",
) -> NormalizedMessage:
    return NormalizedMessage(
        channel=channel,  # type: ignore[arg-type]
        external_user_id=user,
        external_chat_id=chat,
        external_message_id=message_id,
        kind=kind,  # type: ignore[arg-type]
        text=text,
        received_at=NOW,
    )


def _canonical(
    text: str,
    *,
    channel: str = "telegram",
    user: str = "10",
    chat: str = "100",
    message_id: str = "m1",
    kind: str = "text",
) -> dict:
    return {
        "channel": channel,
        "external_user_id": user,
        "external_chat_id": chat,
        "external_message_id": message_id,
        "kind": kind,
        "text": text,
        "received_at": RECEIVED_AT,
    }


def _last_prompt(env) -> str:
    return env.gateway.channel_sent[-1][2]


def _last_blocks(env) -> list:
    return env.gateway.blocks_sent[-1][2]


# --- Configuración (R1-R4) ---------------------------------------------------


def test_accept_phrase_defaults_to_acepto():
    """R1: sin PRIVACY_ACCEPT_PHRASE la frase efectiva es ACEPTO."""
    assert Settings().consent_accept_phrase == "ACEPTO"


def test_reject_phrase_defaults_to_no_acepto():
    """R2: sin PRIVACY_REJECT_PHRASE la frase efectiva es NO ACEPTO."""
    assert Settings().consent_reject_phrase == "NO ACEPTO"


def test_configured_phrases_override_defaults():
    """R1, R2: las frases configuradas se usan sin espacios extremos."""
    settings = Settings(
        privacy_accept_phrase="  Escribo ACEPTO  ",
        privacy_reject_phrase="  NO QUIERO  ",
    )
    assert settings.consent_accept_phrase == "Escribo ACEPTO"
    assert settings.consent_reject_phrase == "NO QUIERO"


def test_equal_phrases_fail_settings():
    """R3: frases efectivas iguales tras normalizar impiden cargar Settings."""
    with pytest.raises(ValidationError) as error:
        Settings(
            privacy_accept_phrase="ACEPTO",
            privacy_reject_phrase="  acepto ",
        )
    assert "PRIVACY_REJECT_PHRASE" in str(error.value)


def test_instruction_without_placeholders_fails_settings():
    """R4: la instrucción debe contener los marcadores de ambas frases."""
    with pytest.raises(ValidationError) as error:
        Settings(privacy_text_consent_instruction="escribe acepto")
    assert "PRIVACY_TEXT_CONSENT_INSTRUCTION" in str(error.value)


# --- Utilidades puras (R5, R11, R14) ----------------------------------------


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("  acepto ", True),
        ("NO ACEPTO", False),
        ("acepto por favor", False),
        ("sí acepto", False),
    ],
)
def test_phrase_match_is_exact_after_normalization(text, expected):
    """R5: igualdad normalizada, nunca contención."""
    assert matches_consent_phrase(text, "ACEPTO") is expected


def test_consume_text_requires_same_version_hash_and_chat():
    """R11, R14: el desafío solo se consume con versión, hash y chat vigentes."""
    store = ConsentChallengeStore()
    store.register("telegram", "10", "100", "v1", "sha")

    assert not store.consume_text(
        "telegram", "10", "100", notice_version="v2", notice_sha="sha"
    )
    assert not store.consume_text(
        "telegram", "10", "100", notice_version="v1", notice_sha="otro"
    )
    assert not store.consume_text(
        "telegram", "10", "200", notice_version="v1", notice_sha="sha"
    )
    assert store.consume_text(
        "telegram", "10", "100", notice_version="v1", notice_sha="sha"
    )
    assert not store.consume_text(
        "telegram", "10", "100", notice_version="v1", notice_sha="sha"
    )


def test_consume_text_consumes_only_once():
    """R11: dos frases simultáneas sobre la misma presentación dejan una decisión."""
    store = ConsentChallengeStore()
    store.register("telegram", "10", "100", "v1", "sha")
    barrier = threading.Barrier(2)
    results: list[bool] = []

    def consume() -> None:
        barrier.wait()
        results.append(
            store.consume_text(
                "telegram", "10", "100", notice_version="v1", notice_sha="sha"
            )
        )

    threads = [threading.Thread(target=consume) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert sorted(results) == [False, True]


# --- Repositorio (R13) -------------------------------------------------------


def test_text_evidence_counts_as_current_consent(env):
    """R13: una evidencia text de la versión vigente habilita el flujo."""
    version = env.settings.privacy_notice_version
    env.repo.add_privacy_decision(
        "telegram",
        "10",
        version,
        notice_sha256(env.settings.privacy_notice_text),
        "accepted",
        "m1",
        "",
        NOW,
        evidence_type="text",
    )

    assert env.repo.has_channel_privacy_consent("telegram", "10", version)


class _Cursor:
    def __init__(self) -> None:
        self.statements: list[tuple[str, tuple]] = []

    def execute(self, sql: str, params: tuple = ()) -> None:
        self.statements.append((sql, tuple(params)))

    def fetchall(self) -> list[tuple]:
        return [("ok",)]


class _Conn:
    def __init__(self) -> None:
        self._cursor = _Cursor()

    def cursor(self) -> _Cursor:
        return self._cursor

    def commit(self) -> None:
        pass

    def rollback(self) -> None:
        pass


def test_postgres_consent_query_accepts_button_and_text():
    """R13: el SQL de Postgres consulta ambas evidencias."""
    conn = _Conn()
    repo = PostgresRepository("postgresql://x", connect=lambda: conn)

    assert repo.has_channel_privacy_consent("telegram", "10", "v1") is True
    sql = conn._cursor.statements[-1][0]
    assert "evidence_type IN ('button', 'text')" in sql


# --- Aviso Telegram (R6-R9, R28) ---------------------------------------------


def test_telegram_notice_has_no_options_block(env):
    """R6: el aviso de Telegram solo lleva bloques de texto."""
    env.present()

    blocks = _last_blocks(env)
    assert blocks
    assert all(isinstance(block, TextBlock) for block in blocks)
    assert not any(isinstance(block, OptionsBlock) for block in blocks)


def test_telegram_notice_text_is_panel_notice_plus_instruction(env):
    """R7: aviso vigente con saludo en la primera presentación e instrucción efectiva."""
    env.present()

    prompt = _last_prompt(env)
    assert env.settings.conversation_greeting in prompt
    assert env.settings.privacy_notice_text in prompt
    assert env.settings.consent_accept_phrase in prompt
    assert env.settings.consent_reject_phrase in prompt

    env.present()
    assert env.settings.conversation_greeting not in _last_prompt(env)


@pytest.mark.parametrize("channel", ["telegram", "whatsapp"])
def test_notice_text_never_contains_button_ids(env, channel):
    """R8: ningún aviso muestra los ids internos de botón."""
    env.present(channel=channel)

    prompt = _last_prompt(env)
    assert PRIVACY_ACCEPT_BUTTON not in prompt
    assert PRIVACY_REJECT_BUTTON not in prompt


def test_telegram_notice_registers_challenge_with_version_hash_chat(env):
    """R9: el aviso de texto registra el desafío ligado a versión, hash y chat."""
    env.present()

    challenge = env.adapters.consent_challenges.get("telegram", "10")
    assert challenge is not None
    assert challenge.notice_version == env.settings.privacy_notice_version
    assert challenge.notice_sha256 == notice_sha256(env.settings.privacy_notice_text)
    assert challenge.external_chat_id == "100"


def test_telegram_notice_registers_challenge_and_enqueues_notice(env):
    """R9: el desafío existe y el aviso se entrega por la cola de salida (#64)."""
    process_channel_message(_message("Hola"), env.settings, env.adapters)

    assert env.adapters.consent_challenges.get("telegram", "10") is not None
    assert env.settings.privacy_notice_text in env.gateway.channel_sent[-1][2]


# --- Aceptación por texto (R10, R12, R14-R17) --------------------------------


def test_exact_accept_after_notice_records_text_evidence(env):
    """R10: aceptar tras el aviso guarda la evidencia text completa."""
    env.present()

    process_channel_message(
        _message(env.settings.consent_accept_phrase, message_id="accept-1"),
        env.settings,
        env.adapters,
    )

    [consent] = env.repo.privacy_consents
    assert consent.result == "accepted"
    assert consent.evidence_type == "text"
    assert consent.external_message_id == "accept-1"
    assert consent.notice_version == env.settings.privacy_notice_version
    assert consent.notice_sha256 == notice_sha256(env.settings.privacy_notice_text)
    assert consent.button_id == ""
    assert consent.accepted_at == NOW
    assert consent.occurred_at == NOW


def test_legacy_route_accept_uses_update_id_as_external_message_id(env):
    """R10: la ruta histórica usa el update_id como id externo canónico."""
    env.present()

    response = env.post(
        text=env.settings.consent_accept_phrase,
        update_id=42,
        user=10,
        chat=100,
        consent=False,
    )

    assert response.status_code == 202
    [consent] = env.repo.privacy_consents
    assert consent.external_message_id == "42"
    assert consent.evidence_type == "text"


def test_text_accept_continues_to_awaiting_login_with_link(env_factory):
    """R12: aceptar por texto crea el contacto, espera login y envía el enlace."""
    env = env_factory(
        identity_public_base_url="https://orchestrator.example",
        identity_link_signing_key="k" * 32,
    )
    env.present()

    process_channel_message(
        _message(env.settings.consent_accept_phrase, message_id="accept-link"),
        env.settings,
        env.adapters,
    )

    contact = env.repo.contacts[10]
    assert env.repo.conversation_states[contact.id][0] == ConversationState.AWAITING_LOGIN
    channel, destination, blocks = env.gateway.blocks_sent[-1]
    assert (channel, destination) == ("telegram", "100")
    assert blocks[0].text == env.settings.privacy_accepted_reply
    assert any(isinstance(block, LinkBlock) for block in blocks)
    assert env.repo.login_links


def test_accept_phrase_before_notice_shows_notice_without_decision(env):
    """R14, R15: la frase antes del aviso no registra y muestra el aviso."""
    response = env.post(
        text=env.settings.consent_accept_phrase,
        update_id=1,
        user=10,
        chat=100,
        consent=False,
    )

    assert response.status_code == 202
    assert env.repo.privacy_consents == []
    assert env.settings.privacy_notice_text in _last_prompt(env)


def test_reject_phrase_before_notice_shows_notice_without_decision(env):
    """R14, R15: la frase de rechazo antes del aviso tampoco registra."""
    response = env.post(
        text=env.settings.consent_reject_phrase,
        update_id=1,
        user=10,
        chat=100,
        consent=False,
    )

    assert response.status_code == 202
    assert env.repo.privacy_consents == []
    assert env.settings.privacy_notice_text in _last_prompt(env)


def test_accept_after_version_change_requires_new_notice(env):
    """R14: un desafío de otra versión no sirve aunque la frase coincida."""
    env.present()
    texts = env.repo.get_conversation_texts()
    env.repo.save_conversation_texts(
        replace(
            texts,
            notice_text=f"{texts.notice_text} Aviso v2.",
            notice_version="v2",
        ),
        "admin-1",
        NOW,
    )

    process_channel_message(
        _message(env.settings.consent_accept_phrase, message_id="accept-v2"),
        env.settings,
        env.adapters,
    )

    assert env.repo.privacy_consents == []
    assert "Aviso v2." in _last_prompt(env)


def test_accept_from_other_chat_does_not_consume_challenge(env):
    """R14: un chat distinto no registra ni consume la presentación vigente."""
    env.present()

    process_channel_message(
        _message(env.settings.consent_accept_phrase, chat="200", message_id="accept-other"),
        env.settings,
        env.adapters,
    )
    assert env.repo.privacy_consents == []
    assert env.repo.contacts == {}

    env.present(user=10, chat=100)
    process_channel_message(
        _message(env.settings.consent_accept_phrase, chat="100", message_id="accept-right"),
        env.settings,
        env.adapters,
    )
    assert len(env.repo.privacy_consents) == 1


def test_second_accept_phrase_does_not_record_twice(env):
    """R11, R14: tras aceptar, otra frase no registra una segunda decisión."""
    env.present()

    process_channel_message(
        _message(env.settings.consent_accept_phrase, message_id="accept-1"),
        env.settings,
        env.adapters,
    )
    process_channel_message(
        _message(env.settings.consent_accept_phrase, message_id="accept-2"),
        env.settings,
        env.adapters,
    )

    assert len(env.repo.privacy_consents) == 1


# --- Rechazo por texto (R18-R20) ---------------------------------------------


def test_reject_phrase_after_notice_records_minimal_text_decision_and_replies(env):
    """R18: rechazar tras el aviso deja la evidencia mínima y responde fijo."""
    env.present()

    process_channel_message(
        _message(env.settings.consent_reject_phrase, message_id="reject-1"),
        env.settings,
        env.adapters,
    )

    [consent] = env.repo.privacy_consents
    assert consent.result == "rejected"
    assert consent.evidence_type == "text"
    assert consent.external_message_id == "reject-1"
    assert consent.notice_version == env.settings.privacy_notice_version
    assert consent.notice_sha256 == notice_sha256(env.settings.privacy_notice_text)
    assert consent.accepted_at is None
    # R18: el chat numérico de Telegram usa la entrega legacy de `_notify_channel`.
    assert env.gateway.sent[-1] == (
        100,
        env.settings.conversation_rejected_reply,
    )
    notices = [
        text
        for _channel, _destination, text in env.gateway.channel_sent
        if env.settings.privacy_notice_text in text
    ]
    assert len(notices) == 1


def test_reject_phrase_leaves_only_privacy_consents_row(env):
    """R19: rechazar no conserva filas personales para el remitente."""
    env.present()
    contact = env.repo.get_or_create_channel_contact("telegram", "10", "100", NOW)
    env.repo.add_message(contact.id, "user", "dato personal", NOW)
    env.repo.add_event(contact.id, "rag_answer", "chunks_found", NOW)
    env.repo.link_case("case-1", contact.id, NOW)
    calls: list[tuple[str, str]] = []
    original = env.repo.delete_contact_content

    def spy(channel: str, external_user_id: str) -> None:
        calls.append((channel, external_user_id))
        original(channel, external_user_id)

    env.repo.delete_contact_content = spy  # type: ignore[method-assign]

    process_channel_message(
        _message(env.settings.consent_reject_phrase, message_id="reject-1"),
        env.settings,
        env.adapters,
    )

    assert calls == [("telegram", "10")]
    assert env.repo.contacts == {}
    assert env.repo.messages == []
    assert env.repo.events == []
    assert env.repo.case_links == {}
    assert env.repo.db_query_audits == []
    assert env.repo.rag_streaks == {}
    assert env.repo.rag_outcomes == set()
    assert all(profile.telegram_user_id != 10 for profile in env.repo.profiles.values())
    assert len(env.repo.privacy_consents) == 1


def test_after_reject_accept_phrase_restarts_and_shows_notice(env):
    """R20: tras rechazar, la frase de aceptación reinicia y solo muestra el aviso."""
    env.present()
    process_channel_message(
        _message(env.settings.consent_reject_phrase, message_id="reject-1"),
        env.settings,
        env.adapters,
    )

    process_channel_message(
        _message(env.settings.consent_accept_phrase, message_id="accept-after-reject"),
        env.settings,
        env.adapters,
    )

    assert [consent.result for consent in env.repo.privacy_consents] == ["rejected"]
    assert env.settings.conversation_greeting in _last_prompt(env)
    assert env.settings.privacy_notice_text in _last_prompt(env)


# --- Texto no coincidente (R21-R23) ------------------------------------------


def test_non_matching_text_resends_notice_with_instruction(env):
    """R21: un texto distinto recuerda el aviso con la instrucción de frases."""
    env.present()

    process_channel_message(
        _message("¿Cómo instalo el módulo?", message_id="m2"),
        env.settings,
        env.adapters,
    )

    prompt = _last_prompt(env)
    assert env.settings.privacy_notice_text in prompt
    assert env.settings.consent_accept_phrase in prompt
    assert env.settings.consent_reject_phrase in prompt
    assert env.repo.privacy_consents == []


def test_non_matching_text_persists_nothing_and_skips_llm(env):
    """R22: el texto no coincidente no crea datos ni llama a RAG/LLM."""
    env.present()

    process_channel_message(
        _message("¿Cómo instalo el módulo?", message_id="m2"),
        env.settings,
        env.adapters,
    )

    assert env.repo.contacts == {}
    assert env.repo.messages == []
    assert env.repo.events == []
    assert env.repo.conversation_states == {}
    assert env.rag.calls == []
    assert env.llm.calls == []


@pytest.mark.parametrize("text", ["sí", "sí acepto"])
def test_affirmation_without_exact_phrase_does_not_use_button_reply(env, text):
    """R23: una afirmación parecida se trata como texto no coincidente."""
    env.present()

    process_channel_message(
        _message(text, message_id="m2"), env.settings, env.adapters
    )

    assert env.repo.privacy_consents == []
    assert env.settings.conversation_confirm_button_reply not in _last_prompt(env)
    assert env.settings.consent_accept_phrase in _last_prompt(env)


# --- Procesamiento en la petición y deduplicación (R16, R17) ------------------


def test_text_accept_storage_failure_returns_500(env):
    """R16: la aceptación se procesa en la petición y un fallo responde 500."""
    env.present()
    env.repo.fail_privacy_consent = True
    client = TestClient(env.client.app, raise_server_exceptions=False)

    response = client.post(
        "/messages",
        json=_canonical(
            env.settings.consent_accept_phrase, message_id="accept-fail"
        ),
        headers={"X-Service-Token": SERVICE_TOKEN},
        follow_redirects=False,
    )

    assert response.status_code == 500
    assert response.json()["error"] == "internal_error"
    assert env.repo.privacy_consents == []
    assert all(
        text != env.settings.privacy_accepted_reply
        for _channel, _destination, text in env.gateway.channel_sent
    )


def test_redelivered_accept_message_is_duplicate(env):
    """R17: la reentrega del mismo mensaje responden duplicate y no duplica."""
    env.present()
    body = _canonical(env.settings.consent_accept_phrase, message_id="accept-dup")

    first = env.client.post(
        "/messages", json=body, headers={"X-Service-Token": SERVICE_TOKEN}
    )
    drain_queues(env.settings, env.adapters)
    second = env.client.post(
        "/messages", json=body, headers={"X-Service-Token": SERVICE_TOKEN}
    )

    assert first.json() == {"status": "accepted"}
    assert second.json() == {"status": "duplicate"}
    assert len(env.repo.privacy_consents) == 1
    assert [
        text for _channel, _destination, text in env.gateway.channel_sent
    ].count(env.settings.privacy_accepted_reply) == 1


# --- Botones antiguos de Telegram (R25-R27) ----------------------------------


def test_telegram_button_with_valid_proof_records_nothing(env):
    """R25: un botón antiguo de Telegram no registra decisión aunque la prueba valga."""
    env.present()
    proof = env.button_proof(PRIVACY_ACCEPT_BUTTON, user=10, channel="telegram")

    response = env.post_button(
        PRIVACY_ACCEPT_BUTTON,
        user=10,
        chat=100,
        channel="telegram",
        proof=proof,
        message_id="btn-telegram",
    )

    assert response.status_code == 202
    assert env.repo.privacy_consents == []
    assert env.repo.contacts == {}


def test_telegram_button_returns_202_and_resends_text_notice(env):
    """R26: el botón antiguo responde 202 y reenvía el aviso de texto sin botones."""
    env.present()
    proof = env.button_proof(PRIVACY_ACCEPT_BUTTON, user=10, channel="telegram")

    response = env.post_button(
        PRIVACY_ACCEPT_BUTTON,
        user=10,
        chat=100,
        channel="telegram",
        proof=proof,
        message_id="btn-telegram",
    )

    assert response.status_code == 202
    blocks = _last_blocks(env)
    assert all(isinstance(block, TextBlock) for block in blocks)
    assert env.settings.privacy_notice_text in blocks[0].text
    assert env.settings.consent_accept_phrase in blocks[0].text
    assert env.repo.privacy_consents == []


def test_telegram_button_after_consent_is_ignored(env):
    """R27: con consentimiento vigente el botón no escribe ni responde."""
    env.repo.add_privacy_consent(
        10,
        env.settings.privacy_notice_version,
        notice_sha256(env.settings.privacy_notice_text),
        NOW,
    )
    before = list(env.gateway.channel_sent)

    response = env.post_button(
        PRIVACY_ACCEPT_BUTTON,
        user=10,
        chat=100,
        channel="telegram",
        proof="f" * 32,
        message_id="btn-post",
    )

    assert response.status_code == 202
    assert env.gateway.channel_sent == before
    assert len(env.repo.privacy_consents) == 1


# --- WhatsApp sin cambios (R28-R30) -----------------------------------------


def test_whatsapp_notice_keeps_signed_options_block(env):
    """R28: WhatsApp conserva el aviso con opciones y pruebas firmadas."""
    env.present(channel="whatsapp")

    options = [
        block for block in _last_blocks(env) if isinstance(block, OptionsBlock)
    ]
    assert len(options) == 1
    assert options[0].options == ["Acepto", "No acepto"]
    assert options[0].option_ids == [PRIVACY_ACCEPT_BUTTON, PRIVACY_REJECT_BUTTON]
    assert all(options[0].option_proofs)


def test_whatsapp_button_accept_records_button_evidence(env):
    """R29: el botón de WhatsApp registra evidencia button como en #37."""
    env.present(channel="whatsapp", user=57300, chat=57301)
    proof = env.button_proof(
        PRIVACY_ACCEPT_BUTTON, user=57300, chat=57301, channel="whatsapp"
    )

    response = env.post_button(
        PRIVACY_ACCEPT_BUTTON,
        user=57300,
        chat=57301,
        channel="whatsapp",
        proof=proof,
        message_id="ws-btn",
    )

    assert response.status_code == 202
    [consent] = env.repo.privacy_consents
    assert (consent.channel, consent.external_user_id) == ("whatsapp", "57300")
    assert consent.result == "accepted"
    assert consent.evidence_type == "button"
    assert consent.external_message_id == "ws-btn"


def test_whatsapp_accept_phrase_does_not_grant_consent(env):
    """R30: en WhatsApp la frase no acepta; se pide el botón."""
    env.present(channel="whatsapp", user=57300, chat=57301)

    process_channel_message(
        _message("ACEPTO", channel="whatsapp", user="57300", chat="57301", message_id="ws-text"),
        env.settings,
        env.adapters,
    )

    assert env.repo.privacy_consents == []
    assert (
        "whatsapp",
        "57301",
        env.settings.conversation_confirm_button_reply,
    ) in env.gateway.channel_sent
    assert isinstance(_last_blocks(env)[-1], OptionsBlock)
