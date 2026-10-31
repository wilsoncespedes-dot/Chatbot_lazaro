"""Reexporta las versiones falsas de los adaptadores para los tests."""
from handover.adapters.gateway import FakeGatewayClient
from handover.adapters.repository import FakeCaseRepository

__all__ = ["FakeCaseRepository", "FakeGatewayClient"]
