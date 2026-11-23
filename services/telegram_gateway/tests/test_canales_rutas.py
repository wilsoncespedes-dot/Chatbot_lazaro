"""R10, R15, R22–R26, R32, R34, R36–R50: rutas y aplicación del registry."""
from __future__ import annotations

import hashlib
import hmac
import json
import re
from datetime import datetime, timezone
from pathlib import Path

from cryptography.fernet import Fernet
import pytest
from fastapi.testclient import TestClient
from lazaro_contracts import ChannelCapabilities, LinkBlock
from pydantic import SecretStr

from telegram_gateway.adapters.channel_repository import (
    FakeChannelRepository,
    PostgresChannelRepository,
)
from telegram_gateway.adapters.dedup import FakeDedupStore
from telegram_gateway.adapters.orchestrator import FakeOrchestratorClient
from telegram_gateway.adapters.telegram import FakeTelegramClient
from telegram_gateway.adapters.whatsapp import FakeWhatsAppAdapter
from telegram_gateway.config import Settings
from telegram_gateway.domain import Adapters, ChannelRecord, ChannelSecrets
from telegram_gateway.main import build_default_adapters, create_app
from telegram_gateway.registry import CHANNEL_REGISTRY
from telegram_gateway.secret_cipher import SecretCipher

TOKEN = "service-token-test"
WEBHOOK_SECRET = "telegram-webhook-secret"
ROOT = Path(__file__).resolve().parents[3]


class _RecordingChannel:
    def __init__(self, *, supports_images: bool = False) -> None:
        self.supports_images = supports_images
        self.sent: list[tuple[str, list]] = []
        self.delivery_status = "sent"

    def capacidades(self, destino=None):
        return ChannelCapabilities(
            free_text_allowed=True,
            max_options=3,
            min_list_options=4,
            max_list_options=10,
            supports_links=True,
            requires_template=False,
            supports_images=self.supports_images,
        )

    def enviar_mensaje(self, destino, bloques):
        self.sent.append((destino, list(bloques)))
        return self.delivery_status

    def recibir_mensaje(self, payload):
        return None

    def identificar_usuario(self, payload):
        return None


def _app(
    *,
    repository: FakeChannelRepository | None = None,
    secret_key: str | None = None,
    whatsapp_enabled: bool = False,
    redis_ok: bool = True,
):
    repository = repository or FakeChannelRepository()
    registry = CHANNEL_REGISTRY.copy()
    instances: list[_RecordingChannel] = []
    availability = [True]

    @registry.register("tipo_prueba")
    class SimulatedFactory:
        managed_by_environment = False

        @classmethod
        def is_available(cls, context):
            return availability[0]

        @classmethod
        def build(cls, record, context, secrets):
            channel = _RecordingChannel()
            instances.append(channel)
            return channel

    whatsapp = FakeWhatsAppAdapter() if whatsapp_enabled else None
    dedup = FakeDedupStore(ping_ok=redis_ok)
    adapters = Adapters(
        telegram=FakeTelegramClient(),
        dedup=dedup,
        orchestrator=FakeOrchestratorClient(),
        whatsapp=whatsapp,
        channels=repository,
        channel_registry=registry,
    )
    settings = Settings(
        service_token=TOKEN,
        telegram_webhook_secret=WEBHOOK_SECRET,
        telegram_bot_token="123456:BOT",
        channel_secrets_key=SecretStr(
            secret_key if secret_key is not None else Fernet.generate_key().decode("ascii")
        ),
        whatsapp_enabled=whatsapp_enabled,
        whatsapp_access_token=SecretStr("access") if whatsapp_enabled else SecretStr(""),
        whatsapp_app_secret=SecretStr("meta-app-secret") if whatsapp_enabled else SecretStr(""),
        whatsapp_verify_token=SecretStr("verify") if whatsapp_enabled else SecretStr(""),
        whatsapp_phone_number_id="phone-1" if whatsapp_enabled else "",
    )
    client = TestClient(create_app(settings, adapters), raise_server_exceptions=False)
    return client, repository, adapters, instances, availability


def _create_body(**overrides) -> dict:
    body = {
        "id": "canal-demo",
        "name": "Canal demo",
        "adapter_type": "tipo_prueba",
        "icon": "chat",
        "color": "#1B6FA8",
        "config": {"modo": "demo"},
        "credentials": {"api_token": "credential-private-value"},
    }
    body.update(overrides)
    return body


def _headers() -> dict[str, str]:
    return {"X-Service-Token": TOKEN}


def test_default_adapters_use_postgres_channel_repository():
    """R27: la composición real del gateway usa PostgresChannelRepository."""
    adapters = build_default_adapters(Settings())
    assert isinstance(adapters.channels, PostgresChannelRepository)


@pytest.mark.parametrize(
    "method,path,body",
    [
        ("get", "/channels", None),
        ("post", "/channels", _create_body()),
        ("patch", "/channels/canal-demo", {"name": "Nuevo"}),
        ("patch", "/channels/canal-demo/active", {"active": False}),
        ("post", "/channels/canal-demo/secret", None),
        ("get", "/channels/canal-demo/secret", None),
    ],
)
def test_all_channel_routes_require_service_token(method, path, body):
    """R38: todas las rutas /channels exigen X-Service-Token válido."""
    client, *_ = _app()
    with client:
        response = getattr(client, method)(path, json=body) if body else getattr(client, method)(path)
    assert response.status_code == 401
    assert response.json()["error"] == "unauthorized"


def test_channel_create_and_list_never_return_stored_credentials_or_ciphertext():
    """R39–R40: la creación devuelve secreto una vez; GET lista metadatos públicos."""
    client, repository, *_ = _app()
    with client:
        created = client.post("/channels", json=_create_body(), headers=_headers())
        assert created.status_code == 201
        secret = created.json()["secret"]
        encrypted = repository.get_encrypted_secrets("canal-demo")
        assert len(secret) == 43
        assert encrypted is not None and secret not in encrypted
        assert "credential-private-value" not in encrypted

        listed = client.get("/channels", headers=_headers())
    assert listed.status_code == 200
    body = listed.json()
    assert body["adapter_types"] == [
        "webhook_generico", "simulado", "gmail_api", "tipo_prueba"
    ]
    channel = next(item for item in body["channels"] if item["id"] == "canal-demo")
    assert channel["has_secrets"] is True
    assert channel["managed_by_environment"] is False
    assert "secret" not in channel
    assert "credentials" not in channel
    assert secret not in listed.text
    assert encrypted not in listed.text
    assert "credential-private-value" not in listed.text


def test_channel_http_update_active_regenerate_reveal_and_not_found():
    """R43–R49: PATCH, estado activo y operaciones explícitas de secreto."""
    client, repository, *_ = _app()
    with client:
        created = client.post("/channels", json=_create_body(), headers=_headers())
        assert created.status_code == 201
        first_secret = created.json()["secret"]
        updated = client.patch(
            "/channels/canal-demo",
            json={"name": "Canal actualizado", "config": {"region": "sur"}},
            headers=_headers(),
        )
        assert updated.status_code == 200
        assert updated.json()["name"] == "Canal actualizado"
        assert updated.json()["config"] == {"region": "sur"}
        assert "credential-private-value" not in updated.text

        active = client.patch(
            "/channels/canal-demo/active", json={"active": False}, headers=_headers()
        )
        assert active.status_code == 200 and active.json()["active"] is False
        assert repository.get("canal-demo").active_follows_environment is False

        revealed = client.get("/channels/canal-demo/secret", headers=_headers())
        regenerated = client.post(
            "/channels/canal-demo/secret", headers=_headers()
        )
        assert revealed.status_code == 200 and revealed.json()["secret"] == first_secret
        assert regenerated.status_code == 200
        assert regenerated.json()["secret"] != first_secret
        missing = client.get("/channels/no-existe/secret", headers=_headers())
        assert missing.status_code == 404
        managed = client.get("/channels/telegram/secret", headers=_headers())
        assert managed.status_code == 409
        assert repository.create(
            ChannelRecord(
                id="canal-sin-secreto",
                name="Canal sin secreto",
                adapter_type="simulado",
                icon="chat",
                color="#1B6FA8",
                config={},
                active=True,
                created_at=datetime(2026, 11, 21, tzinfo=timezone.utc),
                has_secrets=False,
                active_follows_environment=False,
            ),
            None,
        )
        absent_secret = client.get(
            "/channels/canal-sin-secreto/secret", headers=_headers()
        )
        assert absent_secret.status_code == 404
    assert repository.get_encrypted_secrets("canal-demo") is not None


def test_secret_audit_logs_include_channel_id_but_never_secret_or_credentials(caplog):
    """R37, R48: regeneración y revelado auditan el canal y no sus valores secretos."""
    client, *_ = _app()
    with caplog.at_level("INFO"), client:
        response = client.post("/channels", json=_create_body(), headers=_headers())
        secret = response.json()["secret"]
        client.post("/channels/canal-demo/secret", headers=_headers())
        client.get("/channels/canal-demo/secret", headers=_headers())
    assert "channel_secret_regenerated channel_id=canal-demo" in caplog.text
    assert "channel_secret_revealed channel_id=canal-demo" in caplog.text
    assert secret not in caplog.text
    assert "credential-private-value" not in caplog.text


def test_channel_create_rejects_duplicate_unregistered_managed_and_invalid_payloads():
    """R41–R42: altas duplicadas/ilegales no persisten y devuelven 409/422."""
    client, repository, *_ = _app()
    with client:
        assert client.post("/channels", json=_create_body(), headers=_headers()).status_code == 201
        duplicate = client.post("/channels", json=_create_body(), headers=_headers())
        unknown = client.post(
            "/channels",
            json=_create_body(id="canal-otro", adapter_type="no_registrado"),
            headers=_headers(),
        )
        managed = client.post(
            "/channels",
            json=_create_body(id="telegram-nuevo", adapter_type="telegram"),
            headers=_headers(),
        )
        invalid = client.post(
            "/channels", json=_create_body(color="azul"), headers=_headers()
        )
    assert duplicate.status_code == 409
    assert duplicate.json()["error"] == "channel_exists"
    assert unknown.status_code == managed.status_code == invalid.status_code == 422
    assert repository.get("canal-otro") is None
    assert repository.get("telegram-nuevo") is None


def test_send_uses_registry_and_degrades_image_before_delivery():
    """R22–R25: /send resuelve canales, respeta precedencia y degrada imágenes."""
    client, repository, _, instances, availability = _app()
    with client:
        absent = client.post(
            "/send",
            json={"channel": "canal-fantasma", "destination": "55", "blocks": [{"type": "text", "text": "Hola"}]},
            headers=_headers(),
        )
        assert absent.status_code == 422
        assert absent.json()["error"] == "validation_error"

        created = client.post("/channels", json=_create_body(), headers=_headers())
        assert created.status_code == 201
        repository.set_active("canal-demo", False)
        availability[0] = False
        unavailable = client.post(
            "/send",
            json={"channel": "canal-demo", "destination": "55", "blocks": [{"type": "text", "text": "Hola"}]},
            headers=_headers(),
        )
        assert unavailable.status_code == 502
        assert unavailable.json()["error"] == "upstream_error"

        availability[0] = True
        inactive = client.post(
            "/send",
            json={"channel": "canal-demo", "destination": "55", "blocks": [{"type": "text", "text": "Hola"}]},
            headers=_headers(),
        )
        assert inactive.status_code == 422
        assert inactive.json()["error"] == "channel_inactive"

        client.patch(
            "/channels/canal-demo/active", json={"active": True}, headers=_headers()
        )
        image = client.post(
            "/send",
            json={
                "channel": "canal-demo",
                "destination": "55",
                "blocks": [
                    {
                        "type": "image",
                        "url": "https://media.example.test/photo.jpg",
                        "alt_text": "Foto",
                    }
                ],
            },
            headers=_headers(),
        )
    assert image.status_code == 200
    assert isinstance(instances[-1].sent[-1][1][0], LinkBlock)


@pytest.mark.parametrize(
    "method,path,body",
    [
        ("get", "/channels", None),
        ("post", "/channels", _create_body(id="canal-nuevo")),
        ("patch", "/channels/canal-demo", {"name": "Nuevo"}),
        ("patch", "/channels/canal-demo/active", {"active": False}),
        ("post", "/channels/canal-demo/secret", None),
        ("get", "/channels/canal-demo/secret", None),
        (
            "post",
            "/send",
            {"channel": "telegram", "destination": "55", "blocks": [{"type": "text", "text": "hola"}]},
        ),
    ],
)
def test_store_failure_is_generic_for_channel_routes_and_send(method, path, body):
    """R26: fallos del almacén responden 503 sin propagar el texto de excepción."""
    repository = FakeChannelRepository()
    client, *_ = _app(repository=repository)
    with client:
        repository.fail = True
        response = (
            getattr(client, method)(path, json=body, headers=_headers())
            if body
            else getattr(client, method)(path, headers=_headers())
        )
    assert response.status_code == 503
    assert response.json()["error"] == "channel_store_unavailable"
    assert "OSError" not in response.text


def test_seed_failure_is_deferred_and_retried_on_first_store_use(caplog):
    """R32: el arranque continúa y ensure_seeded reintenta en la primera ruta."""
    repository = FakeChannelRepository(fail=True)
    client, *_ = _app(repository=repository)
    with caplog.at_level("WARNING"), client:
        repository.fail = False
        response = client.get("/channels", headers=_headers())
    assert response.status_code == 200
    assert any("channels_seed_deferred" in record.message for record in caplog.records)
    assert {item["id"] for item in response.json()["channels"]} >= {"telegram", "whatsapp"}


def test_webhooks_keep_working_when_channel_store_is_down():
    """R15: los webhooks heredados no consultan PostgreSQL canales."""
    client, repository, adapters, *_ = _app(whatsapp_enabled=True)
    with client:
        repository.fail = True
        telegram = client.post(
            "/telegram/webhook",
            json={
                "update_id": 50,
                "message": {
                    "message_id": 5,
                    "from": {"id": 70},
                    "chat": {"id": 70},
                    "text": "Hola",
                },
            },
            headers={"X-Telegram-Bot-Api-Secret-Token": "telegram-webhook-secret"},
        )
        payload = {
            "object": "whatsapp_business_account",
            "entry": [
                {
                    "changes": [
                        {
                            "field": "messages",
                            "value": {
                                "metadata": {"phone_number_id": "phone-1"},
                                "messages": [
                                    {
                                        "id": "wamid-1",
                                        "from": "57300",
                                        "type": "text",
                                        "text": {"body": "Hola"},
                                    }
                                ],
                            },
                        }
                    ]
                }
            ],
        }
        body = json.dumps(payload, separators=(",", ":")).encode()
        signature = hmac.new(b"meta-app-secret", body, hashlib.sha256).hexdigest()
        whatsapp = client.post(
            "/whatsapp/webhook",
            content=body,
            headers={"X-Hub-Signature-256": f"sha256={signature}"},
        )
    assert telegram.status_code == whatsapp.status_code == 200
    assert adapters.orchestrator.received


def test_service_works_without_key_for_public_operations_and_send(caplog):
    """R34, R36: la clave ausente no impide listar, editar ajustes públicos ni Telegram."""
    client, repository, adapters, *_ = _app(secret_key="")
    with caplog.at_level("WARNING"), client:
        listed = client.get("/channels", headers=_headers())
        public_update = client.patch(
            "/channels/telegram", json={"name": "Telegram visible"}, headers=_headers()
        )
        sent = client.post(
            "/send", json={"chat_id": 77, "text": "Hola"}, headers=_headers()
        )
        create = client.post("/channels", json=_create_body(), headers=_headers())
    assert listed.status_code == public_update.status_code == sent.status_code == 200
    assert adapters.telegram.sent[-1][1] == "Hola"
    assert create.status_code == 503
    assert create.json()["error"] == "channel_secrets_unavailable"
    assert repository.get("canal-demo") is None
    assert any("channel_secrets_key_unavailable reason=missing" in r.message for r in caplog.records)


def test_invalid_key_fails_secret_operations_and_logs_only_reason(caplog):
    """R35–R37: clave inválida responde 503 sin persistir ni registrar el valor."""
    secret = "clave-que-no-debe-aparecer"
    client, repository, *_ = _app(secret_key=secret)
    with caplog.at_level("WARNING"), client:
        response = client.post("/channels", json=_create_body(), headers=_headers())
    assert response.status_code == 503
    assert response.json()["error"] == "channel_secrets_unavailable"
    assert repository.get("canal-demo") is None
    assert secret not in caplog.text
    assert "channel_secrets_key_unavailable reason=invalid" in caplog.text


def test_send_with_unreadable_saved_secrets_returns_503_without_leaking_token():
    """R35, R37: un ciphertext ilegible falla cerrado y devuelve un error genérico."""
    foreign_cipher = SecretCipher(Fernet.generate_key().decode("ascii"))
    encrypted = foreign_cipher.encrypt(
        ChannelSecrets(secret="foreign-secret", credentials={"api_token": "private"})
    )
    repository = FakeChannelRepository()
    repository.create(
        ChannelRecord(
            id="canal-demo",
            name="Canal demo",
            adapter_type="simulado",
            icon="chat",
            color="#1B6FA8",
            config={},
            active=True,
            created_at=datetime(2026, 11, 21, tzinfo=timezone.utc),
            has_secrets=True,
            active_follows_environment=False,
        ),
        encrypted,
    )
    other_key = Fernet.generate_key().decode("ascii")
    client, *_ = _app(repository=repository, secret_key=other_key)
    with client:
        response = client.post(
            "/send",
            json={
                "channel": "canal-demo",
                "destination": "55",
                "blocks": [{"type": "text", "text": "Hola"}],
            },
            headers=_headers(),
        )
    assert response.status_code == 503
    assert response.json()["error"] == "channel_secrets_unavailable"
    assert "foreign-secret" not in response.text
    assert "private" not in response.text


def test_health_reports_postgres_and_redis_failures_without_details():
    """R50: /health informa las dependencias caídas sin DSN ni mensaje de error."""
    repository = FakeChannelRepository(health_ok=False)
    client, *_ = _app(repository=repository)
    with client:
        only_postgres = client.get("/health")
        assert only_postgres.status_code == 503
        assert only_postgres.json()["dependencies"] == {"postgres": "unavailable"}

    repository = FakeChannelRepository(health_ok=False)
    client, *_ = _app(repository=repository, redis_ok=False)
    with client:
        both = client.get("/health")
    assert both.status_code == 503
    assert both.json()["dependencies"] == {
        "redis": "unavailable",
        "postgres": "unavailable",
    }
    assert "postgresql://" not in both.text
    assert "no está disponible" not in both.text


def test_no_channel_name_comparisons_remain_in_registry_core():
    """R10: el núcleo del gateway no compara contra nombres fijos de canales."""
    package = ROOT / "services" / "telegram_gateway" / "telegram_gateway"
    for filename in (
        "main.py",
        "registry.py",
        "channel_service.py",
        "webhook_service.py",
    ):
        source = (package / filename).read_text(encoding="utf-8")
        for line in source.splitlines():
            if "==" not in line and "!=" not in line and " in " not in line:
                continue
            assert re.search(r"['\"](?:telegram|whatsapp)['\"]", line) is None, (
                filename,
                line,
            )
