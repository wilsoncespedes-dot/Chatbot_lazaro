"""Tests de scripts/vencer_casos.py (httpx.MockTransport, sin red)."""
from __future__ import annotations

import importlib.util
import json
import logging
from pathlib import Path

import httpx
import pytest

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "vencer_casos.py"
_spec = importlib.util.spec_from_file_location("vencer_casos", SCRIPT)
vencer = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(vencer)

INTERVAL_ENV = "CHECK_TIMEOUTS_INTERVAL_SECONDS"
HTTP_TIMEOUT_ENV = "CHECK_TIMEOUTS_HTTP_TIMEOUT_SECONDS"


@pytest.fixture()
def env_vars(monkeypatch):
    monkeypatch.setenv("HANDOVER_URL", "http://handover:8000")
    monkeypatch.setenv("SERVICE_TOKEN", "tok")
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.delenv(INTERVAL_ENV, raising=False)
    monkeypatch.delenv(HTTP_TIMEOUT_ENV, raising=False)
    return monkeypatch


def _client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def _ok(calls: list) -> httpx.Client:
    def handler(request):
        calls.append(request)
        return httpx.Response(200, json={"timed_out_cases": []})

    return _client(handler)


def _assert_rejected(argv: list[str], client: httpx.Client) -> None:
    try:
        code = vencer.main(argv, client=client)
    except SystemExit as exc:
        assert exc.code != 0
        return
    assert code != 0


def test_single_call_posts_check_timeouts_with_token(env_vars):
    """R1: una petición POST a {HANDOVER_URL}/cases/check-timeouts con token y cuerpo {}."""
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(200, json={"timed_out_cases": []})

    assert vencer.main([], client=_client(handler)) == 0
    env_vars.setenv("HANDOVER_URL", "http://handover:8000/")
    assert vencer.main([], client=_client(handler)) == 0

    assert len(seen) == 2
    for request in seen:
        assert str(request.url) == "http://handover:8000/cases/check-timeouts"
        assert request.method == "POST"
        assert json.loads(request.content) == {}
        assert request.headers["X-Service-Token"] == "tok"


def test_single_call_exits_zero_on_200(env_vars):
    """R2: en llamada única un 200 termina con código 0."""
    assert vencer.main([], client=_client(lambda r: httpx.Response(200, json={}))) == 0


@pytest.mark.parametrize("status", [401, 500, 503])
def test_single_call_exits_nonzero_on_401_and_500(env_vars, status):
    """R3: una respuesta distinta de 200 termina con código distinto de 0."""
    client = _client(lambda r: httpx.Response(status, json={"error": "fallo"}))
    assert vencer.main([], client=client) != 0


@pytest.mark.parametrize("error", [httpx.ConnectError, httpx.ReadTimeout])
def test_single_call_exits_nonzero_on_network_error(env_vars, error):
    """R4: un error de red o de tiempo de espera termina con código distinto de 0."""

    def boom(request):
        raise error("sin conexión")

    assert vencer.main([], client=_client(boom)) != 0


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("HANDOVER_URL", None),
        ("HANDOVER_URL", ""),
        ("SERVICE_TOKEN", None),
        ("SERVICE_TOKEN", ""),
    ],
)
def test_missing_env_exits_nonzero_without_request(env_vars, name, value):
    """R5: si falta HANDOVER_URL o SERVICE_TOKEN no se envía ninguna petición."""
    calls = []
    client = _ok(calls)
    if value is None:
        env_vars.delenv(name, raising=False)
    else:
        env_vars.setenv(name, value)
    assert vencer.main([], client=client) != 0
    assert calls == []


def test_loop_repeats_and_sleeps_interval(env_vars):
    """R6: --intervalo repite la llamada y espera el intervalo después de cada una."""
    calls: list = []
    sleeps: list[float] = []
    code = vencer.main(
        ["--intervalo", "30"],
        client=_ok(calls),
        sleep=sleeps.append,
        max_rounds=3,
    )
    assert code == 0
    assert len(calls) == 3
    assert sleeps == [30.0, 30.0]


def test_loop_interval_defaults_to_env_then_60(env_vars):
    """R7: --intervalo sin valor usa la variable de entorno o 60 por defecto."""
    calls: list = []
    sleeps: list[float] = []
    env_vars.setenv(INTERVAL_ENV, "45")
    assert (
        vencer.main(["--intervalo"], client=_ok(calls), sleep=sleeps.append, max_rounds=2) == 0
    )
    assert sleeps == [45.0]

    env_vars.delenv(INTERVAL_ENV, raising=False)
    sleeps = []
    assert (
        vencer.main(["--intervalo"], client=_ok(calls), sleep=sleeps.append, max_rounds=2) == 0
    )
    assert sleeps == [60.0]


@pytest.mark.parametrize("argv", [["--intervalo", "0"], ["--intervalo", "-5"], ["--intervalo", "abc"]])
def test_invalid_interval_exits_nonzero_without_request(env_vars, argv):
    """R8: un intervalo no numérico o <= 0 no envía ninguna petición."""
    calls: list = []
    _assert_rejected(argv, _ok(calls))
    assert calls == []


@pytest.mark.parametrize("value", ["0", "-5", "abc"])
def test_invalid_interval_from_env_exits_nonzero_without_request(env_vars, value):
    """R8: --intervalo sin valor con la variable inválida no envía peticiones."""
    env_vars.setenv(INTERVAL_ENV, value)
    calls: list = []
    _assert_rejected(["--intervalo"], _ok(calls))
    assert calls == []


def test_explicit_interval_ignores_invalid_env(env_vars):
    """R8: con --intervalo 30 no se lee la variable de entorno."""
    env_vars.setenv(INTERVAL_ENV, "abc")
    calls: list = []
    sleeps: list[float] = []
    code = vencer.main(
        ["--intervalo", "30"], client=_ok(calls), sleep=sleeps.append, max_rounds=1
    )
    assert code == 0
    assert len(calls) == 1
    assert sleeps == []


@pytest.mark.parametrize("value", ["0", "-5", "abc"])
def test_single_call_ignores_invalid_interval_env(env_vars, value):
    """R30: la llamada única no falla por un CHECK_TIMEOUTS_INTERVAL_SECONDS inválido."""
    env_vars.setenv(INTERVAL_ENV, value)
    calls: list = []
    assert vencer.main([], client=_ok(calls)) == 0
    assert len(calls) == 1


def test_loop_logs_failure_code(env_vars, caplog):
    """R9: un fallo deja en el log el código HTTP o el tipo de error."""
    caplog.set_level(logging.DEBUG, logger="vencer_casos")
    outcomes = ["401", "500", "error"]

    def handler(request):
        outcome = outcomes.pop(0)
        if outcome == "error":
            raise httpx.ConnectError("sin conexión")
        return httpx.Response(int(outcome), json={"error": "fallo"})

    vencer.main(
        ["--intervalo", "1"], client=_client(handler), sleep=lambda _: None, max_rounds=3
    )
    assert "status=401" in caplog.text
    assert "status=500" in caplog.text
    assert "ConnectError" in caplog.text


def test_loop_continues_after_failures(env_vars):
    """R10: el bucle sigue tras un error de red, un 500 y un 401."""
    calls: list = []
    sleeps: list[float] = []
    outcomes = [httpx.ConnectError("sin conexión"), 500, 401, 200]

    def handler(request):
        calls.append(request)
        outcome = outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return httpx.Response(outcome, json={"timed_out_cases": []})

    code = vencer.main(
        ["--intervalo", "1"],
        client=_client(handler),
        sleep=sleeps.append,
        max_rounds=4,
    )
    assert code == 0
    assert len(calls) == 4
    assert sleeps == [1.0, 1.0, 1.0]


def test_token_never_in_logs_or_output(env_vars, caplog, capsys):
    """R11: el token no aparece en el log, la salida estándar ni la salida de error."""
    token = "TOKEN-SECRETO-XYZ"
    env_vars.setenv("SERVICE_TOKEN", token)
    caplog.set_level(logging.DEBUG)

    def run(argv, handler, **kwargs):
        try:
            vencer.main(argv, client=_client(handler), **kwargs)
        except SystemExit as exc:
            assert exc.code != 0
        out, err = capsys.readouterr()
        assert token not in caplog.text
        assert token not in out and token not in err

    def ok(request):
        return httpx.Response(200, json={"timed_out_cases": []})

    def unauthorized(request):
        return httpx.Response(401, json={"error": "unauthorized", "message": "no"})

    def internal(request):
        return httpx.Response(500, json={"error": "internal_error", "message": "no"})

    def network(request):
        raise httpx.ConnectError(f"fallo con {token}")

    run([], ok)
    run([], unauthorized)
    run([], internal)
    run([], network)
    run(["--intervalo", "abc"], ok)
    env_vars.setenv(HTTP_TIMEOUT_ENV, "abc")
    run([], ok)
    env_vars.delenv(HTTP_TIMEOUT_ENV, raising=False)
    run(["--intervalo", "1"], network, sleep=lambda _: None, max_rounds=1)


def _request_timeout(request: httpx.Request) -> float:
    value = request.extensions["timeout"]
    if isinstance(value, dict):
        values = set(value.values())
        assert len(values) == 1
        return next(iter(values))
    return value


@pytest.mark.parametrize(("value", "expected"), [(None, 120.0), ("7", 7.0)])
def test_request_uses_http_timeout_from_env(env_vars, value, expected):
    """R12: cada petición usa CHECK_TIMEOUTS_HTTP_TIMEOUT_SECONDS o 120 por defecto."""
    if value is None:
        env_vars.delenv(HTTP_TIMEOUT_ENV, raising=False)
    else:
        env_vars.setenv(HTTP_TIMEOUT_ENV, value)
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(200, json={"timed_out_cases": []})

    assert vencer.main([], client=_client(handler)) == 0
    assert _request_timeout(seen[0]) == expected


@pytest.mark.parametrize("value", ["0", "-1", "abc"])
@pytest.mark.parametrize("argv", [[], ["--intervalo", "30"]])
def test_invalid_http_timeout_exits_nonzero_without_request(env_vars, caplog, value, argv):
    """R29: un timeout HTTP inválido no envía peticiones y nombra la variable en el log."""
    env_vars.setenv(HTTP_TIMEOUT_ENV, value)
    caplog.set_level(logging.DEBUG, logger="vencer_casos")
    calls: list = []
    assert vencer.main(argv, client=_ok(calls)) != 0
    assert calls == []
    assert HTTP_TIMEOUT_ENV in caplog.text


def test_handover_url_host_port_is_normalized_to_http(env_vars):
    """R12: HANDOVER_URL sin esquema se usa como http://host:puerto."""
    env_vars.setenv("HANDOVER_URL", "handover:8000")
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(200, json={"timed_out_cases": []})

    assert vencer.main([], client=_client(handler)) == 0
    assert str(seen[0].url) == "http://handover:8000/cases/check-timeouts"


def test_short_service_token_is_rejected_in_production(env_vars):
    """R16: con APP_ENV=production un SERVICE_TOKEN corto no envía peticiones."""
    env_vars.setenv("APP_ENV", "production")
    env_vars.setenv("SERVICE_TOKEN", "x" * 31)
    calls: list = []
    assert vencer.main([], client=_ok(calls)) != 0
    assert calls == []


def test_long_service_token_is_accepted_in_production(env_vars):
    """R16: con APP_ENV=production un SERVICE_TOKEN de 32+ caracteres sí llama."""
    env_vars.setenv("APP_ENV", "production")
    env_vars.setenv("SERVICE_TOKEN", "x" * 32)
    calls: list = []
    assert vencer.main([], client=_ok(calls)) == 0
    assert len(calls) == 1
