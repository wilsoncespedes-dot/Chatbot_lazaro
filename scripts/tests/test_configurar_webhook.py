"""Tests de scripts/configurar_webhook.py con httpx.MockTransport (#24)."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "configurar_webhook.py"
_spec = importlib.util.spec_from_file_location("configurar_webhook", SCRIPT)
webhook = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(webhook)

TOKEN = "123456:BOT-TOKEN-SECRETO-XYZ"
SECRET = "SECRETO-WEBHOOK-1234567890-ABCDE"
BASE_URL = "https://lazaro-gateway.onrender.com"

VALID_ENV = {
    "TELEGRAM_BOT_TOKEN": TOKEN,
    "TELEGRAM_WEBHOOK_SECRET": SECRET,
    "PUBLIC_BASE_URL": BASE_URL,
}


def _client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def _telegram_ok(calls: list, info: dict | None = None) -> httpx.Client:
    def handler(request):
        calls.append(request)
        if request.url.path.endswith("/setWebhook"):
            return httpx.Response(200, json={"ok": True, "result": True})
        return httpx.Response(
            200,
            json={
                "ok": True,
                "result": info
                if info is not None
                else {
                    "url": BASE_URL + "/telegram/webhook",
                    "pending_update_count": 2,
                    "last_error_message": "timeout",
                },
            },
        )

    return _client(handler)


def _body(request: httpx.Request) -> dict:
    return json.loads(request.content)


def test_r23_set_webhook_uses_public_url_and_secret(capsys):
    """R23: setWebhook recibe <PUBLIC_BASE_URL>/telegram/webhook y el secret_token."""
    calls: list = []
    assert webhook.main([], env=VALID_ENV, client=_telegram_ok(calls)) == 0
    assert len(calls) == 2
    request = calls[0]
    assert request.method == "POST"
    assert str(request.url).endswith("/setWebhook")
    payload = _body(request)
    assert payload["url"] == BASE_URL + "/telegram/webhook"
    assert payload["secret_token"] == SECRET
    assert payload["allowed_updates"] == ["message"]
    assert "drop_pending_updates" not in payload


@pytest.mark.parametrize(
    "base_url", ["http://lazaro-gateway.onrender.com", "gateway.onrender.com", ""]
)
def test_r24_non_https_public_url_exits_nonzero_without_calls(base_url):
    """R24: PUBLIC_BASE_URL no https -> distinto de 0 sin llamar a Telegram."""
    calls: list = []
    code = webhook.main(
        [], env={**VALID_ENV, "PUBLIC_BASE_URL": base_url}, client=_telegram_ok(calls)
    )
    assert code != 0
    assert calls == []


@pytest.mark.parametrize(
    "secret", ["a" * 31, "a" * 31 + "+", "a" * 257, "cambia-esto"]
)
def test_r25_invalid_secret_exits_nonzero_without_calls(secret):
    """R25: un secret_token inválido -> distinto de 0 sin llamar a Telegram."""
    calls: list = []
    code = webhook.main(
        [], env={**VALID_ENV, "TELEGRAM_WEBHOOK_SECRET": secret},
        client=_telegram_ok(calls),
    )
    assert code != 0
    assert calls == []


@pytest.mark.parametrize(
    "name", ["TELEGRAM_BOT_TOKEN", "TELEGRAM_WEBHOOK_SECRET", "PUBLIC_BASE_URL"]
)
def test_r25_missing_variable_exits_nonzero_without_calls(name):
    """R25: falta una variable obligatoria -> distinto de 0 sin llamar a Telegram."""
    calls: list = []
    env = {key: value for key, value in VALID_ENV.items() if key != name}
    assert webhook.main([], env=env, client=_telegram_ok(calls)) != 0
    assert calls == []


def test_r26_prints_webhook_info(capsys):
    """R26: tras setWebhook se consulta y se imprime getWebhookInfo."""
    calls: list = []
    assert webhook.main([], env=VALID_ENV, client=_telegram_ok(calls)) == 0
    assert str(calls[1].url).endswith("/getWebhookInfo")
    out = capsys.readouterr().out
    assert "url: https://lazaro-gateway.onrender.com/telegram/webhook" in out
    assert "pending_update_count: 2" in out
    assert "last_error_message: timeout" in out


def test_r27_success_never_prints_token_or_secret(capsys):
    """R27: en éxito el token y el secreto no aparecen en stdout ni stderr."""
    calls: list = []
    assert webhook.main([], env=VALID_ENV, client=_telegram_ok(calls)) == 0
    out, err = capsys.readouterr()
    assert TOKEN not in out and TOKEN not in err
    assert SECRET not in out and SECRET not in err


def test_r27_http_error_never_prints_token_or_secret(capsys):
    """R27: ante un error HTTP no se imprime ni el token ni el secreto."""

    def handler(request):
        return httpx.Response(500, text=f"fallo con {TOKEN} y {SECRET}")

    assert webhook.main([], env=VALID_ENV, client=_client(handler)) != 0
    out, err = capsys.readouterr()
    assert TOKEN not in out and TOKEN not in err
    assert SECRET not in out and SECRET not in err


def test_r27_network_error_never_prints_token_or_secret(capsys):
    """R27: ante un error de red no se imprime ni el token ni el secreto."""

    def handler(request):
        raise httpx.ConnectError(f"sin conexión a {TOKEN} con {SECRET}")

    assert webhook.main([], env=VALID_ENV, client=_client(handler)) != 0
    out, err = capsys.readouterr()
    assert TOKEN not in out and TOKEN not in err
    assert SECRET not in out and SECRET not in err
    assert "ConnectError" in err


def test_solo_consultar_only_calls_get_webhook_info(capsys):
    """Consulta sin registrar: no requiere URL ni secreto y no llama a setWebhook."""
    calls: list = []
    env = {"TELEGRAM_BOT_TOKEN": TOKEN}
    assert webhook.main(["--solo-consultar"], env=env, client=_telegram_ok(calls)) == 0
    assert len(calls) == 1
    assert str(calls[0].url).endswith("/getWebhookInfo")
    out = capsys.readouterr().out
    assert "url:" in out


def test_drop_pending_option_is_sent_to_set_webhook():
    """El flag --drop-pending viaja en el payload de setWebhook."""
    calls: list = []
    assert (
        webhook.main(["--drop-pending"], env=VALID_ENV, client=_telegram_ok(calls)) == 0
    )
    assert _body(calls[0])["drop_pending_updates"] is True


def test_env_example_declares_environment_and_public_url():
    """R8, R13: .env.example declara APP_ENV y PUBLIC_BASE_URL."""
    lines = {
        line.split("=", 1)[0].strip()
        for line in (ROOT / ".env.example").read_text(encoding="utf-8").splitlines()
        if "=" in line and not line.lstrip().startswith("#")
    }
    assert {"APP_ENV", "PUBLIC_BASE_URL"} <= lines
