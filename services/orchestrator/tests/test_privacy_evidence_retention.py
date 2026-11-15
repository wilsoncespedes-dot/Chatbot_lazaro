"""Retención y supresión de la evidencia de consentimiento (#57)."""
from __future__ import annotations

import base64
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from orchestrator.adapters.repository import (
    FakeRepository,
    PostgresRepository,
    PrivacyConsent,
)
from orchestrator.config import Settings
from orchestrator.domain import (
    ClientSession,
    execute_suppression,
    purge_personal_data,
)
from orchestrator.privacy import notice_sha256

NOW = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
CUTOFF = NOW - timedelta(days=30)
ROOT = Path(__file__).resolve().parents[3]


def _profile(env, username: str, role: str = "cliente") -> str:
    if role == "cliente":
        return env.repo.create_client_credential(
            username, "hash", NOW - timedelta(days=1), NOW + timedelta(days=30), NOW
        ).id
    return env.repo.create_profile(username, role, "hash", NOW).id


def _session(env, profile_id: str, contact) -> ClientSession:
    session = ClientSession(
        id=f"session-{profile_id}-{contact.id}",
        profile_id=profile_id,
        contact_id=contact.id,
        started_at=NOW - timedelta(minutes=10),
        last_activity_at=NOW - timedelta(minutes=1),
        ended_at=NOW,
    )
    env.repo.client_sessions[session.id] = session
    return session


def _request(env, profile_id: str, contact_id: str, request_id: str = "req-1"):
    created_id, created = env.repo.create_or_get_pending_suppression(
        request_id, profile_id, contact_id, "telegram", NOW
    )
    assert created
    return env.repo.suppression_requests[created_id]


def _consent(
    repo: FakeRepository,
    channel: str,
    external_user_id: str,
    at: datetime,
    result: str = "accepted",
    version: str = "1.0",
) -> None:
    repo.add_privacy_decision(
        channel,
        external_user_id,
        version,
        "sha",
        result,
        f"m-{channel}-{external_user_id}-{at.isoformat()}",
        "",
        at,
        evidence_type="text",
    )


class _ScenarioCursor:
    def __init__(self, events: list, rows: list, fail_on: str | None = None) -> None:
        self.events = events
        self.rows = rows
        self.fail_on = fail_on
        self.sql = ""

    def execute(self, sql, params=()):
        if self.fail_on and sql.startswith(self.fail_on):
            raise RuntimeError("fallo simulado")
        self.sql = sql
        self.events.append(("sql", sql, tuple(params)))

    def fetchall(self):
        for prefix, result in self.rows:
            if self.sql.startswith(prefix):
                return result
        return []


class _ScenarioConn:
    def __init__(self, rows=None, fail_on: str | None = None) -> None:
        self.events: list = []
        self.commits = 0
        self.rollbacks = 0
        self._cursor = _ScenarioCursor(self.events, rows or [], fail_on)

    def cursor(self):
        return self._cursor

    def commit(self):
        self.commits += 1
        self.events.append(("commit",))

    def rollback(self):
        self.rollbacks += 1
        self.events.append(("rollback",))


def _suppression_rows() -> list:
    return [
        ("SELECT profile_id FROM suppression_requests", [("p1",)]),
        (
            "SELECT contact_id, started_at, last_activity_at, ended_at",
            [
                ("c1", NOW - timedelta(minutes=10), NOW - timedelta(minutes=1), NOW),
                ("c2", NOW - timedelta(minutes=10), NOW - timedelta(minutes=1), NOW),
            ],
        ),
        ("DELETE FROM messages", [("m1",)]),
        ("DELETE FROM conversation_summaries", [("s1",)]),
        ("DELETE FROM client_memory", [("p1",)]),
        ("DELETE FROM privacy_consents", [("pc1",), ("pc2",)]),
    ]


def _purge_rows() -> list:
    return [
        ("SELECT id FROM contacts", [("c1",)]),
        ("DELETE FROM contacts", [("c1",)]),
        ("DELETE FROM messages", [("m1",)]),
        ("DELETE FROM events", [("e1",)]),
        ("DELETE FROM privacy_consents", [("pc1",)]),
    ]


# --- Supresión -------------------------------------------------------------------


def test_suppression_deletes_consents_of_all_session_identities(env_factory):
    """R11, R12: borra la evidencia de Telegram y WhatsApp del mismo perfil."""
    env = env_factory()
    client = _profile(env, "cliente1")
    admin = _profile(env, "admin1", "admin")
    telegram = env.repo.get_or_create_channel_contact("telegram", "10", "100", NOW)
    whatsapp = env.repo.get_or_create_channel_contact("whatsapp", "57300", "57301", NOW)
    _session(env, client, telegram)
    _session(env, client, whatsapp)
    _consent(env.repo, "telegram", "10", NOW - timedelta(days=1), "accepted", "1.0")
    _consent(env.repo, "telegram", "10", NOW - timedelta(days=2), "rejected", "0.9")
    _consent(env.repo, "whatsapp", "57300", NOW - timedelta(days=1), "accepted", "1.0")
    _request(env, client, telegram.id)

    execution = execute_suppression("req-1", admin, env.settings, env.adapters)

    assert execution.deleted["privacy_consents"] == 3
    assert env.repo.privacy_consents == []


def test_suppression_keeps_other_clients_consents(env_factory):
    """R13: la evidencia de una identidad ajena a las sesiones no se borra."""
    env = env_factory()
    client = _profile(env, "cliente1")
    admin = _profile(env, "admin1", "admin")
    target = env.repo.get_or_create_channel_contact("telegram", "10", "100", NOW)
    other = env.repo.get_or_create_channel_contact("telegram", "11", "101", NOW)
    _session(env, client, target)
    _consent(env.repo, "telegram", "10", NOW - timedelta(days=1))
    _consent(env.repo, "telegram", "11", NOW - timedelta(days=1))
    _request(env, client, target.id)

    execution = execute_suppression("req-1", admin, env.settings, env.adapters)

    assert execution.deleted["privacy_consents"] == 1
    assert [(c.channel, c.external_user_id) for c in env.repo.privacy_consents] == [
        ("telegram", "11")
    ]
    assert other.id in {contact.id for contact in env.repo.contacts.values()}


@pytest.mark.parametrize("with_evidence", [True, False])
def test_suppression_removed_counts_include_privacy_consents(
    env_factory, with_evidence
):
    """R14: removed_counts siempre informa la clave, con 0 si no había evidencia."""
    env = env_factory()
    client = _profile(env, "cliente1")
    admin = _profile(env, "admin1", "admin")
    contact = env.repo.get_or_create_channel_contact("telegram", "10", "100", NOW)
    _session(env, client, contact)
    if with_evidence:
        _consent(env.repo, "telegram", "10", NOW - timedelta(days=1))
        _consent(env.repo, "telegram", "10", NOW - timedelta(days=2), "rejected", "0.9")
    request = _request(env, client, contact.id)

    execution = execute_suppression("req-1", admin, env.settings, env.adapters)

    expected = 2 if with_evidence else 0
    assert execution.deleted["privacy_consents"] == expected
    assert request.removed_counts["privacy_consents"] == expected


def test_suppression_failure_in_consent_delete_rolls_back(env_factory):
    """R16: un fallo al borrar evidencia no deja estado parcial."""
    env = env_factory()
    client = _profile(env, "cliente1")
    admin = _profile(env, "admin1", "admin")
    contact = env.repo.get_or_create_channel_contact("telegram", "10", "100", NOW)
    _session(env, client, contact)
    env.repo.add_message(contact.id, "user", "hola", NOW - timedelta(minutes=5))
    env.repo.set_client_memory(client, ("Memoria",), "s1", NOW)
    _consent(env.repo, "telegram", "10", NOW - timedelta(days=1))
    request = _request(env, client, contact.id)
    env.repo.fail_privacy_consent_delete = True

    with pytest.raises(RuntimeError):
        execute_suppression("req-1", admin, env.settings, env.adapters)

    assert request.status == "pending"
    assert request.removed_counts is None
    assert [message.text for message in env.repo.messages] == ["hola"]
    assert client in env.repo.client_memory
    assert len(env.repo.privacy_consents) == 1


def test_postgres_suppression_single_transaction_parametrized():
    """R15, R16: DELETE parametrizado y un solo commit tras marcar la solicitud."""
    conn = _ScenarioConn(_suppression_rows())
    repo = PostgresRepository("postgresql://x", connect=lambda: conn, new_id=lambda: "n")

    counts = repo.execute_suppression("req-1", "admin-1", 60, NOW)

    assert counts["privacy_consents"] == 2
    statements = [
        (index, event[1], event[2])
        for index, event in enumerate(conn.events)
        if event[0] == "sql"
    ]
    consent = [item for item in statements if item[1].startswith(
        "DELETE FROM privacy_consents"
    )]
    assert len(consent) == 1
    _index, sql, params = consent[0]
    assert "ANY(%s)" in sql
    assert "10" not in sql
    assert sql.count("%s") == len(params)
    update_index = next(
        index
        for index, sql, _params in statements
        if sql.startswith("UPDATE suppression_requests")
    )
    commits_after = [
        index
        for index, event in enumerate(conn.events)
        if event[0] == "commit" and index > update_index
    ]
    assert len(commits_after) == 1


def test_postgres_suppression_rolls_back_when_consent_delete_fails():
    """R16: si falla el DELETE de evidencia, no hay commit y sí rollback."""
    conn = _ScenarioConn(
        _suppression_rows(), fail_on="DELETE FROM privacy_consents"
    )
    repo = PostgresRepository("postgresql://x", connect=lambda: conn, new_id=lambda: "n")

    with pytest.raises(RuntimeError):
        repo.execute_suppression("req-1", "admin-1", 60, NOW)

    assert conn.rollbacks == 1
    assert not any(
        event[0] == "sql" and event[1].startswith("UPDATE suppression_requests")
        for event in conn.events
    )


def test_client_asked_for_notice_after_suppression(env_factory):
    """R17: tras suprimir, el mismo remitente vuelve a ver el aviso y no se procesa."""
    env = env_factory()
    client = _profile(env, "cliente1")
    admin = _profile(env, "admin1", "admin")
    contact = env.repo.get_or_create_channel_contact("telegram", "10", "100", NOW)
    _session(env, client, contact)
    env.repo.add_privacy_consent(
        10,
        env.settings.privacy_notice_version,
        notice_sha256(env.settings.privacy_notice_text),
        NOW,
    )
    _request(env, client, contact.id)

    execute_suppression("req-1", admin, env.settings, env.adapters)
    assert env.repo.privacy_consents == []

    response = env.post(
        text="¿Cómo instalo el módulo?",
        update_id=2,
        user=10,
        chat=100,
        consent=False,
    )

    assert response.status_code == 202
    notices = [
        text
        for _channel, _destination, text in env.gateway.channel_sent
        if env.settings.privacy_notice_text in text
    ]
    assert notices
    assert env.repo.messages == []
    assert env.rag.calls == []


# --- Purga automática ------------------------------------------------------------


def test_purge_deletes_consents_older_than_cutoff_by_occurred_at(env_factory):
    """R18, R21, R22: borra por fecha de la evidencia, activo o inactivo, y usa accepted_at."""
    env = env_factory()
    active = env.repo.get_or_create_contact(10, 100, NOW)
    env.repo.add_message(active.id, "user", "reciente", NOW)
    inactive = env.repo.get_or_create_contact(11, 101, NOW)
    env.repo.contact_created_at[inactive.id] = CUTOFF - timedelta(days=1)
    _consent(env.repo, "telegram", "10", CUTOFF - timedelta(seconds=1))
    _consent(env.repo, "telegram", "11", CUTOFF - timedelta(days=2))
    env.repo.privacy_consents.append(
        PrivacyConsent(
            notice_version="v0",
            notice_sha256="sha",
            accepted_at=CUTOFF - timedelta(days=3),
            channel="telegram",
            external_user_id="12",
            occurred_at=None,
        )
    )

    response = purge_personal_data(env.settings, env.adapters)

    assert response.deleted["privacy_consents"] == 3
    assert env.repo.privacy_consents == []


def test_purge_keeps_consent_at_cutoff(env_factory):
    """R19: la evidencia justo en el corte se conserva; un segundo antes se borra."""
    env = env_factory()
    _consent(env.repo, "telegram", "10", CUTOFF)
    _consent(env.repo, "telegram", "11", CUTOFF - timedelta(seconds=1))

    response = purge_personal_data(env.settings, env.adapters)

    assert response.deleted["privacy_consents"] == 1
    assert [(c.external_user_id, c.occurred_at) for c in env.repo.privacy_consents] == [
        ("10", CUTOFF)
    ]


def test_purge_counts_include_privacy_consents(env_factory):
    """R20: el recuento aparece en la respuesta y en privacy_purge_runs."""
    env = env_factory()
    _consent(env.repo, "telegram", "10", CUTOFF - timedelta(seconds=1))
    _consent(env.repo, "telegram", "11", CUTOFF)

    response = purge_personal_data(env.settings, env.adapters)

    assert response.deleted["privacy_consents"] == 1
    assert env.repo.privacy_purge_runs[-1]["counts"]["privacy_consents"] == 1


def test_postgres_purge_deletes_consents_in_same_transaction():
    """R18, R20: el DELETE por antigüedad va antes del INSERT de la ejecución."""
    conn = _ScenarioConn(_purge_rows())
    repo = PostgresRepository("postgresql://x", connect=lambda: conn, new_id=lambda: "n")

    counts = repo.purge_personal_data(CUTOFF, NOW)

    assert counts["privacy_consents"] == 1
    statements = [
        (index, event[1], event[2])
        for index, event in enumerate(conn.events)
        if event[0] == "sql"
    ]
    consent = [item for item in statements if item[1].startswith(
        "DELETE FROM privacy_consents"
    )]
    assert len(consent) == 1
    consent_index, sql, params = consent[0]
    assert "COALESCE(occurred_at, accepted_at) < %s" in sql
    assert params == (CUTOFF,)
    insert_index = next(
        index
        for index, statement, _params in statements
        if statement.startswith("INSERT INTO privacy_purge_runs")
    )
    assert consent_index < insert_index
    assert conn.commits == 2 and conn.rollbacks == 0


# --- Paridad ---------------------------------------------------------------------


def _fake_suppression_counts() -> dict[str, int]:
    repo = FakeRepository()
    repo.create_or_get_pending_suppression("req-1", "p1", "c1", "telegram", NOW)
    telegram = repo.get_or_create_channel_contact("telegram", "10", "100", NOW)
    whatsapp = repo.get_or_create_channel_contact("whatsapp", "57300", "57301", NOW)
    for contact in (telegram, whatsapp):
        repo.client_sessions[f"s-{contact.id}"] = ClientSession(
            id=f"s-{contact.id}",
            profile_id="p1",
            contact_id=contact.id,
            started_at=NOW - timedelta(minutes=10),
            last_activity_at=NOW - timedelta(minutes=1),
            ended_at=NOW,
        )
        repo.add_message(contact.id, "user", "mensaje", NOW - timedelta(minutes=2))
    repo.upsert_conversation_summary(
        "s-c1", "p1", telegram.id, "telegram", "Resumen", "session_end", NOW
    )
    repo.set_client_memory("p1", ("Memoria",), "s-c1", NOW)
    _consent(repo, "telegram", "10", NOW - timedelta(days=1))
    _consent(repo, "whatsapp", "57300", NOW - timedelta(days=1))
    return repo.execute_suppression("req-1", "admin-1", 60, NOW) or {}


def _fake_purge_counts() -> dict[str, int]:
    repo = FakeRepository()
    contact = repo.get_or_create_contact(10, 100, NOW)
    repo.contact_created_at[contact.id] = CUTOFF - timedelta(days=1)
    repo.add_message(contact.id, "user", "viejo", CUTOFF - timedelta(seconds=1))
    repo.add_event(contact.id, "rag_answer", "viejo", CUTOFF - timedelta(seconds=1))
    _consent(repo, "telegram", "10", CUTOFF - timedelta(seconds=1))
    _consent(repo, "telegram", "10", CUTOFF)
    return repo.purge_personal_data(CUTOFF, NOW)


@pytest.mark.parametrize("kind", ["suppression", "purge"])
def test_repositories_same_counts_for_suppression_and_purge(kind):
    """R23: Fake y Postgres simulado producen los mismos conteos."""
    if kind == "suppression":
        fake_counts = _fake_suppression_counts()
        conn = _ScenarioConn(_suppression_rows())
        repo = PostgresRepository(
            "postgresql://x", connect=lambda: conn, new_id=lambda: "n"
        )
        postgres_counts = repo.execute_suppression("req-1", "admin-1", 60, NOW)
    else:
        fake_counts = _fake_purge_counts()
        conn = _ScenarioConn(_purge_rows())
        repo = PostgresRepository(
            "postgresql://x", connect=lambda: conn, new_id=lambda: "n"
        )
        postgres_counts = repo.purge_personal_data(CUTOFF, NOW)

    assert postgres_counts == fake_counts


# --- Configuración aprobada ------------------------------------------------------


def _env_example() -> dict[str, str]:
    values: dict[str, str] = {}
    for line in (ROOT / ".env.example").read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def test_approved_values_pass_production_validation():
    """R7: los valores de .env.example validan al construir Settings en producción."""
    env = _env_example()
    settings = Settings(
        app_env="production",
        service_token="s" * 40,
        database_url="postgresql://app:clave@db:5432/lazaro",
        rag_url="rag:8000",
        handover_url="handover:8000",
        telegram_gateway_url="telegram-gateway:8000",
        llm_api_key="clave-real",
        llm_model="modelo-barato",
        privacy_notice_text=env["PRIVACY_NOTICE_TEXT"],
        privacy_notice_version=env["PRIVACY_NOTICE_VERSION"],
        privacy_accept_phrase=env["PRIVACY_ACCEPT_PHRASE"],
        privacy_reject_phrase=env["PRIVACY_REJECT_PHRASE"],
        privacy_accepted_reply=env["PRIVACY_ACCEPTED_REPLY"],
        privacy_retention_days=env["PRIVACY_RETENTION_DAYS"],
        identity_public_base_url="https://orchestrator.example",
        identity_link_signing_key="k" * 32,
        identity_login_required=True,
        panel_2fa_encryption_key=base64.urlsafe_b64encode(b"k" * 32).decode("ascii"),
    )

    assert settings.retention_days == 30
    assert settings.privacy_notice_version == "1.0"
    assert settings.consent_accept_phrase == "ACEPTO"
    assert settings.consent_reject_phrase == "NO ACEPTO"
