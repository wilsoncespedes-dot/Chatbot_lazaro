"""Retención y purga de datos personales del orchestrator (#27)."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from orchestrator.adapters.repository import PostgresRepository
from orchestrator.classifier import Category

SERVICE_TOKEN = "svc-token"
HEADERS = {"X-Service-Token": SERVICE_TOKEN}
NOW = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
RETENTION_DAYS = 30
CUTOFF = NOW - timedelta(days=RETENTION_DAYS)


def _purge(env, headers: dict | None = HEADERS):
    return env.client.post("/privacy/purge", json={}, headers=headers)


def test_purge_requires_service_token(env):
    """R20: sin X-Service-Token válido responde 401 y no borra nada."""
    env.repo.add_message("c1", "user", "hola", NOW - timedelta(days=90))
    response = _purge(env, headers={})
    assert response.status_code == 401
    assert response.json()["error"] == "unauthorized"
    assert len(env.repo.messages) == 1


def test_purge_without_retention_days_returns_503_and_deletes_nothing(env_factory):
    """R21: sin PRIVACY_RETENTION_DAYS responde 503 sin borrar nada."""
    env = env_factory(privacy_retention_days="")
    env.repo.add_message("c1", "user", "hola", NOW - timedelta(days=90))
    response = _purge(env)
    assert response.status_code == 503
    assert response.json()["error"] == "privacy_not_configured"
    assert len(env.repo.messages) == 1


def test_messages_and_events_boundaries(env):
    """R22, R23: se borra antes del corte y se conserva en el corte o después."""
    env.repo.add_message("c1", "user", "antes", CUTOFF - timedelta(seconds=1))
    env.repo.add_message("c1", "user", "corte", CUTOFF)
    env.repo.add_message("c1", "user", "despues", CUTOFF + timedelta(seconds=1))
    env.repo.add_event("c1", "rag_answer", "antes", CUTOFF - timedelta(seconds=1))
    env.repo.add_event("c1", "rag_answer", "corte", CUTOFF)
    env.repo.add_event("c1", "rag_answer", "despues", CUTOFF + timedelta(seconds=1))

    response = _purge(env)
    assert response.status_code == 200
    assert [m.text for m in env.repo.messages] == ["corte", "despues"]
    assert [e.reason for e in env.repo.events] == ["corte", "despues"]
    assert response.json()["deleted"]["messages"] == 1
    assert response.json()["deleted"]["events"] == 1


def test_inactive_contact_is_deleted_with_case_links(env):
    """R24: un contacto inactivo se borra junto con sus case_links."""
    contact = env.repo.get_or_create_contact(10, 100, NOW)
    env.repo.contact_created_at[contact.id] = CUTOFF - timedelta(days=1)
    env.repo.add_message(contact.id, "user", "viejo", CUTOFF - timedelta(days=1))
    env.repo.case_links["case-1"] = contact.id
    env.repo.case_link_created_at["case-1"] = CUTOFF - timedelta(days=1)

    response = _purge(env)
    assert response.status_code == 200
    assert env.repo.contacts == {}
    assert env.repo.case_links == {}
    assert response.json()["deleted"]["contacts"] == 1
    assert response.json()["deleted"]["case_links"] == 1


def test_active_contacts_are_preserved(env):
    """R25: un contacto con mensaje o case_link reciente no se toca."""
    with_message = env.repo.get_or_create_contact(10, 100, NOW)
    env.repo.contact_created_at[with_message.id] = CUTOFF - timedelta(days=1)
    env.repo.add_message(with_message.id, "user", "reciente", CUTOFF)

    with_link = env.repo.get_or_create_contact(11, 101, NOW)
    env.repo.contact_created_at[with_link.id] = CUTOFF - timedelta(days=1)
    env.repo.case_links["case-2"] = with_link.id
    env.repo.case_link_created_at["case-2"] = CUTOFF

    old = env.repo.get_or_create_contact(12, 102, NOW)
    env.repo.contact_created_at[old.id] = CUTOFF - timedelta(days=1)

    _purge(env)
    assert set(env.repo.contacts) == {10, 11}
    assert env.repo.case_links == {"case-2": with_link.id}


def test_operational_tables_and_consents_are_preserved(env):
    """R26: profiles, tokens, sesiones, auditoría y privacy_consents no se tocan."""
    env.repo.create_profile("admin", "admin", "hash", NOW)
    env.repo.add_link_token("token", "p1", NOW)
    env.repo.create_session("session", "p1", "csrf", NOW)
    env.repo.record_login_failure("admin", "127.0.0.1", NOW, NOW)
    env.repo.mark_update_if_new(1)
    env.repo.create_category(
        Category(id="cat-1", code="pedidos", name="Pedidos", keywords=("pedido",), active=True),
        NOW,
    )
    env.repo.set_classifier_threshold(0.7)
    env.repo.add_db_query_audit("p1", 10, "ok", "consultas.v_pedidos", 1, "sha", NOW)
    env.repo.add_privacy_consent(10, "v1", "sha", NOW)

    contact = env.repo.get_or_create_contact(10, 100, NOW)
    env.repo.contact_created_at[contact.id] = CUTOFF - timedelta(days=1)
    env.repo.add_message(contact.id, "user", "viejo", CUTOFF - timedelta(days=1))

    _purge(env)
    assert list(env.repo.profiles) == ["p1"]
    assert list(env.repo.link_tokens) == ["token"]
    assert list(env.repo.sessions) == ["session"]
    assert len(env.repo.login_failures) == 1
    assert env.repo.processed == {1}
    assert list(env.repo.categories) == ["cat-1"]
    assert env.repo.classifier_threshold == 0.7
    assert len(env.repo.db_query_audits) == 1
    assert len(env.repo.privacy_consents) == 1


def test_response_and_purge_run_are_saved(env):
    """R27, R28: respuesta con closed_active_cases 0, fila guardada y segunda pasada a 0."""
    env.repo.add_message("c1", "user", "viejo", CUTOFF - timedelta(days=1))
    response = _purge(env)
    assert response.status_code == 200
    body = response.json()
    assert body["cutoff"].startswith("2025-12-03T03:04:05")
    assert body["closed_active_cases"] == 0
    assert body["deleted"]["messages"] == 1
    [run] = env.repo.privacy_purge_runs
    assert run["ran_at"] == NOW and run["cutoff"] == CUTOFF
    assert run["counts"]["messages"] == 1

    second = _purge(env)
    assert second.status_code == 200
    assert second.json()["deleted"] == {
        "messages": 0,
        "events": 0,
        "contacts": 0,
        "case_links": 0,
    }


class _Cursor:
    def __init__(self, log: list) -> None:
        self.log = log
        self.sql = ""

    def execute(self, sql, params=()):
        self.sql = sql
        self.log.append((sql, tuple(params)))

    def fetchall(self):
        if self.sql.startswith("SELECT id FROM contacts"):
            return [("c1",)]
        if self.sql.startswith("DELETE FROM case_links"):
            return [("case-1",)]
        if self.sql.startswith("DELETE FROM contacts"):
            return [("c1",)]
        if self.sql.startswith("DELETE FROM messages"):
            return [(1,), (2,)]
        if self.sql.startswith("DELETE FROM events"):
            return [(3,)]
        return []


class _Conn:
    def __init__(self) -> None:
        self.log: list = []
        self.commits = 0
        self.rollbacks = 0

    def cursor(self):
        return _Cursor(self.log)

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1


def test_postgres_purge_uses_the_documented_order_and_parameters():
    """R24, R26: calcula inactivos, borra enlaces y contactos, luego mensajes y eventos."""
    conn = _Conn()
    repo = PostgresRepository("postgresql://x", connect=lambda: conn, new_id=lambda: "n")
    counts = repo.purge_personal_data(CUTOFF, NOW)
    assert counts == {"messages": 2, "events": 1, "contacts": 1, "case_links": 1}
    assert conn.commits == 2 and conn.rollbacks == 0
    statements = [(sql, params) for sql, params in conn.log if not sql.startswith("CREATE")]
    starts = ["SELECT id FROM contacts", "DELETE FROM case_links", "DELETE FROM contacts",
              "DELETE FROM messages", "DELETE FROM events", "INSERT INTO privacy_purge_runs"]
    positions = [next(i for i, (sql, _) in enumerate(statements) if sql.startswith(start))
                 for start in starts]
    assert positions == sorted(positions)
    for sql, params in statements:
        assert "c1" not in sql and "case-1" not in sql
        assert sql.count("%s") == len(params)
    insert = statements[-1]
    assert json.loads(insert[1][2]) == counts
