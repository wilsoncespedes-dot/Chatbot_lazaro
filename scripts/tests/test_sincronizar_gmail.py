"""R15-R16: selección de canales Gmail y errores del scheduler."""
from __future__ import annotations

import httpx
import pytest

from scripts.sincronizar_gmail import INTERVAL_ENV, main, run


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self.payload = payload
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("error", request=None, response=httpx.Response(self.status_code))

    def json(self):
        return self.payload


class FakeClient:
    def __init__(self, fail_id=None):
        self.fail_id = fail_id
        self.posts = []

    def get(self, *args, **kwargs):
        return FakeResponse({"channels": [
            {"id": "gmail-on", "adapter_type": "gmail_api", "active": True},
            {"id": "gmail-off", "adapter_type": "gmail_api", "active": False},
            {"id": "telegram", "adapter_type": "telegram", "active": True},
        ]})

    def post(self, url, **kwargs):
        self.posts.append(url)
        status = 500 if self.fail_id and url.endswith(self.fail_id + "/gmail/sync") else 200
        return FakeResponse({"processed": 1, "status": "synced"}, status)


def test_scheduler_syncs_only_active_gmail_channels():
    """R15: el scheduler selecciona solo adaptadores Gmail activos."""
    client = FakeClient()
    assert run(client, "http://gateway", "secret") is True
    assert client.posts == ["http://gateway/channels/gmail-on/gmail/sync"]


def test_scheduler_fails_when_one_gmail_channel_fails():
    """R16: un canal fallido produce resultado global fallido."""
    assert run(FakeClient(fail_id="gmail-on"), "http://gateway", "secret") is False


@pytest.fixture
def gateway_env(monkeypatch):
    monkeypatch.setenv("TELEGRAM_GATEWAY_URL", "http://gateway/")
    monkeypatch.setenv("SERVICE_TOKEN", "secret")
    monkeypatch.delenv(INTERVAL_ENV, raising=False)


def test_main_without_interval_runs_once_and_reports_failure(gateway_env):
    """Sin --intervalo hace una sola pasada y devuelve 1 si un canal falla."""
    client = FakeClient(fail_id="gmail-on")
    slept = []
    assert main([], client=client, sleep=slept.append) == 1
    assert client.posts == ["http://gateway/channels/gmail-on/gmail/sync"]
    assert slept == []


def test_main_interval_loops_every_5_seconds_by_default(gateway_env):
    """--intervalo sin valor repite cada 5 s y sigue aunque una pasada falle."""
    client = FakeClient(fail_id="gmail-on")
    slept = []
    assert main(["--intervalo"], client=client, sleep=slept.append, max_rounds=3) == 0
    assert len(client.posts) == 3
    assert slept == [5.0, 5.0]


def test_main_interval_reads_env_and_explicit_value(gateway_env, monkeypatch):
    """GMAIL_SYNC_INTERVAL_SECONDS cambia el periodo; un valor explícito lo reemplaza."""
    monkeypatch.setenv(INTERVAL_ENV, "15")
    slept = []
    main(["--intervalo"], client=FakeClient(), sleep=slept.append, max_rounds=2)
    assert slept == [15.0]
    slept.clear()
    main(["--intervalo", "5"], client=FakeClient(), sleep=slept.append, max_rounds=2)
    assert slept == [5.0]


@pytest.mark.parametrize("value", ["0", "-3", "abc"])
def test_main_rejects_invalid_interval(gateway_env, value):
    """Un intervalo no positivo o no numérico es un error de uso."""
    with pytest.raises(SystemExit) as exc:
        main(["--intervalo", value], client=FakeClient(), sleep=lambda _: None, max_rounds=1)
    assert exc.value.code == 2


def test_main_loop_survives_unexpected_errors(gateway_env):
    """Una excepción inesperada no tumba el worker."""

    class Exploding(FakeClient):
        def get(self, *args, **kwargs):
            raise RuntimeError("boom")

    slept = []
    assert main(["--intervalo"], client=Exploding(), sleep=slept.append, max_rounds=2) == 0
    assert slept == [5.0]


def test_main_requires_gateway_env(monkeypatch):
    """Sin TELEGRAM_GATEWAY_URL o SERVICE_TOKEN no arranca."""
    monkeypatch.delenv("TELEGRAM_GATEWAY_URL", raising=False)
    monkeypatch.setenv("SERVICE_TOKEN", "secret")
    assert main(["--intervalo"], client=FakeClient(), sleep=lambda _: None, max_rounds=1) == 1
