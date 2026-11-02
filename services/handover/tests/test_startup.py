"""Tests del arranque de handover: validación de ADVISOR_CHAT_IDS y logs de inicio."""
from __future__ import annotations

import logging
import os
import subprocess
import sys
from datetime import datetime, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from handover.adapters.gateway import FakeGatewayClient
from handover.adapters.repository import FakeCaseRepository
from handover.config import Settings
from handover.domain import Adapters, Case
from handover.main import create_app

TOKEN = "svc-token"
HEADERS = {"X-Service-Token": TOKEN}
START = datetime(2026, 1, 2, 3, 0, 0, tzinfo=timezone.utc)
SETTINGS_ENV = (
    "SERVICE_TOKEN",
    "DATABASE_URL",
    "TELEGRAM_GATEWAY_URL",
    "ADVISOR_CHAT_IDS",
    "HANDOVER_TIMEOUT_SECONDS",
    "HANDOVER_TIMEOUT_REPLY",
    "HTTP_TIMEOUT_SECONDS",
)


def _build_adapters() -> tuple[Adapters, FakeCaseRepository, FakeGatewayClient]:
    repo = FakeCaseRepository()
    gateway = FakeGatewayClient()
    adapters = Adapters(repository=repo, gateway=gateway, clock=lambda: START)
    return adapters, repo, gateway


@pytest.mark.parametrize("value", ["111,abc", "111,111"])
def test_create_app_fails_with_invalid_advisor_ids(monkeypatch, value):
    """R9: con ADVISOR_CHAT_IDS inválida, create_app() propaga ValidationError sin app."""
    monkeypatch.setenv("ADVISOR_CHAT_IDS", value)
    with pytest.raises(ValidationError):
        create_app()


def test_startup_log_reports_advisor_count(caplog):
    """R10: create_app registra a INFO advisors_configured con el número de asesores."""
    adapters, _, _ = _build_adapters()
    caplog.set_level(logging.INFO)

    create_app(Settings(advisor_chat_ids="111,222,333"), adapters)

    record = next(
        r for r in caplog.records if r.getMessage() == "advisors_configured count=3"
    )
    assert record.levelno == logging.INFO
    assert all(r.getMessage() != "no_advisors_configured" for r in caplog.records)


@pytest.mark.parametrize("value", ["", " , ,"])
def test_startup_warns_when_no_advisors(caplog, value):
    """R11: con la lista vacía se registra WARNING no_advisors_configured y count=0."""
    adapters, _, _ = _build_adapters()
    caplog.set_level(logging.INFO)

    create_app(Settings(advisor_chat_ids=value), adapters)

    messages = [r.getMessage() for r in caplog.records]
    assert "advisors_configured count=0" in messages
    warning = next(r for r in caplog.records if r.getMessage() == "no_advisors_configured")
    assert warning.levelno == logging.WARNING


def test_create_app_starts_with_empty_advisor_list():
    """R12: con la lista vacía create_app devuelve la app y /health responde 200."""
    adapters, _, _ = _build_adapters()

    app = create_app(Settings(advisor_chat_ids=""), adapters)

    assert isinstance(app, FastAPI)
    assert TestClient(app).get("/health").status_code == 200


def test_startup_log_does_not_contain_advisor_ids(caplog):
    """R13: los registros que emite create_app no incluyen ningún id de asesor."""
    adapters, _, _ = _build_adapters()
    caplog.set_level(logging.DEBUG)

    create_app(Settings(advisor_chat_ids="987654321,-1001234567890"), adapters)

    assert caplog.records
    for record in caplog.records:
        message = record.getMessage()
        assert "987654321" not in message
        assert "1001234567890" not in message


def test_only_commas_config_still_returns_no_advisors():
    """R14: solo comas deja la lista vacía; /handover responde no_advisors y no envía."""
    adapters, repo, gateway = _build_adapters()
    settings = Settings(service_token=TOKEN, advisor_chat_ids=", ,")
    client = TestClient(create_app(settings, adapters))

    response = client.post(
        "/handover",
        json={
            "case_id": "case-1",
            "contact_id": "contact-1",
            "chat_id": 900,
            "reason": "user_request",
            "last_messages": [
                {"role": "user", "text": "quiero un asesor", "at": "2026-01-02T02:59:00Z"}
            ],
        },
        headers=HEADERS,
    )

    assert response.status_code == 200
    assert response.json() == {"status": "no_advisors", "case_id": "case-1"}
    assert gateway.sent == []
    assert repo.cases["case-1"].status == "timed_out"


def test_import_main_logs_advisor_count_to_stderr():
    """R15, R13: el arranque real (import de main) escribe el conteo en stderr sin ids."""
    env = {name: value for name, value in os.environ.items() if name not in SETTINGS_ENV}
    env["ADVISOR_CHAT_IDS"] = "987654321,-1001234567890"
    env["PYTHONPATH"] = os.pathsep.join(sys.path)

    result = subprocess.run(
        [sys.executable, "-c", "import handover.main"],
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )

    assert result.returncode == 0, result.stderr
    assert "advisors_configured count=2" in result.stderr
    assert "987654321" not in result.stderr
    assert "1001234567890" not in result.stderr


def _case(case_id: str, status: str, advisor_id: str | None = None) -> Case:
    return Case(
        case_id=case_id,
        contact_id=f"contact-{case_id}",
        chat_id=900,
        reason="user_request",
        status=status,  # type: ignore[arg-type]
        advisor_id=advisor_id,
        last_messages=[],
        created_at=START,
    )


def test_startup_logs_orphan_case_count(caplog):
    """autorizacion_asesores R49, R50: el arranque registra cuántos huérfanos hay, sin ids."""
    adapters, repo, _ = _build_adapters()
    settings = Settings(advisor_chat_ids="987654321,111")
    repo.create_case(_case("c-registered", "assigned", "987654321"))
    repo.create_case(_case("c-orphan", "assigned", "1001234567890"))
    repo.create_case(_case("c-null", "assigned", None))
    repo.create_case(_case("c-open", "open"))
    repo.create_case(_case("c-closed", "closed"))
    caplog.set_level(logging.INFO)

    with TestClient(create_app(settings, adapters)) as client:
        assert client.get("/health").status_code == 200

    messages = [record.getMessage() for record in caplog.records]
    assert "orphan_cases count=2" in messages
    assert "orphan_cases_present count=2" in messages
    assert all("1001234567890" not in message for message in messages)
    assert all("987654321" not in message for message in messages)
    assert all("c-registered" not in message for message in messages)
    assert all("c-orphan" not in message for message in messages)


def test_startup_without_orphans_logs_zero_and_no_warning(caplog):
    """autorizacion_asesores R49, R50: sin huérfanos no se emite el WARNING."""
    adapters, repo, _ = _build_adapters()
    settings = Settings(advisor_chat_ids="987654321")
    repo.create_case(_case("c-registered", "assigned", "987654321"))
    repo.create_case(_case("c-open", "open"))
    caplog.set_level(logging.INFO)

    with TestClient(create_app(settings, adapters)):
        pass

    messages = [record.getMessage() for record in caplog.records]
    assert "orphan_cases count=0" in messages
    assert all("orphan_cases_present" not in message for message in messages)


def test_startup_orphan_count_failure_warns_and_starts(monkeypatch, caplog):
    """autorizacion_asesores R51: si el recuento falla, WARNING y el servicio arranca."""
    adapters, repo, _ = _build_adapters()
    settings = Settings(advisor_chat_ids="111")

    def boom():
        raise RuntimeError("secreto-xyz")

    monkeypatch.setattr(repo, "count_assigned_by_advisor", boom)
    caplog.set_level(logging.INFO)

    with TestClient(create_app(settings, adapters)) as client:
        assert client.get("/health").status_code == 200

    messages = [record.getMessage() for record in caplog.records]
    assert "orphan_cases_check_failed" in messages
    assert all("secreto-xyz" not in message for message in messages)


def test_create_app_does_not_count_orphans(monkeypatch):
    """autorizacion_asesores R52: create_app no cuenta huérfanos ni abre la conexión."""
    adapters, repo, _ = _build_adapters()
    settings = Settings(advisor_chat_ids="111")
    calls = []

    def boom():
        calls.append(1)
        raise AssertionError("no debe contar huérfanos")

    monkeypatch.setattr(repo, "count_assigned_by_advisor", boom)
    app = create_app(settings, adapters)
    client = TestClient(app)
    assert client.get("/health").status_code == 200
    assert calls == []

