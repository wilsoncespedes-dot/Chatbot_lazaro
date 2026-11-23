"""Repositorio y esquema de eventos del panel en tiempo real (#53)."""
from __future__ import annotations

from migrations import section

_SCHEMA = section("orchestrator: tablas")
_INDEXES = section("orchestrator: índices")
_MIGRATIONS = section("orchestrator: migraciones aditivas previas")



def test_postgres_schema_declares_panel_events():
    """R19, R21: tabla e índice idempotentes para los avisos del panel."""
    schema = " ".join(_SCHEMA)
    assert "CREATE TABLE IF NOT EXISTS panel_events" in schema
    assert "id BIGSERIAL PRIMARY KEY" in schema
    assert "case_id TEXT NOT NULL" in schema
    assert "kind TEXT NOT NULL" in schema
    assert "created_at TIMESTAMPTZ NOT NULL" in schema
    indexes = " ".join(_INDEXES)
    assert "panel_events_created" in indexes
