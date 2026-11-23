"""Fase 6: TikTok Business Messaging, sin llamadas de red reales."""
from __future__ import annotations

import json
from datetime import datetime, timezone

import httpx
import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from lazaro_contracts import TextBlock
from pydantic import SecretStr

from telegram_gateway.adapters.channel_repository import FakeChannelRepository
from telegram_gateway.adapters.channels.tiktok import ChannelTokenStore, TikTokChannel
from telegram_gateway.adapters.dedup import FakeDedupStore
from telegram_gateway.adapters.orchestrator import FakeOrchestratorClient
from telegram_gateway.adapters.telegram import FakeTelegramClient
from telegram_gateway.adapters.tiktok_api import (
    AUTH_ERROR_CODES,
    FakeTikTokApi,
    HttpTikTokApi,
    TikTokApiError,
    TikTokAuthError,
)
from telegram_gateway.adapters.tiktok_quota import (
    TIKTOK_MESSAGES_PER_WINDOW,
    FakeTikTokMessageQuotaStore,
)
from telegram_gateway.config import Settings
from telegram_gateway.domain import Adapters, ChannelSeed, ChannelSecrets
from telegram_gateway.main import create_app
from telegram_gateway.secret_cipher import SecretCipher
from telegram_gateway.tiktok import (
    TikTokTokenInvalid,
    TikTokTokens,
    parse_tiktok_webhook,
    tiktok_signature,
    tokens_from_refresh,
    verify_tiktok_signature,
)

NOW = datetime(2026, 11, 23, 12, 0, tzinfo=timezone.utc)
APP_KEY = "tiktok-app-key"
APP_SECRET = "tiktok-app-secret"
WEBHOOK_SECRET = "tiktok-webhook-secret"
SERVICE_TOKEN = "service-token-for-tests"
BUSINESS_ID = "business-open-id"
CUSTOMER_ID = "customer-open-id"
CONVERSATION_ID = "conversation-1"


def _payload(**content_overrides) -> dict:
    content = {
        "from": "customer",
        "to": "business",
        "unique_identifier": CUSTOMER_ID,
        "from_user": {"id": CUSTOMER_ID, "role": "personal_account"},
        "to_user": {"id": BUSINESS_ID, "role": "business_account"},
        "conversation_id": CONVERSATION_ID,
        "message_id": "message-1",
        "timestamp": int(NOW.timestamp() * 1000),
        "type": "text",
        "text": {"body": "Hola desde TikTok"},
    }
    content.update(content_overrides)
    return {
        "client_key": APP_KEY,
        "event": "im_receive_msg",
        "create_time": int(NOW.timestamp()),
        "user_openid": BUSINESS_ID,
        "content": json.dumps(content),
    }


def _channel_secret_key() -> str:
    return Fernet.generate_key().decode("ascii")


def _test_app(api: FakeTikTokApi | None = None, webhook_secret: str = WEBHOOK_SECRET):
    key = _channel_secret_key()
    settings = Settings(
        service_token=SERVICE_TOKEN,
        telegram_webhook_secret="telegram-hook",
        telegram_bot_token="123456:BOT-TOKEN",
        channel_secrets_key=SecretStr(key),
        tiktok_enabled=True,
        tiktok_client_key=APP_KEY,
        tiktok_client_secret=SecretStr(APP_SECRET),
        tiktok_webhook_secret=SecretStr(webhook_secret),
        tiktok_business_id=BUSINESS_ID,
        tiktok_refresh_token=SecretStr("initial-refresh"),
    )
    repository = FakeChannelRepository(clock=lambda: NOW)
    orchestrator = FakeOrchestratorClient()
    adapters = Adapters(
        telegram=FakeTelegramClient(),
        dedup=FakeDedupStore(),
        orchestrator=orchestrator,
        clock=lambda: NOW,
        channels=repository,
        tiktok=api if api is not None else FakeTikTokApi(),
    )
    return TestClient(create_app(settings, adapters)), settings, repository, orchestrator


def test_tiktok_enabled_requires_app_account_and_encryption_configuration():
    """R1: TikTok no se activa si faltan credenciales de app, cuenta o cifrado."""
    with pytest.raises(ValueError, match="TIKTOK_CLIENT_KEY"):
        Settings(tiktok_enabled=True)


def test_tiktok_signature_verifies_raw_body_and_timestamp():
    """R1: valida HMAC del cuerpo crudo y rechaza firma incorrecta o vencida."""
    body = b'{"message":"hola"}'
    timestamp = int(NOW.timestamp())
    signature = tiktok_signature(APP_SECRET, timestamp, body)
    header = f"t={timestamp},s={signature}"
    old_timestamp = timestamp - 31
    old_header = (
        f"t={old_timestamp},s={tiktok_signature(APP_SECRET, old_timestamp, body)}"
    )

    assert verify_tiktok_signature(APP_SECRET, body, header, NOW)
    assert not verify_tiktok_signature(APP_SECRET, body + b" ", header, NOW)
    assert not verify_tiktok_signature(APP_SECRET, body, old_header, NOW, 30)
    assert not verify_tiktok_signature("", body, header, NOW)


def test_tiktok_webhook_normalizes_the_official_message_schema():
    """R2: convierte im_receive_msg y su content JSON al contrato normalizado."""
    [message] = parse_tiktok_webhook(_payload(), BUSINESS_ID, NOW)

    assert message.channel == "tiktok"
    assert message.external_user_id == CUSTOMER_ID
    assert message.external_chat_id == CONVERSATION_ID
    assert message.external_message_id == "message-1"
    assert message.kind == "text"
    assert message.text == "Hola desde TikTok"
    assert message.received_at == NOW


@pytest.mark.parametrize(
    "payload",
    [
        {**_payload(), "event": "im_send_msg"},
        {**_payload(), "event": "im_receive_msg_eu"},
        {**_payload(), "user_openid": "another-business"},
        {**_payload(), "content": "not-json"},
    ],
)
def test_tiktok_ignores_events_that_cannot_be_safely_processed(payload):
    """R2, R3: ignora ecos, otros eventos, otra cuenta y payloads malformados."""
    assert parse_tiktok_webhook(payload, BUSINESS_ID, NOW) == []


def test_tiktok_ignores_messages_sent_by_the_business_account():
    """R3: una notificación de salida no vuelve a entrar como mensaje del cliente."""
    payload = _payload(
        unique_identifier=None,
        from_user={"id": BUSINESS_ID, "role": "business_account"},
    )
    assert parse_tiktok_webhook(payload, BUSINESS_ID, NOW) == []


def test_tiktok_non_text_and_oversized_messages_are_not_truncated():
    """R4: multimedia y texto sobre el límite se normalizan como unsupported."""
    media = _payload(type="image", text=None)
    oversized = _payload(text={"body": "x" * 5000})

    [media_message] = parse_tiktok_webhook(media, BUSINESS_ID, NOW)
    [oversized_message] = parse_tiktok_webhook(oversized, BUSINESS_ID, NOW)
    assert media_message.kind == "unsupported"
    assert oversized_message.kind == "unsupported"
    assert oversized_message.text is None


def test_tiktok_refresh_response_rotates_encrypted_credentials():
    """R5: acepta la respuesta oficial y conserva el refresh token nuevo."""
    tokens = tokens_from_refresh(
        {
            "code": 0,
            "data": {
                "access_token": "access-2",
                "expires_in": 86400,
                "refresh_token": "refresh-2",
                "refresh_token_expires_in": 31536000,
            },
        },
        "refresh-1",
        NOW,
    )

    assert tokens == TikTokTokens(
        "access-2",
        "refresh-2",
        NOW.replace(day=24),
        NOW.replace(year=2027, day=23),
    )
    with pytest.raises(TikTokTokenInvalid):
        tokens_from_refresh({"code": 40103}, "expired", NOW)


def test_http_tiktok_api_uses_business_refresh_payload_and_access_token_header():
    """R5, R6: usa JSON OAuth oficial y clasifica errores sin filtrar secretos."""
    requests: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path.endswith("refresh_token/"):
            return httpx.Response(
                200,
                json={"code": 0, "data": {"access_token": "access-1"}},
            )
        return httpx.Response(200, json={"code": 0})

    client = httpx.Client(transport=httpx.MockTransport(respond))
    api = HttpTikTokApi(
        "https://business-api.example/refresh_token/",
        "https://business-api.example/send/",
        client,
    )
    api.refresh_token(APP_KEY, APP_SECRET, "refresh-1")
    api.send_message("access-1", {"message_type": "TEXT"})

    assert requests[0].method == "POST"
    assert json.loads(requests[0].read()) == {
        "client_id": APP_KEY,
        "client_secret": APP_SECRET,
        "grant_type": "refresh_token",
        "refresh_token": "refresh-1",
    }
    assert requests[1].headers["Access-Token"] == "access-1"


@pytest.mark.parametrize("code", sorted(AUTH_ERROR_CODES))
def test_tiktok_api_classifies_expired_access_token_codes(code):
    """R6: solo códigos documentados de token activan la renovación OAuth."""

    def respond(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"code": code, "message": "invalid token"})

    api = HttpTikTokApi(
        "https://business-api.example/refresh_token/",
        "https://business-api.example/send/",
        httpx.Client(transport=httpx.MockTransport(respond)),
    )
    with pytest.raises(TikTokAuthError):
        api.send_message("expired", {})


@pytest.mark.parametrize("status_code", [200, 401])
def test_tiktok_quota_error_is_not_mistaken_for_an_auth_error(status_code):
    """R6: un límite de solicitudes no fuerza la rotación del token."""

    def respond(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status_code, json={"code": 40100, "message": "rate limit"}
        )

    api = HttpTikTokApi(
        "https://business-api.example/refresh_token/",
        "https://business-api.example/send/",
        httpx.Client(transport=httpx.MockTransport(respond)),
    )
    with pytest.raises(TikTokApiError) as error:
        api.send_message("access", {})
    assert not isinstance(error.value, TikTokAuthError)


def test_tiktok_channel_refreshes_and_saves_rotated_tokens_encrypted():
    """R5: refresca antes de enviar y persiste el refresh token cifrado."""
    key = _channel_secret_key()
    cipher = SecretCipher(key)
    repository = FakeChannelRepository(clock=lambda: NOW)
    repository.seed(
        [(ChannelSeed("tiktok", "TikTok", "tiktok", "tiktok", "#111827"), True)]
    )
    store = ChannelTokenStore(repository, cipher, "tiktok")
    api = FakeTikTokApi(
        refresh_responses=[
            {
                "code": 0,
                "data": {
                    "access_token": "access-2",
                    "expires_in": 86400,
                    "refresh_token": "refresh-2",
                    "refresh_token_expires_in": 31536000,
                },
            }
        ],
        valid_tokens={"access-2"},
    )
    quota = FakeTikTokMessageQuotaStore()
    channel = TikTokChannel(
        api,
        store,
        lambda: NOW,
        client_key=APP_KEY,
        client_secret=APP_SECRET,
        business_id=BUSINESS_ID,
        bootstrap_refresh_token="refresh-1",
        quota=quota,
    )
    [incoming] = parse_tiktok_webhook(_payload(), BUSINESS_ID, NOW)
    channel.registrar_entrada(incoming)

    assert channel.enviar_mensaje(
        CONVERSATION_ID, [TextBlock(type="text", text="Respuesta")]
    ) == "sent"
    assert api.refresh_calls == ["refresh-1"]
    assert api.sent[0][0] == "access-2"
    assert api.sent[0][1]["recipient"] == CONVERSATION_ID
    saved = store.load()
    assert saved is not None and saved.refresh_token == "refresh-2"
    assert quota.values[CONVERSATION_ID] == 1
    encrypted = repository.get_encrypted_secrets("tiktok")
    assert encrypted is not None
    assert "refresh-2" not in encrypted


def test_tiktok_message_quota_is_ten_per_window_and_resets_on_inbound():
    """R8: limita los envíos a diez por conversación y reinicia ante una entrada nueva."""
    quota = FakeTikTokMessageQuotaStore()
    quota.record_inbound(CONVERSATION_ID)

    assert all(
        quota.reserve_send(CONVERSATION_ID, TIKTOK_MESSAGES_PER_WINDOW)
        for _ in range(TIKTOK_MESSAGES_PER_WINDOW)
    )
    assert not quota.reserve_send(CONVERSATION_ID, TIKTOK_MESSAGES_PER_WINDOW)

    quota.record_inbound(CONVERSATION_ID)
    assert quota.reserve_send(CONVERSATION_ID, TIKTOK_MESSAGES_PER_WINDOW)


def test_tiktok_webhook_is_public_signed_and_forwarded_to_orchestrator():
    """R7: la ruta pública valida firma TikTok y entrega el mensaje sin token interno."""
    client, _, _, orchestrator = _test_app()
    body = json.dumps(_payload(), separators=(",", ":")).encode()
    timestamp = int(NOW.timestamp())
    signature = tiktok_signature(WEBHOOK_SECRET, timestamp, body)

    response = client.post(
        "/webhooks/tiktok",
        content=body,
        headers={
            "Content-Type": "application/json",
            "TikTok-Signature": f"t={timestamp},s={signature}",
        },
    )

    assert response.status_code == 200
    assert len(orchestrator.received) == 1
    message = orchestrator.received[0]
    assert message.channel == "tiktok"
    assert message.external_message_id == "message-1"
    assert message.text == "Hola desde TikTok"


def test_tiktok_webhook_rejects_invalid_signature_without_forwarding():
    """R1, R7: una firma incorrecta recibe 401 y nunca llega al orquestador."""
    client, _, _, orchestrator = _test_app()
    body = json.dumps(_payload(), separators=(",", ":")).encode()

    response = client.post(
        "/webhooks/tiktok",
        content=body,
        headers={"TikTok-Signature": "t=1795435200,s=invalid"},
    )

    assert response.status_code == 401
    assert orchestrator.received == []


def _signed_headers(body: bytes, secret: str = WEBHOOK_SECRET) -> dict[str, str]:
    timestamp = int(NOW.timestamp())
    return {
        "Content-Type": "application/json",
        "TikTok-Signature": f"t={timestamp},s={tiktok_signature(secret, timestamp, body)}",
    }


def test_tiktok_webhook_without_webhook_secret_rejects_everything():
    """Fase 6: sin TIKTOK_WEBHOOK_SECRET ni una firma "válida" pasa (fallo cerrado)."""
    client, _, _, orchestrator = _test_app(webhook_secret="")
    body = json.dumps(_payload(), separators=(",", ":")).encode()

    for secret in ("", APP_SECRET):
        response = client.post(
            "/webhooks/tiktok", content=body, headers=_signed_headers(body, secret)
        )
        assert response.status_code == 401
    assert orchestrator.received == []


def test_tiktok_webhook_signed_with_client_secret_is_rejected():
    """Fase 6: la firma se verifica con TIKTOK_WEBHOOK_SECRET y no con otro secreto."""
    client, _, _, orchestrator = _test_app()
    body = json.dumps(_payload(), separators=(",", ":")).encode()

    response = client.post(
        "/webhooks/tiktok", content=body, headers=_signed_headers(body, APP_SECRET)
    )

    assert response.status_code == 401
    assert orchestrator.received == []


def _seeded_store() -> tuple[FakeChannelRepository, ChannelTokenStore]:
    repository = FakeChannelRepository(clock=lambda: NOW)
    repository.seed(
        [(ChannelSeed("tiktok", "TikTok", "tiktok", "tiktok", "#111827"), True)]
    )
    store = ChannelTokenStore(repository, SecretCipher(_channel_secret_key()), "tiktok")
    return repository, store


def _refresh_response(access: str, refresh: str) -> dict:
    return {
        "code": 0,
        "data": {
            "access_token": access,
            "expires_in": 86400,
            "refresh_token": refresh,
            "refresh_token_expires_in": 31536000,
        },
    }


def _channel(api: FakeTikTokApi, store: ChannelTokenStore) -> TikTokChannel:
    return TikTokChannel(
        api,
        store,
        lambda: NOW,
        client_key=APP_KEY,
        client_secret=APP_SECRET,
        webhook_secret=WEBHOOK_SECRET,
        business_id=BUSINESS_ID,
    )


def test_tiktok_expired_stored_token_is_refreshed_before_sending():
    """Fase 6: un access token vencido en `canales` se renueva antes de enviar."""
    _, store = _seeded_store()
    store.save(
        TikTokTokens(
            "access-old",
            "refresh-old",
            NOW.replace(hour=11),  # venció hace una hora
            NOW.replace(year=2027),
        )
    )
    api = FakeTikTokApi(
        refresh_responses=[_refresh_response("access-new", "refresh-new")],
        valid_tokens={"access-new"},
    )

    status = _channel(api, store).enviar_mensaje(
        CONVERSATION_ID, [TextBlock(type="text", text="Respuesta")]
    )

    assert status == "sent"
    assert api.refresh_calls == ["refresh-old"]
    assert api.rejected == []  # no se intentó con el token vencido
    assert [token for token, _ in api.sent] == ["access-new"]
    assert store.load().refresh_token == "refresh-new"


def test_tiktok_token_rejected_by_api_is_refreshed_and_send_retried():
    """Fase 6: si TikTok rechaza un token aún vigente, se refresca y se reintenta una vez."""
    _, store = _seeded_store()
    store.save(
        TikTokTokens(
            "access-revoked",
            "refresh-1",
            NOW.replace(day=24),  # vigente según la hora local
            NOW.replace(year=2027),
        )
    )
    api = FakeTikTokApi(
        refresh_responses=[_refresh_response("access-2", "refresh-2")],
        valid_tokens={"access-2"},
    )

    status = _channel(api, store).enviar_mensaje(
        CONVERSATION_ID, [TextBlock(type="text", text="Respuesta")]
    )

    assert status == "sent"
    assert api.rejected == ["access-revoked"]
    assert api.refresh_calls == ["refresh-1"]
    assert [token for token, _ in api.sent] == ["access-2"]
    assert store.load().access_token == "access-2"


def test_tiktok_refresh_retry_happens_only_once():
    """Fase 6: si tras refrescar el token sigue sin valer, no hay bucle de refrescos."""
    _, store = _seeded_store()
    store.save(
        TikTokTokens("access-1", "refresh-1", NOW.replace(day=24), NOW.replace(year=2027))
    )
    api = FakeTikTokApi(
        refresh_responses=[_refresh_response("access-2", "refresh-2")],
        valid_tokens=set(),
    )

    status = _channel(api, store).enviar_mensaje(
        CONVERSATION_ID, [TextBlock(type="text", text="Respuesta")]
    )

    assert status == "failed"
    assert api.refresh_calls == ["refresh-1"]
    assert api.rejected == ["access-1", "access-2"]


def test_tiktok_chart_image_arrives_as_link():
    """Fase 6: supports_images=False; un gráfico (ImageBlock) sale como enlace en texto."""
    api = FakeTikTokApi(
        refresh_responses=[_refresh_response("access-1", "refresh-1")],
    )
    client, _, _, _ = _test_app(api)
    chart_url = "https://bot.example.com/media/graficos/abc.png?exp=1&sig=f00"

    response = client.post(
        "/send",
        json={
            "channel": "tiktok",
            "destination": CONVERSATION_ID,
            "blocks": [
                {"type": "image", "url": chart_url, "alt_text": "Casos por estado"},
                {"type": "text", "text": "«abierto» es el mayor con 5 de 8."},
            ],
        },
        headers={"X-Service-Token": SERVICE_TOKEN},
    )

    assert response.status_code == 200
    [(_, payload)] = api.sent
    assert payload["recipient"] == CONVERSATION_ID
    text = json.dumps(payload, ensure_ascii=False)
    assert f"Casos por estado: {chart_url}" in text
    assert "«abierto» es el mayor" in text
