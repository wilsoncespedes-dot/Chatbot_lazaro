"""Fase 1: ningún servicio ni worker arranca con SERVICE_TOKEN vacío o de ejemplo."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from lazaro_contracts.production import InsecureServiceToken, require_service_token

NOW = datetime(2026, 1, 2, tzinfo=timezone.utc)


@pytest.mark.parametrize("token", ["", "   ", "cambia-esto", "CAMBIA-ESTO", None])
def test_insecure_tokens_are_rejected(token):
    with pytest.raises(InsecureServiceToken):
        require_service_token(token)


def test_real_token_is_accepted():
    require_service_token("k3Jx9-ufp2QwLm8vTz4RbNc7HyEa1Gd")


def _assert_refuses_to_start(app) -> None:
    with pytest.raises(InsecureServiceToken):
        with TestClient(app):
            pass


@pytest.mark.parametrize("token", ["", "cambia-esto"])
def test_rag_refuses_to_start(token):
    from rag.adapters.embeddings import FakeEmbeddings
    from rag.adapters.repository import FakeChunkRepository
    from rag.config import Settings
    from rag.main import create_app

    app = create_app(
        Settings(service_token=token), embeddings=FakeEmbeddings(), repository=FakeChunkRepository()
    )
    _assert_refuses_to_start(app)


@pytest.mark.parametrize("token", ["", "cambia-esto"])
def test_handover_refuses_to_start(token):
    from handover.adapters.gateway import FakeGatewayClient
    from handover.adapters.repository import FakeCaseRepository
    from handover.config import Settings
    from handover.domain import Adapters
    from handover.main import create_app

    adapters = Adapters(
        repository=FakeCaseRepository(), gateway=FakeGatewayClient(), clock=lambda: NOW
    )
    _assert_refuses_to_start(create_app(Settings(service_token=token), adapters))


@pytest.mark.parametrize("token", ["", "cambia-esto"])
def test_gateway_refuses_to_start(token):
    from telegram_gateway.adapters.dedup import FakeDedupStore
    from telegram_gateway.adapters.orchestrator import FakeOrchestratorClient
    from telegram_gateway.adapters.telegram import FakeTelegramClient
    from telegram_gateway.config import Settings
    from telegram_gateway.domain import Adapters
    from telegram_gateway.main import create_app

    adapters = Adapters(
        FakeTelegramClient(), FakeDedupStore(), FakeOrchestratorClient(), clock=lambda: NOW
    )
    _assert_refuses_to_start(create_app(Settings(service_token=token), adapters))


@pytest.mark.parametrize("token", ["", "cambia-esto"])
def test_orchestrator_refuses_to_start(token):
    from orchestrator.adapters.db_query import FakeDbQuery
    from orchestrator.adapters.gateway import FakeGatewayClient
    from orchestrator.adapters.handover import FakeHandoverClient
    from orchestrator.adapters.llm import FakeLLM
    from orchestrator.adapters.rag import FakeRagClient
    from orchestrator.adapters.repository import FakeRepository
    from orchestrator.config import Settings
    from orchestrator.domain import Adapters
    from orchestrator.main import create_app

    adapters = Adapters(
        repository=FakeRepository(), rag=FakeRagClient(results=[]), llm=FakeLLM(),
        gateway=FakeGatewayClient(), handover=FakeHandoverClient(), db_query=FakeDbQuery(),
        clock=lambda: NOW, new_id=lambda: "id-1",
    )
    _assert_refuses_to_start(create_app(Settings(service_token=token), adapters))


def test_orchestrator_workers_refuse_to_start(monkeypatch):
    from orchestrator import workers

    monkeypatch.setenv("SERVICE_TOKEN", "cambia-esto")
    with pytest.raises(InsecureServiceToken):
        workers.main(["procesar_entrantes", "--una-vez"])


def test_compose_has_no_default_postgres_password():
    from pathlib import Path

    compose = (Path(__file__).resolve().parents[2] / "docker-compose.yml").read_text(
        encoding="utf-8"
    )
    assert "POSTGRES_PASSWORD:-" not in compose
    assert "POSTGRES_PASSWORD:?" in compose
