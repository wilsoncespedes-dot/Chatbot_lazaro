"""Suite de evaluación de ataques del harness (#39, R56, R57, R62)."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from lazaro_contracts import SearchResult

from orchestrator.adapters.client_data import FakeClientData
from orchestrator.adapters.llm import ScriptedLLM
from orchestrator.db_query import QueryResult
from orchestrator.domain import ConversationState

CASES = json.loads(
    (Path(__file__).parent / "data" / "harness_eval_cases.json").read_text(
        encoding="utf-8"
    )
)["cases"]
CATEGORIES = {
    "acceso_entre_clientes",
    "inyeccion",
    "herramienta_prohibida",
    "consentimiento",
    "fuentes_invalidas",
}
NOW = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
ALLOWLIST = '{"mis_datos.v_datos": ["cliente_id", "nombre"]}'


def _chunks() -> list[SearchResult]:
    return [
        SearchResult(
            chunk_id=f"ch{i}",
            manual="Manual A",
            text=f"texto del fragmento {i}",
            score=0.9,
        )
        for i in range(1, 3)
    ]


def _prepare(env, state: ConversationState, session: bool):
    contact = env.repo.get_or_create_contact(10, 100, env.adapters.clock())
    env.repo.set_conversation_state(contact.id, state, NOW)
    profile = None
    if session:
        profile = env.repo.create_client_credential(
            "clienteA",
            "hash",
            NOW - timedelta(days=1),
            NOW + timedelta(days=30),
            NOW,
        )
        env.repo.add_login_link(
            "token-a",
            contact.id,
            "telegram",
            "100",
            NOW,
            NOW + timedelta(minutes=15),
        )
        assert (
            env.repo.start_client_session("token-a", profile.id, "session-a", NOW)
            == "ok"
        )
    return contact, profile


@pytest.mark.parametrize("case", CASES, ids=lambda case: case["name"])
def test_r56_r62_attack_cases(env_factory, case):
    """R56, R62: cada caso afirma respuesta, herramienta/decisión y adaptadores."""
    env = env_factory(harness_router_enabled=case["router_enabled"])
    if case["client_data_enabled"]:
        env.settings.client_data_enabled = True
        env.settings.client_data_allowlist = ALLOWLIST
        env.settings.client_data_views_schema = "mis_datos"
    contact, profile = _prepare(
        env, ConversationState(case["state"]), case["session"]
    )
    fake = FakeClientData()
    if profile is not None and case.get("client_rows") is not None:
        rows = [tuple(row) for row in case["client_rows"]]
        fake = FakeClientData(
            {
                profile.id: QueryResult(
                    columns=["nombre"], rows=rows, truncated=False
                )
            }
        )
    env.adapters.client_data = fake
    env.adapters.llm = ScriptedLLM(case["llm_replies"])
    env.rag.results = _chunks() if case["rag_results"] == "chunks" else []

    env.post(
        text=case["text"],
        update_id=1,
        user=10,
        chat=100,
        consent=case["consent"],
    )

    expect = case["expect"]
    if expect.get("no_tool_rows"):
        assert env.repo.tool_calls == []
        assert env.repo.suppression_requests == {}
        assert env.gateway.sent or env.gateway.channel_sent
    if expect.get("reply_key"):
        assert env.gateway.sent[-1][1] == getattr(env.settings, expect["reply_key"])
    if expect.get("reply_contains"):
        assert expect["reply_contains"] in env.gateway.sent[-1][1]
    if expect.get("reply_excludes"):
        assert expect["reply_excludes"] not in env.gateway.sent[-1][1]
    if not any(
        key in expect for key in ("reply_key", "reply_contains", "no_tool_rows")
    ):
        assert env.gateway.sent or env.gateway.channel_sent
    if expect.get("event"):
        assert tuple(expect["event"]) in env.events()
    if expect.get("tool") or expect.get("decision"):
        matches = [
            call
            for call in env.repo.tool_calls
            if (expect.get("tool") is None or call.tool == expect["tool"])
            and (
                expect.get("decision") is None
                or call.decision == expect["decision"]
            )
            and (
                expect.get("result") is None or call.result == expect["result"]
            )
        ]
        assert matches, env.repo.tool_calls
    assert bool(env.rag.calls) is expect.get("rag_called", False)
    if "llm_called" in expect:
        assert bool(env.adapters.llm.calls) is expect["llm_called"]
    assert bool(fake.calls) is expect.get("client_data_called", False)
    assert bool(env.handover.requests) is expect.get("handover_called", False)


def test_r56_at_least_two_cases_per_category():
    """R56: la suite sin red cubre al menos dos casos por categoría."""
    assert {case["category"] for case in CASES} == CATEGORIES
    for category in CATEGORIES:
        assert sum(1 for case in CASES if case["category"] == category) >= 2
