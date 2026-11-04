"""Generación, entrega a la IA, continuidad y aislamiento de la memoria (#40)."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest
from lazaro_contracts import SearchResult

from orchestrator.adapters.client_data import FakeClientData
from orchestrator.adapters.llm import ScriptedLLM
from orchestrator.db_query import QueryResult
from orchestrator.domain import (
    ClientSession,
    ConversationState,
    LLM_SYSTEM_PROMPT,
    ToolContext,
    build_llm_prompt,
    end_client_session,
    execute_tool,
    login_client,
    issue_login_link,
    create_client,
)
from orchestrator.memory import MEMORY_CONTEXT_NOTE, MEMORY_SUMMARY_PROMPT

NOW = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
PASSWORD = "clave-segura-123"
ALLOWLIST = '{"mis_datos.v_datos": ["cliente_id", "nombre"]}'
SAFE_SQL = "SELECT nombre FROM mis_datos.v_datos"


def _chunks() -> list[SearchResult]:
    return [
        SearchResult(
            chunk_id="ch1", manual="Manual A", text="texto del fragmento 1", score=0.9
        )
    ]


def _rag_reply() -> str:
    return json.dumps(
        {
            "answer": "Respuesta final",
            "citations": [{"chunk_id": "ch1", "quote": "texto del fragmento 1"}],
        },
        ensure_ascii=False,
    )


def _summary_reply(summary: str = "Resumen", memory: list[str] | None = None) -> str:
    return json.dumps(
        {"resumen": summary, "memoria": memory or []}, ensure_ascii=False
    )


def _contact(env, channel: str = "telegram", user: str = "10", chat: str = "100"):
    return env.repo.get_or_create_channel_contact(channel, user, chat, NOW)


def _session(
    env,
    profile_id: str = "p1",
    channel: str = "telegram",
    user: str = "10",
    chat: str = "100",
    started_at: datetime = NOW,
    last_activity_at: datetime = NOW,
) -> tuple:
    contact = _contact(env, channel, user, chat)
    session = ClientSession(
        id=f"session-{profile_id}-{channel}-{user}",
        profile_id=profile_id,
        contact_id=contact.id,
        started_at=started_at,
        last_activity_at=last_activity_at,
    )
    env.repo.client_sessions[session.id] = session
    env.repo.set_conversation_state(contact.id, ConversationState.ACTIVE, NOW)
    return contact, session


def _ctx(contact, text: str = "¿Cómo instalo el módulo?") -> ToolContext:
    return ToolContext(
        contact=contact,
        text=text,
        received_at=NOW,
        update_id=1,
        state=ConversationState.ACTIVE,
        origin="rule",
    )


# --- R1, R3, R6–R9, R11–R13, R15, R19 -------------------------------------------------------


def test_r1_r3_r6_r7_r9_r13_r19_session_end_saves_summary_and_cleaned_memory(env_factory):
    """R1, R3, R6–R9, R13, R19: resumen y memoria depurada, sin mensajes nuevos."""
    env = env_factory(memory_enabled=True)
    contact, session = _session(env)
    env.repo.add_message(contact.id, "user", "Prefiero que me escriban al correo", NOW)
    env.repo.add_message(contact.id, "bot", "Entendido", NOW)
    env.repo.add_message(contact.id, "user", "Mi contraseña es 123456", NOW)
    llm = ScriptedLLM(
        [
            _summary_reply(
                "Habló del canal de contacto. La contraseña es azul.",
                ["Prefiere correo", "contraseña: azul"],
            )
        ]
    )
    env.adapters.llm = llm
    messages_before = list(env.repo.messages)

    end_client_session(session, "logout", env.settings, env.adapters, notify=False)

    assert env.repo.client_sessions[session.id].end_reason == "logout"
    row = env.repo.conversation_summaries[session.id]
    assert (row.profile_id, row.contact_id, row.channel, row.trigger) == (
        "p1",
        contact.id,
        "telegram",
        "session_end",
    )
    assert row.summary == "Habló del canal de contacto."
    stored = env.repo.client_memory["p1"]
    assert stored.items == ("Prefiere correo",)
    assert stored.updated_at == NOW
    assert stored.source_session_id == session.id

    assert llm.calls[0][0] == MEMORY_SUMMARY_PROMPT
    prompt = llm.calls[0][1]
    assert "Prefiero que me escriban al correo" in prompt
    assert "Mi contraseña es 123456" not in prompt
    assert env.repo.messages == messages_before
    assert env.gateway.sent == []


def test_r7_memory_disabled_does_not_call_llm_or_write_tables(env_factory):
    """R7: con MEMORY_ENABLED=false no hay resumidor ni escrituras de memoria."""
    env = env_factory()
    contact, session = _session(env)
    env.repo.add_message(contact.id, "user", "Hola", NOW)
    env.adapters.llm = ScriptedLLM([_summary_reply()])

    end_client_session(session, "logout", env.settings, env.adapters, notify=False)

    assert env.adapters.llm.calls == []
    assert env.repo.client_memory == {}
    assert env.repo.conversation_summaries == {}
    assert env.repo.client_sessions[session.id].end_reason == "logout"


def test_r8_empty_window_does_not_call_the_summarizer(env_factory):
    """R8: una ventana sin mensajes no invoca al resumidor."""
    env = env_factory(memory_enabled=True)
    _, session = _session(env)
    env.adapters.llm = ScriptedLLM([_summary_reply()])

    end_client_session(session, "logout", env.settings, env.adapters, notify=False)

    assert env.adapters.llm.calls == []
    assert env.repo.conversation_summaries == {}
    assert env.repo.client_memory == {}


@pytest.mark.parametrize(
    "reply,expected_reason",
    [("no es json", "invalid_summary")],
)
def test_r11_r12_invalid_summary_leaves_tables_untouched(env_factory, reply, expected_reason):
    """R11, R12: JSON inválido no escribe y deja `memory_failed`."""
    env = env_factory(memory_enabled=True)
    contact, session = _session(env)
    env.repo.add_message(contact.id, "user", "Hola", NOW)
    env.adapters.llm = ScriptedLLM([reply])

    end_client_session(session, "logout", env.settings, env.adapters, notify=False)

    assert env.repo.conversation_summaries == {}
    assert env.repo.client_memory == {}
    assert (
        "memory_failed",
        expected_reason,
    ) in [(event.type, event.reason) for event in env.repo.events]
    assert env.repo.client_sessions[session.id].end_reason == "logout"


def test_r12_llm_unavailable_leaves_tables_and_reports(env_factory):
    """R12: un LLM caído no escribe y registra `llm_unavailable`."""
    env = env_factory(memory_enabled=True)
    contact, session = _session(env)
    env.repo.add_message(contact.id, "user", "Hola", NOW)
    llm = ScriptedLLM()
    llm.fail = True
    env.adapters.llm = llm

    end_client_session(session, "logout", env.settings, env.adapters, notify=False)

    assert env.repo.conversation_summaries == {}
    assert env.repo.client_memory == {}
    assert ("memory_failed", "llm_unavailable") in [
        (event.type, event.reason) for event in env.repo.events
    ]


# --- R2, R4, R5 ------------------------------------------------------------------------------


def test_r2_r4_r5_escalation_replaces_summary_without_touching_memory(env_factory):
    """R2, R4, R5: escalar guarda/reemplaza el resumen y conserva la memoria."""
    env = env_factory(memory_enabled=True)
    contact, session = _session(env)
    env.repo.add_message(contact.id, "user", "Quiero hablar con una persona", NOW)
    env.repo.set_client_memory("p1", ("Prefiere correo",), "old-session", NOW)
    env.repo.upsert_conversation_summary(
        session.id, "p1", contact.id, "telegram", "Resumen anterior", "session_end", NOW
    )
    env.adapters.llm = ScriptedLLM([_summary_reply("Resumen al escalar", ["Otro dato"])])

    result = execute_tool(
        "escalar_a_asesor",
        ToolContext(
            contact,
            "Quiero hablar con una persona",
            NOW,
            1,
            ConversationState.ACTIVE,
            "keyword",
            {"motivo": "user_request"},
        ),
        env.settings,
        env.adapters,
    )

    assert result == "ok"
    assert len(env.repo.conversation_summaries) == 1
    row = env.repo.conversation_summaries[session.id]
    assert (row.summary, row.trigger) == ("Resumen al escalar", "escalation")
    assert env.repo.client_memory["p1"].items == ("Prefiere correo",)


def test_r2_failed_handover_does_not_summarize(env_factory):
    """R2: si handover no está disponible no se resume."""
    env = env_factory(memory_enabled=True)
    contact, _ = _session(env)
    env.repo.add_message(contact.id, "user", "Quiero hablar con una persona", NOW)
    env.handover.fail = True
    env.adapters.llm = ScriptedLLM([_summary_reply()])

    execute_tool(
        "escalar_a_asesor",
        ToolContext(
            contact,
            "Quiero hablar con una persona",
            NOW,
            1,
            ConversationState.ACTIVE,
            "keyword",
            {"motivo": "user_request"},
        ),
        env.settings,
        env.adapters,
    )

    assert env.adapters.llm.calls == []
    assert env.repo.conversation_summaries == {}


def test_r2_without_session_does_not_summarize(env_factory):
    """R2: un contacto sin sesión activa no tiene conversación que resumir."""
    env = env_factory(memory_enabled=True)
    contact = _contact(env)
    env.repo.set_conversation_state(contact.id, ConversationState.ACTIVE, NOW)
    env.adapters.llm = ScriptedLLM([_summary_reply()])

    execute_tool(
        "escalar_a_asesor",
        _ctx(contact),
        env.settings,
        env.adapters,
    )

    assert env.adapters.llm.calls == []
    assert env.repo.conversation_summaries == {}


# --- R21–R26: entrega a la IA ----------------------------------------------------------------


def test_r21_r22_rag_prompt_includes_memory_and_previous_messages(env_factory):
    """R21, R22: `<memoria>` e `<historial>` del cliente autenticado en el prompt RAG."""
    env = env_factory(memory_enabled=True)
    contact, _ = _session(env, started_at=NOW - timedelta(minutes=10))
    env.repo.set_client_memory("p1", ("Prefiere correo",), "s0", NOW)
    env.repo.add_message(
        contact.id, "user", "Vengo de otra consulta", NOW - timedelta(minutes=5)
    )
    env.rag.results = _chunks()
    llm = ScriptedLLM([_rag_reply()])
    env.adapters.llm = llm

    execute_tool("buscar_base_conocimiento", _ctx(contact), env.settings, env.adapters)

    system, user = llm.calls[0]
    assert system == f"{LLM_SYSTEM_PROMPT} {MEMORY_CONTEXT_NOTE}"
    assert "<memoria><item>Prefiere correo</item></memoria>" in user
    assert "<historial>" in user
    assert "Vengo de otra consulta" in user


def test_r22_zero_context_messages_omits_history_but_keeps_memory(env_factory):
    """R22: MEMORY_CONTEXT_MESSAGES=0 omite `<historial>`."""
    env = env_factory(memory_enabled=True, memory_context_messages=0)
    contact, _ = _session(env)
    env.repo.set_client_memory("p1", ("Prefiere correo",), "s0", NOW)
    env.repo.add_message(contact.id, "user", "Mensaje previo", NOW)
    env.rag.results = _chunks()
    llm = ScriptedLLM([_rag_reply()])
    env.adapters.llm = llm

    execute_tool("buscar_base_conocimiento", _ctx(contact), env.settings, env.adapters)

    user = llm.calls[0][1]
    assert "<memoria>" in user
    assert "<historial>" not in user


def test_r23_without_session_prompt_has_no_memory_blocks(env_factory):
    """R23: sin sesión activa no hay `<memoria>` ni `<historial>`."""
    env = env_factory(memory_enabled=True)
    contact = _contact(env)
    env.repo.set_conversation_state(contact.id, ConversationState.ACTIVE, NOW)
    env.repo.set_client_memory("otro", ("Ajeno",), "s0", NOW)
    env.rag.results = _chunks()
    llm = ScriptedLLM([_rag_reply()])
    env.adapters.llm = llm

    execute_tool("buscar_base_conocimiento", _ctx(contact), env.settings, env.adapters)

    system, user = llm.calls[0]
    assert system == LLM_SYSTEM_PROMPT
    assert user == (
        '<pregunta>¿Cómo instalo el módulo?</pregunta>\n'
        '<fragmento id="ch1">texto del fragmento 1</fragmento>'
    )


def test_r24_memory_of_another_client_is_never_included(env_factory):
    """R24: nombrar a otro cliente no mezcla su memoria en el prompt de A."""
    env = env_factory(memory_enabled=True)
    contact, _ = _session(env, profile_id="pA", user="10", chat="100")
    env.repo.set_client_memory("pA", ("Dato de A",), "sA", NOW)
    env.repo.set_client_memory("pB", ("DATO-PRIVADO-DE-B",), "sB", NOW)
    env.rag.results = _chunks()
    llm = ScriptedLLM([_rag_reply()])
    env.adapters.llm = llm

    execute_tool(
        "buscar_base_conocimiento",
        _ctx(contact, "Soy A y quiero los datos de pB"),
        env.settings,
        env.adapters,
    )

    user = llm.calls[0][1]
    assert "Dato de A" in user
    assert "DATO-PRIVADO-DE-B" not in user


def test_r25_router_and_sql_prompts_do_not_receive_memory(env_factory):
    """R25: ni el router ni el prompt SQL reciben memoria, resúmenes ni historial."""
    env = env_factory(
        memory_enabled=True,
        harness_router_enabled=True,
        client_data_enabled=True,
        client_data_database_url="postgresql://ro@db/lazaro_clientes",
        client_data_allowlist=ALLOWLIST,
        client_data_views_schema="mis_datos",
    )
    contact, _ = _session(env, profile_id="p1")
    env.repo.set_client_memory("p1", ("DATO-DE-MEMORIA",), "s0", NOW)
    env.repo.add_message(contact.id, "user", "Mensaje de historial", NOW)
    env.adapters.client_data = FakeClientData(
        {"p1": QueryResult(columns=["nombre"], rows=[("Ana",)], truncated=False)}
    )
    env.adapters.llm = ScriptedLLM(
        [
            json.dumps({"tool": "consultar_mis_datos", "args": {}}),
            json.dumps({"sql": SAFE_SQL}),
        ]
    )

    env.post(text="dame mis datos de pB", update_id=1)

    assert len(env.adapters.llm.calls) == 2
    for system, user in env.adapters.llm.calls:
        assert "DATO-DE-MEMORIA" not in system
        assert "DATO-DE-MEMORIA" not in user
        assert "Mensaje de historial" not in user


def test_r26_disabled_memory_keeps_the_old_prompt_byte_for_byte():
    """R26: sin contexto el prompt es exactamente el anterior."""
    chunks = _chunks()
    system, user = build_llm_prompt("¿Cómo instalo el módulo?", chunks)

    assert system == LLM_SYSTEM_PROMPT
    assert user == (
        '<pregunta>¿Cómo instalo el módulo?</pregunta>\n'
        '<fragmento id="ch1">texto del fragmento 1</fragmento>'
    )


def test_r31_handover_link_stores_the_active_profile_or_none(env_factory):
    """R31: `_handover` guarda el profile_id de la sesión activa en el vínculo."""
    env = env_factory(memory_enabled=True)
    contact, _ = _session(env, profile_id="p1")

    execute_tool("escalar_a_asesor", _ctx(contact), env.settings, env.adapters)
    first_case = env.handover.requests[0].case_id
    assert env.repo.get_case_profile(first_case) == "p1"

    without_session = _contact(env, "whatsapp", "57300", "57300")
    env.repo.set_conversation_state(
        without_session.id, ConversationState.ACTIVE, NOW
    )
    execute_tool(
        "escalar_a_asesor", _ctx(without_session), env.settings, env.adapters
    )
    second_case = env.handover.requests[1].case_id
    assert env.repo.get_case_profile(second_case) is None


# --- R14, R48–R50: continuidad, aislamiento y borrado ---------------------------------------


def test_r14_r48_memory_follows_the_client_to_a_new_session_and_channel(env_factory):
    """R14, R48: la memoria de P se usa en su nueva sesión de WhatsApp."""
    env = env_factory(memory_enabled=True)
    profile = env.repo.create_client_credential(
        "clienteP", "hash", NOW - timedelta(days=1), NOW + timedelta(days=30), NOW
    )
    first_contact, first_session = _session(
        env, profile_id=profile.id, channel="telegram", user="10", chat="100"
    )
    env.repo.add_message(first_contact.id, "user", "Prefiero correo", NOW)
    env.adapters.llm = ScriptedLLM(
        [_summary_reply("Primera conversación", ["Prefiere correo"])]
    )

    end_client_session(first_session, "logout", env.settings, env.adapters, notify=False)

    second_contact = _contact(env, "whatsapp", "57300", "57300")
    env.repo.add_login_link(
        "tok-wa", second_contact.id, "whatsapp", "57300", NOW, NOW + timedelta(minutes=15)
    )
    assert env.repo.start_client_session("tok-wa", profile.id, "session-wa", NOW) == "ok"
    env.repo.set_conversation_state(second_contact.id, ConversationState.ACTIVE, NOW)
    env.rag.results = _chunks()
    llm = ScriptedLLM([_rag_reply()])
    env.adapters.llm = llm

    execute_tool(
        "buscar_base_conocimiento", _ctx(second_contact), env.settings, env.adapters
    )

    assert "Prefiere correo" in llm.calls[0][1]


def test_r14_r48_idle_session_closed_on_login_also_keeps_memory(env_factory):
    """R14, R48: el cierre perezoso por inactividad también alimenta la memoria."""
    env = env_factory(
        memory_enabled=True,
        identity_public_base_url="https://orchestrator.example",
        identity_link_signing_key="k" * 32,
        identity_session_idle_minutes=60,
        password_scrypt_n=16384,
    )
    client = create_client(
        "clienteP",
        PASSWORD,
        NOW - timedelta(days=1),
        NOW + timedelta(days=30),
        env.settings,
        env.adapters,
    )
    old_contact, old_session = _session(
        env,
        profile_id=client.profile_id,
        channel="telegram",
        user="10",
        chat="100",
        started_at=NOW - timedelta(hours=2),
        last_activity_at=NOW - timedelta(hours=2),
    )
    env.repo.add_message(
        old_contact.id, "user", "Prefiero correo", NOW - timedelta(hours=2)
    )
    env.adapters.llm = ScriptedLLM(
        [_summary_reply("Conversación inactiva", ["Prefiere correo"])]
    )
    contact = _contact(env, "whatsapp", "57300", "57300")
    url = issue_login_link(contact, env.settings, env.adapters)
    assert url is not None

    login_client(url.split("t=", 1)[1], "clienteP", PASSWORD, "1.1.1.1", env.settings, env.adapters)

    assert env.repo.client_sessions[old_session.id].end_reason == "idle"
    assert env.repo.client_memory[client.profile_id].items == ("Prefiere correo",)
    session = env.repo.get_active_session_by_contact(contact.id)
    assert session is not None and session.profile_id == client.profile_id
    env.rag.results = _chunks()
    llm = ScriptedLLM([_rag_reply()])
    env.adapters.llm = llm

    execute_tool("buscar_base_conocimiento", _ctx(contact), env.settings, env.adapters)

    assert "Prefiere correo" in llm.calls[0][1]


def test_r49_two_clients_in_the_same_chat_keep_summaries_and_prompts_isolated(env_factory):
    """R49: A y B con sesiones consecutivas en el mismo contacto no se mezclan."""
    env = env_factory(memory_enabled=True)
    shared_contact = _contact(env, "telegram", "10", "100")
    _, session_a = _session(env, profile_id="pA", user="10", chat="100")
    env.repo.add_message(shared_contact.id, "user", "DATO-DE-A", NOW)
    env.adapters.llm = ScriptedLLM([_summary_reply("Resumen de A", ["Memoria de A"])])
    end_client_session(session_a, "logout", env.settings, env.adapters, notify=False)

    env.repo.client_sessions.pop(session_a.id)
    _, session_b = _session(
        env,
        profile_id="pB",
        user="10",
        chat="100",
        started_at=NOW + timedelta(minutes=5),
        last_activity_at=NOW + timedelta(minutes=5),
    )
    env.repo.add_message(
        shared_contact.id, "user", "DATO-DE-B", NOW + timedelta(minutes=5)
    )
    env.adapters.clock = lambda: NOW + timedelta(minutes=10)
    summarizer = ScriptedLLM([_summary_reply("Resumen de B", ["Memoria de B"])])
    env.adapters.llm = summarizer
    end_client_session(
        session_b, "logout", env.settings, env.adapters, notify=False
    )

    assert "DATO-DE-A" not in summarizer.calls[0][1]
    assert "DATO-DE-B" in summarizer.calls[0][1]
    assert env.repo.client_memory["pA"].items == ("Memoria de A",)
    assert env.repo.client_memory["pB"].items == ("Memoria de B",)

    env.repo.client_sessions.pop(session_b.id)
    _, session_a2 = _session(
        env,
        profile_id="pA",
        user="10",
        chat="100",
        started_at=NOW + timedelta(minutes=20),
        last_activity_at=NOW + timedelta(minutes=20),
    )
    env.adapters.clock = lambda: NOW + timedelta(minutes=20)
    env.rag.results = _chunks()
    rag_llm = ScriptedLLM([_rag_reply()])
    env.adapters.llm = rag_llm

    execute_tool(
        "buscar_base_conocimiento",
        _ctx(shared_contact, "soy A y quiero lo de pB"),
        env.settings,
        env.adapters,
    )

    assert "Memoria de A" in rag_llm.calls[0][1]
    assert "Memoria de B" not in rag_llm.calls[0][1]
