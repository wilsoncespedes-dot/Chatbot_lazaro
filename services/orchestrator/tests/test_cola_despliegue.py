"""Despliegue, configuración, esquema y observabilidad de la cola (#64, R36, R37, R40, R41)."""
from __future__ import annotations

import logging
from pathlib import Path

import pytest
import yaml
from lazaro_contracts import TextBlock
from pydantic import ValidationError

from orchestrator.config import Settings
from orchestrator.domain import InboundEntry, OutboxEntry, destination_key
from orchestrator.queue import run_inbox_once, run_outbox_once

from migrations import section

_SCHEMA = section("orchestrator: tablas")
_INDEXES = section("orchestrator: índices")
_MIGRATIONS = section("orchestrator: migraciones aditivas previas")

ROOT = Path(__file__).resolve().parents[3]

QUEUE_VARS = (
    "INBOX_MAX_ATTEMPTS",
    "INBOX_BACKOFF_BASE_SECONDS",
    "OUTBOX_MAX_ATTEMPTS",
    "OUTBOX_BACKOFF_BASE_SECONDS",
    "OUTBOX_BACKOFF_MAX_SECONDS",
    "OUTBOX_BACKOFF_JITTER",
    "WORKER_POLL_SECONDS",
    "WORKER_LEASE_SECONDS",
)


def test_compose_defines_both_workers(env):
    """R35: compose define los dos workers con la imagen del orquestador."""
    data = yaml.safe_load((ROOT / "docker-compose.yml").read_text(encoding="utf-8"))
    services = data["services"]
    for name in ("procesar_entrantes", "enviar_salientes"):
        service = services[name]
        assert service["build"]["dockerfile"] == "services/orchestrator/Dockerfile"
        assert service["env_file"] == [".env"]
        assert service["depends_on"] == ["orchestrator"]
        assert service["restart"] == "unless-stopped"
        assert service["command"][-1] == name


def test_env_example_documents_queue_variables():
    """R36: `.env.example` documenta las ocho variables."""
    text = (ROOT / ".env.example").read_text(encoding="utf-8")
    for name in QUEUE_VARS:
        assert name in text


def test_settings_defaults():
    """R36: los valores por defecto son seguros y coinciden con el diseño."""
    settings = Settings()
    assert settings.inbox_max_attempts == 3
    assert settings.inbox_backoff_base_seconds == 5
    assert settings.outbox_max_attempts == 6
    assert settings.outbox_backoff_base_seconds == 2
    assert settings.outbox_backoff_max_seconds == 300
    assert settings.outbox_backoff_jitter == 0.2
    assert settings.worker_poll_seconds == 1
    assert settings.worker_lease_seconds == 120


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("INBOX_MAX_ATTEMPTS", "0"),
        ("INBOX_BACKOFF_BASE_SECONDS", "0"),
        ("OUTBOX_MAX_ATTEMPTS", "0"),
        ("OUTBOX_BACKOFF_BASE_SECONDS", "-1"),
        ("OUTBOX_BACKOFF_MAX_SECONDS", "0"),
        ("OUTBOX_BACKOFF_JITTER", "1.5"),
        ("WORKER_POLL_SECONDS", "0"),
        ("WORKER_LEASE_SECONDS", "0"),
    ],
)
def test_invalid_queue_settings_name_the_variable(name, value):
    """R37: una configuración fuera de rango se rechaza nombrando la variable."""
    with pytest.raises(ValidationError) as error:
        Settings(**{name.lower(): value})
    assert name in str(error.value)


def test_schema_creates_tables_and_indexes():
    """R40: el esquema crea inbox/outbox y sus índices con IF NOT EXISTS."""
    schema = " ".join(_SCHEMA)
    assert "CREATE TABLE IF NOT EXISTS inbox" in schema
    assert "CREATE TABLE IF NOT EXISTS outbox" in schema
    indexes = " ".join(_INDEXES)
    assert "inbox_conversation" in indexes
    assert "inbox_created" in indexes
    assert "outbox_destination" in indexes
    assert "outbox_status" in indexes


def test_logs_do_not_contain_queue_personal_data(env, caplog):
    """R41: los logs y last_error solo llevan id, canal y nombre de excepción."""
    caplog.set_level(logging.DEBUG)
    secret = "TEXTO-SECRETO-COLA"
    user = "987654321"
    env.repo.enqueue_inbound(
        InboundEntry(
            conversation_key=f"telegram:{user}",
            channel="telegram",
            external_user_id=user,
            payload_kind="legacy",
            payload={"update_id": 1, "text": secret},
        ),
        None,
    )
    assert run_inbox_once(env.settings, env.adapters)
    row = env.repo.inbox[1]
    assert row["last_error"] == "ValidationError"
    assert secret not in caplog.text
    assert user not in caplog.text

    env.repo.enqueue_outbound(
        OutboxEntry(
            contact_id=None,
            destination_key=destination_key("telegram", "555000111"),
            channel="telegram",
            destination="555000111",
            kind="notice",
            blocks=[TextBlock(type="text", text=secret)],
        )
    )
    env.gateway.fail = True
    assert run_outbox_once(env.settings, env.adapters)
    outbox = env.repo.outbox[1]
    assert outbox["last_error"] == "ServiceUnavailable"
    assert secret not in caplog.text
    assert "555000111" not in caplog.text
