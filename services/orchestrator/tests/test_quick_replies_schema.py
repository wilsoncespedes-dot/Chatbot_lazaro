"""Esquema y arranque vacío de las respuestas rápidas del bot (#71)."""
from __future__ import annotations

from orchestrator.adapters.repository import FakeRepository
from migrations import section

_SCHEMA = section("orchestrator: tablas")
_INDEXES = section("orchestrator: índices")
_MIGRATIONS = section("orchestrator: migraciones aditivas previas")


def test_schema_declares_quick_replies_and_images_idempotently():
    """R1: las dos tablas existen con sus columnas y sin inserciones de datos."""
    schema = " ".join(_SCHEMA)
    assert "CREATE TABLE IF NOT EXISTS quick_replies" in schema
    assert "triggers JSONB NOT NULL" in schema
    assert "blocks JSONB NOT NULL" in schema
    assert "image_id TEXT" in schema
    assert "priority INTEGER NOT NULL" in schema
    assert "CREATE TABLE IF NOT EXISTS quick_reply_images" in schema
    assert "content_type TEXT NOT NULL" in schema
    assert "data BYTEA NOT NULL" in schema
    assert "size INTEGER NOT NULL" in schema
    assert all("IF NOT EXISTS" in statement for statement in _SCHEMA)


def test_no_business_content_is_seeded_in_schema_or_migrations():
    """R36: no se siembran respuestas rápidas en el esquema ni al migrar."""
    statements = " ".join(_SCHEMA + _INDEXES + _MIGRATIONS).upper()
    assert "INSERT INTO QUICK_REPLIES" not in statements
    assert "INSERT INTO QUICK_REPLY_IMAGES" not in statements


def test_fake_repository_starts_without_quick_replies():
    """R36: el repositorio de pruebas arranca vacío, sin valores por defecto."""
    repo = FakeRepository()
    assert repo.list_quick_replies() == []
    assert repo.list_quick_replies(only_active=True) == []
    assert repo.quick_reply_images == {}
