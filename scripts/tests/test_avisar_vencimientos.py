"""Tests de scripts/avisar_vencimientos.py (#42)."""
from __future__ import annotations

import importlib.util
import logging
from pathlib import Path

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "avisar_vencimientos.py"
_spec = importlib.util.spec_from_file_location("avisar_vencimientos", SCRIPT)
worker = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(worker)

TOKEN = "token-de-servicio-largo-123"
BASE_URL = "https://orchestrator.example"


def _client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def _env(monkeypatch, **changes):
    values = {
        "ORCHESTRATOR_URL": BASE_URL,
        "SERVICE_TOKEN": TOKEN,
        "APP_ENV": "development",
    }
    values.update(changes)
    for key, value in values.items():
        if value is None:
            monkeypatch.delenv(key, raising=False)
        else:
            monkeypatch.setenv(key, value)


def test_single_call_sends_token_and_path(monkeypatch):
    """R60: llama a POST /credentials/expiry-notices con X-Service-Token."""
    _env(monkeypatch)
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(
            200,
            json={
                "enabled": True,
                "candidates": 1,
                "sent_text": 1,
                "sent_template": 0,
                "failed": 0,
                "skipped": {},
            },
        )

    assert worker.main([], client=_client(handler)) == 0
    assert len(calls) == 1
    request = calls[0]
    assert request.method == "POST"
    assert str(request.url).endswith("/credentials/expiry-notices")
    assert request.headers["X-Service-Token"] == TOKEN


def test_missing_env_returns_nonzero_without_network(monkeypatch):
    """R61: sin ORCHESTRATOR_URL o SERVICE_TOKEN termina sin llamar a la red."""
    called = []

    def handler(request):
        called.append(request)
        return httpx.Response(200, json={})

    for missing in ("ORCHESTRATOR_URL", "SERVICE_TOKEN"):
        _env(monkeypatch, **{missing: None})
        assert worker.main([], client=_client(handler)) != 0
    assert called == []


@pytest.mark.parametrize("value", ["0", "-1", "abc"])
def test_invalid_interval_exits_without_network(monkeypatch, value):
    """R61: un intervalo no numérico o no positivo termina con código != 0."""
    _env(monkeypatch)
    called = []

    def handler(request):
        called.append(request)
        return httpx.Response(200, json={})

    with pytest.raises(SystemExit) as exc:
        worker.main(["--intervalo", value], client=_client(handler))
    assert exc.value.code != 0
    assert called == []


def test_invalid_timeout_returns_nonzero_without_network(monkeypatch):
    """R61: un timeout inválido termina sin llamar a la red."""
    _env(monkeypatch, EXPIRY_NOTICE_HTTP_TIMEOUT_SECONDS="0")
    called = []

    def handler(request):
        called.append(request)
        return httpx.Response(200, json={})

    assert worker.main([], client=_client(handler)) != 0
    assert called == []


def test_loop_continues_after_error(monkeypatch):
    """R60: el bucle sigue iterando ante un error y registra el resultado."""
    _env(monkeypatch)
    responses = [httpx.Response(500, json={"error": "internal_error"}), httpx.Response(200, json={})]
    sleeps = []

    def handler(request):
        return responses.pop(0)

    assert worker.main(
        ["--intervalo", "1"], client=_client(handler), sleep=sleeps.append, max_rounds=2
    ) == 0
    assert sleeps == [1]


def test_logs_do_not_include_token_or_personal_data(monkeypatch, caplog):
    """R60: el log no contiene el token ni datos personales."""
    _env(monkeypatch)
    caplog.set_level(logging.INFO)
    worker.main(
        [],
        client=_client(lambda request: httpx.Response(500, json={"error": "x"})),
    )
    assert TOKEN not in caplog.text
    assert "profile_id" not in caplog.text
    assert "chat" not in caplog.text
