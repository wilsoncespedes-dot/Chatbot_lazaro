"""Fixtures del orquestador: solo adaptadores falsos (sin red ni Postgres)."""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from lazaro_contracts import SearchResult

from orchestrator.adapters.db_query import FakeDbQuery
from orchestrator.adapters.gateway import FakeGatewayClient
from orchestrator.adapters.handover import FakeHandoverClient
from orchestrator.adapters.llm import FakeLLM
from orchestrator.adapters.rag import FakeRagClient
from orchestrator.adapters.repository import FakeRepository
from orchestrator.config import Settings
from orchestrator.domain import Adapters
from orchestrator.main import create_app
from orchestrator.privacy import notice_sha256

SERVICE_TOKEN = "svc-token"
FIXED_NOW = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
RECEIVED_AT = "2026-01-02T03:04:00+00:00"

PRIVACY_NOTICE_TEXT = (
    "Aviso de privacidad. Tratamos tus datos para atender tu consulta. "
    "Acepto el tratamiento de mis datos."
)
PRIVACY_NOTICE_VERSION = "v1"
PRIVACY_ACCEPT_PHRASE = "Acepto el tratamiento de mis datos."
PRIVACY_ACCEPTED_REPLY = "Gracias. Ya puedes escribirnos."
PRIVACY_RETENTION_DAYS = "30"


def llm_json(answer: str, chunk_id: str, quote: str) -> str:
    return json.dumps(
        {"answer": answer, "citations": [{"chunk_id": chunk_id, "quote": quote}]},
        ensure_ascii=False,
    )


def make_chunks(n: int = 2) -> list[SearchResult]:
    return [
        SearchResult(chunk_id=f"ch{i}", manual="Manual A", text=f"texto del fragmento {i}", score=0.9)
        for i in range(1, n + 1)
    ]


@dataclass
class Env:
    client: TestClient
    repo: FakeRepository
    rag: FakeRagClient
    llm: FakeLLM
    gateway: FakeGatewayClient
    handover: FakeHandoverClient
    db_query: FakeDbQuery
    settings: Settings
    adapters: Adapters

    def post(self, text: str = "¿Cómo instalo el módulo?", update_id: int = 1, user: int = 10,
             chat: int = 100, headers: dict | None = None, consent: bool = True,
             raise_server_exceptions: bool | None = None):
        if consent:
            self.repo.add_privacy_consent(
                user,
                self.settings.privacy_notice_version,
                notice_sha256(self.settings.privacy_notice_text),
                FIXED_NOW,
            )
        body = {
            "update_id": update_id,
            "telegram_user_id": user,
            "chat_id": chat,
            "text": text,
            "received_at": RECEIVED_AT,
        }
        client = self.client
        if raise_server_exceptions is not None:
            client = TestClient(
                self.client.app, raise_server_exceptions=raise_server_exceptions
            )
        return client.post(
            "/messages", json=body,
            headers={"X-Service-Token": SERVICE_TOKEN} if headers is None else headers,
        )

    def events(self) -> list[tuple[str, str]]:
        return [(e.type, e.reason) for e in self.repo.events]


def make_env(**settings_overrides) -> Env:
    values = {
        "service_token": SERVICE_TOKEN,
        "rag_top_k": 7,
        "privacy_notice_text": PRIVACY_NOTICE_TEXT,
        "privacy_notice_version": PRIVACY_NOTICE_VERSION,
        "privacy_accept_phrase": PRIVACY_ACCEPT_PHRASE,
        "privacy_accepted_reply": PRIVACY_ACCEPTED_REPLY,
        "privacy_retention_days": PRIVACY_RETENTION_DAYS,
    }
    values.update(settings_overrides)
    settings = Settings(**values)
    repo = FakeRepository()
    rag = FakeRagClient(results=make_chunks())
    llm = FakeLLM(reply=llm_json("Respuesta final", "ch1", "texto del fragmento 1"))
    gateway = FakeGatewayClient()
    handover = FakeHandoverClient()
    db_query = FakeDbQuery()
    counter = iter(range(1, 10_000))
    adapters = Adapters(
        repository=repo, rag=rag, llm=llm, gateway=gateway, handover=handover,
        db_query=db_query,
        clock=lambda: FIXED_NOW, new_id=lambda: f"case-{next(counter)}",
    )
    client = TestClient(create_app(settings, adapters))
    return Env(client, repo, rag, llm, gateway, handover, db_query, settings, adapters)


@pytest.fixture()
def env() -> Env:
    return make_env()


@pytest.fixture()
def env_factory():
    return make_env
