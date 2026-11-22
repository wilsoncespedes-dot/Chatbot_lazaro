"""R19–R27: rutas internas y entrega compartida del canal simulado."""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from lazaro_contracts import (
    LAZARO_SIGNATURE_HEADER,
    LAZARO_TIMESTAMP_HEADER,
    NormalizedMessage,
)
from pydantic import SecretStr

from telegram_gateway.adapters.channel_repository import FakeChannelRepository
from telegram_gateway.adapters.dedup import FakeDedupStore
from telegram_gateway.adapters.mailbox import FakeMailboxRepository
from telegram_gateway.adapters.orchestrator import FakeOrchestratorClient
from telegram_gateway.adapters.telegram import FakeTelegramClient
from telegram_gateway.config import Settings
from telegram_gateway.domain import Adapters
from telegram_gateway.main import create_app
from telegram_gateway.registry import CHANNEL_REGISTRY
from telegram_gateway.signature import sign_payload

NOW = datetime(2026, 11, 21, 15, 0, tzinfo=timezone.utc)
TOKEN = "service-token-test"
CHANNEL = "tiktok-simulado"
OTHER = "otro-simulado"
ROOT = Path(__file__).resolve().parents[3]


class _CountingOrchestrator(FakeOrchestratorClient):
    def __init__(self, fail: bool = False) -> None:
        super().__init__(fail=fail)
        self.calls = 0

    def post_message(self, request: NormalizedMessage) -> None:
        self.calls += 1
        super().post_message(request)


class _App:
    def __init__(
        self,
        client: TestClient,
        repository: FakeChannelRepository,
        mailbox: FakeMailboxRepository,
        orchestrator: _CountingOrchestrator,
    ) -> None:
        self.client = client
        self.repository = repository
        self.mailbox = mailbox
        self.orchestrator = orchestrator


def _app(
    *,
    orchestrator_fail: bool = False,
    mailbox: FakeMailboxRepository | None = None,
) -> _App:
    repository = FakeChannelRepository(clock=lambda: NOW)
    mailbox = mailbox or FakeMailboxRepository()
    orchestrator = _CountingOrchestrator(fail=orchestrator_fail)
    adapters = Adapters(
        telegram=FakeTelegramClient(),
        dedup=FakeDedupStore(),
        orchestrator=orchestrator,
        clock=lambda: NOW,
        channels=repository,
        channel_registry=CHANNEL_REGISTRY.copy(),
        mailbox=mailbox,
    )
    settings = Settings(
        service_token=TOKEN,
        telegram_webhook_secret="telegram-webhook-secret",
        telegram_bot_token="123456:BOT",
        channel_secrets_key=SecretStr(Fernet.generate_key().decode("ascii")),
    )
    client = TestClient(create_app(settings, adapters), raise_server_exceptions=False)
    return _App(client, repository, mailbox, orchestrator)


def _headers() -> dict[str, str]:
    return {"X-Service-Token": TOKEN}


def _create(
    app: _App,
    channel_id: str = CHANNEL,
    *,
    adapter_type: str = "simulado",
    name: str = "TikTok",
    config: dict | None = None,
    active: bool = True,
) -> str:
    response = app.client.post(
        "/channels",
        json={
            "id": channel_id,
            "name": name,
            "adapter_type": adapter_type,
            "icon": "chat",
            "color": "#1B6FA8",
            "config": config or {},
            "active": active,
        },
        headers=_headers(),
    )
    assert response.status_code == 201, response.text
    return response.json()["secret"]


def _body(channel: str, message_id: str = "m-1", text: str = "Hola") -> bytes:
    payload = {
        "channel": channel,
        "external_user_id": "cliente-demo",
        "external_chat_id": "cliente-demo",
        "external_message_id": message_id,
        "kind": "text",
        "text": text,
        "received_at": "2026-11-21T15:00:00Z",
    }
    return json.dumps(payload, separators=(",", ":")).encode("utf-8")


def _signed(
    app: _App, channel: str, secret: str, body: bytes, timestamp: str | None = None
):
    ts = timestamp or str(int(NOW.timestamp()))
    return app.client.post(
        f"/webhooks/{channel}",
        content=body,
        headers={
            "Content-Type": "application/json",
            LAZARO_TIMESTAMP_HEADER: ts,
            LAZARO_SIGNATURE_HEADER: sign_payload(secret, ts, body),
        },
    )


def _simulate(app: _App, channel: str = CHANNEL, user: str = "cliente-demo", text: str = "Hola"):
    return app.client.post(
        f"/channels/{channel}/simulate",
        json={"external_user_id": user, "text": text},
        headers=_headers(),
    )


def _mailbox(app: _App, channel: str = CHANNEL, destination: str = "cliente-demo"):
    return app.client.get(
        f"/channels/{channel}/mailbox",
        params={"destination": destination},
        headers=_headers(),
    )


def test_signed_webhook_records_client_and_rejection_when_orchestrator_fails(caplog):
    """R21–R23: cliente y rechazo en el buzón; el webhook sigue en 200 accepted."""
    app = _app(orchestrator_fail=True)
    with app.client:
        secret = _create(app)
        with caplog.at_level(logging.ERROR):
            response = _signed(app, CHANNEL, secret, _body(CHANNEL))
        read = _mailbox(app)
    assert response.status_code == 200
    assert response.json() == {"status": "accepted"}
    entries = read.json()["entries"]
    assert [entry["kind"] for entry in entries] == ["client", "rejected"]
    assert entries[0]["text"] == "Hola"
    assert "orquestador" in entries[1]["text"]
    assert app.orchestrator.calls == 1
    assert "webhook_forward_failed channel_id=tiktok-simulado" in caplog.text


def test_simulate_returns_forwarded_false_with_reason_when_orchestrator_fails():
    """R20, R23: /simulate traduce el rechazo a forwarded=false con motivo."""
    app = _app(orchestrator_fail=True)
    with app.client:
        _create(app)
        response = _simulate(app)
        read = _mailbox(app)
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "accepted"
    assert body["forwarded"] is False
    assert body["reason"]
    assert [entry["kind"] for entry in read.json()["entries"]] == [
        "client",
        "rejected",
    ]


def test_simulate_returns_forwarded_true_when_orchestrator_accepts():
    """R24: mensaje aceptado -> forwarded=true y sin motivo."""
    app = _app()
    with app.client:
        _create(app)
        response = _simulate(app)
        read = _mailbox(app)
    assert response.status_code == 200
    assert response.json() == {"status": "accepted", "forwarded": True}
    assert [entry["kind"] for entry in read.json()["entries"]] == ["client"]
    assert app.orchestrator.received[0].text == "Hola"


def test_duplicate_signed_message_adds_no_mailbox_entries():
    """R25: el mismo external_message_id no duplica entradas ni entrega."""
    app = _app()
    with app.client:
        secret = _create(app)
        body = _body(CHANNEL, message_id="dup-1")
        first = _signed(app, CHANNEL, secret, body)
        second = _signed(app, CHANNEL, secret, body)
        read = _mailbox(app)
    assert first.json() == {"status": "accepted"}
    assert second.json() == {"status": "duplicate"}
    assert [entry["kind"] for entry in read.json()["entries"]] == ["client"]
    assert app.orchestrator.calls == 1


def test_internal_routes_require_service_token():
    """R19, R20: sin X-Service-Token el buzón y el simulador responden 401."""
    app = _app()
    with app.client:
        _create(app)
        mailbox = app.client.get(f"/channels/{CHANNEL}/mailbox")
        simulated = app.client.post(
            f"/channels/{CHANNEL}/simulate",
            json={"external_user_id": "cliente-demo", "text": "Hola"},
        )
    assert mailbox.status_code == simulated.status_code == 401
    assert mailbox.json()["error"] == simulated.json()["error"] == "unauthorized"
    assert app.orchestrator.calls == 0


@pytest.mark.parametrize(
    "body",
    [
        {"external_user_id": "con espacios", "text": "Hola"},
        {"external_user_id": "", "text": "Hola"},
        {"external_user_id": "cliente-demo", "text": ""},
        {"external_user_id": "cliente-demo", "text": "x" * 4097},
        {"external_user_id": "cliente-demo"},
    ],
)
def test_simulate_rejects_invalid_body_with_422(body):
    """R20: el cuerpo de /simulate valida contra SimulatedInboundRequest."""
    app = _app()
    with app.client:
        _create(app)
        response = app.client.post(
            f"/channels/{CHANNEL}/simulate",
            json=body,
            headers=_headers(),
        )
    assert response.status_code == 422
    assert response.json()["error"] == "validation_error"
    assert app.orchestrator.calls == 0


def test_missing_or_non_mailbox_channel_is_the_same_404():
    """R19, R20: canal inexistente, Telegram y genérico responden el mismo 404."""
    app = _app()
    with app.client:
        _create(app, "canal-generico", adapter_type="webhook_generico", name="Genérico")
        bodies = []
        for channel_id in ("no-existe", "telegram", "canal-generico"):
            mailbox = app.client.get(
                f"/channels/{channel_id}/mailbox", headers=_headers()
            )
            simulated = app.client.post(
                f"/channels/{channel_id}/simulate",
                json={"external_user_id": "cliente-demo", "text": "Hola"},
                headers=_headers(),
            )
            bodies.append(mailbox.json())
            assert simulated.status_code == 404
        assert all(body == bodies[0] for body in bodies)
        assert bodies[0]["error"] == "not_found"


def test_inactive_simulated_channel_can_be_read_but_not_simulated():
    """R19, R20: inactivo -> 422 channel_inactive; el buzón sigue consultable."""
    app = _app()
    with app.client:
        secret = _create(app)
        _signed(app, CHANNEL, secret, _body(CHANNEL))
        app.client.patch(
            f"/channels/{CHANNEL}/active", json={"active": False}, headers=_headers()
        )
        read = _mailbox(app)
        simulated = _simulate(app)
    assert read.status_code == 200
    assert len(read.json()["entries"]) == 1
    assert simulated.status_code == 422
    assert simulated.json()["error"] == "channel_inactive"


def test_mailbox_limit_and_after_are_validated():
    """R19: after y limit fuera de rango responden 422 validation_error."""
    app = _app()
    with app.client:
        _create(app)
        for params in ({"limit": 0}, {"limit": 501}, {"after": -1}):
            response = app.client.get(
                f"/channels/{CHANNEL}/mailbox", params=params, headers=_headers()
            )
            assert response.status_code == 422
            assert response.json()["error"] == "validation_error"


def test_channel_without_hooks_keeps_behavior_from_62():
    """R21: el canal genérico no se altera y no escribe en el buzón."""
    app = _app()
    with app.client:
        secret = _create(app, "canal-generico", adapter_type="webhook_generico")
        response = _signed(app, "canal-generico", secret, _body("canal-generico"))
        mailbox = app.client.get(
            "/channels/canal-generico/mailbox", headers=_headers()
        )
    assert response.status_code == 200
    assert response.json() == {"status": "accepted"}
    assert app.orchestrator.calls == 1
    assert mailbox.status_code == 404


def test_mailbox_hook_failure_does_not_change_delivery(caplog):
    """R26: un fallo al escribir en el buzón no impide entregar; se registra."""
    app = _app(mailbox=FakeMailboxRepository(fail=True))
    with app.client:
        secret = _create(app)
        with caplog.at_level(logging.ERROR):
            webhook = _signed(app, CHANNEL, secret, _body(CHANNEL))
            simulated = _simulate(app, text="Otro")
    assert webhook.status_code == 200
    assert webhook.json() == {"status": "accepted"}
    assert simulated.json()["forwarded"] is True
    assert app.orchestrator.calls == 2
    logs = "\n".join(record.getMessage() for record in caplog.records)
    assert "registrar_entrada_failed channel_id=tiktok-simulado" in logs
    assert "OSError" in logs


def test_two_simulated_channels_work_end_to_end_without_new_code():
    """R27: dos filas simulado reciben, envían y leen su buzón sin código nuevo."""
    app = _app()
    with app.client:
        first_secret = _create(app, CHANNEL, name="TikTok", config={"capabilities": {"supports_images": True}})
        second_secret = _create(app, OTHER, name="Foro", config={})
        first = _signed(app, CHANNEL, first_secret, _body(CHANNEL, "a-1"))
        second = _signed(app, OTHER, second_secret, _body(OTHER, "b-1"))
        first_send = app.client.post(
            "/send",
            json={
                "channel": CHANNEL,
                "destination": "cliente-demo",
                "blocks": [{"type": "text", "text": "respuesta uno"}],
            },
            headers=_headers(),
        )
        second_send = app.client.post(
            "/send",
            json={
                "channel": OTHER,
                "destination": "cliente-demo",
                "blocks": [{"type": "text", "text": "respuesta dos"}],
            },
            headers=_headers(),
        )
        first_mailbox = _mailbox(app, CHANNEL).json()
        second_mailbox = _mailbox(app, OTHER).json()
    assert first.json() == second.json() == {"status": "accepted"}
    assert first_send.status_code == second_send.status_code == 200
    assert [entry["kind"] for entry in first_mailbox["entries"]] == ["client", "reply"]
    assert [entry["kind"] for entry in second_mailbox["entries"]] == ["client", "reply"]
    assert first_mailbox["entries"][-1]["text"] == "respuesta uno"
    assert second_mailbox["entries"][-1]["text"] == "respuesta dos"


def test_core_files_do_not_compare_with_channel_names():
    """R21: los módulos nuevos del camino compartido no comparan nombres fijos."""
    package = ROOT / "services" / "telegram_gateway" / "telegram_gateway"
    for filename in ("main.py", "channel_service.py", "webhook_service.py"):
        source = (package / filename).read_text(encoding="utf-8")
        for line in source.splitlines():
            if "==" not in line and "!=" not in line and " in " not in line:
                continue
            assert re.search(r"['\"](?:telegram|whatsapp)['\"]", line) is None, (
                filename,
                line,
            )
