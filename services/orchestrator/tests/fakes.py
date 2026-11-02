"""Reexporta las versiones falsas de los adaptadores para los tests."""
from orchestrator.adapters.db_query import FakeDbQuery
from orchestrator.adapters.gateway import FakeGatewayClient
from orchestrator.adapters.handover import FakeHandoverClient
from orchestrator.adapters.llm import FakeLLM
from orchestrator.adapters.rag import FakeRagClient
from orchestrator.adapters.repository import FakeRepository

__all__ = [
    "FakeDbQuery",
    "FakeGatewayClient",
    "FakeHandoverClient",
    "FakeLLM",
    "FakeRagClient",
    "FakeRepository",
]
