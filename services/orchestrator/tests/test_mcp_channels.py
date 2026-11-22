"""El resultado MCP no depende del canal (#74)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from orchestrator.adapters.llm import ScriptedLLM, ToolStep
from orchestrator.adapters.mcp import FakeMcpClient, McpCallResult
from orchestrator.domain import ConversationState, ToolContext, execute_tool

from fakes import drain_queues

NOW = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
DEMO_ROWS = [
    {
        "id": "demo-1",
        "destino": "Melgar",
        "titulo": "Oferta de demostración",
        "es_demo": True,
        "etiqueta": "DEMOSTRACIÓN",
    }
]


def _login(env, channel: str, user: str, chat: str):
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
    return contact


def _answer(env, channel: str, user: str, chat: str, fake: FakeMcpClient) -> str:
    contact = _login(env, channel, user, chat)
    env.adapters.mcp = fake
    env.adapters.llm = ScriptedLLM(
        tool_steps=[ToolStep("ofertas_demo", {"destino": "Melgar"})],
        final_reply="Hay ofertas de demostración para Melgar.",
    )
    before = len(env.gateway.channel_sent)
    execute_tool(
        "consultar_herramientas_mcp",
        ToolContext(
            contact=contact,
            text="¿tienes algo para Melgar esta semana?",
            received_at=NOW,
            update_id=1,
            state=ConversationState.ACTIVE,
            origin="rule",
        ),
        env.settings,
        env.adapters,
    )
    drain_queues(env.settings, env.adapters)
    return env.gateway.channel_sent[before:][-1][2]


def test_same_answer_telegram_and_simulado(env):
    """R26: Telegram y el canal simulado producen la misma respuesta."""
    env.settings.mcp_enabled = True
    fake = FakeMcpClient(
        results={"ofertas_demo": McpCallResult(rows=DEMO_ROWS, demo=True)}
    )

    telegram = _answer(env, "telegram", "10", "100", fake)
    simulado = _answer(env, "simulado", "20", "200", fake)

    assert telegram == simulado
    assert "Melgar" in telegram
