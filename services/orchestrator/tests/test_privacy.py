"""Consentimiento y aviso de privacidad en la ruta de cliente (#27)."""
from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timezone

from fastapi.testclient import TestClient
from lazaro_contracts import MessageRequest
from orchestrator.domain import process_message
from orchestrator.privacy import PRIVACY_ACCEPT_BUTTON

FIXED_NOW = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
BUTTON_RECEIVED_AT = datetime(2026, 1, 2, 3, 4, 0, tzinfo=timezone.utc)
PRIVACY_NOTICE_TEXT = (
    "Aviso de privacidad. Tratamos tus datos para atender tu consulta. "
    "Acepto el tratamiento de mis datos."
)
PRIVACY_NOTICE_VERSION = "v1"
PRIVACY_ACCEPT_PHRASE = "Acepto el tratamiento de mis datos."
PRIVACY_ACCEPTED_REPLY = "Gracias. Ya puedes escribirnos."


def _no_processing(env) -> bool:
    return (
        env.repo.contacts == {}
        and env.repo.messages == []
        and env.repo.events == []
        and env.rag.calls == []
        and env.llm.calls == []
        and env.handover.requests == []
    )


def _empty_privacy(**overrides):
    values = {
        "privacy_notice_text": "",
        "privacy_notice_version": "",
        "privacy_accept_phrase": "",
        "privacy_accepted_reply": "",
        "privacy_retention_days": "",
    }
    values.update(overrides)
    return values


def test_without_privacy_config_drops_client_route(env_factory, caplog):
    """R4, R5, R6: sin configuración no se toca nada, se responde 202 y el log no lleva datos."""
    env = env_factory(**_empty_privacy())
    caplog.set_level(logging.INFO)
    secret = "TEXTO-SECRETO-DEL-CLIENTE"
    response = env.post(text=secret, user=987654321, chat=123456789, consent=False)
    assert response.status_code == 202
    assert response.json() == {"status": "accepted"}
    assert _no_processing(env)
    assert env.gateway.sent == []
    assert "privacy_not_configured" in caplog.text
    assert secret not in caplog.text
    assert "987654321" not in caplog.text
    assert "123456789" not in caplog.text


def test_without_consent_sends_notice_and_stores_nothing(env):
    """R7, R8 de #27 y R2 de #37: sin consentimiento solo se muestra el aviso."""
    response = env.post(text="¿Cómo instalo el módulo?", consent=False)
    assert response.status_code == 202
    [chat_id, prompt] = env.gateway.sent[0]
    assert chat_id == 100
    assert PRIVACY_NOTICE_TEXT in prompt
    assert "Acepto" in prompt and "No acepto" in prompt
    assert _no_processing(env)
    assert env.rag.calls == []
    assert env.llm.calls == []
    assert env.handover.requests == []
    assert env.repo.privacy_consents == []


def test_button_acceptance_records_consent(env):
    """R4, R24, R26: el botón guarda la prueba y deja la conversación en espera de login."""
    response = env.post_button(PRIVACY_ACCEPT_BUTTON, message_id="btn-1")
    assert response.json() == {"status": "accepted"}
    assert env.gateway.sent[-1] == (100, PRIVACY_ACCEPTED_REPLY)
    [consent] = env.repo.privacy_consents
    assert consent.telegram_user_id == 10
    assert consent.notice_version == PRIVACY_NOTICE_VERSION
    assert consent.notice_sha256 == hashlib.sha256(
        PRIVACY_NOTICE_TEXT.encode("utf-8")
    ).hexdigest()
    assert consent.accepted_at == BUTTON_RECEIVED_AT
    assert consent.external_message_id == "btn-1"
    assert consent.button_id == PRIVACY_ACCEPT_BUTTON
    assert consent.result == "accepted" and consent.evidence_type == "button"
    contact = env.repo.contacts[10]
    assert env.repo.conversation_states[contact.id][0].value == "awaiting_login"
    assert env.repo.messages == [] and env.repo.events == []
    assert env.rag.calls == [] and env.llm.calls == []
    assert env.handover.requests == []


def test_acceptance_with_extra_text_does_not_record_consent(env):
    """R6, R34: el texto afirmativo no concede; solo pide usar el botón."""
    response = env.post(
        text=f"{PRIVACY_ACCEPT_PHRASE} y además quiero otra cosa.", consent=False
    )
    assert response.status_code == 202
    assert env.repo.privacy_consents == []
    assert _no_processing(env)
    assert all(
        PRIVACY_NOTICE_TEXT in text or "botón" in text
        for _, text in env.gateway.sent
    )


def test_personal_routes_never_create_consent(env):
    """R14 de #27 y R10/R15 de #35: un remitente no personal recibe el aviso."""
    for index, text in enumerate(
        ["/start token-invalido", "/consultar cuántos pedidos hay", "/responder case-1 hola", "/cerrar case-1"],
        start=1,
    ):
        response = env.post(text=text, update_id=index, user=111, chat=111, consent=False)
        assert response.status_code == 202
    assert env.repo.privacy_consents == []
    assert len(env.gateway.sent) == 4
    assert all(chat_id == 111 for chat_id, _ in env.gateway.sent)
    assert all(PRIVACY_NOTICE_TEXT in text for _, text in env.gateway.sent)


def test_version_change_requires_new_acceptance_and_keeps_old_rows(env):
    """R7, R15: un consentimiento de otra versión no vale; el anterior se conserva."""
    env.repo.add_privacy_consent(10, "v0", "sha-v0", FIXED_NOW)
    env.post(text="hola", consent=False)
    assert PRIVACY_NOTICE_TEXT in env.gateway.sent[-1][1]
    assert env.repo.messages == []

    env.post_button(PRIVACY_ACCEPT_BUTTON, message_id="btn-v1")
    assert [c.notice_version for c in env.repo.privacy_consents] == ["v0", "v1"]


def test_current_consent_keeps_the_normal_flow(env):
    """R16: con consentimiento vigente la ruta de cliente funciona como antes."""
    response = env.post()
    assert response.status_code == 202
    assert env.rag.calls == [("¿Cómo instalo el módulo?", 7)]
    assert env.gateway.sent == [(100, "Respuesta final")]
    assert [m.role for m in env.repo.messages] == ["user", "bot"]


def test_consent_store_failure_returns_500_without_confirmation(env):
    """R4, R17, R18: si falla guardar la evidencia no se confirma y se responde 500."""
    env.repo.fail_privacy_consent = True
    # `raise_server_exceptions=False` deja ver la respuesta del handler global
    # en lugar de propagar la excepción del transporte de TestClient.
    client = TestClient(env.client.app, raise_server_exceptions=False)
    response = client.post(
        "/messages",
        json={
            "channel": "telegram",
            "external_user_id": "10",
            "external_chat_id": "100",
            "external_message_id": "btn-fail",
            "kind": "button",
            "button_id": PRIVACY_ACCEPT_BUTTON,
            "button_proof": env.button_proof(
                PRIVACY_ACCEPT_BUTTON, user=10, channel="telegram"
            ),
            "received_at": "2026-01-02T03:04:00+00:00",
        },
        headers={"X-Service-Token": "svc-token"},
        # El botón se procesa en la petición; el handler global devuelve 500.
        follow_redirects=False,
    )
    assert response.status_code == 500
    assert response.json()["error"] == "internal_error"
    assert all(text != PRIVACY_ACCEPTED_REPLY for _, text in env.gateway.sent)
    assert env.repo.privacy_consents == []


def test_personal_routes_work_without_privacy_configuration(env_factory):
    """R6 de #35: el personal vinculado opera sin configuración ni consentimiento."""
    env = env_factory(**_empty_privacy())
    profile = env.repo.create_profile("asesor1", "asesor", "hash", FIXED_NOW)
    env.repo.profiles[profile.id].telegram_user_id = 111
    texts = [
        "/start token-invalido",
        "/consultar cuántos pedidos hay",
        "/responder case-1 hola",
        "/cerrar case-1",
    ]
    for index, text in enumerate(texts, start=1):
        response = env.post(
            text=text, update_id=index, user=111, chat=111, consent=False
        )
        assert response.status_code == 202
    assert env.gateway.sent[0] == (111, env.settings.link_failed_reply)
    assert len(env.repo.db_query_audits) == 1
    assert len(env.handover.authorized) == 2
    assert all(
        text not in (PRIVACY_NOTICE_TEXT, PRIVACY_ACCEPTED_REPLY)
        for _, text in env.gateway.sent
    )


def test_gate_direct_call_blocks_before_contact(env_factory):
    """R4, R8: process_message no crea contacto cuando la puerta descarta el mensaje."""
    env = env_factory(**_empty_privacy())
    request = MessageRequest(
        update_id=1,
        telegram_user_id=10,
        chat_id=100,
        text="hola",
        received_at=FIXED_NOW,
    )
    process_message(request, env.settings, env.adapters)
    assert env.repo.contacts == {}
