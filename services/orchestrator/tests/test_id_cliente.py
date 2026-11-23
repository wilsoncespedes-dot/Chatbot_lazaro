"""ID público de cliente: formato, generación, unicidad, backfill y supresión (#73)."""
from __future__ import annotations

import inspect
from datetime import datetime, timedelta, timezone

import pytest

import orchestrator.client_id as client_id_module
import orchestrator.domain as domain_module
from orchestrator.client_id import (
    ALPHABET,
    PublicIdGenerationError,
    PublicIdTaken,
    generate_public_id,
    normalize_public_id,
)
from orchestrator.domain import (
    ClientSession,
    create_client,
    renew_credential,
    revoke_credential,
)

from migrations import section

_SCHEMA = section("orchestrator: tablas")
_INDEXES = section("orchestrator: índices")
_MIGRATIONS = section("orchestrator: migraciones aditivas previas")

NOW = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
PASSWORD = "clave-segura-123"


def _env(env_factory):
    return env_factory(password_scrypt_n=16384)


def _client(env, username: str = "cliente1"):
    return create_client(
        username,
        PASSWORD,
        NOW - timedelta(days=1),
        NOW + timedelta(days=30),
        env.settings,
        env.adapters,
    )


def _stored(env, username: str):
    return next(
        profile for profile in env.repo.profiles.values() if profile.username == username
    )


def test_generate_public_id_format_and_alphabet():
    """R1: ocho caracteres del alfabeto y formato `XXXX-XXXX`."""
    for _ in range(50):
        value = generate_public_id()
        assert len(value) == 9 and value[4] == "-"
        assert set(value.replace("-", "")) <= set(ALPHABET)
        assert normalize_public_id(value) == value


def test_generate_public_id_uses_secrets_and_takes_no_arguments(monkeypatch):
    """R2: sin datos del cliente y usando `secrets.choice`."""
    assert inspect.signature(generate_public_id).parameters == {}
    calls: list[str] = []

    def choice(alphabet: str) -> str:
        calls.append(alphabet)
        return alphabet[0]

    monkeypatch.setattr(client_id_module.secrets, "choice", choice)
    assert generate_public_id() == "2222-2222"
    assert calls == [ALPHABET] * 8


def test_normalize_public_id_is_tolerant_but_rejects_ambiguous_characters():
    """R21, R22: espacios y guiones se ignoran; `0`/`O` no son válidos."""
    assert normalize_public_id("ab3k-7mnp") == "AB3K-7MNP"
    assert normalize_public_id(" AB3K 7MNP ") == "AB3K-7MNP"
    assert normalize_public_id("AB3K7MNP") == "AB3K-7MNP"
    assert normalize_public_id("AB0K-7MNP") is None
    assert normalize_public_id("corto") is None


def test_create_client_stores_public_id_and_schema_has_unique_index(env_factory):
    """R3: el ID se guarda en `profiles.public_id` con índice único."""
    env = _env(env_factory)
    status = _client(env)

    stored = _stored(env, "cliente1")
    assert status.public_id == stored.public_id
    assert normalize_public_id(stored.public_id or "") == stored.public_id
    assert "ALTER TABLE profiles ADD COLUMN IF NOT EXISTS public_id TEXT" in _MIGRATIONS
    assert "profiles_public_id_key" in " ".join(_MIGRATIONS)


def test_create_client_retries_when_public_id_is_taken(env_factory, monkeypatch):
    """R4: un ID existente se reintenta hasta encontrar uno libre."""
    env = _env(env_factory)
    env.repo.create_client_credential(
        "otro",
        "hash",
        NOW - timedelta(days=1),
        NOW + timedelta(days=30),
        NOW,
        public_id="AAAA-AAAA",
    )
    sequence = iter(["AAAA-AAAA", "AAAA-AAAA", "BBBB-BBBB"])
    monkeypatch.setattr(domain_module, "generate_public_id", lambda: next(sequence))

    status = _client(env, "cliente1")

    assert status.public_id == "BBBB-BBBB"
    assert _stored(env, "cliente1").public_id == "BBBB-BBBB"


def test_create_client_raises_after_five_collisions(env_factory, monkeypatch):
    """R5: agotar los cinco intentos no crea perfil ni credencial."""
    env = _env(env_factory)
    env.repo.create_client_credential(
        "otro",
        "hash",
        NOW - timedelta(days=1),
        NOW + timedelta(days=30),
        NOW,
        public_id="AAAA-AAAA",
    )
    monkeypatch.setattr(
        domain_module, "generate_public_id", lambda: "AAAA-AAAA"
    )

    with pytest.raises(PublicIdGenerationError):
        _client(env, "cliente1")

    assert not [p for p in env.repo.profiles.values() if p.username == "cliente1"]
    assert len(env.repo.client_credentials) == 1


def test_renew_revoke_and_close_session_keep_the_same_public_id(env_factory):
    """R6: renovar, revocar y cerrar sesión no cambian el ID."""
    env = _env(env_factory)
    status = _client(env)
    public_id = status.public_id

    renew_credential(status.profile_id, env.settings, env.adapters)
    revoke_credential(status.profile_id, env.settings, env.adapters)
    env.repo.client_sessions["s1"] = ClientSession(
        id="s1",
        profile_id=status.profile_id,
        contact_id="c1",
        started_at=NOW,
        last_activity_at=NOW,
    )
    env.repo.end_client_session("s1", "logout", NOW)

    assert env.repo.get_profile(status.profile_id).public_id == public_id


def test_ensure_public_ids_backfills_without_changing_existing_ids(env_factory):
    """R7: rellena clientes sin ID y es idempotente."""
    env = _env(env_factory)
    status = _client(env)
    stored = _stored(env, "cliente1")
    original = stored.public_id
    stored.public_id = None

    assert env.repo.ensure_public_ids(generate_public_id) == 1
    assert stored.public_id is not None and stored.public_id != original
    assert env.repo.ensure_public_ids(generate_public_id) == 0
    assert stored.public_id == env.repo.get_profile(status.profile_id).public_id


def test_suppression_removes_the_public_id(env_factory):
    """R8: tras la supresión el ID ya no identifica al cliente."""
    env = _env(env_factory)
    status = _client(env)
    contact = env.repo.get_or_create_channel_contact("telegram", "10", "100", NOW)
    env.repo.client_sessions["s1"] = ClientSession(
        id="s1",
        profile_id=status.profile_id,
        contact_id=contact.id,
        started_at=NOW - timedelta(minutes=10),
        last_activity_at=NOW - timedelta(minutes=1),
        ended_at=NOW,
    )
    request_id, created = env.repo.create_or_get_pending_suppression(
        "req-1", status.profile_id, contact.id, "telegram", NOW
    )
    assert created

    env.repo.execute_suppression(request_id, "admin-1", 60, NOW)

    assert env.repo.get_profile(status.profile_id).public_id is None
    assert env.repo.find_client_by_public_id(status.public_id or "") is None


def test_repository_rejects_a_repeated_public_id(env_factory):
    """R3, R4: el repositorio señala la colisión para que el dominio reintente."""
    env = _env(env_factory)
    _client(env)
    first = _stored(env, "cliente1").public_id
    with pytest.raises(PublicIdTaken):
        env.repo.create_client_credential(
            "cliente2",
            "hash",
            NOW - timedelta(days=1),
            NOW + timedelta(days=30),
            NOW,
            public_id=first,
        )
