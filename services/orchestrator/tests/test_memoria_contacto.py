"""Fase 3: memoria por contacto sin login.

- "me llamo Ana y me interesa el plan Pro" → reinicio → "¿qué plan te dije?"
  responde Pro y la llama Ana.
- Dos contactos nunca comparten hechos, historial ni resumen.
- Los hechos pasan el filtro de datos sensibles de `memory.py`.
- Al iniciar sesión los hechos del contacto se fusionan con `client_memory`.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from lazaro_contracts import SearchResult

from orchestrator.adapters.gateway import FakeGatewayClient
from orchestrator.adapters.llm import ScriptedLLM
from orchestrator.domain import (
    Adapters,
    ConversationState,
    ToolContext,
    create_client,
    execute_tool,
    issue_login_link,
    login_client,
)
from orchestrator.main import create_app
from orchestrator.memory import (
    CONTACT_FACTS_PROMPT,
    MEMORY_ANSWER_PROMPT,
    clean_contact_facts,
    merge_facts_into_memory,
    parse_facts_answer,
)
from migrations.testing import database_url_for_tests, migrated_database

from fakes import drain_queues

NOW = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
HEADERS = {"X-Service-Token": "svc-token"}
PASSWORD = "clave-segura-123"


def _rag_reply(answer: str = "Respuesta final") -> str:
    return json.dumps(
        {
            "answer": answer,
            "citations": [{"chunk_id": "ch1", "quote": "texto del fragmento 1"}],
        },
        ensure_ascii=False,
    )


def _facts_reply(hechos: dict, resumen: str = "") -> str:
    return json.dumps({"hechos": hechos, "resumen": resumen}, ensure_ascii=False)


def _answer_reply(answer: str) -> str:
    return json.dumps({"answer": answer}, ensure_ascii=False)


def _texts(gateway: FakeGatewayClient) -> list[str]:
    # Los bloques de Telegram quedan en `channel_sent` y también en `sent`.
    return [text for _, _, text in gateway.channel_sent] or [
        text for _, text in gateway.sent
    ]


def _calls_with(llm: ScriptedLLM, system: str) -> list[tuple[str, str]]:
    return [call for call in llm.calls if call[0].startswith(system)]


def _contact(env, user: int = 10):
    return env.repo.get_or_create_contact(user, 100 if user == 10 else user * 10, NOW)


def _restart(env, llm: ScriptedLLM) -> tuple[TestClient, Adapters]:
    """Otro proceso: app y adaptadores nuevos sobre la misma base."""
    adapters = Adapters(
        repository=env.repo,
        rag=env.rag,
        llm=llm,
        gateway=FakeGatewayClient(),
        handover=env.handover,
        db_query=env.db_query,
        clock=lambda: NOW + timedelta(hours=3),
        new_id=lambda: "after-restart",
    )
    return TestClient(create_app(env.settings, adapters)), adapters


def _post(client: TestClient, settings, adapters, text: str, update_id: int, user: int = 10):
    body = {
        "update_id": update_id,
        "telegram_user_id": user,
        "chat_id": 100 if user == 10 else user * 10,
        "text": text,
        "received_at": "2026-01-02T06:04:00+00:00",
    }
    response = client.post("/messages", json=body, headers=HEADERS)
    drain_queues(settings, adapters)
    return response


# ── aceptación ──────────────────────────────────────────────────────────────


def test_ana_and_plan_pro_survive_a_restart_and_are_recalled(env_factory):
    env = env_factory(memory_enabled=True)
    first = ScriptedLLM(
        [
            _rag_reply(),
            _facts_reply(
                {"nombre": "Ana", "producto_interes": "plan Pro"},
                "Ana pregunta por el plan Pro.",
            ),
        ]
    )
    env.adapters.llm = first

    env.post(text="me llamo Ana y me interesa el plan Pro", update_id=1)

    assert len(_calls_with(first, CONTACT_FACTS_PROMPT)) == 1
    contact = _contact(env)
    stored = env.repo.get_contact_memory(contact.id)
    assert dict(stored.facts) == {"nombre": "Ana", "producto_interes": "plan Pro"}

    second = ScriptedLLM([_answer_reply("Ana, me dijiste que te interesa el plan Pro.")])
    client, adapters = _restart(env, second)
    _post(client, env.settings, adapters, "¿qué plan te dije?", update_id=2)

    replies = _texts(adapters.gateway)
    assert replies == ["Ana, me dijiste que te interesa el plan Pro."]
    system, user = _calls_with(second, MEMORY_ANSWER_PROMPT)[0]
    assert '<dato clave="nombre">Ana</dato>' in user
    assert '<dato clave="producto_interes">plan Pro</dato>' in user
    assert "me llamo Ana y me interesa el plan Pro" in user  # últimos mensajes
    assert "<pregunta>¿qué plan te dije?</pregunta>" in user


def test_recall_without_a_valid_model_answer_uses_the_saved_facts(env_factory):
    env = env_factory(memory_enabled=True)
    contact = _contact(env)
    env.repo.save_contact_memory(
        contact.id, {"nombre": "Ana", "producto_interes": "plan Pro"}, "", None, NOW
    )
    env.adapters.llm = ScriptedLLM(["esto no es json"])

    env.post(text="¿Te acuerdas de qué plan te dije?", update_id=1)

    reply = _texts(env.gateway)[-1]
    assert "Ana" in reply and "plan Pro" in reply
    assert ("memory_answer", "fallback") in env.events()


def test_recall_answer_with_invented_numbers_is_rejected(env_factory):
    env = env_factory(memory_enabled=True)
    contact = _contact(env)
    env.repo.save_contact_memory(contact.id, {"nombre": "Ana"}, "", None, NOW)
    env.adapters.llm = ScriptedLLM([_answer_reply("Ana, tu pedido es el 4471.")])

    env.post(text="¿cómo me llamo?", update_id=1)

    reply = _texts(env.gateway)[-1]
    assert "4471" not in reply
    assert "Ana" in reply


def test_two_contacts_never_share_memory(env_factory):
    env = env_factory(memory_enabled=True)
    llm = ScriptedLLM(
        [_rag_reply(), _facts_reply({"nombre": "Ana", "producto_interes": "plan Pro"})]
    )
    env.adapters.llm = llm
    env.post(text="me llamo Ana y me interesa el plan Pro", update_id=1, user=10)

    other = ScriptedLLM([_rag_reply()])
    env.adapters.llm = other
    env.post(text="¿qué plan te dije?", update_id=2, user=20, chat=200)

    # B no tiene memoria propia: su pregunta va al flujo normal y ningún
    # prompt de B lleva datos ni mensajes de A.
    assert _calls_with(other, MEMORY_ANSWER_PROMPT) == []
    for system, user in other.calls:
        assert "Ana" not in user and "Pro" not in user
    contact_b = _contact(env, 20)
    assert env.repo.get_contact_memory(contact_b.id).facts == ()
    assert dict(env.repo.get_contact_memory(_contact(env).id).facts)["nombre"] == "Ana"


def test_rag_prompt_carries_contact_facts_summary_and_recent_messages(env_factory):
    env = env_factory(memory_enabled=True)
    contact = _contact(env)
    env.repo.set_conversation_state(contact.id, ConversationState.ACTIVE, NOW)
    env.repo.save_contact_memory(
        contact.id, {"nombre": "Ana"}, "Pregunta por la instalación.", None, NOW
    )
    env.repo.add_message(contact.id, "user", "Mensaje anterior", NOW - timedelta(minutes=2))
    env.repo.add_message(contact.id, "user", "¿Cómo instalo el módulo?", NOW)
    env.rag.results = [
        SearchResult(chunk_id="ch1", manual="M", text="texto del fragmento 1", score=0.9)
    ]
    llm = ScriptedLLM([_rag_reply()])
    env.adapters.llm = llm

    execute_tool(
        "buscar_base_conocimiento",
        ToolContext(contact, "¿Cómo instalo el módulo?", NOW, 1, ConversationState.ACTIVE, "rule"),
        env.settings,
        env.adapters,
    )

    user = llm.calls[0][1]
    assert '<datos_contacto><dato clave="nombre">Ana</dato></datos_contacto>' in user
    assert "<resumen_contacto>Pregunta por la instalación.</resumen_contacto>" in user
    assert "Mensaje anterior" in user
    # el mensaje actual va en <pregunta>, no repetido en el historial
    assert user.count("¿Cómo instalo el módulo?") == 1


def test_history_keeps_the_last_twenty_messages_by_default(env_factory):
    env = env_factory(memory_enabled=True)
    assert env.settings.memory_context_messages == 20


# ── extracción ──────────────────────────────────────────────────────────────


def test_extraction_runs_on_new_data_or_every_n_messages(env_factory):
    env = env_factory(memory_enabled=True, memory_facts_every_messages=3)
    llm = ScriptedLLM([])
    llm.default_reply = _rag_reply()
    env.adapters.llm = llm

    env.post(text="¿Cómo instalo el módulo?", update_id=1)
    env.post(text="¿Y cómo lo actualizo?", update_id=2)
    assert _calls_with(llm, CONTACT_FACTS_PROMPT) == []
    env.post(text="¿Dónde veo los reportes?", update_id=3)
    assert len(_calls_with(llm, CONTACT_FACTS_PROMPT)) == 1

    env.post(text="trabajo en Acme", update_id=4)  # dato nuevo: no espera a N
    assert len(_calls_with(llm, CONTACT_FACTS_PROMPT)) == 2


def test_memory_disabled_never_extracts_nor_recalls(env_factory):
    env = env_factory(memory_enabled=False)
    llm = ScriptedLLM([_rag_reply(), _rag_reply()])
    env.adapters.llm = llm

    env.post(text="me llamo Ana", update_id=1)
    env.post(text="¿cómo me llamo?", update_id=2)

    assert _calls_with(llm, CONTACT_FACTS_PROMPT) == []
    assert _calls_with(llm, MEMORY_ANSWER_PROMPT) == []
    assert env.repo.get_contact_memory(_contact(env).id).facts == ()


def test_sensitive_or_unknown_facts_are_dropped(env_factory):
    env = env_factory(memory_enabled=True)
    llm = ScriptedLLM(
        [
            _rag_reply(),
            _facts_reply(
                {
                    "nombre": "Ana",
                    "pedido_caso": "pedido 12345678",
                    "preferencia_contacto": "ana@example.com",
                    "cedula": "Ana 1",
                    "empresa": "",
                },
                "Su contraseña es hunter2. Pregunta por el plan Pro.",
            ),
        ]
    )
    env.adapters.llm = llm

    env.post(text="me llamo Ana, mi pedido es 12345678", update_id=1)

    stored = env.repo.get_contact_memory(_contact(env).id)
    assert dict(stored.facts) == {"nombre": "Ana"}
    assert "contraseña" not in stored.summary
    assert "plan Pro" in stored.summary


def test_invalid_extraction_keeps_previous_facts(env_factory):
    env = env_factory(memory_enabled=True)
    contact = _contact(env)
    env.repo.save_contact_memory(contact.id, {"nombre": "Ana"}, "", None, NOW)
    env.adapters.llm = ScriptedLLM([_rag_reply(), "no json"])

    env.post(text="me llamo Ana María", update_id=1)

    assert dict(env.repo.get_contact_memory(contact.id).facts) == {"nombre": "Ana"}
    assert ("memory_failed", "invalid_facts") in env.events()


def test_contact_extraction_is_skipped_during_a_client_session(env_factory, panel):
    """Con sesión, los datos van a `client_memory` al cerrarla (#40), no al contacto."""
    env = env_factory(memory_enabled=True)
    contact = _contact(env)
    panel.add_client_session(env, "s1", "p1", contact.id, NOW, NOW)
    env.repo.set_conversation_state(contact.id, ConversationState.ACTIVE, NOW)
    llm = ScriptedLLM([_rag_reply()])
    env.adapters.llm = llm

    env.post(text="me llamo Ana", update_id=1)

    assert _calls_with(llm, CONTACT_FACTS_PROMPT) == []


# ── login ───────────────────────────────────────────────────────────────────


def test_login_merges_contact_facts_into_client_memory(env_factory):
    env = env_factory(
        memory_enabled=True,
        identity_public_base_url="https://orchestrator.example",
        identity_link_signing_key="k" * 32,
        password_scrypt_n=16384,
    )
    client = create_client(
        "clienteA", PASSWORD, NOW - timedelta(days=1), NOW + timedelta(days=30),
        env.settings, env.adapters,
    )
    env.repo.set_client_memory(
        client.profile_id, ("Nombre: Anita", "Prefiere correo"), "s0", NOW
    )
    contact = env.repo.get_or_create_channel_contact("whatsapp", "57300", "57300", NOW)
    env.repo.save_contact_memory(
        contact.id, {"nombre": "Ana", "producto_interes": "plan Pro"}, "Resumen", None, NOW
    )
    url = issue_login_link(contact, env.settings, env.adapters)
    assert url is not None

    login_client(url.split("t=", 1)[1], "clienteA", PASSWORD, "1.1.1.1", env.settings, env.adapters)

    items = env.repo.client_memory[client.profile_id].items
    assert items == ("Nombre: Ana", "Producto de interés: plan Pro", "Prefiere correo")
    # el contacto queda limpio: otro cliente en el mismo chat no los hereda
    cleared = env.repo.get_contact_memory(contact.id)
    assert cleared.facts == () and cleared.summary == ""


# ── lógica pura ─────────────────────────────────────────────────────────────


def test_parse_facts_answer_requires_the_exact_shape():
    answer = parse_facts_answer('{"hechos": {"nombre": "Ana"}, "resumen": "R"}')
    assert answer.hechos == {"nombre": "Ana"} and answer.resumen == "R"
    assert parse_facts_answer('```json\n{"hechos": {}}\n```').resumen is None
    for raw in ("[]", '{"hechos": []}', '{"hechos": {}, "otro": 1}', "nada"):
        with pytest.raises(ValueError):
            parse_facts_answer(raw)


def test_clean_contact_facts_keeps_only_allowed_safe_values():
    cleaned = clean_contact_facts(
        {"nombre": "  Ana  ", "empresa": "x" * 500, "rol": "admin", "pedido_caso": 7},
        ("contraseña",),
        6,
        40,
    )
    assert cleaned == {"nombre": "Ana", "empresa": "x" * 40}


def test_merge_replaces_items_with_the_same_label():
    merged = merge_facts_into_memory(
        ("Nombre: Anita", "Prefiere correo"), (("nombre", "Ana"),)
    )
    assert merged == ("Nombre: Ana", "Prefiere correo")


# ── Postgres real (TEST_DATABASE_URL) ───────────────────────────────────────


@pytest.mark.integration
@pytest.mark.skipif(
    not database_url_for_tests(),
    reason="requiere TEST_DATABASE_URL con un Postgres local desechable",
)
def test_postgres_contact_memory_survives_restart_and_is_isolated():
    from orchestrator.adapters.repository import PostgresRepository

    with migrated_database() as url:
        repo = PostgresRepository(url)
        ana = repo.get_or_create_channel_contact("whatsapp", "57300", "57300", NOW)
        beto = repo.get_or_create_channel_contact("whatsapp", "57301", "57301", NOW)
        repo.add_message(ana.id, "user", "me llamo Ana", NOW)
        source = repo.recent_contact_messages(ana.id, None, 5)[-1][0]
        repo.save_contact_memory(
            ana.id, {"nombre": "Ana", "producto_interes": "plan Pro"}, "Resumen", source, NOW
        )
        assert repo.bump_contact_memory_pending(ana.id, NOW) == 1
        assert repo.bump_contact_memory_pending(ana.id, NOW) == 2

        restarted = PostgresRepository(url)
        stored = restarted.get_contact_memory(ana.id)
        assert dict(stored.facts) == {"nombre": "Ana", "producto_interes": "plan Pro"}
        assert stored.summary == "Resumen"
        assert restarted.get_contact_memory(beto.id).facts == ()

        # una actualización reemplaza el valor y reinicia el contador
        restarted.save_contact_memory(ana.id, {"producto_interes": "plan Básico"}, None, None, NOW)
        stored = restarted.get_contact_memory(ana.id)
        assert dict(stored.facts)["producto_interes"] == "plan Básico"
        assert stored.summary == "Resumen"
        assert restarted.bump_contact_memory_pending(ana.id, NOW) == 1

        # rechazar el consentimiento borra el contacto y su memoria (cascada)
        restarted.delete_contact_content("whatsapp", "57300")
        assert restarted.get_contact_memory(ana.id).facts == ()
        restarted.clear_contact_memory(beto.id)
