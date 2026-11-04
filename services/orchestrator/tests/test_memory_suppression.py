"""Supresión por persona, retención y no regresión de herramientas (#40)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from lazaro_contracts import SearchResult

from orchestrator.adapters.llm import ScriptedLLM
from orchestrator.adapters.repository import PostgresRepository
from orchestrator.domain import (
    ClientSession,
    ConversationState,
    SuppressionForbidden,
    SuppressionNotFound,
    SuppressionNotPending,
    ToolContext,
    advisor_client_memory,
    execute_suppression,
    execute_tool,
    purge_personal_data,
)

NOW = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
CUTOFF = NOW - timedelta(days=30)


def _profile(env, username: str, role: str) -> str:
    if role == "cliente":
        return env.repo.create_client_credential(
            username, "hash", NOW - timedelta(days=1), NOW + timedelta(days=30), NOW
        ).id
    return env.repo.create_profile(username, role, "hash", NOW).id


def _contact(env, user: int, chat: int):
    return env.repo.get_or_create_contact(user, chat, NOW)


def _session(
    env,
    profile_id: str,
    contact_id: str,
    started_at: datetime = NOW - timedelta(minutes=10),
    last_activity_at: datetime = NOW - timedelta(minutes=1),
    ended_at: datetime | None = NOW,
) -> ClientSession:
    session = ClientSession(
        id=f"session-{profile_id}-{contact_id}",
        profile_id=profile_id,
        contact_id=contact_id,
        started_at=started_at,
        last_activity_at=last_activity_at,
        ended_at=ended_at,
    )
    env.repo.client_sessions[session.id] = session
    return session


def _request(env, profile_id: str, contact_id: str, request_id: str = "req-1"):
    created_id, created = env.repo.create_or_get_pending_suppression(
        request_id, profile_id, contact_id, "telegram", NOW
    )
    assert created
    return env.repo.suppression_requests[created_id]


def _ctx(contact, state: ConversationState = ConversationState.ACTIVE) -> ToolContext:
    return ToolContext(contact, "texto", NOW, 1, state, "rule")


@pytest.mark.parametrize("mode", ["missing", "asesor_default", "cliente"])
def test_r36_forbidden_actor_cannot_delete_anything(env_factory, mode):
    """R36: perfil inexistente, asesor con default admin o cliente reciben 403."""
    env = env_factory(memory_enabled=True)
    client_id = _profile(env, "cliente1", "cliente")
    contact = _contact(env, 10, 100)
    _session(env, client_id, contact.id)
    _request(env, client_id, contact.id)
    env.repo.set_client_memory(client_id, ("Dato",), "s", NOW)
    if mode == "missing":
        actor_id = "no-existe"
    elif mode == "asesor_default":
        actor_id = _profile(env, "asesor1", "asesor")
    else:
        actor_id = _profile(env, "cliente2", "cliente")

    with pytest.raises(SuppressionForbidden):
        execute_suppression("req-1", actor_id, env.settings, env.adapters)

    assert client_id in env.repo.client_memory
    assert env.repo.suppression_requests["req-1"].status == "pending"


def test_r36_asesor_role_can_execute_when_configured(env_factory):
    """R36: si SUPPRESSION_EXECUTOR_ROLES incluye asesor, ese rol puede ejecutar."""
    env = env_factory(memory_enabled=True, suppression_executor_roles="admin,asesor")
    client_id = _profile(env, "cliente1", "cliente")
    actor_id = _profile(env, "asesor1", "asesor")
    contact = _contact(env, 10, 100)
    _session(env, client_id, contact.id)
    _request(env, client_id, contact.id)
    env.repo.set_client_memory(client_id, ("Dato",), "s", NOW)

    result = execute_suppression("req-1", actor_id, env.settings, env.adapters)

    assert result.profile_id == client_id
    assert client_id not in env.repo.client_memory


def test_r37_unknown_request_is_404(env_factory):
    """R37: una solicitud inexistente no borra nada."""
    env = env_factory(memory_enabled=True)
    actor_id = _profile(env, "admin1", "admin")

    with pytest.raises(SuppressionNotFound):
        execute_suppression("no-existe", actor_id, env.settings, env.adapters)


def test_r38_request_not_pending_is_409(env_factory):
    """R38: una solicitud ya ejecutada no se vuelve a borrar."""
    env = env_factory(memory_enabled=True)
    actor_id = _profile(env, "admin1", "admin")
    client_id = _profile(env, "cliente1", "cliente")
    contact = _contact(env, 10, 100)
    request = _request(env, client_id, contact.id)
    request.status = "executed"
    env.repo.set_client_memory(client_id, ("Dato",), "s", NOW)

    with pytest.raises(SuppressionNotPending):
        execute_suppression("req-1", actor_id, env.settings, env.adapters)

    assert client_id in env.repo.client_memory


def test_r39_active_session_is_closed_without_summarizing(env_factory):
    """R39: la sesión activa se cierra como `suppression` y no llama al resumidor."""
    env = env_factory(memory_enabled=True)
    actor_id = _profile(env, "admin1", "admin")
    client_id = _profile(env, "cliente1", "cliente")
    contact = _contact(env, 10, 100)
    session = _session(
        env,
        client_id,
        contact.id,
        last_activity_at=NOW,
        ended_at=None,
    )
    env.repo.add_message(contact.id, "user", "Hola", NOW - timedelta(minutes=5))
    _request(env, client_id, contact.id)

    result = execute_suppression("req-1", actor_id, env.settings, env.adapters)

    assert env.repo.client_sessions[session.id].end_reason == "suppression"
    assert env.repo.client_sessions[session.id].ended_at == NOW
    assert env.adapters.llm.calls == []
    assert env.repo.conversation_summaries == {}
    assert result.deleted["messages"] == 1


def test_r40_r41_r42_r43_r44_r45_only_the_requested_client_is_deleted(env_factory):
    """R40–R45: borra lo de P, conserva lo de Q y lo previo al login; audita."""
    env = env_factory(memory_enabled=True)
    actor_id = _profile(env, "admin1", "admin")
    client_p = _profile(env, "clienteP", "cliente")
    client_q = _profile(env, "clienteQ", "cliente")
    contact_p = _contact(env, 10, 100)
    contact_q = _contact(env, 11, 101)
    _session(env, client_p, contact_p.id)
    _session(env, client_q, contact_q.id)

    env.repo.add_message(contact_p.id, "user", "antes del login", NOW - timedelta(hours=1))
    env.repo.add_message(contact_p.id, "user", "dentro de la ventana", NOW - timedelta(minutes=5))
    env.repo.add_message(contact_q.id, "user", "mensaje de Q", NOW - timedelta(minutes=5))
    env.repo.set_client_memory(client_p, ("Memoria P",), "sp", NOW)
    env.repo.set_client_memory(client_q, ("Memoria Q",), "sq", NOW)
    env.repo.upsert_conversation_summary(
        "sp", client_p, contact_p.id, "telegram", "Resumen P", "session_end", NOW
    )
    env.repo.upsert_conversation_summary(
        "sq", client_q, contact_q.id, "telegram", "Resumen Q", "session_end", NOW
    )
    request = _request(env, client_p, contact_p.id)

    result = execute_suppression("req-1", actor_id, env.settings, env.adapters)

    assert result.deleted == {
        "messages": 1,
        "conversation_summaries": 1,
        "client_memory": 1,
    }
    assert [m.text for m in env.repo.messages] == [
        "antes del login",
        "mensaje de Q",
    ]
    assert client_p not in env.repo.client_memory
    assert env.repo.client_memory[client_q].items == ("Memoria Q",)
    assert set(env.repo.conversation_summaries) == {"sq"}
    assert request.status == "executed"
    assert request.executed_at == NOW
    assert request.executed_by == actor_id
    assert request.removed_counts == result.deleted
    audit = env.repo.identity_audits[-1]
    assert (audit.profile_id, audit.action) == (client_p, "suppression_executed")
    assert audit.reason == f"request:req-1 by:{actor_id}"


def test_r46_ai_tools_never_delete_memory_or_summaries(env_factory):
    """R46: ninguna de las seis herramientas reduce memoria ni resúmenes."""
    env = env_factory(memory_enabled=True)
    profile_id = _profile(env, "cliente1", "cliente")
    env.repo.set_client_memory(profile_id, ("Dato persistente",), "s0", NOW)
    env.repo.upsert_conversation_summary(
        "s0", profile_id, "c0", "telegram", "Resumen previo", "session_end", NOW
    )

    def prepare(index: int, state: ConversationState, session: bool):
        contact = _contact(env, 100 + index, 200 + index)
        env.repo.set_conversation_state(contact.id, state, NOW)
        if session:
            _session(
                env,
                profile_id,
                contact.id,
                ended_at=None,
                last_activity_at=NOW,
            )
        return contact

    cases = [
        ("buscar_base_conocimiento", ConversationState.ACTIVE, True),
        ("consultar_mis_datos", ConversationState.ACTIVE, True),
        ("escalar_a_asesor", ConversationState.ACTIVE, True),
        ("crear_solicitud_supresion", ConversationState.ACTIVE, True),
        ("enviar_link_inicio_sesion", ConversationState.AWAITING_LOGIN, False),
        ("cerrar_sesion", ConversationState.ACTIVE, True),
    ]
    for index, (tool, state, session) in enumerate(cases):
        contact = prepare(index, state, session)
        before = len(env.repo.conversation_summaries)
        execute_tool(tool, _ctx(contact, state), env.settings, env.adapters)
        assert profile_id in env.repo.client_memory
        assert len(env.repo.conversation_summaries) >= before


def test_r50_after_suppression_the_prompt_and_panel_do_not_show_old_memory(env_factory):
    """R50: tras la supresión una sesión nueva y el panel ya no reciben la memoria."""
    env = env_factory(memory_enabled=True)
    actor_id = _profile(env, "admin1", "admin")
    client_id = _profile(env, "clienteP", "cliente")
    old_contact = _contact(env, 10, 100)
    _session(env, client_id, old_contact.id)
    env.repo.add_message(old_contact.id, "user", "Dato previo", NOW - timedelta(minutes=5))
    env.repo.set_client_memory(client_id, ("Memoria anterior",), "old", NOW)
    env.repo.upsert_conversation_summary(
        "old", client_id, old_contact.id, "telegram", "Resumen anterior", "session_end", NOW
    )
    _request(env, client_id, old_contact.id)

    execute_suppression("req-1", actor_id, env.settings, env.adapters)

    new_contact = _contact(env, 11, 101)
    _session(env, client_id, new_contact.id, ended_at=None, last_activity_at=NOW)
    env.rag.results = [
        SearchResult(
            chunk_id="ch1", manual="M", text="texto del fragmento 1", score=0.9
        )
    ]
    llm = ScriptedLLM(
        [
            '{"answer": "Respuesta final", "citations": '
            '[{"chunk_id": "ch1", "quote": "texto del fragmento 1"}]}'
        ]
    )
    env.adapters.llm = llm

    execute_tool("buscar_base_conocimiento", _ctx(new_contact), env.settings, env.adapters)

    assert "Memoria anterior" not in llm.calls[0][1]
    assert "<memoria>" not in llm.calls[0][1]

    env.repo.link_case("case-after", new_contact.id, NOW, profile_id=client_id)
    view = advisor_client_memory("case-after", "700", env.settings, env.adapters)
    assert view.authenticated is True
    assert view.items == ()
    assert view.summaries == ()


# --- R47, R53: retención ---------------------------------------------------------------------


def test_r47_r53_purge_deletes_old_summaries_and_never_memory(env_factory):
    """R47, R53: la purga borra resúmenes antiguos, cuenta y conserva la memoria."""
    env = env_factory(memory_enabled=True)
    env.repo.set_client_memory("p1", ("Memoria permanente",), "s0", CUTOFF - timedelta(days=1))
    env.repo.upsert_conversation_summary(
        "old", "p1", "c1", "telegram", "Resumen viejo", "session_end",
        CUTOFF - timedelta(seconds=1),
    )
    env.repo.upsert_conversation_summary(
        "new", "p1", "c1", "telegram", "Resumen reciente", "session_end", CUTOFF
    )

    response = purge_personal_data(env.settings, env.adapters)

    assert set(env.repo.conversation_summaries) == {"new"}
    assert env.repo.client_memory["p1"].items == ("Memoria permanente",)
    assert response.deleted["conversation_summaries"] == 1
    assert env.repo.privacy_purge_runs[-1]["counts"]["conversation_summaries"] == 1


class _PurgeCursor:
    def __init__(self, log: list) -> None:
        self.log = log
        self.sql = ""

    def execute(self, sql, params=()):
        self.sql = sql
        self.log.append((sql, tuple(params)))

    def fetchall(self):
        return []


class _PurgeConn:
    def __init__(self) -> None:
        self.log: list = []

    def cursor(self):
        return _PurgeCursor(self.log)

    def commit(self):
        pass

    def rollback(self):
        pass


def test_r47_r53_postgres_purge_touches_summaries_not_client_memory():
    """R47, R53: el SQL de purga borra resúmenes vencidos y no toca `client_memory`."""
    conn = _PurgeConn()
    repo = PostgresRepository("postgresql://x", connect=lambda: conn, new_id=lambda: "n")

    repo.purge_personal_data(CUTOFF, NOW)

    statements = [sql for sql, _ in conn.log]
    assert any(sql.startswith("DELETE FROM conversation_summaries") for sql in statements)
    assert not any(sql.startswith("DELETE FROM client_memory") for sql in statements)


class _SuppressionCursor:
    def __init__(self, log: list) -> None:
        self.log = log
        self.sql = ""

    def execute(self, sql, params=()):
        self.sql = sql
        self.log.append((sql, tuple(params)))

    def fetchall(self):
        if "FROM suppression_requests" in self.sql and "FOR UPDATE" in self.sql:
            return [("p1",)]
        if "FROM client_sessions" in self.sql:
            return [
                ("c1", NOW - timedelta(minutes=10), NOW - timedelta(minutes=1), NOW)
            ]
        if self.sql.startswith("DELETE FROM messages"):
            return [(1,), (2,)]
        if self.sql.startswith("DELETE FROM conversation_summaries"):
            return [("s1",)]
        if self.sql.startswith("DELETE FROM client_memory"):
            return [("p1",)]
        return []


class _SuppressionConn:
    def __init__(self) -> None:
        self.log: list = []
        self.commits = 0
        self.rollbacks = 0

    def cursor(self):
        return _SuppressionCursor(self.log)

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1


def test_r44_postgres_suppression_is_parameterized_and_atomic():
    """R44: la transacción usa parámetros, devuelve recuentos y hace commit."""
    conn = _SuppressionConn()
    repo = PostgresRepository("postgresql://x", connect=lambda: conn, new_id=lambda: "n")

    counts = repo.execute_suppression("req-1", "admin-1", 60, NOW)

    assert counts == {
        "messages": 2,
        "conversation_summaries": 1,
        "client_memory": 1,
    }
    assert conn.rollbacks == 0 and conn.commits >= 2
    statements = [(sql, params) for sql, params in conn.log]
    for sql, params in statements:
        assert "req-1" not in sql and "admin-1" not in sql
        assert sql.count("%s") == len(params)
    assert any(
        sql.startswith("UPDATE suppression_requests") for sql, _ in statements
    )
