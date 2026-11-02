"""Consentimiento y aviso de privacidad en la ruta de cliente (#27)."""
from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timezone

from lazaro_contracts import MessageRequest
from orchestrator.domain import process_message

FIXED_NOW = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
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
    """R7, R8: sin consentimiento se envía el aviso y no se procesa ni guarda nada."""
    response = env.post(text="¿Cómo instalo el módulo?", consent=False)
    assert response.status_code == 202
    assert env.gateway.sent == [(100, PRIVACY_NOTICE_TEXT)]
    assert _no_processing(env)
    assert env.rag.calls == []
    assert env.llm.calls == []
    assert env.handover.requests == []
    assert env.repo.privacy_consents == []


def test_exact_acceptance_records_consent(env):
    """R9, R10, R11: la frase exacta guarda la prueba y no se procesa como mensaje."""
    response = env.post(text="  acepto   el TRATAMIENTO de mis datos.  ", consent=False)
    assert response.status_code == 202
    assert env.gateway.sent == [(100, PRIVACY_ACCEPTED_REPLY)]
    [consent] = env.repo.privacy_consents
    assert consent.telegram_user_id == 10
    assert consent.notice_version == PRIVACY_NOTICE_VERSION
    assert consent.notice_sha256 == hashlib.sha256(
        PRIVACY_NOTICE_TEXT.encode("utf-8")
    ).hexdigest()
    assert consent.accepted_at == FIXED_NOW
    assert env.repo.messages == [] and env.repo.events == []
    assert env.repo.contacts == {}
    assert env.rag.calls == [] and env.llm.calls == []
    assert env.handover.requests == []


def test_acceptance_with_extra_text_does_not_record_consent(env):
    """R12, R13: la frase con texto extra no acepta y vuelve a enviar el aviso."""
    response = env.post(
        text=f"{PRIVACY_ACCEPT_PHRASE} y además quiero otra cosa.", consent=False
    )
    assert response.status_code == 202
    assert env.gateway.sent == [(100, PRIVACY_NOTICE_TEXT)]
    assert env.repo.privacy_consents == []
    assert _no_processing(env)


def test_personal_routes_never_create_consent(env):
    """R14: /start y los comandos de personal no crean consentimiento."""
    for index, text in enumerate(
        ["/start token-invalido", "/consultar cuántos pedidos hay", "/responder case-1 hola", "/cerrar case-1"],
        start=1,
    ):
        response = env.post(text=text, update_id=index, user=111, chat=111, consent=False)
        assert response.status_code == 202
    assert env.repo.privacy_consents == []
    assert all(text != PRIVACY_NOTICE_TEXT for _, text in env.gateway.sent)


def test_version_change_requires_new_acceptance_and_keeps_old_rows(env):
    """R15: un consentimiento de otra versión no vale; el anterior se conserva."""
    env.repo.add_privacy_consent(10, "v0", "sha-v0", FIXED_NOW)
    env.post(text="hola", consent=False)
    assert env.gateway.sent == [(100, PRIVACY_NOTICE_TEXT)]
    assert env.repo.messages == []

    env.post(text=PRIVACY_ACCEPT_PHRASE, update_id=2, consent=False)
    assert [c.notice_version for c in env.repo.privacy_consents] == ["v0", "v1"]


def test_current_consent_keeps_the_normal_flow(env):
    """R16: con consentimiento vigente la ruta de cliente funciona como antes."""
    response = env.post()
    assert response.status_code == 202
    assert env.rag.calls == [("¿Cómo instalo el módulo?", 7)]
    assert env.gateway.sent == [(100, "Respuesta final")]
    assert [m.role for m in env.repo.messages] == ["user", "bot"]


def test_consent_store_failure_returns_500_without_confirmation(env):
    """R17, R18: si falla guardar el consentimiento no se confirma y se responde 500."""
    env.repo.fail_privacy_consent = True
    response = env.post(
        text=PRIVACY_ACCEPT_PHRASE, consent=False, raise_server_exceptions=False
    )
    assert response.status_code == 500
    assert response.json()["error"] == "internal_error"
    assert env.gateway.sent == []
    assert env.repo.privacy_consents == []


def test_personal_routes_work_without_privacy_configuration(env_factory):
    """R19: /start, /consultar, /responder y /cerrar funcionan sin configuración ni consentimiento."""
    env = env_factory(**_empty_privacy())
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
