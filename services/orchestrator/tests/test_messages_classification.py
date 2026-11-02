"""Tests de la clasificación dentro de process_message (#25)."""
from __future__ import annotations

import logging
from datetime import datetime, timezone

import pytest

from orchestrator.classifier import Category

FIXED_NOW = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
TEXT = "mi factura"


def _add_category(
    env, code: str, keywords: tuple[str, ...], active: bool = True
) -> Category:
    category = Category(
        id=f"id-{code}", code=code, name=code.title(), keywords=keywords, active=active
    )
    assert env.repo.create_category(category, FIXED_NOW) is True
    return category


def _query_events(env) -> list:
    return [event for event in env.repo.events if event.type == "query_classified"]


# --- R22: evento antes de RAG ------------------------------------------------------


def test_query_classified_is_saved_before_rag_search(env):
    """R22: el evento se registra antes de llamar a rag.search, con code y confianza."""
    _add_category(env, "facturacion", ("factura",))
    seen: list[list[str]] = []
    original = env.rag.search

    def spy(query: str, top_k: int):
        seen.append([event.type for event in env.repo.events])
        return original(query, top_k)

    env.rag.search = spy

    env.post(text=TEXT)

    assert seen == [["query_classified"]]
    event = env.repo.events[0]
    assert (event.type, event.reason, event.at) == (
        "query_classified",
        "facturacion:1.00",
        FIXED_NOW,
    )
    assert event.contact_id == env.repo.contacts[10].id
    assert env.rag.calls == [(TEXT, 7)]


# --- R23: sin cambios en RAG ni en la respuesta ------------------------------------


def test_classification_does_not_change_rag_arguments_or_client_reply(env):
    """R23: categoría, sin clasificar y sin categorías producen la misma llamada y envío."""
    _add_category(env, "facturacion", ("factura",))
    calls: list[tuple[list, list]] = []

    env.rag.calls.clear()
    env.gateway.sent.clear()
    env.post(text=TEXT, update_id=1)
    calls.append((list(env.rag.calls), list(env.gateway.sent)))

    env.repo.categories.clear()
    _add_category(env, "soporte", ("error",))
    env.rag.calls.clear()
    env.gateway.sent.clear()
    env.post(text=TEXT, update_id=2)
    calls.append((list(env.rag.calls), list(env.gateway.sent)))

    env.repo.categories.clear()
    env.rag.calls.clear()
    env.gateway.sent.clear()
    env.post(text=TEXT, update_id=3)
    calls.append((list(env.rag.calls), list(env.gateway.sent)))

    assert calls == [
        ([(TEXT, 7)], [(100, "Respuesta final")]),
        ([(TEXT, 7)], [(100, "Respuesta final")]),
        ([(TEXT, 7)], [(100, "Respuesta final")]),
    ]
    reasons = [event.reason for event in _query_events(env)]
    assert reasons == [
        "facturacion:1.00",
        "sin_clasificar:0.00",
        "sin_clasificar:0.00",
    ]


# --- R24: mensajes no elegibles ----------------------------------------------------


def test_start_token_is_not_classified(env):
    """R24: /start <token> no clasifica ni llama al RAG."""
    _add_category(env, "facturacion", ("factura",))

    env.post(text="/start token-de-prueba")

    assert _query_events(env) == []
    assert env.rag.calls == []


def test_advisor_command_is_not_classified(env):
    """R24: un comando de asesor no clasifica ni llama al RAG."""
    _add_category(env, "facturacion", ("factura",))

    env.post(text="/responder case-1 hola")

    assert _query_events(env) == []
    assert env.rag.calls == []


def test_message_forwarded_to_case_is_not_classified(env):
    """R24: un mensaje reenviado a un caso abierto no clasifica ni llama al RAG."""
    _add_category(env, "facturacion", ("factura",))
    contact = env.repo.get_or_create_contact(10, 100, env.adapters.clock())
    env.repo.link_case("case-1", contact.id, env.adapters.clock())
    env.handover.client_message_status = "forwarded"

    env.post(text=TEXT)

    assert _query_events(env) == []
    assert env.rag.calls == []


def test_handover_keyword_is_not_classified(env):
    """R24: una petición de asesor por palabra clave no clasifica ni llama al RAG."""
    _add_category(env, "facturacion", ("factura",))

    env.post(text="quiero un asesor")

    assert _query_events(env) == []
    assert env.rag.calls == []


# --- R25: fallo del repositorio ----------------------------------------------------


@pytest.mark.parametrize("operation", ["list_categories", "get_classifier_threshold"])
def test_repository_failure_logs_and_continues_to_rag(env, monkeypatch, caplog, operation):
    """R25: si leer categorías o umbral falla, se registra y el flujo RAG continúa."""
    _add_category(env, "facturacion", ("factura",))
    caplog.set_level(logging.ERROR)

    def boom():
        raise RuntimeError("sin base de datos")

    monkeypatch.setattr(env.repo, operation, boom)

    response = env.post()

    assert response.status_code == 202
    assert _query_events(env) == []
    assert env.rag.calls == [("¿Cómo instalo el módulo?", 7)]
    assert ("rag_answer", "chunks_found") in env.events()
    assert "classification_failed" in caplog.text


# --- R26: umbral por defecto y guardado --------------------------------------------


def _seed_scores(env) -> None:
    _add_category(env, "facturacion", ("factura", "pago"))
    _add_category(env, "soporte", ("error",))


def test_default_threshold_classifies(env):
    """R26: sin umbral guardado se usa CLASSIFIER_DEFAULT_THRESHOLD (0.6)."""
    _seed_scores(env)

    env.post(text="factura pago error")

    assert [event.reason for event in _query_events(env)] == ["facturacion:0.67"]


def test_configured_default_threshold_is_used(env):
    """R26: el valor por defecto sale de la configuración."""
    _seed_scores(env)
    env.settings.classifier_default_threshold = 0.7

    env.post(text="factura pago error")

    assert [event.reason for event in _query_events(env)] == ["sin_clasificar:0.67"]


def test_stored_threshold_overrides_the_default(env):
    """R26: un umbral guardado desde el panel tiene prioridad sobre el por defecto."""
    _seed_scores(env)
    env.repo.set_classifier_threshold(0.9)

    env.post(text="factura pago error")

    assert [event.reason for event in _query_events(env)] == ["sin_clasificar:0.67"]
