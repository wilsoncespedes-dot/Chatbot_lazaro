"""Matriz y visibilidad de la herramienta MCP del harness (#74)."""
from __future__ import annotations

from datetime import datetime, timezone

from orchestrator.adapters.mcp import FakeMcpClient
from orchestrator.config import Settings
from orchestrator.domain import ConversationState, ToolContext, execute_tool
from orchestrator.harness import TOOL_MATRIX, build_router_prompt

NOW = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)


def _contact(env, state: ConversationState):
    contact = env.repo.get_or_create_contact(10, 100, NOW)
    env.repo.set_conversation_state(contact.id, state, NOW)
    return contact


def _ctx(contact, state: ConversationState) -> ToolContext:
    return ToolContext(
        contact=contact,
        text="¿tienes algo para Melgar esta semana?",
        received_at=NOW,
        update_id=1,
        state=state,
        origin="rule",
    )


def test_mcp_tool_only_in_active():
    """R14: `consultar_herramientas_mcp` solo se autoriza en `active`."""
    for state in ConversationState:
        assert ("consultar_herramientas_mcp" in TOOL_MATRIX[state]) is (
            state == ConversationState.ACTIVE
        )


def test_router_prompt_hides_mcp_when_disabled():
    """R15: con MCP apagado, el router no ofrece la herramienta."""
    enabled, _ = build_router_prompt(
        ConversationState.ACTIVE, "hola", mcp_enabled=True
    )
    disabled, _ = build_router_prompt(
        ConversationState.ACTIVE, "hola", mcp_enabled=False
    )
    assert "consultar_herramientas_mcp" in enabled
    assert "consultar_herramientas_mcp" not in disabled


def test_disabled_never_contacts_mcp(env):
    """R15: con MCP_ENABLED=false no se contacta al servidor MCP."""
    env.settings.mcp_enabled = False
    fake = FakeMcpClient()
    env.adapters.mcp = fake
    contact = _contact(env, ConversationState.ACTIVE)

    result = execute_tool(
        "consultar_herramientas_mcp",
        _ctx(contact, ConversationState.ACTIVE),
        env.settings,
        env.adapters,
    )

    assert result == "ok"
    assert fake.list_calls == 0
    assert fake.calls == []
    assert env.rag.calls


def test_denied_in_with_advisor_no_mcp_call(env):
    """R16: un estado que no autoriza la herramienta no contacta al MCP."""
    env.settings.mcp_enabled = True
    fake = FakeMcpClient()
    env.adapters.mcp = fake
    contact = _contact(env, ConversationState.WITH_ADVISOR)

    result = execute_tool(
        "consultar_herramientas_mcp",
        _ctx(contact, ConversationState.WITH_ADVISOR),
        env.settings,
        env.adapters,
    )

    assert result == "denied"
    assert fake.list_calls == 0
    assert fake.calls == []
    assert env.repo.tool_calls[-1].decision == "denied"


def test_mcp_settings_defaults():
    """R30: los valores por defecto dejan el MCP apagado y acotado."""
    settings = Settings(_env_file=None)
    assert settings.mcp_enabled is False
    assert settings.mcp_url == "http://mcp_lectura:8000/mcp"
    assert settings.mcp_timeout_seconds == 10
    assert settings.mcp_max_tool_steps == 3
    assert "DEMOSTRACIÓN" in settings.mcp_demo_notice
