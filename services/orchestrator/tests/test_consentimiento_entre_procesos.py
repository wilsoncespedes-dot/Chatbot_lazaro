"""El aviso y la decisión de consentimiento se atienden en el mismo proceso.

En producción el worker `procesar_entrantes` es otro proceso, con su propia
memoria. Si el aviso lo enviara el worker, su desafío quedaría en la memoria
del worker y el «Acepto» (que se procesa en la petición) no lo encontraría:
el bot repetiría el aviso y el cliente tendría que aceptar dos veces.
"""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone

from fakes import channel_info, default_channel_infos, drain_queues
from lazaro_contracts import NormalizedMessage

from orchestrator.adapters.channels import FakeChannelDirectory
from orchestrator.privacy import ConsentChallengeStore

NOW = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
TOKEN = "svc-token"
CHANNEL = "soporte-correo"


def _message(text: str, message_id: str) -> NormalizedMessage:
    return NormalizedMessage(
        channel=CHANNEL,  # type: ignore[arg-type]
        external_user_id="cliente@example.com",
        external_chat_id="hilo-1",
        external_message_id=message_id,
        kind="text",
        text=text,
        received_at=NOW,
    )


def _setup(env):
    """Canal en modo `texto` y un worker con memoria propia, como en producción."""
    env.adapters.channels = FakeChannelDirectory(
        [*default_channel_infos(), channel_info(CHANNEL, consent_mode="texto")]
    )
    return replace(
        env.adapters, consent_challenges=ConsentChallengeStore(), consent_shown=set()
    )


def _post(env, worker, message: NormalizedMessage):
    response = env.client.post(
        "/messages",
        json=message.model_dump(mode="json"),
        headers={"X-Service-Token": TOKEN},
    )
    drain_queues(env.settings, worker)
    return response


def _texts_sent(env) -> list[str]:
    # El falso del gateway también copia a `channel_sent` los envíos por bloques.
    return [text for channel, _, text in env.gateway.channel_sent if channel == CHANNEL]


def _notices_sent(env) -> int:
    notice = env.repo.get_conversation_texts().notice_text
    return sum(1 for text in _texts_sent(env) if notice in text)


def test_first_contact_is_answered_in_the_request_not_in_the_worker(env):
    worker = _setup(env)
    assert _post(env, worker, _message("Hola", "m-1")).status_code == 202
    assert env.adapters.consent_challenges.get(CHANNEL, "cliente@example.com") is not None
    assert worker.consent_challenges.get(CHANNEL, "cliente@example.com") is None
    assert all(row["status"] != "pending" for row in env.repo.inbox.values())


def test_accept_phrase_is_recognized_the_first_time(env):
    worker = _setup(env)
    _post(env, worker, _message("Hola", "m-1"))
    assert _notices_sent(env) == 1
    _post(env, worker, _message(env.settings.consent_accept_phrase, "m-2"))
    assert env.repo.last_privacy_result(CHANNEL, "cliente@example.com") == "accepted"
    assert _notices_sent(env) == 1


def test_consented_messages_still_go_through_the_queue(env):
    """Tras aceptar, el bot (RAG/LLM) sigue corriendo en el worker, no en la petición."""
    worker = _setup(env)
    _post(env, worker, _message("Hola", "m-1"))
    _post(env, worker, _message(env.settings.consent_accept_phrase, "m-2"))
    response = env.client.post(
        "/messages",
        json=_message("¿Cómo instalo el módulo?", "m-3").model_dump(mode="json"),
        headers={"X-Service-Token": TOKEN},
    )
    assert response.status_code == 202
    assert [row["status"] for row in env.repo.inbox.values()].count("pending") == 1
    assert env.llm.calls == []
