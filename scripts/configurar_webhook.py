"""Configura el webhook de Telegram sin imprimir jamás el token ni el secreto.

Uso: python scripts/configurar_webhook.py [--solo-consultar] [--drop-pending]
Lee TELEGRAM_BOT_TOKEN, TELEGRAM_WEBHOOK_SECRET y PUBLIC_BASE_URL del entorno.
PUBLIC_BASE_URL es la URL pública del servicio telegram-gateway (https).
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Mapping

import httpx

_CONTRACTS = Path(__file__).resolve().parents[1] / "contracts"
if _CONTRACTS.is_dir() and str(_CONTRACTS) not in sys.path:
    sys.path.insert(0, str(_CONTRACTS))

from lazaro_contracts.production import is_valid_webhook_secret  # noqa: E402

API_BASE = "https://api.telegram.org"
WEBHOOK_PATH = "/telegram/webhook"


def _response_ok(response: httpx.Response) -> tuple[bool, dict]:
    if response.status_code != 200:
        return False, {}
    try:
        body = response.json()
    except ValueError:
        return False, {}
    if not isinstance(body, dict):
        return False, {}
    return bool(body.get("ok")), body


def _network_error(exc: Exception) -> int:
    print(
        f"Error de red al llamar a Telegram: {type(exc).__name__}",
        file=sys.stderr,
    )
    return 1


def _http_error(action: str, response: httpx.Response) -> int:
    print(
        f"{action} falló: Telegram respondió con código {response.status_code}",
        file=sys.stderr,
    )
    return 1


def _print_webhook_info(result: Mapping[str, object]) -> None:
    print(f"url: {result.get('url') or ''}")
    print(f"pending_update_count: {result.get('pending_update_count', 0)}")
    print(f"last_error_message: {result.get('last_error_message') or ''}")


def main(
    argv: list[str] | None = None,
    env: Mapping[str, str] | None = None,
    client: httpx.Client | None = None,
) -> int:
    parser = argparse.ArgumentParser(description="Registra el webhook de Telegram.")
    parser.add_argument(
        "--solo-consultar",
        action="store_true",
        help="no registra el webhook; solo consulta getWebhookInfo",
    )
    parser.add_argument(
        "--drop-pending",
        action="store_true",
        help="descarta las actualizaciones pendientes al registrar",
    )
    args = parser.parse_args(argv)
    values = os.environ if env is None else env

    required = ["TELEGRAM_BOT_TOKEN"]
    if not args.solo_consultar:
        required += ["TELEGRAM_WEBHOOK_SECRET", "PUBLIC_BASE_URL"]
    missing = [name for name in required if not values.get(name, "").strip()]
    if missing:
        print(
            "Faltan variables de entorno: " + ", ".join(missing),
            file=sys.stderr,
        )
        return 2

    token = values.get("TELEGRAM_BOT_TOKEN", "")
    secret = values.get("TELEGRAM_WEBHOOK_SECRET", "")
    public_base_url = values.get("PUBLIC_BASE_URL", "").strip()

    if not args.solo_consultar:
        if not public_base_url.startswith("https://"):
            print("PUBLIC_BASE_URL debe empezar por https://", file=sys.stderr)
            return 2
        if not is_valid_webhook_secret(secret):
            print(
                "TELEGRAM_WEBHOOK_SECRET no cumple el formato de Telegram.",
                file=sys.stderr,
            )
            return 2

    owns_client = client is None
    http = client or httpx.Client(timeout=10)
    try:
        if not args.solo_consultar:
            payload: dict[str, object] = {
                "url": public_base_url.rstrip("/") + WEBHOOK_PATH,
                "secret_token": secret,
                "allowed_updates": ["message"],
            }
            if args.drop_pending:
                payload["drop_pending_updates"] = True
            try:
                response = http.post(f"{API_BASE}/bot{token}/setWebhook", json=payload)
            except Exception as exc:
                return _network_error(exc)
            ok, _ = _response_ok(response)
            if not ok:
                return _http_error("setWebhook", response)

        try:
            response = http.get(f"{API_BASE}/bot{token}/getWebhookInfo")
        except Exception as exc:
            return _network_error(exc)
        ok, body = _response_ok(response)
        if not ok:
            return _http_error("getWebhookInfo", response)
        result = body.get("result")
        _print_webhook_info(result if isinstance(result, dict) else {})
        return 0
    finally:
        if owns_client:
            http.close()


if __name__ == "__main__":
    sys.exit(main())
