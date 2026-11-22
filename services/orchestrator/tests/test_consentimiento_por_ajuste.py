"""R22–R25 (#65): el modo de consentimiento sale de `config.consent_mode`."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fakes import channel_info, default_channel_infos, drain_queues
from lazaro_contracts import NormalizedMessage, OptionsBlock

from orchestrator.adapters.channels import FakeChannelDirectory
from orchestrator.domain import consent_text_pending
from orchestrator.privacy import CONSENT_ACCEPT_LABEL

NOW = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
TOKEN = "svc-token"


def _message(channel: str, text: str = "Hola", message_id: str = "m1") -> NormalizedMessage:
    return NormalizedMessage(
        channel=channel,  # type: ignore[arg-type]
        external_user_id="u-1",
        external_chat_id="d-1",
        external_message_id=message_id,
        kind="text",
        text=text,
        received_at=NOW,
    )


def _post(env, message: NormalizedMessage):
    response = env.client.post(
        "/messages",
        json=message.model_dump(mode="json"),
        headers={"X-Service-Token": TOKEN},
    )
    drain_queues(env.settings, env.adapters)
    return response


def _with(env, *infos):
    env.adapters.channels = FakeChannelDirectory([*default_channel_infos(), *infos])


def _options_sent(env, channel: str) -> list[OptionsBlock]:
    return [
        block
        for sent_channel, _, blocks in env.gateway.blocks_sent
        if sent_channel == channel
        for block in blocks
        if isinstance(block, OptionsBlock)
    ]


@pytest.mark.parametrize("channel", ["canal-texto", "canal-ausente"])
def test_texto_mode_shows_phrase_instruction_and_registers_challenge(env, channel):
    """R22 (y S2: canal ausente = `texto`): aviso con frase de aceptación y desafío."""
    _with(env, channel_info("canal-texto", consent_mode="texto"))
    assert _post(env, _message(channel)).status_code == 202
    prompt = env.gateway.channel_sent[-1]
    assert prompt[:2] == (channel, "d-1")
    assert env.settings.consent_accept_phrase in prompt[2]
    assert env.settings.consent_reject_phrase in prompt[2]
    assert _options_sent(env, channel) == []
    assert env.adapters.consent_challenges.get(channel, "u-1") is not None


def test_boton_mode_shows_accept_and_reject_options(env):
    """R23: modo `boton` presenta las opciones Acepto / No acepto."""
    _with(env, channel_info("canal-boton", consent_mode="boton"))
    assert _post(env, _message("canal-boton")).status_code == 202
    [options] = _options_sent(env, "canal-boton")
    labels = [option.label if hasattr(option, "label") else option for option in options.options]
    rendered = " ".join(str(label) for label in labels)
    assert CONSENT_ACCEPT_LABEL in rendered or "Acepto" in rendered
    assert env.adapters.consent_challenges.get("canal-boton", "u-1") is not None


def test_texto_mode_phrase_is_processed_in_the_request(env):
    """R24: la frase de aceptación de un canal `texto` se procesa en la petición."""
    _with(env, channel_info("canal-texto", consent_mode="texto"))
    _post(env, _message("canal-texto"))
    accept = _message("canal-texto", env.settings.consent_accept_phrase, "accept-1")
    assert consent_text_pending(accept, env.settings, env.adapters) is True
    response = env.client.post(
        "/messages", json=accept.model_dump(mode="json"), headers={"X-Service-Token": TOKEN}
    )
    assert response.status_code == 202
    # Procesado dentro de la petición: la evidencia existe sin drenar la cola.
    [consent] = env.repo.privacy_consents
    assert (consent.channel, consent.result, consent.evidence_type) == (
        "canal-texto",
        "accepted",
        "text",
    )


def test_boton_mode_phrase_is_not_consent(env):
    """R25: en modo `boton` la frase escrita no cuenta como consentimiento."""
    _with(env, channel_info("canal-boton", consent_mode="boton"))
    _post(env, _message("canal-boton"))
    accept = _message("canal-boton", env.settings.consent_accept_phrase, "accept-1")
    assert consent_text_pending(accept, env.settings, env.adapters) is False
    _post(env, accept)
    assert [c for c in env.repo.privacy_consents if c.result == "accepted"] == []


def test_builtin_channels_keep_their_previous_modes(env):
    """Telegram (`texto`) y WhatsApp (`boton`) conservan su comportamiento."""
    phrase = env.settings.consent_accept_phrase
    assert consent_text_pending(_message("telegram", phrase), env.settings, env.adapters)
    assert not consent_text_pending(_message("whatsapp", phrase), env.settings, env.adapters)
