"""Fase 2: Telegram y WhatsApp entran por el webhook común y nada se pierde.

- Las URLs históricas pasan por `WebhookService` (adaptador → NormalizedMessage).
- Orquestador caído → el mensaje se guarda y se entrega cuando vuelve.
- Sin orquestador ni cola → 503 y el reenvío del canal se procesa.
- Espera creciente entre reintentos y descarte al caducar.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from telegram_gateway.adapters.dedup import FakeDedupStore
from telegram_gateway.adapters.inbound_retry import FakeInboundRetryStore
from telegram_gateway.adapters.message_buffer import FakeMessageBuffer
from telegram_gateway.adapters.orchestrator import FakeOrchestratorClient
from telegram_gateway.adapters.telegram import FakeTelegramClient
from telegram_gateway.adapters.whatsapp_window import FakeWhatsAppWindowStore
from telegram_gateway.config import Settings
from telegram_gateway.domain import Adapters
from telegram_gateway.grouping import flush_due
from telegram_gateway.inbound import process_due_retries, retry_delay_seconds
from telegram_gateway.main import create_app

TOKEN = "svc-token"
SECRET = "hook-secret"
APP_SECRET = "APP-SECRET"
PHONE = "PN-1"
NOW = datetime(2026, 11, 23, 10, 0, tzinfo=timezone.utc)
HOOK = {"X-Telegram-Bot-Api-Secret-Token": SECRET}


class Clock:
    def __init__(self) -> None:
        self.now = NOW

    def __call__(self) -> datetime:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += timedelta(seconds=seconds)


class Env:
    def __init__(self, *, grouping: bool = False, store_fail: bool = False) -> None:
        self.clock = Clock()
        self.settings = Settings(
            service_token=TOKEN,
            telegram_webhook_secret=SECRET,
            telegram_bot_token="123456:BOT",
            message_grouping_enabled=grouping,
            whatsapp_enabled=True,
            whatsapp_access_token="ACCESS",
            whatsapp_app_secret=APP_SECRET,
            whatsapp_verify_token="VERIFY",
            whatsapp_phone_number_id=PHONE,
        )
        self.telegram = FakeTelegramClient()
        self.dedup = FakeDedupStore()
        self.orchestrator = FakeOrchestratorClient()
        self.store = FakeInboundRetryStore(fail=store_fail)
        self.buffer = FakeMessageBuffer(clock=self.clock) if grouping else None
        self.adapters = Adapters(
            self.telegram,
            self.dedup,
            self.orchestrator,
            clock=self.clock,
            buffer=self.buffer,
            whatsapp_window=FakeWhatsAppWindowStore(),
            inbound_retry=self.store,
        )
        self.client = TestClient(
            create_app(self.settings, self.adapters), raise_server_exceptions=False
        )

    def telegram_text(self, update_id: int = 10, text: str = "hola"):
        update = {
            "update_id": update_id,
            "message": {"from": {"id": 55}, "chat": {"id": 77}, "text": text},
        }
        return self.client.post("/telegram/webhook", json=update, headers=HOOK)

    def whatsapp_text(self, wamid: str = "wamid.1", text: str = "hola"):
        payload = {
            "object": "whatsapp_business_account",
            "entry": [
                {
                    "changes": [
                        {
                            "field": "messages",
                            "value": {
                                "metadata": {"phone_number_id": PHONE},
                                "messages": [
                                    {
                                        "from": "57300",
                                        "id": wamid,
                                        "type": "text",
                                        "text": {"body": text},
                                    }
                                ],
                            },
                        }
                    ]
                }
            ],
        }
        body = json.dumps(payload).encode()
        signature = hmac.new(APP_SECRET.encode(), body, hashlib.sha256).hexdigest()
        return self.client.post(
            "/whatsapp/webhook",
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-Hub-Signature-256": f"sha256={signature}",
            },
        )


def test_telegram_url_goes_through_channel_registry():
    """Misma URL pública, pero el canal se resuelve en el registro: inactivo → 404."""
    env = Env()
    deactivate = env.client.patch(
        "/channels/telegram/active",
        json={"active": False},
        headers={"X-Service-Token": TOKEN},
    )
    assert deactivate.status_code == 200
    response = env.telegram_text()
    assert response.status_code == 404
    assert env.orchestrator.received == []


def test_whatsapp_url_goes_through_channel_registry():
    env = Env()
    env.client.patch(
        "/channels/whatsapp/active",
        json={"active": False},
        headers={"X-Service-Token": TOKEN},
    )
    assert env.whatsapp_text().status_code == 404
    assert env.orchestrator.received == []


def test_generic_route_does_not_expose_telegram_or_whatsapp():
    """#62 R7-R9: los canales con webhook propio solo entran por su URL histórica."""
    env = Env()
    for channel_id in ("telegram", "whatsapp"):
        response = env.client.post(f"/webhooks/{channel_id}", content=b"{}", headers=HOOK)
        assert response.status_code == 404


def test_telegram_message_is_delivered_when_orchestrator_returns(caplog):
    env = Env()
    env.orchestrator.fail = True
    with caplog.at_level(logging.WARNING):
        response = env.telegram_text(update_id=42, text="me interesa el plan Pro")
    assert response.status_code == 200
    assert len(env.store.rows) == 1
    assert "plan Pro" not in caplog.text

    # Antes de la primera espera no se reintenta.
    assert process_due_retries(env.settings, env.adapters) == 0

    env.orchestrator.fail = False
    env.clock.advance(env.settings.inbound_retry_base_seconds)
    assert process_due_retries(env.settings, env.adapters) == 1
    [message] = env.orchestrator.received
    assert (message.channel, message.external_message_id, message.text) == (
        "telegram",
        "42",
        "me interesa el plan Pro",
    )
    assert env.store.rows == {}


def test_whatsapp_message_is_delivered_when_orchestrator_returns():
    env = Env()
    env.orchestrator.fail = True
    assert env.whatsapp_text(wamid="wamid.x").status_code == 200
    env.orchestrator.fail = False
    env.clock.advance(60)
    process_due_retries(env.settings, env.adapters)
    assert [m.external_message_id for m in env.orchestrator.received] == ["wamid.x"]


def test_retry_waits_grow_until_the_cap():
    env = Env()
    env.orchestrator.fail = True
    env.telegram_text(update_id=7)
    waits = []
    for _ in range(5):
        row = next(iter(env.store.rows.values()))
        env.clock.now = row["next_attempt_at"]
        process_due_retries(env.settings, env.adapters)
        row = next(iter(env.store.rows.values()))
        waits.append((row["next_attempt_at"] - env.clock.now).total_seconds())
    assert waits == [4.0, 8.0, 16.0, 32.0, 64.0]
    assert retry_delay_seconds(30, env.settings) == env.settings.inbound_retry_max_delay_seconds


def test_expired_message_is_discarded_with_log(caplog):
    env = Env()
    env.orchestrator.fail = True
    env.telegram_text(update_id=8)
    env.clock.advance(env.settings.inbound_retry_max_age_seconds + 1)
    with caplog.at_level(logging.ERROR):
        process_due_retries(env.settings, env.adapters)
    assert env.store.rows == {}
    assert "inbound_retry_discarded channel=telegram message_id=8" in caplog.text
    assert "reason=expired" in caplog.text


def test_rejected_message_is_not_retried():
    """Un 422 del orquestador no se reintenta (el contenido no cambiará)."""
    env = Env()
    env.orchestrator.reject = True
    assert env.telegram_text().status_code == 200
    assert env.store.rows == {}


def test_no_orchestrator_and_no_queue_is_503_and_resend_is_processed():
    """Solo se responde ok cuando el mensaje quedó entregado o persistido."""
    env = Env(store_fail=True)
    env.orchestrator.fail = True
    first = env.telegram_text(update_id=11)
    assert first.status_code == 503
    assert first.json()["error"] == "service_unavailable"
    # La marca de Redis se quitó: el reenvío de Telegram no es "duplicado".
    env.orchestrator.fail = False
    second = env.telegram_text(update_id=11)
    assert second.status_code == 200
    assert [m.external_message_id for m in env.orchestrator.received] == ["11"]


def test_whatsapp_batch_is_503_when_nothing_can_be_persisted():
    env = Env(store_fail=True)
    env.orchestrator.fail = True
    assert env.whatsapp_text().status_code == 503


def test_failed_group_goes_to_the_persistent_queue(caplog):
    """La agrupación de Telegram ya no descarta grupos: los pasa a la cola."""
    env = Env(grouping=True)
    env.telegram_text(update_id=1, text="hola")
    env.telegram_text(update_id=2, text="¿precio?")
    env.orchestrator.fail = True
    env.clock.advance(env.settings.message_grouping_max_wait_seconds + 1)
    with caplog.at_level(logging.WARNING):
        flush_due(env.settings, env.adapters)
    assert "grouping_queued" in caplog.text
    assert env.buffer.pending(77) == []
    [row] = env.store.rows.values()
    assert row["external_message_id"] == "1"

    env.orchestrator.fail = False
    env.clock.advance(env.settings.inbound_retry_base_seconds)
    process_due_retries(env.settings, env.adapters)
    assert [m.text for m in env.orchestrator.received] == ["hola\n¿precio?"]


def test_redis_down_forwards_both_copies_and_orchestrator_deduplicates():
    """Con Redis caído el gateway reenvía; la barrera es el índice único del inbox."""
    env = Env()
    env.dedup.fail = True
    env.telegram_text(update_id=99)
    env.telegram_text(update_id=99)
    ids = [m.external_message_id for m in env.orchestrator.received]
    assert ids == ["99", "99"]
