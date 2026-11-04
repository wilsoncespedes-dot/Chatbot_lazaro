"""Webhook de WhatsApp Cloud API y POST /send extremo a extremo (#43)."""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

import httpx
from fastapi.testclient import TestClient

from telegram_gateway.adapters.dedup import FakeDedupStore
from telegram_gateway.adapters.orchestrator import FakeOrchestratorClient
from telegram_gateway.adapters.telegram import FakeTelegramClient
from telegram_gateway.adapters.whatsapp_cloud import (
    WhatsAppCloudAdapter,
    WhatsAppCloudConfig,
)
from telegram_gateway.adapters.whatsapp_window import FakeWhatsAppWindowStore
from telegram_gateway.config import Settings
from telegram_gateway.domain import Adapters
from telegram_gateway.main import create_app

URL = "/whatsapp/webhook"
SERVICE_TOKEN = "svc-token"
APP_SECRET = "APP-SECRET"
VERIFY_TOKEN = "VERIFY-TOKEN"
PHONE_NUMBER_ID = "PN-1"
NOW = datetime(2026, 11, 3, 16, 0, 0, tzinfo=timezone.utc)
HEADERS = {"X-Service-Token": SERVICE_TOKEN}


def whatsapp_settings() -> Settings:
    return Settings(
        service_token=SERVICE_TOKEN,
        telegram_webhook_secret="hook-secret",
        telegram_bot_token="123456:BOT",
        message_grouping_enabled=False,
        whatsapp_enabled=True,
        whatsapp_access_token="ACCESS-TOKEN-VALUE",
        whatsapp_app_secret=APP_SECRET,
        whatsapp_verify_token=VERIFY_TOKEN,
        whatsapp_phone_number_id=PHONE_NUMBER_ID,
    )


class Env:
    def __init__(self, *, whatsapp=None, window=None):
        self.settings = whatsapp_settings()
        self.telegram = FakeTelegramClient()
        self.dedup = FakeDedupStore()
        self.orchestrator = FakeOrchestratorClient()
        self.window = window or FakeWhatsAppWindowStore()
        self.adapters = Adapters(
            self.telegram,
            self.dedup,
            self.orchestrator,
            clock=lambda: NOW,
            whatsapp=whatsapp,
            whatsapp_window=self.window,
        )
        self.client = TestClient(create_app(self.settings, self.adapters))


def make_adapter(handler, window):
    return WhatsAppCloudAdapter(
        WhatsAppCloudConfig(
            access_token="ACCESS-TOKEN-VALUE",
            phone_number_id=PHONE_NUMBER_ID,
            graph_base_url="https://graph.test",
            api_version="v21.0",
            template_language="es",
            interactive_body_text="Elige una opción:",
            window_hours=24,
        ),
        httpx.Client(transport=httpx.MockTransport(handler)),
        window,
        lambda: NOW,
    )


def text_message(
    *, from_="573001112233", message_id="wamid.1", body="hola"
) -> dict:
    return {"from": from_, "id": message_id, "type": "text", "text": {"body": body}}


def webhook_value(
    *,
    messages=None,
    statuses=None,
    phone_number_id=PHONE_NUMBER_ID,
) -> dict:
    value: dict = {"metadata": {"phone_number_id": phone_number_id}}
    if messages is not None:
        value["messages"] = messages
    if statuses is not None:
        value["statuses"] = statuses
    return value


def webhook(
    *,
    messages=(),
    statuses=None,
    changes=None,
    object_="whatsapp_business_account",
) -> dict:
    if changes is None:
        changes = [
            {
                "field": "messages",
                "value": webhook_value(
                    messages=list(messages), statuses=statuses
                ),
            }
        ]
    return {"object": object_, "entry": [{"changes": changes}]}


def signature(body: bytes, secret: str = APP_SECRET) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def post(
    client: TestClient,
    payload: dict | None = None,
    *,
    body: bytes | None = None,
    signature_value: str | None | bool = True,
):
    if body is None:
        body = json.dumps(payload).encode()
    headers = {"Content-Type": "application/json"}
    if signature_value is True:
        headers["X-Hub-Signature-256"] = signature(body)
    elif isinstance(signature_value, str):
        headers["X-Hub-Signature-256"] = signature_value
    return client.post(URL, content=body, headers=headers)


def log_text(caplog) -> str:
    return "\n".join(record.getMessage() for record in caplog.records)


# ── R8-R10: verificación GET ────────────────────────────────────────────────


def test_get_subscription_returns_challenge_as_plain_text():
    """R8: modo y token válidos devuelven el challenge."""
    env = Env()
    response = env.client.get(
        URL,
        params={
            "hub.mode": "subscribe",
            "hub.verify_token": VERIFY_TOKEN,
            "hub.challenge": "challenge-123",
        },
    )
    assert response.status_code == 200
    assert response.text == "challenge-123"
    assert response.headers["content-type"].startswith("text/plain")


def test_get_subscription_rejects_wrong_mode_token_or_missing_challenge():
    """R9: cualquier verificación inválida devuelve 403 forbidden."""
    env = Env()
    cases = [
        {"hub.mode": "unsubscribe", "hub.verify_token": VERIFY_TOKEN, "hub.challenge": "1"},
        {"hub.mode": "subscribe", "hub.verify_token": "otro", "hub.challenge": "1"},
        {"hub.mode": "subscribe", "hub.challenge": "1"},
        {"hub.mode": "subscribe", "hub.verify_token": VERIFY_TOKEN},
    ]
    for params in cases:
        response = env.client.get(URL, params=params)
        assert response.status_code == 403, params
        assert response.json()["error"] == "forbidden"


def test_webhook_does_not_require_service_token():
    """R10: GET y POST se autentican solo con verify token/firma."""
    env = Env()
    get = env.client.get(
        URL,
        params={
            "hub.mode": "subscribe",
            "hub.verify_token": VERIFY_TOKEN,
            "hub.challenge": "ok",
        },
    )
    assert get.status_code == 200
    assert post(env.client, webhook(messages=[text_message()])).status_code == 200
    assert len(env.orchestrator.received) == 1


# ── R11-R15, R51: firma y filtrado del cuerpo ───────────────────────────────


def test_valid_signature_processes_and_returns_ok():
    """R11: firma válida → 200 {"ok": true} y reenvío."""
    env = Env()
    response = post(env.client, webhook(messages=[text_message()]))
    assert response.status_code == 200
    assert response.json() == {"ok": True}
    assert len(env.orchestrator.received) == 1


def test_invalid_signature_returns_401_and_touches_nothing():
    """R12: sin encabezado, sin prefijo o HMAC distinto no toca almacenes."""
    env = Env()
    payload = webhook(messages=[text_message()])
    bodies = [
        (json.dumps(payload).encode(), None),
        (json.dumps(payload).encode(), "deadbeef"),
        (json.dumps(payload).encode(), "sha256=" + "0" * 64),
    ]
    for body, value in bodies:
        response = post(
            env.client,
            body=body,
            signature_value=value,
        )
        assert response.status_code == 401
        assert response.json()["error"] == "unauthorized"
    assert env.orchestrator.received == []
    assert env.dedup.message_keys == set()
    assert env.window.values == {}


def test_signature_is_over_raw_bytes_not_reserialized_json():
    """R13: un cuerpo semánticamente igual pero con otros bytes se rechaza."""
    env = Env()
    signed = b'{"object": "whatsapp_business_account", "entry": []}'
    sent = b'{"object":"whatsapp_business_account","entry":[]}'
    response = post(env.client, body=sent, signature_value=signature(signed))
    assert response.status_code == 401


def test_valid_signature_with_invalid_json_or_foreign_object_is_ignored():
    """R14: no-JSON, listas u object ajeno responden 200 sin reenviar."""
    env = Env()
    for body in (b"no es json", b"[]", json.dumps({"object": "page"}).encode()):
        response = post(env.client, body=body)
        assert response.status_code == 200
        assert response.json() == {"ok": True}
    assert env.orchestrator.received == []


def test_non_applicable_changes_are_ignored_and_applicable_one_still_processed():
    """R15, R51: campo o número ajeno se ignora sin frenar el resto."""
    env = Env()
    payload = webhook(
        changes=[
            {
                "field": "other",
                "value": webhook_value(messages=[text_message(message_id="ignored-1")]),
            },
            {
                "field": "messages",
                "value": webhook_value(
                    messages=[text_message(message_id="ignored-2")],
                    phone_number_id="OTRO",
                ),
            },
            {
                "field": "messages",
                "value": webhook_value(
                    messages=[text_message(message_id="valid-1", body="válido")]
                ),
            },
        ]
    )
    response = post(env.client, payload)
    assert response.status_code == 200
    [message] = env.orchestrator.received
    assert message.external_message_id == "valid-1"
    assert message.text == "válido"


# ── R16-R22, R27, R52: normalización ────────────────────────────────────────


def test_text_message_is_normalized_with_injected_clock():
    """R16: campos canónicos y received_at del reloj inyectado."""
    env = Env()
    post(
        env.client,
        webhook(messages=[text_message(from_="57300", message_id="wamid.9", body="Hola")]),
    )
    [message] = env.orchestrator.received
    assert (
        message.channel,
        message.external_user_id,
        message.external_chat_id,
        message.external_message_id,
        message.kind,
        message.text,
        message.received_at,
    ) == ("whatsapp", "57300", "57300", "wamid.9", "text", "Hola", NOW)


def test_interactive_button_and_list_replies_are_normalized():
    """R17: button_reply y list_reply separan id y prueba."""
    env = Env()
    post(
        env.client,
        webhook(
            messages=[
                {
                    "from": "57300",
                    "id": "wamid.b1",
                    "type": "interactive",
                    "interactive": {
                        "button_reply": {"id": "privacy.accept:proof-1", "title": "Acepto"}
                    },
                },
                {
                    "from": "57300",
                    "id": "wamid.b2",
                    "type": "interactive",
                    "interactive": {
                        "list_reply": {"id": "opcion", "title": "Opción"}
                    },
                },
            ]
        ),
    )
    first, second = env.orchestrator.received
    assert (first.kind, first.button_id, first.button_proof) == (
        "button",
        "privacy.accept",
        "proof-1",
    )
    assert (second.kind, second.button_id, second.button_proof) == (
        "button",
        "opcion",
        None,
    )


def test_template_quick_reply_button_payload_is_split():
    """R18: button.payload usa la misma separación id/prueba."""
    env = Env()
    post(
        env.client,
        webhook(
            messages=[
                {
                    "from": "57300",
                    "id": "wamid.bt",
                    "type": "button",
                    "button": {"payload": "acepto:prueba"},
                }
            ]
        ),
    )
    [message] = env.orchestrator.received
    assert (message.kind, message.button_id, message.button_proof) == (
        "button",
        "acepto",
        "prueba",
    )


def test_non_text_types_are_forwarded_as_unsupported():
    """R19: imagen, audio, sticker y tipo desconocido → unsupported."""
    env = Env()
    messages = [
        {"from": "57300", "id": f"wamid.{kind}", "type": kind}
        for kind in ("image", "audio", "sticker", "location", "desconocido")
    ]
    post(env.client, webhook(messages=messages))
    assert [message.kind for message in env.orchestrator.received] == [
        "unsupported"
    ] * 5
    assert all(message.text is None for message in env.orchestrator.received)


def test_reaction_is_not_forwarded_but_renews_the_window():
    """R20, R27: una reacción no llega al orquestador, pero cuenta para la ventana."""
    env = Env()
    post(
        env.client,
        webhook(
            messages=[
                {
                    "from": "57300",
                    "id": "wamid.reaction",
                    "type": "reaction",
                    "reaction": {"emoji": "👍"},
                }
            ]
        ),
    )
    assert env.orchestrator.received == []
    assert env.window.values["57300"] == NOW


def test_invalid_messages_are_discarded_without_dropping_later_valid_ones():
    """R21, R52: inválidos se descartan y el válido posterior sí se reenvía."""
    env = Env()
    messages = [
        {"id": "wamid.no-from", "type": "text", "text": {"body": "x"}},
        {"from": "57300", "type": "text", "text": {"body": "x"}},
        text_message(message_id="wamid.empty", body=""),
        text_message(message_id="wamid.long", body="a" * 4097),
        text_message(message_id="wamid.ok", body="sí"),
    ]
    post(env.client, webhook(messages=messages))
    [message] = env.orchestrator.received
    assert message.external_message_id == "wamid.ok"


def test_multiple_messages_keep_body_order():
    """R22: el reenvío conserva el orden del cuerpo."""
    env = Env()
    post(
        env.client,
        webhook(
            messages=[
                text_message(message_id="m1", body="uno"),
                text_message(message_id="m2", body="dos"),
                text_message(message_id="m3", body="tres"),
            ]
        ),
    )
    assert [message.external_message_id for message in env.orchestrator.received] == [
        "m1",
        "m2",
        "m3",
    ]


# ── R23-R26, R53: idempotencia ──────────────────────────────────────────────


def test_duplicate_wamid_is_forwarded_once_and_both_return_200():
    """R23, R53: el mismo wamid no se duplica y ambos webhooks responden 200."""
    env = Env()
    payload = webhook(messages=[text_message(message_id="wamid.dup")])
    first = post(env.client, payload)
    second = post(env.client, payload)
    assert first.status_code == 200 and second.status_code == 200
    assert len(env.orchestrator.received) == 1


def test_whatsapp_wamid_equal_to_telegram_id_is_not_confused():
    """R24: la clave compuesta aísla el wamid de un update_id de Telegram."""
    env = Env()
    env.dedup.mark_message_if_new("telegram", "123", 60)
    post(env.client, webhook(messages=[text_message(message_id="123")]))
    assert len(env.orchestrator.received) == 1


def test_dedup_failure_forwards_as_new():
    """R25: si Redis falla se reenvía y se registra el fallo."""
    env = Env()
    env.dedup.fail = True
    response = post(env.client, webhook(messages=[text_message()]))
    assert response.status_code == 200
    assert len(env.orchestrator.received) == 1


def test_orchestrator_failure_returns_200_and_logs_without_text(caplog):
    """R26, R6: el webhook responde 200 y el log no contiene el texto."""
    env = Env()
    env.orchestrator.fail = True
    with caplog.at_level(logging.ERROR):
        response = post(
            env.client,
            webhook(
                messages=[
                    text_message(message_id="wamid.fail", body="texto-privado")
                ]
            ),
        )
    assert response.status_code == 200
    log = log_text(caplog)
    assert "wamid.fail" in log
    assert "texto-privado" not in log
    assert "573001112233" not in log


def test_only_duplicates_still_returns_ok():
    """R53: un lote solo con repetidos responde 200."""
    env = Env()
    env.dedup.mark_message_if_new("whatsapp", "wamid.only", 60)
    response = post(env.client, webhook(messages=[text_message(message_id="wamid.only")]))
    assert response.status_code == 200
    assert response.json() == {"ok": True}
    assert env.orchestrator.received == []


# ── R47: estados de entrega ─────────────────────────────────────────────────


def test_delivery_statuses_are_logged_without_forwarding_or_dedup(caplog):
    """R47: statuses se registran en log y no se marcan como mensajes."""
    env = Env()
    payload = webhook(
        statuses=[
            {"id": "wamid.s1", "status": "delivered"},
            {
                "id": "wamid.s2",
                "status": "failed",
                "errors": [{"code": 131047}],
            },
        ]
    )
    with caplog.at_level(logging.INFO):
        response = post(env.client, payload)
    assert response.status_code == 200
    assert env.orchestrator.received == []
    assert env.dedup.message_keys == set()
    log = log_text(caplog)
    assert "whatsapp_status" in log and "wamid.s1" in log and "131047" in log


# ── R31, R33, R34, R44, R45: POST /send extremo a extremo ───────────────────


def test_send_text_outside_window_returns_422_without_http():
    """R31, R33: texto fuera de ventana falla antes de llamar a Meta."""
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json={"messages": []})

    window = FakeWhatsAppWindowStore()
    env = Env(whatsapp=make_adapter(handler, window), window=window)
    response = env.client.post(
        "/send",
        json={
            "channel": "whatsapp",
            "destination": "573001112233",
            "blocks": [{"type": "text", "text": "Hola"}],
        },
        headers=HEADERS,
    )
    assert response.status_code == 422
    assert response.json()["error"] == "validation_error"
    assert calls == []


def test_send_template_outside_window_succeeds():
    """R34: una plantilla se envía aunque la ventana esté cerrada."""
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json={"messages": []})

    window = FakeWhatsAppWindowStore()
    env = Env(whatsapp=make_adapter(handler, window), window=window)
    response = env.client.post(
        "/send",
        json={
            "channel": "whatsapp",
            "destination": "573001112233",
            "blocks": [{"type": "template", "name": "aviso", "variables": ["hoy"]}],
        },
        headers=HEADERS,
    )
    assert response.status_code == 200
    assert response.json() == {"sent": True}
    assert len(calls) == 1


def test_send_template_error_from_meta_returns_422():
    """R44: un código de plantilla se traduce a 422 validation_error."""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"error": {"code": 132001}})

    window = FakeWhatsAppWindowStore()
    env = Env(whatsapp=make_adapter(handler, window), window=window)
    response = env.client.post(
        "/send",
        json={
            "channel": "whatsapp",
            "destination": "573001112233",
            "blocks": [{"type": "template", "name": "aviso"}],
        },
        headers=HEADERS,
    )
    assert response.status_code == 422
    assert response.json()["error"] == "validation_error"


def test_send_meta_500_returns_502_upstream_error():
    """R45: un fallo de Meta se traduce a 502 upstream_error."""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": {"code": 100}})

    window = FakeWhatsAppWindowStore()
    env = Env(whatsapp=make_adapter(handler, window), window=window)
    response = env.client.post(
        "/send",
        json={
            "channel": "whatsapp",
            "destination": "573001112233",
            "blocks": [{"type": "template", "name": "aviso"}],
        },
        headers=HEADERS,
    )
    assert response.status_code == 502
    assert response.json()["error"] == "upstream_error"
