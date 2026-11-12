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


def callback_update(
    update_id=50,
    data="privacy.accept:" + "a" * 32,
    callback_id="cb-1",
    chat_id=77,
    user_id=55,
):
    return {
        "update_id": update_id,
        "callback_query": {
            "id": callback_id,
            "from": {"id": user_id},
            "message": {"message_id": 90, "chat": {"id": chat_id}},
            "data": data,
        },
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

        def exists(self, key):
            return False

        def set(self, key, value, nx=False, ex=None):
            self.calls.append((key, nx, ex))
            return True

    store = RedisDedupStore("redis://localhost:6379/0")
    store._client = FakeRedis()
    assert store.mark_if_new(9, 60) is True
    assert store._client.calls == [
        ("gw:message:telegram:9", True, 60),
        ("gw:update:9", True, 60),
    ]


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


# ── R38: callback_query de botones de consentimiento ──────────────────────────


def test_callback_query_is_normalized_and_forwarded_as_button(env):
    """R38: el callback se convierte en el botón canónico y no se trata como texto."""
    r = env.client.post(URL, json=callback_update(), headers=HOOK)

    assert r.status_code == 200
    [message] = env.orchestrator.received
    assert message.channel == "telegram"
    assert message.kind == "button"
    assert message.button_id == "privacy.accept"
    assert message.button_proof == "a" * 32
    assert message.external_user_id == "55"
    assert message.external_chat_id == "77"
    assert message.external_message_id == "cb-1"
    assert env.telegram.sent == []
    assert ("telegram", "cb-1") in env.dedup.message_keys


def test_duplicate_callback_is_not_forwarded_twice(env):
    """R38: el id del callback deduplica igual que un mensaje."""
    env.client.post(URL, json=callback_update(), headers=HOOK)
    env.client.post(URL, json=callback_update(), headers=HOOK)

    assert len(env.orchestrator.received) == 1


def test_callback_without_data_is_ignored(env):
    """R38: un callback sin `data` no se reenvía ni envía nada al usuario."""
    update = callback_update()
    del update["callback_query"]["data"]
    r = env.client.post(URL, json=update, headers=HOOK)

    assert r.status_code == 200
    assert env.orchestrator.received == [] and env.telegram.sent == []


def test_callback_without_proof_is_still_forwarded_for_the_orchestrator_to_reject(env):
    """R38: el gateway no inventa prueba; el orquestador decide y falla cerrado."""
    env.client.post(
        URL, json=callback_update(data="privacy.accept"), headers=HOOK
    )

    [message] = env.orchestrator.received
    assert message.button_id == "privacy.accept"
    assert message.button_proof is None


@pytest.mark.parametrize("body", [{"message": {}}, {"update_id": "1"}, {"update_id": 1.5}])
def test_webhook_invalid_body_returns_422(env, body):
    """R17"""
    r = env.client.post(URL, json=body, headers=HOOK)
    assert r.status_code == 422
    assert r.json()["error"] == "validation_error"


def _build_consent_flow():
    """R38, R46: gateway real + orquestador falso comparten el aviso presentado."""
    from orchestrator.adapters.db_query import FakeDbQuery
    from orchestrator.adapters.gateway import FakeGatewayClient
    from orchestrator.adapters.handover import FakeHandoverClient
    from orchestrator.adapters.llm import FakeLLM
    from orchestrator.adapters.rag import FakeRagClient
    from orchestrator.adapters.repository import FakeRepository
    from orchestrator.config import Settings as OrchestratorSettings
    from lazaro_contracts import MessageRequest, NormalizedMessage
    from orchestrator.domain import Adapters as OrchestratorAdapters
    from orchestrator.domain import process_channel_message, process_message
    from orchestrator.privacy import ConversationTexts

    texts = ConversationTexts(
        notice_text="Aviso e2e",
        notice_version="v1",
        greeting="Hola",
        accepted_reply="Gracias",
        rejected_reply="Cerrado",
        login_reminder="Inicia sesión",
        suspended_reply="Suspendido",
        unsupported_reply="Solo texto",
        confirm_button_reply="Pulsa el botón",
    )
    repo = FakeRepository()
    repo.save_conversation_texts(texts, "admin-1", FIXED_NOW)
    orchestrator_settings = OrchestratorSettings(
        service_token=SERVICE_TOKEN, privacy_retention_days="30"
    )
    orchestrator_gateway = FakeGatewayClient()
    orchestrator_adapters = OrchestratorAdapters(
        repository=repo,
        rag=FakeRagClient(),
        llm=FakeLLM(),
        gateway=orchestrator_gateway,
        handover=FakeHandoverClient(),
        db_query=FakeDbQuery(),
        clock=lambda: FIXED_NOW,
        new_id=lambda: "case-1",
    )

    class OrchestratorClient:
        def post_message(self, request):
            if isinstance(request, MessageRequest):
                process_message(request, orchestrator_settings, orchestrator_adapters)
                return
            process_channel_message(request, orchestrator_settings, orchestrator_adapters)

    gateway_settings = Settings(
        service_token=SERVICE_TOKEN,
        telegram_webhook_secret=WEBHOOK_SECRET,
        telegram_bot_token=BOT_TOKEN,
        dedup_ttl_seconds=123,
    )
    client = TestClient(
        create_app(
            gateway_settings,
            Adapters(
                FakeTelegramClient(),
                FakeDedupStore(),
                OrchestratorClient(),
                clock=lambda: FIXED_NOW,
            ),
        )
    )
    process_channel_message(
        NormalizedMessage(
            channel="telegram",
            external_user_id="55",
            external_chat_id="77",
            external_message_id="present-1",
            kind="text",
            text="Hola",
            received_at=FIXED_NOW,
        ),
        orchestrator_settings,
        orchestrator_adapters,
    )
    return client, repo, texts, orchestrator_adapters


def test_webhook_callback_reaches_orchestrator_and_persists_the_decision():
    """R38, R46 R25-R27: el callback antiguo no registra; la frase de texto sí."""
    from orchestrator.domain import ConversationState
    from orchestrator.privacy import notice_sha256

    client, repo, texts, _adapters = _build_consent_flow()

    callback = client.post(
        URL,
        json=callback_update(data="privacy.accept:" + "a" * 32, callback_id="cb-e2e"),
        headers=HOOK,
    )

    assert callback.status_code == 200
    assert repo.privacy_consents == []

    response = client.post(
        URL,
        json=text_update(update_id=10, text="ACEPTO", chat_id=77, user_id=55),
        headers=HOOK,
    )

    assert response.status_code == 200
    [consent] = repo.privacy_consents
    assert consent.result == "accepted"
    assert consent.evidence_type == "text"
    assert consent.external_message_id == "10"
    assert consent.notice_version == "v1"
    assert consent.notice_sha256 == notice_sha256(texts.notice_text)
    [contact] = repo.contacts.values()
    assert repo.conversation_states[contact.id][0] == ConversationState.AWAITING_LOGIN


def test_webhook_callback_from_another_chat_does_not_consume_the_challenge():
    """R38, R46 R14, R25, R26: otro chat no registra; el chat correcto sí acepta."""
    client, repo, _texts, adapters = _build_consent_flow()

    wrong_chat = client.post(
        URL,
        json=callback_update(
            data="privacy.accept:" + "a" * 32, callback_id="cb-wrong", chat_id=88
        ),
        headers=HOOK,
    )

    assert wrong_chat.status_code == 200
    assert repo.privacy_consents == []
    assert adapters.consent_challenges.get("telegram", "55") is not None

    # El aviso vigente vuelve a presentarse en el chat correcto (R14, R15).
    client.post(
        URL,
        json=text_update(update_id=60, text="Hola", chat_id=77, user_id=55),
        headers=HOOK,
    )
    challenge = adapters.consent_challenges.get("telegram", "55")
    assert challenge is not None
    assert challenge.external_chat_id == "77"

    right_chat = client.post(
        URL,
        json=text_update(update_id=61, text="ACEPTO", chat_id=77, user_id=55),
        headers=HOOK,
    )

    assert right_chat.status_code == 200
    [consent] = repo.privacy_consents
    assert consent.result == "accepted"
    assert consent.external_message_id == "61"
    assert adapters.consent_challenges.get("telegram", "55") is None


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
        "TELEGRAM_ANSWER_CALLBACK_TIMEOUT_SECONDS",
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


# ── #44: confirmar callback_query (answerCallbackQuery) ──────────────────────


def test_http_answer_callback_query_posts_exact_body_and_timeout(monkeypatch):
    """R2: URL answerCallbackQuery, cuerpo exacto y timeout propio."""
    import httpx

    from telegram_gateway.adapters.telegram import HttpTelegramClient

    calls = {}

    def fake_post(url, **kwargs):
        calls["url"] = url
        calls["json"] = kwargs["json"]
        calls["timeout"] = kwargs["timeout"]
        return httpx.Response(200, request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx, "post", fake_post)
    HttpTelegramClient(BOT_TOKEN).answer_callback_query("cb-1")

    assert calls["url"].endswith("/answerCallbackQuery")
    assert calls["json"] == {"callback_query_id": "cb-1"}
    assert calls["timeout"] == 3.0


def test_http_answer_callback_query_status_error_hides_bot_token(monkeypatch):
    """R3: un estado no 2xx lanza TelegramError sin token ni URL."""
    import httpx

    from telegram_gateway.adapters.telegram import HttpTelegramClient
    from telegram_gateway.domain import TelegramError

    def fake_post(url, **kwargs):
        return httpx.Response(400, request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx, "post", fake_post)
    with pytest.raises(TelegramError) as info:
        HttpTelegramClient(BOT_TOKEN).answer_callback_query("cb-1")
    assert BOT_TOKEN not in str(info.value)
    assert info.value.__cause__ is None


def test_http_answer_callback_query_transport_errors_hide_bot_token(monkeypatch):
    """R3: ConnectError y TimeoutException lanzan TelegramError sin token."""
    import httpx

    from telegram_gateway.adapters.telegram import HttpTelegramClient
    from telegram_gateway.domain import TelegramError

    for error in (httpx.ConnectError("fallo"), httpx.TimeoutException("timeout")):

        def boom(url, **kwargs):
            raise error

        monkeypatch.setattr(httpx, "post", boom)
        with pytest.raises(TelegramError) as info:
            HttpTelegramClient(BOT_TOKEN).answer_callback_query("cb-1")
        assert BOT_TOKEN not in str(info.value)
        assert info.value.__cause__ is None


def test_answer_callback_timeout_setting_default_and_env(monkeypatch):
    """R2: default 3.0 y lectura desde el entorno."""
    monkeypatch.delenv("TELEGRAM_ANSWER_CALLBACK_TIMEOUT_SECONDS", raising=False)
    assert Settings().telegram_answer_callback_timeout_seconds == 3.0
    monkeypatch.setenv("TELEGRAM_ANSWER_CALLBACK_TIMEOUT_SECONDS", "5.5")
    assert Settings().telegram_answer_callback_timeout_seconds == 5.5


@pytest.mark.parametrize("value", ["0", "-1"])
def test_answer_callback_timeout_rejects_non_positive(monkeypatch, value):
    """R2: el timeout debe ser mayor que cero."""
    from pydantic import ValidationError

    monkeypatch.setenv("TELEGRAM_ANSWER_CALLBACK_TIMEOUT_SECONDS", value)
    with pytest.raises(ValidationError):
        Settings()


def test_callback_valid_is_answered_and_forwarded(env):
    """R1: se confirma con el id real y el botón se reenvía."""
    r = env.client.post(URL, json=callback_update(callback_id="cb-1"), headers=HOOK)

    assert r.status_code == 200
    assert env.telegram.answered == ["cb-1"]
    assert len(env.orchestrator.received) == 1


def test_callback_answer_failure_still_forwards_and_returns_200(env, caplog):
    """R4: un fallo al confirmar se registra y no impide dedupe ni reenvío."""
    env.telegram.fail_answer = True
    with caplog.at_level(logging.WARNING):
        r = env.client.post(URL, json=callback_update(callback_id="cb-1"), headers=HOOK)

    assert r.status_code == 200
    assert len(env.orchestrator.received) == 1
    log = "\n".join(record.getMessage() for record in caplog.records)
    assert "TelegramError" in log
    assert BOT_TOKEN not in log


def test_callback_answer_unexpected_exception_still_forwards(caplog):
    """R4: cualquier excepción (no solo TelegramError) se tolera y loguea el tipo."""
    class ExplodingTelegramClient(FakeTelegramClient):
        def answer_callback_query(self, callback_query_id: str) -> None:
            raise RuntimeError(f"fallo con {BOT_TOKEN}")

    orchestrator = FakeOrchestratorClient()
    settings = Settings(
        service_token=SERVICE_TOKEN,
        telegram_webhook_secret=WEBHOOK_SECRET,
        telegram_bot_token=BOT_TOKEN,
    )
    client = TestClient(
        create_app(
            settings,
            Adapters(
                ExplodingTelegramClient(),
                FakeDedupStore(),
                orchestrator,
                clock=lambda: FIXED_NOW,
            ),
        )
    )
    with caplog.at_level(logging.WARNING):
        r = client.post(URL, json=callback_update(callback_id="cb-1"), headers=HOOK)

    assert r.status_code == 200
    assert len(orchestrator.received) == 1
    log = "\n".join(record.getMessage() for record in caplog.records)
    assert "RuntimeError" in log
    assert BOT_TOKEN not in log


def test_duplicate_callback_is_answered_every_time_but_forwarded_once(env):
    """R5: el duplicado se confirma igualmente pero no se reenvía."""
    env.client.post(URL, json=callback_update(callback_id="cb-1"), headers=HOOK)
    r = env.client.post(URL, json=callback_update(callback_id="cb-1"), headers=HOOK)

    assert r.status_code == 200
    assert env.telegram.answered == ["cb-1", "cb-1"]
    assert len(env.orchestrator.received) == 1


def test_callback_without_data_but_real_id_is_answered_and_not_forwarded(env):
    """R6: un callback rechazado por `extract_callback` se confirma con su id real."""
    update = callback_update(callback_id="cb-1")
    del update["callback_query"]["data"]
    r = env.client.post(URL, json=update, headers=HOOK)

    assert r.status_code == 200
    assert env.telegram.answered == ["cb-1"]
    assert env.orchestrator.received == []


def test_callback_with_invalid_data_but_real_id_is_answered_and_not_forwarded(env):
    """R6: un callback inválido al normalizar se confirma con su id real."""
    update = callback_update(data="a" * 129 + ":proof", callback_id="cb-1")
    r = env.client.post(URL, json=update, headers=HOOK)

    assert r.status_code == 200
    assert env.telegram.answered == ["cb-1"]
    assert env.orchestrator.received == []


@pytest.mark.parametrize("callback_id", [None, "", "   ", 123])
def test_callback_without_real_id_is_not_answered(env, callback_id):
    """R7: nunca se confirma con un id sintético como `str(update_id)`."""
    update = callback_update(update_id=50, callback_id="cb-1")
    if callback_id is None:
        del update["callback_query"]["id"]
    else:
        update["callback_query"]["id"] = callback_id
    r = env.client.post(URL, json=update, headers=HOOK)

    assert r.status_code == 200
    assert env.telegram.answered == []
    assert "50" not in env.telegram.answered
    assert len(env.orchestrator.received) == 1


def test_text_update_does_not_answer_callback(env):
    """R8: un update sin callback_query no invoca answerCallbackQuery."""
    r = env.client.post(URL, json=text_update(), headers=HOOK)

    assert r.status_code == 200
    assert env.telegram.answered == []
