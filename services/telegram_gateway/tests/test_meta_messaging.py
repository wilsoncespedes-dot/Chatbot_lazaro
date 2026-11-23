"""Fase 7: Messenger e Instagram Messaging de Meta, con dobles locales."""
from __future__ import annotations

import hashlib
import hmac
import json
from datetime import datetime, timezone

import httpx
import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from lazaro_contracts import ImageBlock, TextBlock
from pydantic import SecretStr

from telegram_gateway.adapters.channel_repository import FakeChannelRepository
from telegram_gateway.adapters.channels.meta_messenger import (
    FacebookMessengerChannel,
    InstagramMessagingChannel,
    MetaPageTokenStore,
)
from telegram_gateway.adapters.dedup import FakeDedupStore
from telegram_gateway.adapters.meta_messaging import (
    FakeMetaMessagingApi,
    HttpMetaMessagingApi,
    MAX_META_TEXT_BYTES,
    split_meta_text,
)
from telegram_gateway.adapters.meta_window import FakeMetaMessageWindowStore
from telegram_gateway.adapters.orchestrator import FakeOrchestratorClient
from telegram_gateway.adapters.telegram import FakeTelegramClient
from telegram_gateway.config import Settings
from telegram_gateway.domain import Adapters, ChannelSeed
from telegram_gateway.domain import ChannelWindowClosed
from telegram_gateway.main import create_app
from telegram_gateway.secret_cipher import SecretCipher
from telegram_gateway.meta_messaging import (
    META_FACEBOOK_CHANNEL,
    META_INSTAGRAM_CHANNEL,
    meta_channel_for_payload,
    meta_channels_for_payload,
    parse_meta_webhook,
)

NOW = datetime(2026, 11, 23, 12, 0, tzinfo=timezone.utc)
PAGE_ID = "page-123"
INSTAGRAM_ID = "instagram-456"
APP_SECRET = "meta-app-secret"
VERIFY_TOKEN = "verify-token"
PAGE_TOKEN = "page-access-token"
SERVICE_TOKEN = "service-token-for-tests"
WEBHOOK = "/webhooks/messenger"
MESSENGER_USER = "psid-789"
INSTAGRAM_USER = "igsid-012"


def _event(sender: str, recipient: str, message_id: str, text: str) -> dict:
    return {
        "sender": {"id": sender},
        "recipient": {"id": recipient},
        "timestamp": int(NOW.timestamp() * 1000),
        "message": {"mid": message_id, "text": text},
    }


def _messenger_payload(message_id: str = "messenger-message-1") -> dict:
    return {
        "object": "page",
        "entry": [
            {
                "id": PAGE_ID,
                "time": int(NOW.timestamp() * 1000),
                "messaging": [
                    _event(MESSENGER_USER, PAGE_ID, message_id, "Hola por Messenger")
                ],
            }
        ],
    }


def _instagram_payload(message_id: str = "instagram-message-1") -> dict:
    return {
        "object": "instagram",
        "entry": [
            {
                "id": INSTAGRAM_ID,
                "time": int(NOW.timestamp() * 1000),
                "messaging": [
                    _event(
                        INSTAGRAM_USER,
                        INSTAGRAM_ID,
                        message_id,
                        "Hola por Instagram",
                    )
                ],
            }
        ],
    }


def _meta_app(window: FakeMetaMessageWindowStore | None = None):
    settings = Settings(
        service_token=SERVICE_TOKEN,
        telegram_webhook_secret="telegram-hook",
        telegram_bot_token="123456:BOT-TOKEN",
        channel_secrets_key=SecretStr(Fernet.generate_key().decode("ascii")),
        meta_messenger_enabled=True,
        meta_instagram_enabled=True,
        meta_page_id=PAGE_ID,
        meta_instagram_account_id=INSTAGRAM_ID,
        meta_page_access_token=SecretStr(PAGE_TOKEN),
        meta_app_secret=SecretStr(APP_SECRET),
        meta_webhook_verify_token=SecretStr(VERIFY_TOKEN),
    )
    repository = FakeChannelRepository(clock=lambda: NOW)
    orchestrator = FakeOrchestratorClient()
    meta = FakeMetaMessagingApi()
    adapters = Adapters(
        telegram=FakeTelegramClient(),
        dedup=FakeDedupStore(),
        orchestrator=orchestrator,
        clock=lambda: NOW,
        channels=repository,
        meta=meta,
        meta_window=window,
    )
    return TestClient(create_app(settings, adapters)), orchestrator, meta


def test_meta_enabled_requires_credentials_and_instagram_account_id():
    """R1: Meta no arranca habilitado sin secretos y el id requerido de Instagram."""
    with pytest.raises(ValueError, match="CHANNEL_SECRETS_KEY"):
        Settings(meta_instagram_enabled=True)
    with pytest.raises(ValueError, match="META_INSTAGRAM_ACCOUNT_ID"):
        Settings(
            meta_instagram_enabled=True,
            meta_page_id=PAGE_ID,
            channel_secrets_key=SecretStr(Fernet.generate_key().decode("ascii")),
            meta_app_secret=SecretStr(APP_SECRET),
            meta_webhook_verify_token=SecretStr(VERIFY_TOKEN),
        )


def _signature(body: bytes) -> str:
    digest = hmac.new(APP_SECRET.encode(), body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def test_messenger_webhook_normalizes_page_scoped_message():
    """R1: una notificación Page válida produce un mensaje Messenger normalizado."""
    [message] = parse_meta_webhook(
        _messenger_payload(), META_FACEBOOK_CHANNEL, PAGE_ID, INSTAGRAM_ID, NOW
    )

    assert message.channel == "facebook"
    assert message.external_user_id == MESSENGER_USER
    assert message.external_chat_id == MESSENGER_USER
    assert message.external_message_id == "messenger-message-1"
    assert message.text == "Hola por Messenger"


def test_instagram_webhook_normalizes_instagram_scoped_message():
    """R1: una notificación Instagram válida produce un mensaje normalizado."""
    [message] = parse_meta_webhook(
        _instagram_payload(), META_INSTAGRAM_CHANNEL, PAGE_ID, INSTAGRAM_ID, NOW
    )

    assert message.channel == "instagram"
    assert message.external_user_id == INSTAGRAM_USER
    assert message.external_message_id == "instagram-message-1"
    assert message.text == "Hola por Instagram"


def test_meta_normalizer_skips_echoes_and_other_pages():
    """R2, R3: no repite ecos ni acepta eventos de una página distinta."""
    echo = _messenger_payload()
    echo["entry"][0]["messaging"][0]["message"]["is_echo"] = True
    wrong_page = _messenger_payload()
    wrong_page["entry"][0]["id"] = "another-page"

    assert parse_meta_webhook(echo, "facebook", PAGE_ID, INSTAGRAM_ID, NOW) == []
    assert parse_meta_webhook(wrong_page, "facebook", PAGE_ID, INSTAGRAM_ID, NOW) == []


def test_meta_webhook_router_distinguishes_instagram_page_events():
    """R1: enruta por objeto y cuenta cuando Instagram usa el objeto Page."""
    page_shaped_instagram = {
        "object": "page",
        "entry": [
            {
                "id": PAGE_ID,
                "messaging": [_event(INSTAGRAM_USER, INSTAGRAM_ID, "m1", "Hola")],
            }
        ],
    }
    assert meta_channel_for_payload(_messenger_payload(), PAGE_ID, INSTAGRAM_ID) == "facebook"
    assert meta_channel_for_payload(_instagram_payload(), PAGE_ID, INSTAGRAM_ID) == "instagram"
    assert (
        meta_channel_for_payload(page_shaped_instagram, PAGE_ID, INSTAGRAM_ID)
        == "instagram"
    )
    mixed = {
        "object": "page",
        "entry": [
            {
                "id": PAGE_ID,
                "messaging": [
                    _event(MESSENGER_USER, PAGE_ID, "m2", "Messenger"),
                    _event(INSTAGRAM_USER, INSTAGRAM_ID, "i2", "Instagram"),
                ],
            }
        ],
    }
    assert meta_channels_for_payload(mixed, PAGE_ID, INSTAGRAM_ID) == (
        "facebook",
        "instagram",
    )


def test_meta_send_text_split_preserves_unicode_and_byte_limit():
    """R4: divide texto por bytes UTF-8 sin perder ni partir caracteres Unicode."""
    text = "Inicio " + "🙂á palabra " * 150 + "fin"
    parts = split_meta_text(text)

    assert len(parts) > 1
    assert all(len(part.encode("utf-8")) <= MAX_META_TEXT_BYTES for part in parts)
    assert "".join(parts) == text
    with pytest.raises(ValueError):
        split_meta_text("hola", 0)


def test_http_meta_send_uses_page_endpoint_and_bearer_token():
    """R4, R5: envía RESPONSE al destinatario del mismo canal sin token en URL."""
    requests: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"recipient_id": INSTAGRAM_USER, "message_id": "m1"})

    api = HttpMetaMessagingApi(
        "https://graph.facebook.com",
        "v26.0",
        PAGE_ID,
        httpx.Client(transport=httpx.MockTransport(respond)),
    )
    api.send_message("instagram", INSTAGRAM_USER, "Respuesta aprobada", PAGE_TOKEN)

    assert requests[0].url.path == f"/v26.0/{PAGE_ID}/messages"
    assert requests[0].url.query == b""
    assert requests[0].headers["Authorization"] == f"Bearer {PAGE_TOKEN}"
    assert json.loads(requests[0].read()) == {
        "recipient": {"id": INSTAGRAM_USER},
        "messaging_type": "RESPONSE",
        "message": {"text": "Respuesta aprobada"},
    }


@pytest.mark.parametrize(
    ("channel_cls", "channel", "recipient"),
    [
        (FacebookMessengerChannel, "facebook", MESSENGER_USER),
        (InstagramMessagingChannel, "instagram", INSTAGRAM_USER),
    ],
)
def test_channel_sends_to_the_original_meta_user(channel_cls, channel, recipient):
    """R4: cada canal publica la respuesta al id externo de su conversación."""
    api = FakeMetaMessagingApi()
    adapter = channel_cls(
        api,
        lambda: NOW,
        app_secret=APP_SECRET,
        page_id=PAGE_ID,
        instagram_account_id=INSTAGRAM_ID,
        page_token=PAGE_TOKEN,
    )

    assert adapter.enviar_mensaje(
        recipient, [TextBlock(type="text", text="Respuesta")]
    ) == "sent"
    assert api.sent == [(channel, recipient, "Respuesta")]


def test_meta_send_requires_an_open_standard_messaging_window():
    """R5: entrega solo dentro de la ventana iniciada por el mensaje entrante."""
    api = FakeMetaMessagingApi()
    window = FakeMetaMessageWindowStore()
    adapter = FacebookMessengerChannel(
        api,
        lambda: NOW,
        app_secret=APP_SECRET,
        page_id=PAGE_ID,
        instagram_account_id=INSTAGRAM_ID,
        page_token=PAGE_TOKEN,
        window=window,
        window_hours=24,
    )
    [message] = parse_meta_webhook(
        _messenger_payload(), "facebook", PAGE_ID, INSTAGRAM_ID, NOW
    )
    adapter.registrar_entrada(message)
    assert adapter.enviar_mensaje(
        MESSENGER_USER, [TextBlock(type="text", text="Respuesta")]
    ) == "sent"

    window.values[("facebook", MESSENGER_USER)] = NOW.replace(day=22)
    with pytest.raises(ChannelWindowClosed):
        adapter.enviar_mensaje(
            MESSENGER_USER, [TextBlock(type="text", text="Fuera de ventana")]
        )

    with pytest.raises(ChannelWindowClosed):
        adapter.enviar_mensaje(
            "sin-entrada", [TextBlock(type="text", text="Sin ventana")]
        )


def test_meta_webhook_verification_and_both_channels_are_public_and_idempotent():
    """R1-R4: handshake, firma, identidad por canal y deduplicación del webhook."""
    client, orchestrator, _ = _meta_app()
    handshake = client.get(
        WEBHOOK,
        params={
            "hub.mode": "subscribe",
            "hub.verify_token": VERIFY_TOKEN,
            "hub.challenge": "challenge-123",
        },
    )
    assert handshake.status_code == 200
    assert handshake.text == "challenge-123"

    for payload in (_messenger_payload(), _instagram_payload()):
        body = json.dumps(payload, separators=(",", ":")).encode()
        response = client.post(
            WEBHOOK,
            content=body,
            headers={"X-Hub-Signature-256": _signature(body)},
        )
        assert response.status_code == 200
        duplicate = client.post(
            WEBHOOK,
            content=body,
            headers={"X-Hub-Signature-256": _signature(body)},
        )
        assert duplicate.status_code == 200

    assert [message.channel for message in orchestrator.received] == [
        "facebook",
        "instagram",
    ]


def test_meta_webhook_rejects_invalid_signature_without_forwarding():
    """R3: la firma incorrecta responde 401 y no entrega el mensaje al núcleo."""
    client, orchestrator, _ = _meta_app()
    body = json.dumps(_messenger_payload(), separators=(",", ":")).encode()

    response = client.post(
        WEBHOOK,
        content=body,
        headers={"X-Hub-Signature-256": "sha256=invalid"},
    )

    assert response.status_code == 401
    assert orchestrator.received == []


def test_meta_webhook_forwards_both_platforms_from_a_mixed_page_batch():
    """R1, R4: un lote Page mezclado no pierde Messenger ni Instagram."""
    client, orchestrator, _ = _meta_app()
    payload = {
        "object": "page",
        "entry": [
            {
                "id": PAGE_ID,
                "messaging": [
                    _event(MESSENGER_USER, PAGE_ID, "mixed-m1", "Messenger"),
                    _event(INSTAGRAM_USER, INSTAGRAM_ID, "mixed-i1", "Instagram"),
                ],
            }
        ],
    }
    body = json.dumps(payload, separators=(",", ":")).encode()

    response = client.post(
        WEBHOOK,
        content=body,
        headers={"X-Hub-Signature-256": _signature(body)},
    )

    assert response.status_code == 200
    assert [message.channel for message in orchestrator.received] == [
        "facebook",
        "instagram",
    ]


# ── Fase 7: criterios de aceptación adicionales ─────────────────────────────


def test_meta_handshake_with_wrong_token_is_forbidden():
    """GET con verify token incorrecto no devuelve el challenge."""
    client, _, _ = _meta_app()
    response = client.get(
        WEBHOOK,
        params={
            "hub.mode": "subscribe",
            "hub.verify_token": "otro",
            "hub.challenge": "challenge-123",
        },
    )
    assert response.status_code == 403
    assert "challenge-123" not in response.text


def test_meta_echo_and_read_delivery_events_get_no_response():
    """Un eco (is_echo) o un evento read/delivery no llega al núcleo: no hay respuesta."""
    client, orchestrator, meta = _meta_app()
    echo = _messenger_payload("echo-1")
    echo["entry"][0]["messaging"][0]["message"]["is_echo"] = True
    receipts = {
        "object": "page",
        "entry": [
            {
                "id": PAGE_ID,
                "messaging": [
                    {
                        "sender": {"id": MESSENGER_USER},
                        "recipient": {"id": PAGE_ID},
                        "timestamp": 1,
                        "read": {"watermark": 1},
                    },
                    {
                        "sender": {"id": MESSENGER_USER},
                        "recipient": {"id": PAGE_ID},
                        "timestamp": 1,
                        "delivery": {"mids": ["m1"], "watermark": 1},
                    },
                ],
            }
        ],
    }
    for payload in (echo, receipts):
        body = json.dumps(payload, separators=(",", ":")).encode()
        response = client.post(
            WEBHOOK, content=body, headers={"X-Hub-Signature-256": _signature(body)}
        )
        assert response.status_code == 200
    assert orchestrator.received == []
    assert meta.sent == [] and meta.images == []


def test_old_meta_path_is_not_a_public_webhook():
    """La ruta pública es /webhooks/messenger; /meta/webhook ya no existe sin token."""
    client, _, _ = _meta_app()
    response = client.get(
        "/meta/webhook",
        params={"hub.mode": "subscribe", "hub.verify_token": VERIFY_TOKEN, "hub.challenge": "c"},
    )
    assert response.status_code == 401


def test_http_meta_send_image_uses_attachment_payload():
    """Send API: una imagen se envía como attachment por URL, con Bearer y sin token en URL."""
    requests: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"recipient_id": MESSENGER_USER, "message_id": "m1"})

    api = HttpMetaMessagingApi(
        "https://graph.facebook.com",
        "v26.0",
        PAGE_ID,
        httpx.Client(transport=httpx.MockTransport(respond)),
    )
    url = "https://bot.example.com/media/graficos/abc.png?exp=1&sig=f00"
    api.send_image("facebook", MESSENGER_USER, url, PAGE_TOKEN)

    assert requests[0].headers["Authorization"] == f"Bearer {PAGE_TOKEN}"
    assert PAGE_TOKEN not in str(requests[0].url)
    assert json.loads(requests[0].read()) == {
        "recipient": {"id": MESSENGER_USER},
        "messaging_type": "RESPONSE",
        "message": {
            "attachment": {
                "type": "image",
                "payload": {"url": url, "is_reusable": False},
            }
        },
    }


def test_meta_channel_sends_chart_as_image_then_summary_text():
    """supports_images=True: el gráfico sale como imagen y el resumen como texto, en orden."""
    api = FakeMetaMessagingApi()
    adapter = FacebookMessengerChannel(
        api,
        lambda: NOW,
        app_secret=APP_SECRET,
        page_id=PAGE_ID,
        instagram_account_id=INSTAGRAM_ID,
        page_token=PAGE_TOKEN,
    )
    url = "https://bot.example.com/media/graficos/abc.png?exp=1&sig=f00"

    status = adapter.enviar_mensaje(
        MESSENGER_USER,
        [
            ImageBlock(type="image", url=url, alt_text="Casos por estado"),
            TextBlock(type="text", text="«abierto» es el mayor."),
        ],
    )

    assert status == "sent"
    assert adapter.capacidades().supports_images is True
    assert api.images == [("facebook", MESSENGER_USER, url)]
    assert api.sent == [("facebook", MESSENGER_USER, "«abierto» es el mayor.")]


def test_meta_page_token_is_stored_encrypted_and_used_without_env():
    """El token del entorno se guarda cifrado en `canales` y basta después sin entorno."""
    cipher = SecretCipher(Fernet.generate_key().decode("ascii"))
    repository = FakeChannelRepository(clock=lambda: NOW)
    repository.seed(
        [(ChannelSeed("facebook", "Facebook", "meta_messenger", "facebook", "#0866FF"), True)]
    )
    store = MetaPageTokenStore(repository, cipher, "facebook")
    api = FakeMetaMessagingApi()

    def channel(token: str) -> FacebookMessengerChannel:
        return FacebookMessengerChannel(
            api,
            lambda: NOW,
            app_secret=APP_SECRET,
            page_id=PAGE_ID,
            instagram_account_id=INSTAGRAM_ID,
            page_token=token,
            token_store=store,
        )

    block = [TextBlock(type="text", text="Hola")]
    assert channel(PAGE_TOKEN).enviar_mensaje(MESSENGER_USER, block) == "sent"
    encrypted = repository.get_encrypted_secrets("facebook")
    assert encrypted is not None and PAGE_TOKEN not in encrypted
    assert store.load() == PAGE_TOKEN

    # Sin META_PAGE_ACCESS_TOKEN en el entorno se usa el token cifrado.
    assert channel("").enviar_mensaje(MESSENGER_USER, block) == "sent"
    # Rotación: un token nuevo en el entorno reemplaza al guardado.
    assert channel("page-token-2").enviar_mensaje(MESSENGER_USER, block) == "sent"
    assert store.load() == "page-token-2"
    assert api.tokens == [PAGE_TOKEN, PAGE_TOKEN, "page-token-2"]


def test_meta_send_outside_window_returns_channel_window_closed():
    """/send fuera de la ventana de 24 h responde 422 channel_window_closed y no envía."""
    window = FakeMetaMessageWindowStore()
    client, _, meta = _meta_app(window)
    window.values[("facebook", MESSENGER_USER)] = NOW.replace(day=21)

    response = client.post(
        "/send",
        json={
            "channel": "facebook",
            "destination": MESSENGER_USER,
            "blocks": [{"type": "text", "text": "Respuesta tardía"}],
        },
        headers={"X-Service-Token": SERVICE_TOKEN},
    )

    assert response.status_code == 422
    assert response.json()["error"] == "channel_window_closed"
    assert meta.sent == []


def test_meta_valid_message_then_reply_inside_window_is_delivered():
    """Entrada firmada abre la ventana; la respuesta por /send sale por el Send API."""
    window = FakeMetaMessageWindowStore()
    client, orchestrator, meta = _meta_app(window)
    body = json.dumps(_messenger_payload("in-1"), separators=(",", ":")).encode()
    assert client.post(
        WEBHOOK, content=body, headers={"X-Hub-Signature-256": _signature(body)}
    ).status_code == 200
    [message] = orchestrator.received
    assert message.channel == "facebook"

    response = client.post(
        "/send",
        json={
            "channel": "facebook",
            "destination": message.external_chat_id,
            "blocks": [{"type": "text", "text": "Respuesta"}],
        },
        headers={"X-Service-Token": SERVICE_TOKEN},
    )

    assert response.status_code == 200
    assert meta.sent == [("facebook", MESSENGER_USER, "Respuesta")]
