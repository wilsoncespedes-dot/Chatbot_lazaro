"""Flujo del orquestador como cliente MCP (#74)."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from orchestrator.adapters.llm import ScriptedLLM, ToolStep
from orchestrator.adapters.mcp import FakeMcpClient, McpCallResult
from orchestrator.domain import ConversationState, ToolContext, execute_tool

from fakes import drain_queues

NOW = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
TEXT = "¿tienes algo para Melgar esta semana?"
DEMO_ROWS = [
    {
        "id": "demo-1",
        "destino": "Melgar",
        "titulo": "Oferta de demostración",
        "es_demo": True,
        "etiqueta": "DEMOSTRACIÓN",
    }
]


def _rag_reply() -> str:
    return json.dumps(
        {
            "answer": "Respuesta RAG",
            "citations": [
                {"chunk_id": "ch1", "quote": "texto del fragmento 1"}
            ],
        }
    )


def _login(env, channel: str = "telegram", user: str = "10", chat: str = "100"):
    contact = env.repo.get_or_create_channel_contact(channel, user, chat, NOW)
    env.repo.set_conversation_state(contact.id, ConversationState.ACTIVE, NOW)
    profile = env.repo.create_client_credential(
        f"cliente-{channel}-{user}",
        "hash",
        NOW - timedelta(days=1),
        NOW + timedelta(days=30),
        NOW,
    )
    token_hash = f"hash-{channel}-{user}"
    env.repo.add_login_link(
        token_hash, contact.id, channel, chat, NOW, NOW + timedelta(minutes=15)
    )
    assert env.repo.start_client_session(
        token_hash, profile.id, f"session-{channel}-{user}", NOW
    ) == "ok"
    return contact, profile


def _ctx(contact) -> ToolContext:
    return ToolContext(
        contact=contact,
        text=TEXT,
        received_at=NOW,
        update_id=1,
        state=ConversationState.ACTIVE,
        origin="rule",
    )


def _run(env, tool_steps=None, final_reply="", replies=None):
    env.settings.mcp_enabled = True
    env.adapters.llm = ScriptedLLM(
        replies=list(replies or []),
        tool_steps=list(tool_steps or []),
        final_reply=final_reply,
    )
    return env


def test_cliente_id_comes_from_session(env):
    """R17: el `cliente_id` enviado al MCP sale de la sesión, no del modelo."""
    contact, profile = _login(env)
    fake = FakeMcpClient(
        results={"ofertas_demo": McpCallResult(rows=DEMO_ROWS, demo=True)}
    )
    env.adapters.mcp = fake
    _run(
        env,
        tool_steps=[ToolStep("ofertas_demo", {"destino": "Melgar"})],
        final_reply="Hay ofertas de demostración.",
    )

    execute_tool(
        "consultar_herramientas_mcp",
        _ctx(contact),
        env.settings,
        env.adapters,
    )

    assert fake.calls == [("ofertas_demo", {"destino": "Melgar"}, profile.id)]


def test_model_cliente_id_arg_is_dropped(env):
    """R18: las claves que no están en el esquema (incluida identidad) se descartan."""
    contact, profile = _login(env)
    fake = FakeMcpClient(
        results={"ofertas_demo": McpCallResult(rows=DEMO_ROWS, demo=True)}
    )
    env.adapters.mcp = fake
    _run(
        env,
        tool_steps=[
            ToolStep(
                "ofertas_demo",
                {
                    "destino": "Melgar",
                    "desde": "2026-01-01",
                    "hasta": "2026-01-07",
                    "cliente_id": "otro-cliente",
                    "user_id": "999",
                },
            )
        ],
        final_reply="Hay ofertas.",
    )

    execute_tool(
        "consultar_herramientas_mcp",
        _ctx(contact),
        env.settings,
        env.adapters,
    )

    name, args, cliente_id = fake.calls[0]
    assert name == "ofertas_demo"
    assert "cliente_id" not in args and "user_id" not in args
    assert args == {
        "destino": "Melgar",
        "desde": "2026-01-01",
        "hasta": "2026-01-07",
    }
    assert cliente_id == profile.id


def test_unlisted_tool_rejected(env):
    """R19: una herramienta que el servidor no listó no se contacta."""
    contact, _ = _login(env)
    fake = FakeMcpClient()
    env.adapters.mcp = fake
    scripted = _run(
        env,
        tool_steps=[ToolStep("borrar_todo", {})],
        final_reply="No puedo hacer eso.",
        replies=[_rag_reply()],
    ).adapters.llm

    execute_tool(
        "consultar_herramientas_mcp",
        _ctx(contact),
        env.settings,
        env.adapters,
    )

    assert fake.calls == []
    assert scripted.tool_calls
    assert "tool_not_allowed" in scripted.tool_calls[0][2]


def test_max_tool_steps(env):
    """R20: nunca se superan `MCP_MAX_TOOL_STEPS` llamadas por mensaje."""
    contact, _ = _login(env)
    env.settings.mcp_max_tool_steps = 3
    fake = FakeMcpClient(
        results={"buscar_manuales": McpCallResult(rows=[])}
    )
    env.adapters.mcp = fake
    scripted = _run(
        env,
        tool_steps=[
            ToolStep("buscar_manuales", {"consulta": f"q{i}"}) for i in range(5)
        ],
        final_reply="Listo.",
    ).adapters.llm

    execute_tool(
        "consultar_herramientas_mcp",
        _ctx(contact),
        env.settings,
        env.adapters,
    )

    assert len(fake.calls) == 3
    assert len(scripted.tool_calls) == 3


def test_mcp_down_falls_back_to_rag_and_logs(env):
    """R21: si el MCP no está, se registra y se responde con RAG."""
    contact, _ = _login(env)
    env.adapters.mcp = FakeMcpClient(fail=True)
    _run(env, replies=[_rag_reply()])

    result = execute_tool(
        "consultar_herramientas_mcp",
        _ctx(contact),
        env.settings,
        env.adapters,
    )
    drain_queues(env.settings, env.adapters)

    assert result == "ok"
    assert ("mcp_unavailable", "list_tools") in env.events()
    assert env.gateway.sent[-1][1] == "Respuesta RAG"


def test_no_tool_call_falls_back_to_rag(env):
    """R22: si el modelo no pide herramientas, responde el flujo RAG."""
    contact, _ = _login(env)
    fake = FakeMcpClient()
    env.adapters.mcp = fake
    _run(env, tool_steps=[], final_reply="texto sin herramientas", replies=[_rag_reply()])

    result = execute_tool(
        "consultar_herramientas_mcp",
        _ctx(contact),
        env.settings,
        env.adapters,
    )
    drain_queues(env.settings, env.adapters)

    assert result == "ok"
    assert fake.calls == []
    assert env.gateway.sent[-1][1] == "Respuesta RAG"


def test_demo_notice_appended(env):
    """R23: una fila de demostración añade el aviso configurable."""
    contact, _ = _login(env)
    fake = FakeMcpClient(
        results={"ofertas_demo": McpCallResult(rows=DEMO_ROWS, demo=True)}
    )
    env.adapters.mcp = fake
    _run(
        env,
        tool_steps=[ToolStep("ofertas_demo", {"destino": "Melgar"})],
        final_reply="Hay ofertas de demostración.",
    )

    execute_tool(
        "consultar_herramientas_mcp",
        _ctx(contact),
        env.settings,
        env.adapters,
    )
    drain_queues(env.settings, env.adapters)

    sent = env.gateway.sent[-1][1]
    assert sent.startswith("Hay ofertas de demostración.")
    assert env.settings.mcp_demo_notice in sent


def test_tool_calls_audit_detail(env):
    """R24: `tool_calls` guarda herramientas usadas y filas, sin argumentos."""
    contact, _ = _login(env)
    fake = FakeMcpClient(
        results={
            "buscar_manuales": McpCallResult(
                rows=[{"chunk_id": "c1"}, {"chunk_id": "c2"}]
            )
        }
    )
    env.adapters.mcp = fake
    _run(
        env,
        tool_steps=[ToolStep("buscar_manuales", {"consulta": "Melgar"})],
        final_reply="Dos resultados.",
    )

    execute_tool(
        "consultar_herramientas_mcp",
        _ctx(contact),
        env.settings,
        env.adapters,
    )

    call = env.repo.tool_calls[-1]
    assert call.tool == "consultar_herramientas_mcp"
    assert call.detail == "mcp_tools=buscar_manuales;rows=2"
    assert "Melgar" not in call.detail
