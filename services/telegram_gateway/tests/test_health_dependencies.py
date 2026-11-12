"""Healthchecks de dependencias en telegram_gateway (#47)."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from lazaro_contracts import HealthResponse
from pydantic import ValidationError

from telegram_gateway.adapters.dedup import FakeDedupStore
from telegram_gateway.adapters.orchestrator import FakeOrchestratorClient
from telegram_gateway.adapters.telegram import FakeTelegramClient
from telegram_gateway.config import Settings
from telegram_gateway.domain import Adapters
from telegram_gateway.main import create_app

SERVICE = "telegram_gateway"


def _client(dedup: FakeDedupStore, timeout: float = 2.0) -> tuple[TestClient, Settings]:
    settings = Settings(service_token="svc-token", healthcheck_timeout_seconds=timeout)
    adapters = Adapters(
        telegram=FakeTelegramClient(),
        dedup=dedup,
        orchestrator=FakeOrchestratorClient(),
    )
    return TestClient(create_app(settings, adapters)), settings


def test_health_ok_when_redis_responds() -> None:
    """R1, R3, R7: con Redis sano /health responde 200 y el cuerpo vigente."""
    dedup = FakeDedupStore()
    client, _ = _client(dedup)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": SERVICE}
    assert dedup.ping_calls == [2.0]


def test_health_is_public_and_ignores_service_token() -> None:
    """R1: /health no exige X-Service-Token."""
    client, _ = _client(FakeDedupStore())
    response = client.get("/health", headers={"X-Service-Token": "incorrecto"})
    assert response.status_code == 200


def test_health_returns_503_when_redis_is_unavailable() -> None:
    """R2, R3, R6: si Redis falla, /health responde 503 unhealthy."""
    dedup = FakeDedupStore(ping_ok=False)
    client, _ = _client(dedup)
    response = client.get("/health")
    assert response.status_code == 503
    body = response.json()
    assert body == {
        "status": "unhealthy",
        "service": SERVICE,
        "dependencies": {"redis": "unavailable"},
    }
    HealthResponse.model_validate(body)


def test_health_returns_503_when_redis_times_out() -> None:
    """R2, R5: un timeout o error del probe también se reporta como unavailable."""
    dedup = FakeDedupStore(ping_error=TimeoutError("agotado"))
    client, _ = _client(dedup)
    response = client.get("/health")
    assert response.status_code == 503
    assert response.json()["dependencies"] == {"redis": "unavailable"}


def test_health_failure_body_does_not_expose_redis_url() -> None:
    """R2: la respuesta no filtra URL ni credenciales de la dependencia."""
    dedup = FakeDedupStore(ping_error=ConnectionError("redis://user:secreto@host:6379/0"))
    client, _ = _client(dedup)
    text = client.get("/health").text
    assert "redis://" not in text
    assert "secreto" not in text
    assert "host" not in text


@pytest.mark.parametrize("value", [0, -1, 11])
def test_healthcheck_timeout_must_be_positive_and_bounded(value: float) -> None:
    """R5: HEALTHCHECK_TIMEOUT_SECONDS solo admite valores > 0 y <= 10."""
    with pytest.raises(ValidationError):
        Settings(healthcheck_timeout_seconds=value)


def test_healthcheck_timeout_default_is_two_seconds(monkeypatch) -> None:
    """R5: el valor por defecto del probe es 2 segundos."""
    monkeypatch.delenv("HEALTHCHECK_TIMEOUT_SECONDS", raising=False)
    assert Settings().healthcheck_timeout_seconds == 2.0


def test_redis_dedup_ping_uses_a_bounded_probe(monkeypatch) -> None:
    """R3, R5: el probe real de Redis aplica el timeout y cierra su cliente."""
    import redis

    from telegram_gateway.adapters.dedup import RedisDedupStore

    created: list[dict] = []
    closed: list[str] = []

    class _Probe:
        def __init__(self, kwargs: dict) -> None:
            self.kwargs = kwargs

        def ping(self) -> bool:
            return True

        def close(self) -> None:
            closed.append("closed")

    def _from_url(url: str, **kwargs):
        created.append({"url": url, **kwargs})
        return _Probe(kwargs)

    monkeypatch.setattr(redis.Redis, "from_url", staticmethod(_from_url))
    store = RedisDedupStore("redis://redis:6379/0")
    assert store.ping(1.5) is True
    assert created[-1] == {
        "url": "redis://redis:6379/0",
        "socket_connect_timeout": 1.5,
        "socket_timeout": 1.5,
    }
    assert closed == ["closed"]
