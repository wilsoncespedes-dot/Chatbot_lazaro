"""Reexporta las versiones falsas de los adaptadores para los tests."""
from __future__ import annotations

from orchestrator.adapters.client_data import FakeClientData
from orchestrator.adapters.db_query import FakeDbQuery
from orchestrator.adapters.gateway import FakeGatewayClient
from orchestrator.adapters.handover import FakeHandoverClient
from orchestrator.adapters.llm import FakeLLM, ScriptedLLM
from orchestrator.adapters.rag import FakeRagClient
from orchestrator.adapters.repository import FakeRepository


__all__ = [
    "FakeClientData",
    "FakeDbQuery",
    "FakeGatewayClient",
    "FakeHandoverClient",
    "FakeLLM",
    "FakeRagClient",
    "FakeRepository",
    "ScriptedLLM",
]
