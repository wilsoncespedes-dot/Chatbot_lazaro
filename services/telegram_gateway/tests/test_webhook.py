"""Tests del webhook y de la configuración del telegram_gateway."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from telegram_gateway.adapters.dedup import FakeDedupStore
from telegram_gateway.adapters.orchestrator import FakeOrchestratorClient
from telegram_gateway.adapters.telegram import FakeTelegramClient
from telegram_gateway.config import Settings
from telegram_gateway.domain import Adapters
from telegram_gateway.main import create_app

# Deben coincidir con conftest.py (no se importa: --import-mode=importlib).
SERVICE_TOKEN = "svc-token"
WEBHOOK_SECRET = "hook-secret"
BOT_TOKEN = "123456:BOT-TOKEN-SECRETO"
FIXED_NOW = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)

URL = "/telegram/webhook"
HOOK = {"X-Telegram-Bot-Api-Secret-Token": WEBHOOK_SECRET}
ROOT = Path(__file__).resolve().parents[3]


def text_update(update_id=10, text="hola", chat_id=77, user_id=55):
    return {
        "update_id": update_id,
        "message": {"message_id": 1, "from": {"id": user_id}, "chat": {"id": chat_id}, "text": text},
    }


def test_webhook_without_secret_returns_401(env):
    """R1"""
    r = env.client.post(URL, json=text_update())
    assert r.status_code == 401
    assert r.json()["error"] == "unauthorized"
    assert env.orchestrator.received == []


def test_webhook_wrong_secret_returns_401(env):
    """R1"""
    r = env.client.post(URL, json=text_update(), headers={"X-Telegram-Bot-Api-Secret-Token": "x"})
    assert r.status_code == 401
    assert r.json()["error"] == "unauthorized"
    assert env.orchestrator.received == []


def test_webhook_empty_configured_secret_returns_401():
    """R2"""
    orch = FakeOrchestratorClient()
    app = create_app(
        Settings(service_token=SERVICE_TOKEN, telegram_webhook_secret=""),
        Adapters(FakeTelegramClient(), FakeDedupStore(), orch),
    )
    client = TestClient(app)
    for headers in ({}, {"X-Telegram-Bot-Api-Secret-Token": ""}):
        r = client.post(URL, json=text_update(), headers=headers)
        assert r.status_code == 401
    assert orch.received == []


def test_webhook_does_not_require_service_token(env):
    """R3"""
    r = env.client.post(URL, json=text_update(), headers=HOOK)
    assert r.status_code == 200


def test_new_text_update_is_forwarded_with_contract_fields(env):
    """R4, R5, R6, R7"""
    r = env.client.post(URL, json=text_update(update_id=10, text="hola"), headers=HOOK)
    assert r.status_code == 200
    assert len(env.orchestrator.received) == 1
    m = env.orchestrator.received[0]
    assert (m.update_id, m.telegram_user_id, m.chat_id, m.text) == (10, 55, 77, "hola")
    assert m.received_at == FIXED_NOW and m.received_at.tzinfo is not None


def test_http_orchestrator_sends_service_token_header(monkeypatch):
    """R6: el cliente HTTP envía X-Service-Token (httpx.post simulado, sin red)."""
    import httpx

    from telegram_gateway.adapters.orchestrator import HttpOrchestratorClient
    from telegram_gateway.domain import build_message_request, extract_incoming

    calls = {}

    def fake_post(url, **kwargs):
        calls["url"] = url
        calls["headers"] = kwargs["headers"]
        return httpx.Response(202, request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx, "post", fake_post)
    incoming = extract_incoming(text_update())
    HttpOrchestratorClient("http://orch:8000/", SERVICE_TOKEN).post_message(
        build_message_request(incoming, FIXED_NOW)
    )
    assert calls["url"] == "http://orch:8000/messages"
    assert calls["headers"]["X-Service-Token"] == SERVICE_TOKEN


def test_duplicate_update_is_not_forwarded_and_returns_200(env):
    """R8"""
    env.client.post(URL, json=text_update(), headers=HOOK)
    r = env.client.post(URL, json=text_update(), headers=HOOK)
    assert r.status_code == 200
    assert len(env.orchestrator.received) == 1
    assert env.telegram.sent == []


def test_duplicate_non_text_update_sends_nothing_twice(env):
    """R8"""
    upd = {"update_id": 5, "message": {"from": {"id": 1}, "chat": {"id": 2}, "sticker": {}}}
    env.client.post(URL, json=upd, headers=HOOK)
    env.client.post(URL, json=upd, headers=HOOK)
    assert len(env.telegram.sent) == 1


def test_dedup_key_stored_with_ttl(env):
    """R9"""
    env.client.post(URL, json=text_update(update_id=42), headers=HOOK)
    assert env.dedup.keys == {42: 123}


def test_redis_adapter_uses_set_nx_ex():
    """R9: RedisDedupStore usa SET NX EX con cliente simulado."""
    from telegram_gateway.adapters.dedup import RedisDedupStore

    class FakeRedis:
        def __init__(self):
            self.calls = []

        def set(self, key, value, nx=False, ex=None):
            self.calls.append((key, nx, ex))
            return True

    store = RedisDedupStore("redis://localhost:6379/0")
    store._client = FakeRedis()
    assert store.mark_if_new(9, 60) is True
    assert store._client.calls == [("gw:update:9", True, 60)]


def test_dedup_store_failure_still_forwards(env, caplog):
    """R10"""
    env.dedup.fail = True
    with caplog.at_level(logging.ERROR):
        r = env.client.post(URL, json=text_update(), headers=HOOK)
    assert r.status_code == 200
    assert len(env.orchestrator.received) == 1
    assert any("Redis" in rec.getMessage() for rec in caplog.records)


def test_orchestrator_down_returns_200_and_logs_error(env, caplog):
    """R11, R12"""
    env.orchestrator.fail = True
    with caplog.at_level(logging.ERROR):
        r = env.client.post(URL, json=text_update(update_id=99, text="texto-privado"), headers=HOOK)
    assert r.status_code == 200
    log = "\n".join(rec.getMessage() for rec in caplog.records)
    assert "99" in log
    assert "texto-privado" not in log
    assert SERVICE_TOKEN not in log


def test_non_text_update_sends_fixed_reply_and_not_forwarded(env):
    """R13, R14"""
    upd = {"update_id": 5, "message": {"from": {"id": 1}, "chat": {"id": 2}, "voice": {}}}
    r = env.client.post(URL, json=upd, headers=HOOK)
    assert r.status_code == 200
    assert env.telegram.sent == [(2, env.settings.non_text_reply)]
    assert env.orchestrator.received == []


def test_non_text_reply_failure_returns_200(env, caplog):
    """R15"""
    env.telegram.fail = True
    upd = {"update_id": 5, "message": {"from": {"id": 1}, "chat": {"id": 2}, "photo": []}}
    with caplog.at_level(logging.ERROR):
        r = env.client.post(URL, json=upd, headers=HOOK)
    assert r.status_code == 200
    assert caplog.records


@pytest.mark.parametrize("text", ["", "   ", "\n\t "])
def test_empty_or_blank_text_treated_as_non_text(env, text):
    """R4, R13, R14"""
    r = env.client.post(URL, json=text_update(text=text, chat_id=3), headers=HOOK)
    assert r.status_code == 200
    assert env.telegram.sent == [(3, env.settings.non_text_reply)]
    assert env.orchestrator.received == []


def test_update_without_message_is_ignored(env):
    """R16"""
    r = env.client.post(
        URL, json={"update_id": 1, "edited_message": {"text": "x"}}, headers=HOOK
    )
    assert r.status_code == 200
    assert env.orchestrator.received == [] and env.telegram.sent == []


@pytest.mark.parametrize("body", [{"message": {}}, {"update_id": "1"}, {"update_id": 1.5}])
def test_webhook_invalid_body_returns_422(env, body):
    """R17"""
    r = env.client.post(URL, json=body, headers=HOOK)
    assert r.status_code == 422
    assert r.json()["error"] == "validation_error"


def test_settings_defaults(monkeypatch):
    """R22"""
    for name in ("DEDUP_TTL_SECONDS", "HTTP_TIMEOUT_SECONDS", "NON_TEXT_REPLY"):
        monkeypatch.delenv(name, raising=False)
    s = Settings()
    assert s.dedup_ttl_seconds == 86400
    assert s.http_timeout_seconds == 10
    assert s.non_text_reply == "Por ahora solo puedo leer mensajes de texto."


def test_settings_reads_env(monkeypatch):
    """R22"""
    monkeypatch.setenv("TELEGRAM_WEBHOOK_SECRET", "s")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "b")
    monkeypatch.setenv("REDIS_URL", "redis://x")
    monkeypatch.setenv("ORCHESTRATOR_URL", "http://o")
    monkeypatch.setenv("DEDUP_TTL_SECONDS", "5")
    s = Settings()
    assert (s.telegram_webhook_secret, s.telegram_bot_token, s.redis_url) == ("s", "b", "redis://x")
    assert (s.orchestrator_url, s.dedup_ttl_seconds) == ("http://o", 5)


def test_env_example_lists_all_variables():
    """R25"""
    text = (ROOT / ".env.example").read_text(encoding="utf-8")
    declared = {
        ln.split("=", 1)[0].strip()
        for ln in text.splitlines()
        if "=" in ln and not ln.lstrip().startswith("#")
    }
    for name in (
        "TELEGRAM_WEBHOOK_SECRET",
        "TELEGRAM_BOT_TOKEN",
        "REDIS_URL",
        "ORCHESTRATOR_URL",
        "DEDUP_TTL_SECONDS",
        "HTTP_TIMEOUT_SECONDS",
        "NON_TEXT_REPLY",
    ):
        assert name in declared, name


def test_bot_token_not_in_logs_or_errors(env, caplog):
    """R24"""
    env.telegram.fail = True
    upd = {"update_id": 5, "message": {"from": {"id": 1}, "chat": {"id": 2}, "voice": {}}}
    with caplog.at_level(logging.DEBUG):
        r1 = env.client.post(URL, json=upd, headers=HOOK)
        r2 = env.client.post(
            "/send", json={"chat_id": 1, "text": "x"}, headers={"X-Service-Token": SERVICE_TOKEN}
        )
    assert BOT_TOKEN not in r1.text + r2.text
    assert BOT_TOKEN not in "\n".join(rec.getMessage() for rec in caplog.records)


def test_http_telegram_error_hides_bot_token(monkeypatch):
    """R24: el cliente HTTP no filtra la URL con el token en el error."""
    import httpx

    from telegram_gateway.adapters.telegram import HttpTelegramClient
    from telegram_gateway.domain import TelegramError

    def boom(url, **kwargs):
        raise httpx.ConnectError(f"fallo en {url}")

    monkeypatch.setattr(httpx, "post", boom)
    with pytest.raises(TelegramError) as info:
        HttpTelegramClient(BOT_TOKEN).send_message(1, "x")
    assert BOT_TOKEN not in str(info.value)
    assert info.value.__cause__ is None
