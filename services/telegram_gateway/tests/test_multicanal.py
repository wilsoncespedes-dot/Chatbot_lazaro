"""Tests del límite multicanal del gateway: normalización, bloques y ventana (#36)."""
from __future__ import annotations

import httpx
import pytest
from fastapi.testclient import TestClient
from lazaro_contracts import (
    ChannelCapabilities,
    LinkBlock,
    ListBlock,
    OptionsBlock,
    TemplateBlock,
    TextBlock,
)

from telegram_gateway.adapters.dedup import FakeDedupStore, RedisDedupStore
from telegram_gateway.adapters.orchestrator import FakeOrchestratorClient
from telegram_gateway.adapters.telegram import (
    FakeTelegramClient,
    TelegramChannelAdapter,
    build_inline_keyboard,
    render_blocks,
)
from telegram_gateway.adapters.whatsapp import FakeWhatsAppAdapter
from telegram_gateway.config import Settings
from telegram_gateway.domain import (
    Adapters,
    ChannelSendFailed,
    ChannelWindowClosed,
    TemplateNotApproved,
    extract_incoming,
    normalize_incoming,
    send_response,
)
from telegram_gateway.main import create_app

SERVICE_TOKEN = "svc-token"
WEBHOOK_SECRET = "hook-secret"
HOOK = {"X-Telegram-Bot-Api-Secret-Token": WEBHOOK_SECRET}
HEADERS = {"X-Service-Token": SERVICE_TOKEN}
URL = "/telegram/webhook"


def text_update(update_id=10, text="hola", chat_id=77, user_id=55):
    return {
        "update_id": update_id,
        "message": {
            "message_id": 90,
            "from": {"id": user_id},
            "chat": {"id": chat_id},
            "text": text,
        },
    }


def make_client(*, whatsapp=None):
    settings = Settings(
        service_token=SERVICE_TOKEN,
        telegram_webhook_secret=WEBHOOK_SECRET,
        telegram_bot_token="123456:BOT",
        dedup_ttl_seconds=123,
    )
    telegram = FakeTelegramClient()
    dedup = FakeDedupStore()
    adapters = Adapters(
        telegram,
        dedup,
        FakeOrchestratorClient(),
        whatsapp=whatsapp,
    )
    return TestClient(create_app(settings, adapters)), telegram, dedup


# ── R1, R3: normalización de Telegram ────────────────────────────────────────


def test_telegram_update_is_normalized_to_common_message():
    """R1, R3: el update Telegram se traduce al mensaje normalizado."""
    incoming = extract_incoming(text_update(update_id=10, text="hola"))
    message = normalize_incoming(incoming, adapters_time())
    assert (
        message.channel,
        message.external_user_id,
        message.external_chat_id,
        message.external_message_id,
        message.kind,
        message.text,
    ) == ("telegram", "55", "77", "10", "text", "hola")


def test_non_text_telegram_update_is_normalized_as_unsupported():
    """R1, R3: un update sin texto se representa como no soportado."""
    incoming = extract_incoming(
        {"update_id": 5, "message": {"from": {"id": 1}, "chat": {"id": 2}, "voice": {}}}
    )
    message = normalize_incoming(incoming, adapters_time())
    assert message.kind == "unsupported" and message.text is None


def test_webhook_uses_composed_dedup_key():
    """R5, R6: el webhook deduplica por (canal, mensaje externo)."""
    client, _, dedup = make_client()
    client.post(URL, json=text_update(update_id=42), headers=HOOK)
    client.post(URL, json=text_update(update_id=42), headers=HOOK)
    assert ("telegram", "42") in dedup.message_keys
    assert dedup.keys == {42: 123}


def test_canonical_send_uses_injected_whatsapp_adapter():
    """R4, R7: /send canónico usa el adaptador inyectado y sus capacidades."""
    whatsapp = FakeWhatsAppAdapter()
    client, _telegram, _dedup = make_client(whatsapp=whatsapp)
    response = client.post(
        "/send",
        json={
            "channel": "whatsapp",
            "destination": "57300",
            "blocks": [{"type": "text", "text": "Hola"}],
        },
        headers=HEADERS,
    )
    assert response.status_code == 200
    assert whatsapp.sent[0][0] == "57300"


def test_canonical_send_fails_closed_outside_window():
    """R8: el envío canónico de texto libre falla cerrado fuera de ventana."""
    whatsapp = FakeWhatsAppAdapter(window_open=False)
    client, _telegram, _dedup = make_client(whatsapp=whatsapp)
    response = client.post(
        "/send",
        json={
            "channel": "whatsapp",
            "destination": "57300",
            "blocks": [{"type": "text", "text": "Hola"}],
        },
        headers=HEADERS,
    )
    assert response.status_code == 422
    assert response.json()["error"] == "validation_error"
    assert whatsapp.sent == []


def test_canonical_send_allows_approved_template():
    """R9: fuera de ventana una plantilla aprobada sí se envía."""
    whatsapp = FakeWhatsAppAdapter(
        window_open=False, approved_templates={"aviso"}
    )
    client, _telegram, _dedup = make_client(whatsapp=whatsapp)
    response = client.post(
        "/send",
        json={
            "channel": "whatsapp",
            "destination": "57300",
            "blocks": [{"type": "template", "name": "aviso", "variables": ["hoy"]}],
        },
        headers=HEADERS,
    )
    assert response.status_code == 200
    assert whatsapp.sent


def test_canonical_send_without_adapter_returns_502():
    """R7: sin adaptador para el canal el gateway falla cerrado."""
    client, _telegram, _dedup = make_client(whatsapp=None)
    response = client.post(
        "/send",
        json={
            "channel": "whatsapp",
            "destination": "57300",
            "blocks": [{"type": "text", "text": "Hola"}],
        },
        headers=HEADERS,
    )
    assert response.status_code == 502
    assert response.json()["error"] == "upstream_error"


def test_telegram_adapter_renders_abstract_blocks():
    """R2, R3, R10: el adaptador Telegram representa el contenido de los bloques."""
    blocks = [
        TextBlock(type="text", text="Elige una opción:"),
        OptionsBlock(type="options", options=["Pedidos", "Pagos"]),
        ListBlock(type="list", options=["Uno", "Dos", "Tres", "Cuatro"]),
        LinkBlock(type="link", text="Abrir", url="https://example.com"),
    ]
    text = render_blocks(blocks)
    assert "Elige una opción:" in text
    assert "Pedidos" in text and "Pagos" in text
    assert "Cuatro" in text
    assert "https://example.com" in text


def test_telegram_adapter_send_keeps_legacy_text_delivery():
    """R3: el adaptador común envía con el cliente Telegram existente."""
    client = FakeTelegramClient()
    adapter = TelegramChannelAdapter(client)
    status = adapter.send("77", [TextBlock(type="text", text="hola")])
    assert status == "sent"
    assert client.sent == [(77, "hola")]
    assert client.reply_markups == [None]


def test_telegram_adapter_sends_signed_options_as_inline_keyboard():
    """R38: las opciones con IDs canónicos se pintan como botones interactivos."""
    client = FakeTelegramClient()
    adapter = TelegramChannelAdapter(client)
    blocks = [
        TextBlock(type="text", text="¿Aceptas?"),
        OptionsBlock(
            type="options",
            options=["Acepto", "No acepto"],
            option_ids=["privacy.accept", "privacy.reject"],
            option_proofs=["a" * 32, "b" * 32],
        ),
    ]
    status = adapter.send("77", blocks)
    assert status == "sent"
    assert build_inline_keyboard(blocks) == {
        "inline_keyboard": [
            [
                {
                    "text": "Acepto",
                    "callback_data": f"privacy.accept:{'a' * 32}",
                },
                {
                    "text": "No acepto",
                    "callback_data": f"privacy.reject:{'b' * 32}",
                },
            ]
        ]
    }
    assert client.reply_markups[-1] == {
        "inline_keyboard": [
            [
                {
                    "text": "Acepto",
                    "callback_data": f"privacy.accept:{'a' * 32}",
                },
                {
                    "text": "No acepto",
                    "callback_data": f"privacy.reject:{'b' * 32}",
                },
            ]
        ]
    }


def test_options_without_ids_keep_legacy_text_rendering():
    """R3, R38: sin metadatos de botón no se envía teclado interactivo."""
    client = FakeTelegramClient()
    adapter = TelegramChannelAdapter(client)
    adapter.send(
        "77",
        [OptionsBlock(type="options", options=["Pedidos", "Pagos"])],
    )
    assert client.reply_markups == [None]
    assert "Pedidos" in client.sent[0][1]


def test_http_telegram_client_sends_reply_markup(monkeypatch):
    """R38: el cliente HTTP incluye `reply_markup` sin abrir red real."""
    calls = {}

    def fake_post(url, **kwargs):
        calls["json"] = kwargs["json"]
        return httpx.Response(200, request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx, "post", fake_post)
    from telegram_gateway.adapters.telegram import HttpTelegramClient

    markup = {"inline_keyboard": [[{"text": "Acepto", "callback_data": "privacy.accept:abc"}]]}
    HttpTelegramClient("123:BOT").send_message(7, "hola", reply_markup=markup)
    assert calls["json"]["reply_markup"] == markup


# ── R4, R7-R9, R12: adaptador falso de WhatsApp ─────────────────────────────


def test_fake_whatsapp_normalizes_text_and_button_messages():
    """R4: el adaptador falso normaliza texto y botón sin red."""
    adapter = FakeWhatsAppAdapter()
    text = adapter.normalize_incoming(
        {"from": "57300", "message_id": "m1", "type": "text", "text": "Hola"},
        adapters_time(),
    )
    button = adapter.normalize_incoming(
        {
            "from": "57300",
            "message_id": "m2",
            "type": "button",
            "button_id": "acepto",
        },
        adapters_time(),
    )
    assert (text.channel, text.kind, text.text) == ("whatsapp", "text", "Hola")
    assert (button.kind, button.button_id) == ("button", "acepto")


def test_fake_whatsapp_capabilities_follow_window():
    """R4, R8: la ventana cerrada prohíbe texto y exige plantilla."""
    open_adapter = FakeWhatsAppAdapter(window_open=True)
    closed_adapter = FakeWhatsAppAdapter(window_open=False)
    assert open_adapter.capabilities().free_text_allowed is True
    assert open_adapter.capabilities().requires_template is False
    closed = closed_adapter.capabilities()
    assert closed.free_text_allowed is False and closed.requires_template is True


def test_fake_whatsapp_sends_text_inside_window():
    """R4: con la ventana abierta el fake registra los bloques enviados."""
    adapter = FakeWhatsAppAdapter()
    blocks = [TextBlock(type="text", text="Hola")]
    assert adapter.send("57300", blocks) == "sent"
    assert adapter.sent == [("57300", blocks)]


def test_closed_window_rejects_free_text():
    """R8: fuera de ventana el adaptador rechaza texto libre."""
    adapter = FakeWhatsAppAdapter(window_open=False)
    with pytest.raises(ChannelWindowClosed):
        adapter.send("57300", [TextBlock(type="text", text="Hola")])
    assert adapter.sent == []


def test_closed_window_allows_approved_template_only():
    """R9: fuera de ventana solo pasa una plantilla aprobada."""
    adapter = FakeWhatsAppAdapter(window_open=False, approved_templates={"aviso"})
    approved = TemplateBlock(type="template", name="aviso", variables=["hoy"])
    assert adapter.send("57300", [approved]) == "sent"
    with pytest.raises(TemplateNotApproved):
        adapter.send("57300", [TemplateBlock(type="template", name="otra")])


def test_core_checks_capabilities_before_send():
    """R7: el núcleo consulta capabilities() antes de llamar a send()."""
    calls: list[str] = []

    class SpyAdapter:
        channel = "whatsapp"

        def capabilities(self):
            calls.append("capabilities")
            return ChannelCapabilities(
                free_text_allowed=False,
                max_options=3,
                min_list_options=4,
                max_list_options=10,
                supports_links=True,
                requires_template=True,
            )

        def send(self, destination, blocks):
            calls.append("send")
            return "sent"

    with pytest.raises(ChannelWindowClosed):
        send_response(SpyAdapter(), "57300", [TextBlock(type="text", text="Hola")])
    assert calls == ["capabilities"]


def test_send_failure_is_simulable_and_status_is_common_vocabulary():
    """R4, R12: el fake permite fallos y traduce estados al vocabulario común."""
    adapter = FakeWhatsAppAdapter(fail=True)
    with pytest.raises(ChannelSendFailed):
        adapter.send("57300", [TextBlock(type="text", text="Hola")])
    for raw, expected in (
        ("sent", "sent"),
        ("delivered", "delivered"),
        ("read", "read"),
        ("failed", "failed"),
        ("SENT", "sent"),
        ("desconocido", "failed"),
    ):
        assert adapter.delivery_status(raw) == expected


# ── R5, R6: deduplicación por canal ─────────────────────────────────────────


def test_dedup_store_isolates_same_id_between_channels():
    """R5, R6: el mismo id en dos canales se procesa una vez por canal."""
    store = FakeDedupStore()
    assert store.mark_message_if_new("whatsapp", "1", 60) is True
    assert store.mark_message_if_new("whatsapp", "1", 60) is False
    assert store.mark_message_if_new("telegram", "1", 60) is True
    assert store.mark_message_if_new("telegram", "1", 60) is False


def test_redis_dedup_key_includes_channel():
    """R5, R6: la clave persistente no usa el id externo aislado."""
    class FakeRedis:
        def __init__(self, legacy=()):
            self.keys = []
            self.stored = set(legacy)

        def exists(self, key):
            return key in self.stored

        def set(self, key, value, nx=False, ex=None):
            self.keys.append(key)
            if nx and key in self.stored:
                return None
            self.stored.add(key)
            return True

    store = RedisDedupStore("redis://localhost:6379/0")
    store._client = FakeRedis()
    store.mark_message_if_new("whatsapp", "m1", 60)
    store.mark_message_if_new("telegram", "m1", 60)
    assert store._client.keys == [
        "gw:message:whatsapp:m1",
        "gw:message:telegram:m1",
        "gw:update:m1",
    ]


def test_redis_dedup_preserves_legacy_update_key():
    """R5: una clave `gw:update:*` histórica sigue descartando el repetido."""
    class FakeRedis:
        def __init__(self):
            self.keys = []
            self.stored = {"gw:update:9"}

        def exists(self, key):
            return key in self.stored

        def set(self, key, value, nx=False, ex=None):
            self.keys.append(key)
            if nx and key in self.stored:
                return None
            self.stored.add(key)
            return True

    store = RedisDedupStore("redis://localhost:6379/0")
    store._client = FakeRedis()
    assert store.mark_message_if_new("telegram", "9", 60) is False
    assert "gw:message:telegram:9" in store._client.stored
    assert store.mark_message_if_new("whatsapp", "9", 60) is True


def test_fake_dedup_preserves_legacy_update_key():
    """R5: la versión falsa también consulta las claves históricas."""
    store = FakeDedupStore()
    store.keys[5] = 60
    assert store.mark_message_if_new("telegram", "5", 60) is False
    assert store.mark_message_if_new("whatsapp", "5", 60) is True


# ── R10, R11: equivalencia y ausencia de red ────────────────────────────────


def test_both_adapters_preserve_the_same_abstract_response():
    """R10: Telegram y WhatsApp conservan el contenido y el significado."""
    blocks = [
        TextBlock(type="text", text="Elige:"),
        OptionsBlock(type="options", options=["Sí", "No"]),
        LinkBlock(type="link", text="Ayuda", url="https://example.com/ayuda"),
    ]
    telegram_text = render_blocks(blocks)
    whatsapp = FakeWhatsAppAdapter()
    whatsapp.send("57300", blocks)
    sent_blocks = whatsapp.sent[0][1]
    assert [block.model_dump() for block in sent_blocks] == [
        block.model_dump() for block in blocks
    ]
    assert "Elige:" in telegram_text and "Sí" in telegram_text
    assert "https://example.com/ayuda" in telegram_text


def test_no_network_is_used(monkeypatch):
    """R11: las pruebas no dependen de red ni credenciales externas."""
    def boom(*args, **kwargs):
        raise AssertionError("no debe abrirse una conexión real")

    monkeypatch.setattr(httpx, "post", boom)
    telegram = TelegramChannelAdapter(FakeTelegramClient())
    whatsapp = FakeWhatsAppAdapter()
    telegram.send("1", [TextBlock(type="text", text="hola")])
    whatsapp.send("57300", [TextBlock(type="text", text="hola")])
    assert telegram.delivery_status("delivered") == "delivered"


def adapters_time():
    from datetime import datetime, timezone

    return datetime(2026, 11, 3, 16, 5, 12, tzinfo=timezone.utc)
