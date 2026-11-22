"""Reexporta las versiones falsas de los adaptadores para los tests."""
from __future__ import annotations

from datetime import datetime, timezone

from lazaro_contracts import ChannelCapabilities, ChannelInfo

from orchestrator.adapters.channels import FakeChannelDirectory
from orchestrator.adapters.client_data import FakeClientData
from orchestrator.adapters.db_query import FakeDbQuery
from orchestrator.adapters.gateway import FakeGatewayClient
from orchestrator.adapters.handover import FakeHandoverClient
from orchestrator.adapters.llm import FakeLLM, ScriptedLLM
from orchestrator.adapters.rag import FakeRagClient
from orchestrator.adapters.repository import FakeRepository
from orchestrator.config import Settings
from orchestrator.domain import Adapters
from orchestrator.queue import run_inbox_once, run_outbox_once


_CREATED = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _caps(windowed: bool) -> ChannelCapabilities:
    return ChannelCapabilities(
        free_text_allowed=not windowed,
        max_options=3,
        min_list_options=4,
        max_list_options=10,
        supports_links=True,
        requires_template=windowed,
    )


def channel_info(
    channel_id: str,
    *,
    name: str | None = None,
    windowed: bool = False,
    consent_mode: str | None = "texto",
    capabilities: ChannelCapabilities | None | str = "auto",
    active: bool = True,
    adapter_type: str | None = None,
    icon: str = "chat",
    color: str = "#1B6FA8",
    public: bool = False,
    contact_url: str = "",
) -> ChannelInfo:
    """`ChannelInfo` de prueba como lo publicaría `GET /channels` del gateway."""
    config: dict[str, object] = (
        {} if consent_mode is None else {"consent_mode": consent_mode}
    )
    if public:
        config["public"] = True
    if contact_url:
        config["contact_url"] = contact_url
    return ChannelInfo(
        id=channel_id,
        name=name or channel_id,
        adapter_type=adapter_type or channel_id,
        icon=icon,
        color=color,
        config=config,
        active=active,
        configured=True,
        has_secrets=False,
        managed_by_environment=False,
        created_at=_CREATED,
        capabilities=_caps(windowed) if capabilities == "auto" else capabilities,
    )


def default_channel_infos() -> tuple[ChannelInfo, ...]:
    """Único lugar con los canales de prueba (#65): telegram, whatsapp y simulado."""
    return (
        channel_info("telegram", name="Telegram", consent_mode="texto"),
        channel_info(
            "whatsapp",
            name="WhatsApp",
            windowed=True,
            consent_mode="boton",
            adapter_type="whatsapp_cloud",
        ),
        channel_info("simulado", name="Simulado", consent_mode="texto"),
    )


def drain_queues(
    settings: Settings, adapters: Adapters, max_steps: int = 10000
) -> None:
    """Procesa la cola de entrada y entrega la salida hasta vaciarla (#64)."""
    steps = 0
    while steps < max_steps and run_inbox_once(settings, adapters):
        steps += 1
    while steps < max_steps and run_outbox_once(settings, adapters):
        steps += 1


__all__ = [
    "FakeChannelDirectory",
    "channel_info",
    "default_channel_infos",
    "FakeClientData",
    "FakeDbQuery",
    "FakeGatewayClient",
    "FakeHandoverClient",
    "FakeLLM",
    "FakeRagClient",
    "FakeRepository",
    "ScriptedLLM",
    "drain_queues",
]
