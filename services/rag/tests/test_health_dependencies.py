"""Healthchecks de dependencias en rag (#47)."""
from __future__ import annotations

import pytest
from lazaro_contracts import HealthResponse
from pydantic import ValidationError

from rag.adapters.repository import PgVectorChunkRepository
from rag.config import Settings

SERVICE = "rag"


class _Cursor:
    def __init__(self, log: list, error: BaseException | None = None) -> None:
        self.log = log
        self.error = error

    def execute(self, sql, params=()):
        self.log.append((sql, tuple(params)))
        if self.error is not None:
            raise self.error

    def fetchone(self):
        return (1,)


class _Conn:
    def __init__(self, error: BaseException | None = None) -> None:
        self.log: list[tuple[str, tuple]] = []
        self.error = error
        self.closed = False

    def cursor(self):
        return _Cursor(self.log, self.error)

    def close(self):
        self.closed = True


def test_health_ok_when_postgres_responds(env) -> None:
    """R1, R4: con PostgreSQL sano /health responde 200 y el cuerpo vigente."""
    response = env.client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": SERVICE}
    assert env.repo.health_checks == [2.0]


def test_health_is_public(env) -> None:
    """R1: /health no exige X-Service-Token."""
    response = env.client.get("/health", headers={"X-Service-Token": "incorrecto"})
    assert response.status_code == 200


def test_health_returns_503_when_postgres_fails(env) -> None:
    """R2, R4, R6: si PostgreSQL falla, /health responde 503 unhealthy."""
    env.repo.health_error = RuntimeError("postgresql://user:secreto@host/db")
    response = env.client.get("/health")
    assert response.status_code == 503
    body = response.json()
    assert body == {
        "status": "unhealthy",
        "service": SERVICE,
        "dependencies": {"postgres": "unavailable"},
    }
    HealthResponse.model_validate(body)
    assert "secreto" not in response.text
    assert "postgresql://" not in response.text


def test_health_returns_503_on_timeout(env) -> None:
    """R2, R5: un timeout del probe se reporta como unavailable."""
    env.repo.health_error = TimeoutError("agotado")
    response = env.client.get("/health")
    assert response.status_code == 503
    assert response.json()["dependencies"] == {"postgres": "unavailable"}


@pytest.mark.parametrize("value", [0, -1, 11])
def test_healthcheck_timeout_must_be_positive_and_bounded(value: float) -> None:
    """R5: HEALTHCHECK_TIMEOUT_SECONDS solo admite valores > 0 y <= 10."""
    with pytest.raises(ValidationError):
        Settings(healthcheck_timeout_seconds=value)


def test_postgres_health_check_uses_select_one_without_schema() -> None:
    """R4, R5, R8: conexión independiente, solo SELECT 1 y sin inicializar esquema."""
    conn = _Conn()
    timeouts: list[float] = []

    def connect_health(timeout: float):
        timeouts.append(timeout)
        return conn

    repo = PgVectorChunkRepository(
        "postgresql://x",
        connect=lambda: (_ for _ in ()).throw(AssertionError("no debe usarse")),
        connect_health=connect_health,
    )
    repo.health_check(1.5)
    assert timeouts == [1.5]
    assert conn.log == [("SELECT 1", ())]
    assert conn.closed is True


def test_postgres_health_check_propagates_failures_and_closes() -> None:
    """R2, R5, R8: el fallo técnico sube al caller y la conexión se cierra."""
    conn = _Conn(error=TimeoutError("agotado"))
    repo = PgVectorChunkRepository(
        "postgresql://x", connect_health=lambda timeout: conn
    )
    with pytest.raises(TimeoutError):
        repo.health_check(1.0)
    assert conn.closed is True
