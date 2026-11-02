"""Fixtures de handover: solo adaptadores falsos y reloj inyectado (sin red ni Postgres)."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from handover.adapters.gateway import FakeGatewayClient
from handover.adapters.repository import FakeCaseRepository
from handover.config import Settings
from handover.domain import Adapters, Case
from handover.main import create_app

SERVICE_TOKEN = "svc-token"
HEADERS = {"X-Service-Token": SERVICE_TOKEN}
START = datetime(2026, 1, 2, 3, 0, 0, tzinfo=timezone.utc)
ADVISORS = [111, 222, 333]
TIMEOUT_REPLY = "Sigue en espera"


@dataclass
class FakeClock:
    now: datetime = START

    def __call__(self) -> datetime:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now = self.now + timedelta(seconds=seconds)


@dataclass
class Env:
    client: TestClient
    repo: FakeCaseRepository
    gateway: FakeGatewayClient
    clock: FakeClock
    settings: Settings
    adapters: Adapters

    def handover(
        self,
        case_id: str = "case-1",
        contact_id: str = "contact-1",
        chat_id: int = 900,
        reason: str = "user_request",
        last_messages: list[dict] | None = None,
        headers: dict | None = None,
    ):
        body = {
            "case_id": case_id,
            "contact_id": contact_id,
            "chat_id": chat_id,
            "reason": reason,
            "last_messages": last_messages
            if last_messages is not None
            else [{"role": "user", "text": "quiero un asesor", "at": "2026-01-02T02:59:00Z"}],
        }
        return self.client.post(
            "/handover", json=body, headers=HEADERS if headers is None else headers
        )

    def add_case(self, case_id: str, status: str = "open", created_at: datetime | None = None,
                 chat_id: int = 900, contact_id: str | None = None, **extra) -> Case:
        case = Case(
            case_id=case_id,
            contact_id=contact_id or f"contact-{case_id}",
            chat_id=chat_id,
            reason="no_relevant_chunks",
            status=status,  # type: ignore[arg-type]
            last_messages=[],
            created_at=created_at or self.clock(),
            **extra,
        )
        self.repo.create_case(case)
        return case


def make_env(
    advisors: list[int] | None = None,
    repo: FakeCaseRepository | None = None,
    gateway: FakeGatewayClient | None = None,
    settings_overrides: dict | None = None,
) -> Env:
    ids = ADVISORS if advisors is None else advisors
    values = {
        "service_token": SERVICE_TOKEN,
        "advisor_chat_ids": ",".join(str(i) for i in ids),
        "handover_timeout_seconds": 300,
        "handover_timeout_reply": TIMEOUT_REPLY,
        "privacy_retention_days": "30",
        "privacy_active_case_max_days": "7",
    }
    values.update(settings_overrides or {})
    settings = Settings(**values)
    repo = repo or FakeCaseRepository()
    gateway = gateway or FakeGatewayClient()
    clock = FakeClock()
    adapters = Adapters(repository=repo, gateway=gateway, clock=clock)
    client = TestClient(create_app(settings, adapters))
    return Env(client, repo, gateway, clock, settings, adapters)


@pytest.fixture()
def env() -> Env:
    return make_env()


@pytest.fixture()
def env_factory():
    """Devuelve la fábrica para pruebas que necesitan ajustar asesores o repositorio."""
    return make_env


@pytest.fixture()
def env_no_advisors() -> Env:
    return make_env(advisors=[])
