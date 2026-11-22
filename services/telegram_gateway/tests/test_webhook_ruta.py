"""R6-R30: ruta pública POST /webhooks/{canal_id} con firma, orden y entrega."""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from lazaro_contracts import (
    LAZARO_SIGNATURE_HEADER,
    LAZARO_TIMESTAMP_HEADER,
    ChannelCapabilities,
    NormalizedMessage,
    TextBlock,
)
from pydantic import SecretStr

from telegram_gateway.adapters.callback import FakeCallbackClient
from telegram_gateway.adapters.channel_repository import FakeChannelRepository
from telegram_gateway.adapters.dedup import FakeDedupStore
from telegram_gateway.adapters.orchestrator import FakeOrchestratorClient
from telegram_gateway.adapters.telegram import FakeTelegramClient
from telegram_gateway.config import Settings
from telegram_gateway.domain import (
    Adapters,
    ChannelRecord,
    ChannelSecrets,
    OrchestratorError,
)
from telegram_gateway.main import create_app
from telegram_gateway.registry import CHANNEL_REGISTRY, ChannelRegistry
from telegram_gateway.secret_cipher import SecretCipher
from telegram_gateway.signature import sign_payload

NOW = datetime(2026, 11, 21, 15, 0, tzinfo=timezone.utc)
SECRET = "secreto-canal-externo"
OTHER_SECRET = "secreto-canal-otro"
TOKEN = "service-token-test"
MESSAGE: dict[str, Any] = {
    "channel": "canal-externo",
    "external_user_id": "usuario-1",
    "external_chat_id": "usuario-1",
    "external_message_id": "msg-1",
    "kind": "text",
    "text": "Hola, necesito ayuda",
    "received_at": "2026-11-21T15:00:00Z",
}


class _CountingOrchestrator(FakeOrchestratorClient):
    def __init__(self, fail: bool = False) -> None:
        super().__init__(fail=fail)
        self.calls = 0

    def post_message(self, request: NormalizedMessage) -> None:
        self.calls += 1
        super().post_message(request)


@dataclass
class _App:
    client: TestClient
    repository: FakeChannelRepository
    dedup: FakeDedupStore
    orchestrator: _CountingOrchestrator
    registry: ChannelRegistry
    key: str


def _registry() -> ChannelRegistry:
    return CHANNEL_REGISTRY.copy()


def _app(
    *,
    registry: ChannelRegistry | None = None,
    max_body: int = 1_048_576,
    orchestrator: _CountingOrchestrator | None = None,
) -> _App:
    key = Fernet.generate_key().decode("ascii")
    repository = FakeChannelRepository(clock=lambda: NOW)
    dedup = FakeDedupStore()
    orchestrator = orchestrator or _CountingOrchestrator()
    registry = registry or _registry()
    adapters = Adapters(
        telegram=FakeTelegramClient(),
        dedup=dedup,
        orchestrator=orchestrator,
        clock=lambda: NOW,
        channels=repository,
        channel_registry=registry,
        callback=FakeCallbackClient(),
    )
    settings = Settings(
        service_token=TOKEN,
        telegram_webhook_secret="telegram-webhook-secret",
        telegram_bot_token="123456:BOT",
        channel_secrets_key=SecretStr(key),
        webhook_max_body_bytes=max_body,
    )
    client = TestClient(create_app(settings, adapters), raise_server_exceptions=False)
    return _App(client, repository, dedup, orchestrator, registry, key)


def _create_channel(
    app: _App,
    channel_id: str = "canal-externo",
    *,
    adapter_type: str = "webhook_generico",
    secret: str = SECRET,
    active: bool = True,
    key: str | None = None,
) -> None:
    cipher = SecretCipher(key or app.key)
    app.repository.create(
        ChannelRecord(
            id=channel_id,
            name="Canal externo",
            adapter_type=adapter_type,
            icon="globe",
            color="#1B6FA8",
            config={},
            active=active,
            created_at=NOW,
            has_secrets=True,
            active_follows_environment=False,
        ),
        cipher.encrypt(ChannelSecrets(secret=secret)),
    )


def _body(payload: Any) -> bytes:
    if isinstance(payload, bytes):
        return payload
    return json.dumps(payload, separators=(",", ":")).encode("utf-8")


def _signed(
    app: _App,
    channel_id: str,
    payload: Any,
    *,
    secret: str = SECRET,
    timestamp: str | None = None,
    signature: str | None = None,
    include_timestamp: bool = True,
    include_signature: bool = True,
):
    body = _body(payload)
    ts = str(int(NOW.timestamp())) if timestamp is None else timestamp
    sig = sign_payload(secret, ts, body) if signature is None else signature
    headers = {"Content-Type": "application/json"}
    if include_timestamp:
        headers[LAZARO_TIMESTAMP_HEADER] = ts
    if include_signature:
        headers[LAZARO_SIGNATURE_HEADER] = sig
    return app.client.post(f"/webhooks/{channel_id}", content=body, headers=headers)


# ── R6: ruta pública ────────────────────────────────────────────────────────


def test_generic_webhook_is_public_but_other_routes_still_require_token():
    """R6: el webhook genérico no exige token y /channels sigue respondiendo 401."""
    app = _app()
    _create_channel(app)
    with app.client:
        accepted = _signed(app, "canal-externo", MESSAGE)
        internal = app.client.get("/channels")
    assert accepted.status_code == 200
    assert internal.status_code == 401
    assert internal.json()["error"] == "unauthorized"


# ── R7-R9: 404 uniforme ─────────────────────────────────────────────────────


def _unavailable_registry() -> ChannelRegistry:
    registry = _registry()

    @registry.register("no_disponible")
    class UnavailableFactory:
        managed_by_environment = False

        @classmethod
        def is_available(cls, context):
            return False

        @classmethod
        def build(cls, record, context, secrets):
            raise AssertionError("no debería construirse")

    return registry


def test_missing_inactive_unregistered_or_secretless_channel_is_404():
    """R7-R9: todos los casos responden el mismo 404 sin revelar cuál es."""
    app = _app(registry=_unavailable_registry())
    _create_channel(app, "canal-inactivo", active=False)
    _create_channel(app, "canal-desconocido", adapter_type="no_registrado")
    _create_channel(app, "canal-no-disponible", adapter_type="no_disponible")
    bodies = []
    with app.client:
        for channel_id in (
            "no-existe",
            "canal-inactivo",
            "telegram",
            "whatsapp",
            "canal-desconocido",
            "canal-no-disponible",
        ):
            response = _signed(app, channel_id, MESSAGE)
            assert response.status_code == 404
            bodies.append(response.json())
    assert all(body == bodies[0] for body in bodies)
    assert bodies[0]["error"] == "not_found"


# ── R10-R15: firma, ventana y precedencia ───────────────────────────────────


def test_missing_or_wrong_signature_is_401():
    """R10, R11: sin firma o con firma de otro secreto responde 401."""
    app = _app()
    _create_channel(app)
    with app.client:
        missing = _signed(app, "canal-externo", MESSAGE, include_signature=False)
        wrong = _signed(app, "canal-externo", MESSAGE, secret="otro-secreto")
    for response in (missing, wrong):
        assert response.status_code == 401
        assert response.json()["error"] == "unauthorized"


@pytest.mark.parametrize(
    "timestamp",
    [
        None,
        "no-es-entero",
        str(int((NOW - timedelta(seconds=301)).timestamp())),
        str(int((NOW + timedelta(seconds=301)).timestamp())),
    ],
)
def test_bad_or_expired_timestamp_is_401(timestamp):
    """R12: timestamp ausente, no decimal, vencido o futuro responde 401."""
    app = _app()
    _create_channel(app)
    with app.client:
        if timestamp is None:
            response = _signed(app, "canal-externo", MESSAGE, include_timestamp=False)
        else:
            response = _signed(app, "canal-externo", MESSAGE, timestamp=timestamp)
    assert response.status_code == 401


def test_413_when_body_exceeds_configured_limit():
    """R15: un cuerpo mayor que WEBHOOK_MAX_BODY_BYTES responde 413."""
    app = _app(max_body=1024)
    _create_channel(app)
    payload = {**MESSAGE, "text": "x" * 2000}
    with app.client:
        response = _signed(app, "canal-externo", payload)
    assert response.status_code == 413
    assert response.json()["error"] == "payload_too_large"


def test_error_precedence_is_404_then_413_then_401_then_422():
    """R14: el cuerpo inválido con firma incorrecta responde 401, nunca 422."""
    app = _app(max_body=1024)
    _create_channel(app)
    huge = b"x" * 2000
    with app.client:
        not_found = _signed(app, "no-existe", huge)
        too_large = _signed(app, "canal-externo", huge, secret="otro-secreto")
        unauthorized = _signed(app, "canal-externo", b"{no-json", secret="otro-secreto")
        invalid = _signed(app, "canal-externo", b"{no-json")
    assert not_found.status_code == 404
    assert too_large.status_code == 413
    assert unauthorized.status_code == 401
    assert invalid.status_code == 422


# ── R16-R22: formato y adaptadores ──────────────────────────────────────────


@pytest.mark.parametrize("payload", [b"{no-json", b"[]", b'"texto"'])
def test_body_must_be_a_utf8_json_object(payload):
    """R16: cuerpo no JSON o raíz no objeto responde 422 con error y message."""
    app = _app()
    _create_channel(app)
    with app.client:
        response = _signed(app, "canal-externo", payload)
    assert response.status_code == 422
    body = response.json()
    assert body["error"] == "validation_error"
    assert body["message"]


def test_adapter_returning_none_is_422():
    """R18: si recibir_mensaje devuelve None, responde 422."""
    app = _app()
    _create_channel(app)
    with app.client:
        response = _signed(app, "canal-externo", {"channel": "canal-externo"})
    assert response.status_code == 422
    assert response.json()["error"] == "validation_error"


class _TranslatorChannel:
    def __init__(self, channel_id: str, direction: str = "inbound") -> None:
        self.channel_id = channel_id
        self.direction = direction

    def recibir_mensaje(self, payload):
        return NormalizedMessage(
            channel=self.channel_id,
            external_user_id="usuario-1",
            external_chat_id="usuario-1",
            external_message_id=str(payload.get("id", "msg")),
            kind="text",
            text=str(payload.get("texto", "hola")),
            received_at=NOW,
            direction=self.direction,
        )

    def enviar_mensaje(self, destino, bloques):
        return "sent"

    def identificar_usuario(self, payload):
        return None

    def capacidades(self, destino=None):
        return ChannelCapabilities(
            free_text_allowed=True,
            max_options=0,
            min_list_options=0,
            max_list_options=0,
            supports_links=False,
            requires_template=False,
            supports_buttons=False,
        )


def _translator_registry(direction: str = "inbound") -> ChannelRegistry:
    registry = _registry()

    @registry.register("traductor")
    class TranslatorFactory:
        managed_by_environment = False

        @classmethod
        def is_available(cls, context):
            return True

        @classmethod
        def build(cls, record, context, secrets):
            return _TranslatorChannel(record.id, direction)

    return registry


def test_adapter_specific_payload_is_translated_before_delivery():
    """R17, R20: el mensaje normalizado que devuelve el adaptador se entrega."""
    app = _app(registry=_translator_registry())
    _create_channel(app, "canal-traductor", adapter_type="traductor")
    with app.client:
        response = _signed(
            app, "canal-traductor", {"id": "msg-t", "texto": "hola traducido"}
        )
    assert response.status_code == 200
    assert response.json() == {"status": "accepted"}
    delivered = app.orchestrator.received[0]
    assert delivered.channel == "canal-traductor"
    assert delivered.text == "hola traducido"


def test_channel_mismatch_and_outbound_direction_are_422():
    """R21, R22: channel distinto o direction outbound responden 422."""
    app = _app()
    _create_channel(app)
    with app.client:
        mismatch = _signed(app, "canal-externo", {**MESSAGE, "channel": "otro-canal"})
        outbound = _signed(app, "canal-externo", {**MESSAGE, "direction": "outbound"})
    assert mismatch.status_code == 422
    assert outbound.status_code == 422


def test_adapter_returning_outbound_message_is_422():
    """R22: el servicio rechaza un NormalizedMessage que no sea inbound."""
    app = _app(registry=_translator_registry(direction="outbound"))
    _create_channel(app, "canal-traductor", adapter_type="traductor")
    with app.client:
        response = _signed(app, "canal-traductor", {"id": "msg-t"})
    assert response.status_code == 422
    assert response.json()["error"] == "validation_error"
    assert not app.orchestrator.received


# ── R23-R28: idempotencia y entrega ─────────────────────────────────────────


def test_new_message_is_delivered_once_and_duplicate_is_not_repeated():
    """R23, R24, R28: aceptado una vez; el mismo par responde duplicate."""
    app = _app()
    _create_channel(app)
    with app.client:
        first = _signed(app, "canal-externo", MESSAGE)
        second = _signed(app, "canal-externo", MESSAGE)
    assert first.status_code == second.status_code == 200
    assert first.json() == {"status": "accepted"}
    assert second.json() == {"status": "duplicate"}
    assert app.orchestrator.calls == 1


def test_same_external_id_on_two_channels_is_accepted_on_each():
    """R25: la idempotencia es por (canal, external_message_id)."""
    app = _app()
    _create_channel(app)
    _create_channel(app, "canal-otro", secret=OTHER_SECRET)
    with app.client:
        first = _signed(app, "canal-externo", MESSAGE)
        other = _signed(
            app,
            "canal-otro",
            {**MESSAGE, "channel": "canal-otro"},
            secret=OTHER_SECRET,
        )
    assert first.json() == other.json() == {"status": "accepted"}
    assert app.orchestrator.calls == 2


def test_redis_failure_treats_message_as_new_and_logs_error(caplog):
    """R26: si la deduplicación falla, el mensaje se trata como nuevo."""
    app = _app()
    _create_channel(app)
    app.dedup.fail = True
    with caplog.at_level(logging.ERROR), app.client:
        response = _signed(app, "canal-externo", MESSAGE)
    assert response.status_code == 200
    assert app.orchestrator.calls == 1
    assert "se trata como nuevo" in caplog.text
    assert "ConnectionError" in caplog.text


def test_orchestrator_failure_is_logged_once_and_still_accepted(caplog):
    """R27: un fallo del orquestador no se reintenta y responde 200 accepted."""
    app = _app(orchestrator=_CountingOrchestrator(fail=True))
    _create_channel(app)
    with caplog.at_level(logging.ERROR), app.client:
        response = _signed(app, "canal-externo", MESSAGE)
    assert response.status_code == 200
    assert response.json() == {"status": "accepted"}
    assert app.orchestrator.calls == 1
    assert "webhook_forward_failed channel_id=canal-externo" in caplog.text


@pytest.mark.parametrize(
    "error", [OrchestratorError("El orquestador respondió 422.")]
)
def test_orchestrator_rejection_is_logged_with_reason(error, caplog):
    """R27: un rechazo del orquestador (incluido 422) queda registrado."""
    orchestrator = _CountingOrchestrator()
    orchestrator.error = error  # type: ignore[attr-defined]

    def _raise(request):
        orchestrator.calls += 1
        raise error

    orchestrator.post_message = _raise  # type: ignore[assignment]
    app = _app(orchestrator=orchestrator)
    _create_channel(app)
    with caplog.at_level(logging.ERROR), app.client:
        response = _signed(app, "canal-externo", MESSAGE)
    assert response.status_code == 200
    assert app.orchestrator.calls == 1
    assert "webhook_forward_failed channel_id=canal-externo" in caplog.text
    assert "422" in caplog.text


# ── R29, R30: disponibilidad y no filtrar secretos ──────────────────────────


def test_channel_store_failure_is_503():
    """R29: si el almacén falla responde 503 channel_store_unavailable."""
    app = _app()
    with app.client:
        app.repository.fail = True
        response = _signed(app, "canal-externo", MESSAGE)
    assert response.status_code == 503
    assert response.json()["error"] == "channel_store_unavailable"


def test_undecryptable_channel_secrets_is_503():
    """R29: secretos ilegibles responden 503 channel_secrets_unavailable."""
    app = _app()
    foreign = Fernet.generate_key().decode("ascii")
    _create_channel(app, key=foreign)
    with app.client:
        response = _signed(app, "canal-externo", MESSAGE)
    assert response.status_code == 503
    assert response.json()["error"] == "channel_secrets_unavailable"


def test_secret_signature_and_body_never_appear_in_logs_or_errors(caplog):
    """R30: ni secreto, ni firma, ni cuerpo se registran ni se devuelven."""
    app = _app()
    _create_channel(app)
    body_marker = "cuerpo-privado-del-cliente"
    payload = {**MESSAGE, "text": body_marker}
    raw = _body(payload)
    wrong_signature = sign_payload("otro-secreto", str(int(NOW.timestamp())), raw)
    with caplog.at_level(logging.DEBUG), app.client:
        response = _signed(
            app, "canal-externo", payload, signature=wrong_signature
        )
    logs = caplog.text
    assert response.status_code == 401
    for value in (SECRET, wrong_signature, body_marker):
        assert value not in logs
        assert value not in response.text
