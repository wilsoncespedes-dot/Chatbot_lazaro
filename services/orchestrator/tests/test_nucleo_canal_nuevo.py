"""R26–R30, R38–R42 (#65): un canal nuevo (`simulado`) recorre el flujo completo."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fakes import drain_queues
from lazaro_contracts import LinkBlock

from orchestrator.domain import (
    ConversationState,
    PanelValidationError,
    advisor_inbox,
    create_client,
    inbox_channel_options,
    login_client,
)

NOW = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
RECEIVED_AT = "2026-01-02T03:04:00+00:00"
TOKEN = "svc-token"
HEADERS = {"X-Service-Token": TOKEN}
PASSWORD = "clave-segura-123"
CHANNEL = "simulado"
USER = "cliente-demo"
DEST = "buzon-demo"


def _message(text: str, message_id: str, **changes) -> dict:
    body = {
        "channel": CHANNEL,
        "external_user_id": USER,
        "external_chat_id": DEST,
        "external_message_id": message_id,
        "kind": "text",
        "text": text,
        "received_at": RECEIVED_AT,
    }
    body.update(changes)
    return body


def _post(env, body: dict):
    response = env.client.post("/messages", json=body, headers=HEADERS)
    drain_queues(env.settings, env.adapters)
    return response


def _login_env(env_factory):
    return env_factory(
        identity_login_required=True,
        identity_public_base_url="https://orchestrator.example",
        identity_link_signing_key="k" * 32,
        password_scrypt_n=16384,
    )


def _sent_to_simulado(env) -> list[str]:
    return [text for channel, dest, text in env.gateway.channel_sent if (channel, dest) == (CHANNEL, DEST)]


def test_new_channel_full_flow_from_consent_to_advisor_reply(env_factory, panel):
    """R39–R42: consentimiento, login, bot, escalamiento y respuesta del asesor por el mismo canal."""
    env = _login_env(env_factory)
    create_client(
        "cliente1", PASSWORD, NOW - timedelta(days=1), NOW + timedelta(days=30),
        env.settings, env.adapters,
    )

    # R39: primer mensaje → aviso de privacidad por el mismo canal y destino.
    assert _post(env, _message("Hola", "m-1")).status_code == 202
    notice = _sent_to_simulado(env)[-1]
    assert env.settings.privacy_notice_text in notice
    assert env.settings.consent_accept_phrase in notice
    assert all(channel == CHANNEL for channel, _, _ in env.gateway.channel_sent)

    # R40: acepta → enlace de acceso por el mismo canal.
    assert _post(env, _message(env.settings.consent_accept_phrase, "m-2")).status_code == 202
    channel, destination, blocks = env.gateway.blocks_sent[-1]
    assert (channel, destination) == (CHANNEL, DEST)
    [link] = [block for block in blocks if isinstance(block, LinkBlock)]
    contact = env.repo.contacts[(CHANNEL, USER)]
    assert env.repo.get_conversation_state(contact.id) == ConversationState.AWAITING_LOGIN

    token = str(link.url).split("t=", 1)[1]
    outcome = login_client(token, "cliente1", PASSWORD, "1.1.1.1", env.settings, env.adapters)
    drain_queues(env.settings, env.adapters)
    assert outcome.status == "ok"
    assert env.repo.get_conversation_state(contact.id) == ConversationState.ACTIVE
    assert env.repo.get_conversation_texts().active_welcome in _sent_to_simulado(env)

    # R40: escribe → el bot responde por el mismo canal y destino.
    assert _post(env, _message("¿Cómo instalo el módulo?", "m-3")).status_code == 202
    assert _sent_to_simulado(env)[-1] == "Respuesta final"

    # R41: pide asesor → el caso se crea con el contacto del canal simulado.
    assert _post(env, _message("quiero hablar con un asesor", "m-4")).status_code == 202
    [request] = env.handover.requests
    assert request.contact_id == contact.id
    case_id = request.case_id

    # R42: el asesor responde → sale por el canal y destino de esa conversación.
    panel.login(env)
    response = env.client.post(
        "/asesor/reply",
        data={"csrf_token": panel.CSRF, "case_id": case_id, "text": "Hola, soy tu asesor"},
        follow_redirects=False,
    )
    drain_queues(env.settings, env.adapters)
    assert response.status_code == 303
    assert env.gateway.channel_sent[-1] == (CHANNEL, DEST, "Hola, soy tu asesor")
    assert {m.canal_id for m in env.repo.messages if m.contact_id == contact.id} == {CHANNEL}


def test_post_messages_accepts_new_channel_and_rejects_outbound(env):
    """R29, R30: canal válido cualquiera → 202; dirección saliente → 422."""
    assert _post(env, _message("Hola", "m-1")).status_code == 202
    assert _post(env, _message("Hola", "m-2", channel="otro-canal")).status_code == 202
    outbound = _post(env, _message("Hola", "m-3", direction="outbound"))
    assert outbound.status_code == 422
    assert outbound.json()["error"] == "validation_error"


def test_legacy_telegram_payloads_keep_the_historic_flow(env):
    """R38: MessageRequest y NormalizedMessage numérico de Telegram usan el flujo histórico."""
    response = env.post("¿Cómo instalo el módulo?", update_id=5)
    assert response.status_code == 202
    assert env.gateway.sent[-1] == (100, "Respuesta final")
    canonical = _post(
        env,
        _message(
            "¿Y el otro módulo?", "6", channel="telegram",
            external_user_id="10", external_chat_id="100",
        ),
    )
    assert canonical.status_code == 202
    assert env.gateway.sent[-1] == (100, "Respuesta final")
    assert env.repo.contacts[10].channel == "telegram"


def test_inbox_channel_filter_comes_from_directory(env, panel):
    """R26, R27: opciones y validación del filtro desde el directorio de canales."""
    options = inbox_channel_options(env.adapters)
    assert set(options) == {
        ("telegram", "Telegram"),
        ("whatsapp", "WhatsApp"),
        ("simulado", "Simulado"),
    }
    panel.login(env)
    page = env.client.get("/asesor/cases")
    assert page.status_code == 200
    assert '<option value="simulado">Simulado</option>' in page.text
    advisor_inbox("700", "simulado", None, env.settings, env.adapters)
    with pytest.raises(PanelValidationError):
        advisor_inbox("700", "instagram", None, env.settings, env.adapters)
