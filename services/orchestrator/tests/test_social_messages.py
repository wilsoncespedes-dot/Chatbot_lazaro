"""Tests de la respuesta social determinista (#59)."""
from __future__ import annotations

import pytest

from orchestrator.config import Settings
from orchestrator.harness import is_social_message


def test_is_social_message_is_pure_and_exact():
    """R11, R8: igualdad normalizada, sin IO y sin mutar la lista de frases."""
    phrases = Settings().social_message_list
    before = list(phrases)
    for text in (
        "hola", "¡Hola!", "buenas", "¿Qué tal?", "gracias", "gracias por todo",
        "vale", "entendido", "hasta luego", "¿Cómo estás?",
    ):
        assert is_social_message(text, phrases) is True
    for text in ("hola como creo un usuario", "hola asesor", "¿cuánto cuesta?", ""):
        assert is_social_message(text, phrases) is False
    assert phrases == before


def test_social_settings_are_read_from_env(monkeypatch):
    """R10: la lista y la respuesta se leen del entorno."""
    monkeypatch.setenv("SOCIAL_MESSAGES", " hola , , gracias ")
    monkeypatch.setenv("SOCIAL_REPLY", "Respuesta de prueba")
    settings = Settings()
    assert settings.social_message_list == ["hola", "gracias"]
    assert settings.social_reply == "Respuesta de prueba"


def test_social_reply_is_sent(env):
    """R1: un saludo recibe el texto configurado."""
    env.post(text="hola")
    assert env.gateway.sent == [(100, env.settings.social_reply)]


@pytest.mark.parametrize(
    "text", ["buenas", "¿Qué tal?", "gracias por todo", "vale", "hasta luego"]
)
def test_expanded_social_phrases_get_social_reply(env, text):
    """#59 ampliado: las frases nuevas también se resuelven sin RAG ni LLM."""
    env.post(text=text)
    assert env.gateway.sent == [(100, env.settings.social_reply)]
    assert env.rag.calls == [] and env.llm.calls == []


def test_social_reply_does_not_call_rag_or_llm(env):
    """R2, R3: la respuesta social no consulta manuales ni al modelo."""
    env.post(text="hola")
    assert env.rag.calls == []
    assert env.llm.calls == []


def test_social_reply_does_not_record_failure_or_handover(env):
    """R4, R5, R6: no cuenta fallo RAG ni avisa a asesores."""
    env.post(text="hola")
    assert ("no_results", "no_relevant_chunks") not in env.events()
    assert env.repo.rag_outcomes == set()
    assert env.handover.requests == []


def test_non_social_message_keeps_existing_flow(env):
    """R7: una pregunta sigue por RAG y LLM como antes."""
    env.post()
    assert env.rag.calls == [("¿Cómo instalo el módulo?", 7)]
    assert len(env.llm.calls) == 1


def test_greeting_with_question_goes_to_rag_with_full_text(env):
    """R8: un saludo más pregunta no se sustituye por la respuesta social."""
    text = "hola, ¿cómo instalo el módulo?"
    env.post(text=text)
    assert env.rag.calls[0][0] == text
    assert env.gateway.sent != [(100, env.settings.social_reply)]


def test_handover_keyword_wins_over_social(env_factory):
    """R9: la keyword gana aunque el texto sea social exacto."""
    # El texto es social según SOCIAL_MESSAGES, así que la prueba detectaría
    # una guardia colocada antes de las keywords de asesor.
    env = env_factory(social_messages="hola,quiero un asesor")
    env.post(text="quiero un asesor")
    assert len(env.handover.requests) == 1
    assert env.gateway.sent != [(100, env.settings.social_reply)]
