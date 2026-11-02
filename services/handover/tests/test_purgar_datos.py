"""Tests de scripts/purgar_datos.py (httpx.MockTransport, sin red)."""
from __future__ import annotations

import importlib.util
import json
import logging
from pathlib import Path

import httpx
import pytest

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "purgar_datos.py"
_spec = importlib.util.spec_from_file_location("purgar_datos", SCRIPT)
purgar = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(purgar)

INTERVAL_ENV = "PRIVACY_PURGE_INTERVAL_SECONDS"
HTTP_TIMEOUT_ENV = "PRIVACY_PURGE_HTTP_TIMEOUT_SECONDS"


@pytest.fixture()
def env_vars(monkeypatch):
    monkeypatch.setenv("HANDOVER_URL", "http://handover:8000")
    monkeypatch.setenv("ORCHESTRATOR_URL", "http://orchestrator:8000")
    monkeypatch.setenv("SERVICE_TOKEN", "tok")
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.delenv(INTERVAL_ENV, raising=False)
    monkeypatch.delenv(HTTP_TIMEOUT_ENV, raising=False)
    return monkeypatch


def _client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def _ok_client(calls: list) -> httpx.Client:
    def handler(request):
        calls.append(request)
        return httpx.Response(
            200, json={"cutoff": "2025-12-03T03:04:05Z", "deleted": {}, "closed_active_cases": 0}
        )

    return _client(handler)


def test_calls_handover_then_orchestrator_with_token_and_empty_body(env_vars):
    """R41, R42: handover primero y orchestrator después, con token y cuerpo {}."""
    calls: list = []
    assert purgar.main([], client=_ok_client(calls)) == 0
    assert [str(request.url) for request in calls] == [
        "http://handover:8000/privacy/purge",
        "http://orchestrator:8000/privacy/purge",
    ]
    for request in calls:
        assert request.method == "POST"
        assert json.loads(request.content) == {}
        assert request.headers["X-Service-Token"] == "tok"


def test_exit_zero_only_when_both_calls_are_200(env_vars):
    """R44: dos respuestas 200 terminan con código 0."""
    assert purgar.main([], client=_ok_client([])) == 0


@pytest.mark.parametrize("status", [401, 500, 503])
def test_handover_failure_skips_orchestrator_and_exits_nonzero(env_vars, status, caplog):
    """R43, R45: si handover falla no se llama al orchestrator y el código no es 0."""
    calls: list = []

    def handler(request):
        calls.append(request)
        return httpx.Response(status, json={"error": "fallo"})

    caplog.set_level(logging.DEBUG, logger="purgar_datos")
    assert purgar.main([], client=_client(handler)) != 0
    assert [str(request.url) for request in calls] == ["http://handover:8000/privacy/purge"]
    assert "privacy_purge_skipped service=orchestrator" in caplog.text


@pytest.mark.parametrize("error", [httpx.ConnectError, httpx.ReadTimeout])
def test_handover_network_error_skips_orchestrator(env_vars, error):
    """R43: un error de conexión en handover tampoco llama al orchestrator."""
    calls: list = []

    def handler(request):
        calls.append(request)
        raise error("sin conexión")

    assert purgar.main([], client=_client(handler)) != 0
    assert len(calls) == 1


def test_orchestrator_failure_exits_nonzero(env_vars):
    """R45: si falla la llamada al orchestrator el código no es 0."""
    calls: list = []

    def handler(request):
        calls.append(request)
        if request.url.host == "orchestrator":
            return httpx.Response(500, json={"error": "internal_error"})
        return httpx.Response(200, json={"deleted": {}, "closed_active_cases": 0})

    assert purgar.main([], client=_client(handler)) != 0
    assert [request.url.host for request in calls] == ["handover", "orchestrator"]


def test_loop_continues_after_a_failure_and_repeats_the_order(env_vars):
    """R46: en bucle sigue tras un fallo y repite handover → orchestrator."""
    calls: list = []
    handover_outcomes = [500, 200, 200]

    def handler(request):
        calls.append(request.url.host)
        if request.url.host == "handover":
            return httpx.Response(handover_outcomes.pop(0), json={})
        return httpx.Response(200, json={"deleted": {}, "closed_active_cases": 0})

    sleeps: list[float] = []
    code = purgar.main(
        ["--intervalo", "5"], client=_client(handler), sleep=sleeps.append, max_rounds=3
    )
    assert code == 0
    assert calls == ["handover", "handover", "orchestrator", "handover", "orchestrator"]
    assert sleeps == [5.0, 5.0]


def test_missing_env_exits_nonzero_without_request(env_vars):
    """R41, R42: sin URL o sin token no se envía ninguna petición."""
    calls: list = []
    env_vars.delenv("ORCHESTRATOR_URL")
    assert purgar.main([], client=_ok_client(calls)) != 0
    assert calls == []


def test_token_never_appears_in_logs(env_vars, caplog):
    """R41, R42: el token de servicio no se registra."""
    token = "TOKEN-SECRETO-XYZ"
    env_vars.setenv("SERVICE_TOKEN", token)
    caplog.set_level(logging.DEBUG)
    purgar.main([], client=_ok_client([]))
    assert token not in caplog.text
