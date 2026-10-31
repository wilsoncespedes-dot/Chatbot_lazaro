"""Fixtures del gateway: solo adaptadores falsos (sin red ni Redis)."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from telegram_gateway.adapters.dedup import FakeDedupStore
from telegram_gateway.adapters.orchestrator import FakeOrchestratorClient
from telegram_gateway.adapters.telegram import FakeTelegramClient
from telegram_gateway.config import Settings
from telegram_gateway.domain import Adapters
from telegram_gateway.main import create_app

SERVICE_TOKEN = "svc-token"
WEBHOOK_SECRET = "hook-secret"
BOT_TOKEN = "123456:BOT-TOKEN-SECRETO"
FIXED_NOW = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)


@dataclass
class Env:
    client: TestClient
    telegram: FakeTelegramClient
    dedup: FakeDedupStore
    orchestrator: FakeOrchestratorClient
    settings: Settings


@pytest.fixture()
def env() -> Env:
    settings = Settings(
        service_token=SERVICE_TOKEN,
        telegram_webhook_secret=WEBHOOK_SECRET,
        telegram_bot_token=BOT_TOKEN,
        dedup_ttl_seconds=123,
    )
    telegram = FakeTelegramClient()
    dedup = FakeDedupStore()
    orchestrator = FakeOrchestratorClient()
    adapters = Adapters(telegram, dedup, orchestrator, clock=lambda: FIXED_NOW)
    client = TestClient(create_app(settings, adapters))
    return Env(client, telegram, dedup, orchestrator, settings)
