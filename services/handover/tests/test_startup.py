"""Tests del arranque de handover: roster persistido y logs de inicio."""
from __future__ import annotations

import logging
import os
import subprocess
import sys
from datetime import datetime, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from lazaro_contracts import AdvisorRosterEntry

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


def test_create_app_starts_without_advisor_chat_ids():
    """R44: sin ADVISOR_CHAT_IDS create_app devuelve la app y /health responde 200."""
    adapters, _, _ = _build_adapters()
    app = create_app(Settings(service_token=TOKEN), adapters)
    assert isinstance(app, FastAPI)
    assert TestClient(app).get("/health").status_code == 200


def test_startup_log_reports_roster_count(caplog):
    """R13, R44: el arranque registra cuántos perfiles asesores hay en el roster."""
    adapters, repo, _ = _build_adapters()
    repo.replace_roster(
        [
            AdvisorRosterEntry(profile_id="p1", role="asesor"),
            AdvisorRosterEntry(profile_id="p2", role="asesor"),
            AdvisorRosterEntry(profile_id="p3", role="asesor"),
        ],
        1,
    )
    caplog.set_level(logging.INFO)
    with TestClient(create_app(Settings(service_token=TOKEN), adapters)):
        pass
    assert any(r.getMessage() == "advisors_configured count=3" for r in caplog.records)
    assert all(r.getMessage() != "no_advisors_configured" for r in caplog.records)


def test_startup_warns_when_no_advisors(caplog):
    """R15: con el roster vacío se registra WARNING no_advisors_configured y count=0."""
    adapters, _, _ = _build_adapters()
    caplog.set_level(logging.INFO)
    with TestClient(create_app(Settings(service_token=TOKEN), adapters)):
        pass
    messages = [r.getMessage() for r in caplog.records]
    assert "advisors_configured count=0" in messages
    warning = next(r for r in caplog.records if r.getMessage() == "no_advisors_configured")
    assert warning.levelno == logging.WARNING


def test_startup_log_does_not_contain_profile_ids(caplog):
    """R44: los registros de arranque no incluyen los ids de los perfiles."""
    adapters, repo, _ = _build_adapters()
    repo.replace_roster(
        [AdvisorRosterEntry(profile_id="perfil-secreto-987", role="asesor")], 1
    )
    caplog.set_level(logging.DEBUG)
    with TestClient(create_app(Settings(service_token=TOKEN), adapters)):
        pass
    assert caplog.records
    for record in caplog.records:
        assert "perfil-secreto-987" not in record.getMessage()


def test_handover_without_roster_returns_no_advisors():
    """R15: roster vacío -> no_advisors sin enviar y el caso pasa a timed_out."""
    adapters, repo, gateway = _build_adapters()
    settings = Settings(service_token=TOKEN)
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


def test_import_main_does_not_require_advisor_chat_ids():
    """R44, R45: importar main funciona sin ADVISOR_CHAT_IDS."""
    env = {name: value for name, value in os.environ.items() if name not in SETTINGS_ENV}
    env["PYTHONPATH"] = os.pathsep.join(sys.path)

    result = subprocess.run(
        [sys.executable, "-c", "import handover.main"],
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )

    assert result.returncode == 0, result.stderr


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
    """R20-R22: el arranque registra cuántos huérfanos hay, sin ids."""
    adapters, repo, _ = _build_adapters()
    repo.replace_roster([AdvisorRosterEntry(profile_id="p1", role="asesor")], 1)
    repo.create_case(_case("c-registered", "assigned", "p1"))
    repo.create_case(_case("c-orphan", "assigned", "retirado"))
    repo.create_case(_case("c-null", "assigned", None))
    repo.create_case(_case("c-open", "open"))
    repo.create_case(_case("c-closed", "closed"))
    caplog.set_level(logging.INFO)

    with TestClient(create_app(Settings(service_token=TOKEN), adapters)) as client:
        assert client.get("/health").status_code == 200

    messages = [record.getMessage() for record in caplog.records]
    assert "orphan_cases count=2" in messages
    assert "orphan_cases_present count=2" in messages
    assert all("retirado" not in message for message in messages)
    assert all("c-registered" not in message for message in messages)
    assert all("c-orphan" not in message for message in messages)


def test_startup_without_orphans_logs_zero_and_no_warning(caplog):
    """R20: sin huérfanos no se emite el WARNING."""
    adapters, repo, _ = _build_adapters()
    repo.replace_roster([AdvisorRosterEntry(profile_id="p1", role="asesor")], 1)
    repo.create_case(_case("c-registered", "assigned", "p1"))
    repo.create_case(_case("c-open", "open"))
    caplog.set_level(logging.INFO)

    with TestClient(create_app(Settings(service_token=TOKEN), adapters)):
        pass

    messages = [record.getMessage() for record in caplog.records]
    assert "orphan_cases count=0" in messages
    assert all("orphan_cases_present" not in message for message in messages)


def test_startup_orphan_count_failure_warns_and_starts(monkeypatch, caplog):
    """R20: si el recuento falla, WARNING y el servicio arranca."""
    adapters, repo, _ = _build_adapters()

    def boom():
        raise RuntimeError("secreto-xyz")

    monkeypatch.setattr(repo, "count_assigned_by_advisor", boom)
    caplog.set_level(logging.INFO)

    with TestClient(create_app(Settings(service_token=TOKEN), adapters)) as client:
        assert client.get("/health").status_code == 200

    messages = [record.getMessage() for record in caplog.records]
    assert "orphan_cases_check_failed" in messages
    assert all("secreto-xyz" not in message for message in messages)


def test_create_app_does_not_count_orphans(monkeypatch):
    """R20: create_app no cuenta huérfanos hasta el arranque real."""
    adapters, repo, _ = _build_adapters()
    calls = []

    def boom():
        calls.append(1)
        raise AssertionError("no debe contar huérfanos")

    monkeypatch.setattr(repo, "count_assigned_by_advisor", boom)
    app = create_app(Settings(service_token=TOKEN), adapters)
    client = TestClient(app)
    assert client.get("/health").status_code == 200
    assert calls == []
