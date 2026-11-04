"""Repositorio de credenciales, enlaces, sesiones, intentos y auditoría (#38, T7-T10)."""
from __future__ import annotations

import threading
from datetime import datetime, timedelta, timezone

import pytest

from orchestrator.accounts import hash_password_scrypt
from orchestrator.adapters.repository import FakeRepository, PostgresRepository, _INDEXES, _SCHEMA

NOW = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
PASSWORD_HASH = hash_password_scrypt("clave-segura-123", 16384)


def _credential(repo: FakeRepository, username: str = "cliente1"):
    return repo.create_client_credential(
        username, PASSWORD_HASH, NOW, NOW + timedelta(days=30), NOW
    )


def _contact(repo: FakeRepository, external_user_id: str):
    return repo.get_or_create_channel_contact(
        "telegram", external_user_id, f"chat-{external_user_id}", NOW
    )


# --- T7: esquema -----------------------------------------------------------------


def test_schema_has_identity_tables_and_partial_indexes():
    """R4, R27: tablas y los dos índices únicos parciales de sesión activa."""
    schema = " ".join(_SCHEMA)
    indexes = " ".join(_INDEXES)
    for table in (
        "client_credentials",
        "login_links",
        "client_sessions",
        "identity_login_attempts",
        "identity_audit",
    ):
        assert f"CREATE TABLE IF NOT EXISTS {table}" in schema
    assert "client_sessions_one_active_profile" in indexes
    assert "client_sessions_one_active_contact" in indexes
    assert "WHERE ended_at IS NULL" in indexes
    assert "token_hash TEXT PRIMARY KEY" in schema


# --- T8: credenciales ------------------------------------------------------------


def test_create_client_credential_creates_profile_and_credential():
    """R38: perfil `cliente` y credencial juntos, sin exponer el hash."""
    repo = FakeRepository()
    profile = _credential(repo)

    assert profile.role == "cliente" and profile.username == "cliente1"
    credential = repo.get_client_credential(profile.id)
    assert credential is not None
    assert credential.valid_from == NOW
    assert credential.valid_until == NOW + timedelta(days=30)
    assert credential.revoked_at is None


def test_renew_uses_given_date_and_rejects_revoked():
    """R39, R46: renovar actualiza vigencia; una revocada no cambia."""
    repo = FakeRepository()
    profile = _credential(repo)
    new_until = NOW + timedelta(days=60)
    assert repo.renew_client_credential(profile.id, new_until, NOW) is True
    assert repo.get_client_credential(profile.id).valid_until == new_until

    repo.revoke_client_credential(profile.id, NOW)
    assert repo.renew_client_credential(profile.id, new_until, NOW) is False
    assert repo.get_client_credential(profile.id).valid_until == new_until


# --- T9: enlaces y sesiones ------------------------------------------------------


def test_login_link_is_stored_by_hash_only_and_previous_link_invalidated():
    """R4, R5: solo el hash; emitir otro invalida el anterior."""
    repo = FakeRepository()
    contact = _contact(repo, "10")
    first_hash = "a" * 64
    second_hash = "b" * 64
    repo.add_login_link(
        first_hash, contact.id, "telegram", "chat-10", NOW, NOW + timedelta(minutes=15)
    )
    repo.add_login_link(
        second_hash, contact.id, "telegram", "chat-10", NOW, NOW + timedelta(minutes=15)
    )

    assert first_hash in repo.login_links and second_hash in repo.login_links
    assert repo.get_login_link(first_hash, NOW) is None
    assert repo.get_login_link(second_hash, NOW) is not None


def test_expired_link_is_not_returned():
    """R6: un enlace vencido no se devuelve."""
    repo = FakeRepository()
    contact = _contact(repo, "10")
    repo.add_login_link(
        "h1", contact.id, "telegram", "chat-10", NOW, NOW + timedelta(minutes=1)
    )
    assert repo.get_login_link("h1", NOW + timedelta(minutes=1)) is None


def test_start_session_consumes_link_once_and_reports_conflict():
    """R15, R27: un solo uso del token y una sola sesión activa por perfil/contacto."""
    repo = FakeRepository()
    first = _credential(repo, "cliente1")
    first_contact = _contact(repo, "10")
    second_contact = _contact(repo, "11")
    repo.add_login_link(
        "h1", first_contact.id, "telegram", "chat-10", NOW, NOW + timedelta(minutes=15)
    )
    repo.add_login_link(
        "h2", second_contact.id, "telegram", "chat-11", NOW, NOW + timedelta(minutes=15)
    )

    assert repo.start_client_session("h1", first.id, "s1", NOW) == "ok"
    assert repo.start_client_session("h1", first.id, "s2", NOW) == "invalid_link"
    assert repo.start_client_session("h2", first.id, "s3", NOW) == "conflict"
    assert repo.get_login_link("h2", NOW) is not None
    session = repo.get_active_session_by_profile(first.id)
    assert session is not None and session.contact_id == first_contact.id


def test_two_concurrent_sessions_only_one_wins():
    """R27: dos tokens del mismo perfil en hilos → un `ok` y un `conflict`."""
    repo = FakeRepository()
    profile = _credential(repo)
    one = _contact(repo, "10")
    two = _contact(repo, "11")
    repo.add_login_link("h1", one.id, "telegram", "chat-10", NOW, NOW + timedelta(minutes=15))
    repo.add_login_link("h2", two.id, "telegram", "chat-11", NOW, NOW + timedelta(minutes=15))
    barrier = threading.Barrier(2)
    results: dict[str, str] = {}

    def worker(token_hash: str, session_id: str) -> None:
        barrier.wait(timeout=5)
        results[token_hash] = repo.start_client_session(
            token_hash, profile.id, session_id, NOW
        )

    threads = [
        threading.Thread(target=worker, args=("h1", "s1")),
        threading.Thread(target=worker, args=("h2", "s2")),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=5)

    assert sorted(results.values()) == ["conflict", "ok"]
    unused = next(token for token, result in results.items() if result == "conflict")
    winner = next(token for token, result in results.items() if result == "ok")
    assert repo.get_login_link(unused, NOW) is not None
    assert repo.get_login_link(winner, NOW) is None


def test_touch_and_end_session():
    """R28, R30: se actualiza actividad y solo una vez se cierra."""
    repo = FakeRepository()
    profile = _credential(repo)
    contact = _contact(repo, "10")
    repo.add_login_link("h1", contact.id, "telegram", "chat-10", NOW, NOW + timedelta(minutes=15))
    assert repo.start_client_session("h1", profile.id, "s1", NOW) == "ok"

    later = NOW + timedelta(minutes=5)
    repo.touch_client_session("s1", later)
    assert repo.get_active_session_by_contact(contact.id).last_activity_at == later
    assert repo.end_client_session("s1", "logout", later) is True
    assert repo.end_client_session("s1", "logout", later) is False
    assert repo.get_active_session_by_contact(contact.id) is None


# --- T10: intentos, auditoría y overrides ----------------------------------------


def test_login_attempts_count_prune_and_clear():
    """R48: cuenta por usuario e IP dentro de la ventana y se borra al acierto."""
    repo = FakeRepository()
    repo.record_identity_login_failure("ana", "1.1.1.1", NOW, NOW - timedelta(minutes=15))
    repo.record_identity_login_failure("ana", "2.2.2.2", NOW, NOW - timedelta(minutes=15))
    repo.record_identity_login_failure("otra", "1.1.1.1", NOW, NOW - timedelta(minutes=15))
    repo.record_identity_login_failure(
        "ana", "1.1.1.1", NOW - timedelta(hours=2), NOW - timedelta(minutes=15)
    )

    assert repo.count_identity_login_failures(
        "ana", "1.1.1.1", NOW - timedelta(minutes=15)
    ) == (2, 2)

    repo.clear_identity_login_failures("ana")
    assert repo.count_identity_login_failures(
        "ana", "1.1.1.1", NOW - timedelta(minutes=15)
    ) == (0, 1)


def test_identity_audit_and_overrides():
    """R37, R49: auditoría con acción/motivo y claves `identity.*`."""
    repo = FakeRepository()
    repo.add_identity_audit("p1", "c1", "login", "vigente", NOW)
    assert repo.identity_audits[0].action == "login"
    assert repo.identity_audits[0].reason == "vigente"

    repo.identity_overrides["identity.link_ttl_minutes"] = "45"
    assert repo.get_identity_overrides() == {"identity.link_ttl_minutes": "45"}


def test_postgres_identity_sql_is_parameterized():
    """R4, R38: el SQL de Postgres usa parámetros y no concatena datos."""
    statements: list[tuple[str, tuple]] = []

    class Cursor:
        def execute(self, sql, params=()):
            statements.append((sql, tuple(params)))

        def fetchall(self):
            return []

    class Conn:
        def cursor(self):
            return Cursor()

        def commit(self):
            pass

        def rollback(self):
            pass

    repo = PostgresRepository(
        "postgresql://x", connect=lambda: Conn(), new_id=lambda: "p1"
    )
    repo.add_identity_audit("p1", "c1", "login", "vigente", NOW)
    repo.record_identity_login_failure(
        "ana", "1.1.1.1", NOW, NOW - timedelta(minutes=15)
    )
    repo.get_login_link("h1", NOW)

    joined = " ".join(sql for sql, _ in statements)
    assert "identity_audit" in joined
    assert "identity_login_attempts" in joined
    assert "login_links" in joined
    assert "%s" in joined
    assert "ana" not in joined


def test_postgres_start_session_only_maps_unique_violation_to_conflict():
    """R27: solo el 23505 es conflicto; otros errores de BD se propagan."""
    rollbacks: list[str] = []

    class Cursor:
        def __init__(self, error):
            self.error = error

        def execute(self, sql, params=()):
            if sql.startswith("WITH l AS"):
                raise self.error

        def fetchall(self):
            return []

    class Conn:
        def __init__(self, error):
            self.error = error

        def cursor(self):
            return Cursor(self.error)

        def commit(self):
            pass

        def rollback(self):
            rollbacks.append("rollback")

    class UniqueViolation(Exception):
        def __init__(self):
            super().__init__({"C": "23505", "M": "duplicate key value"})

    class ConnectionError(Exception):
        pass

    conflict_repo = PostgresRepository(
        "postgresql://x", connect=lambda: Conn(UniqueViolation()), new_id=lambda: "s1"
    )
    assert conflict_repo.start_client_session("h1", "p1", "s1", NOW) == "conflict"
    assert rollbacks == ["rollback"]

    failing_repo = PostgresRepository(
        "postgresql://x",
        connect=lambda: Conn(ConnectionError("connection lost")),
        new_id=lambda: "s2",
    )
    with pytest.raises(ConnectionError):
        failing_repo.start_client_session("h2", "p1", "s2", NOW)
    assert rollbacks == ["rollback", "rollback"]
