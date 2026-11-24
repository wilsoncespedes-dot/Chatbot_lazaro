"""Sincroniza todos los canales Gmail activos mediante el gateway: una vez o en bucle.

Uso: python scripts/sincronizar_gmail.py [--intervalo [segundos]]
Requiere `TELEGRAM_GATEWAY_URL` y `SERVICE_TOKEN`. Sin `--intervalo` hace una
pasada (para un scheduler externo); con `--intervalo` repite cada
`GMAIL_SYNC_INTERVAL_SECONDS` (5 por defecto), como el servicio
`gmail_sync_worker` de docker-compose.
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from typing import Any, Callable

import httpx

DEFAULT_INTERVAL_SECONDS = 5
INTERVAL_ENV = "GMAIL_SYNC_INTERVAL_SECONDS"

logger = logging.getLogger("sincronizar_gmail")

_FROM_ENV = object()


def run(client: Any, base_url: str, service_token: str, timeout: float = 30) -> bool:
    headers = {"X-Service-Token": service_token}
    try:
        response = client.get(f"{base_url.rstrip('/')}/channels", headers=headers, timeout=timeout)
        response.raise_for_status()
        payload = response.json()
        channels = payload.get("channels", []) if isinstance(payload, dict) else []
        ok = True
        for channel in channels:
            if (
                not isinstance(channel, dict)
                or channel.get("adapter_type") != "gmail_api"
                or not channel.get("active")
            ):
                continue
            channel_id = channel.get("id")
            if not isinstance(channel_id, str):
                ok = False
                continue
            try:
                result = client.post(
                    f"{base_url.rstrip('/')}/channels/{channel_id}/gmail/sync",
                    headers=headers,
                    timeout=timeout,
                )
                result.raise_for_status()
                body = result.json()
                status = body.get("status") if isinstance(body, dict) else "unknown"
                processed = body.get("processed", 0) if isinstance(body, dict) else 0
                # Con pasadas cada pocos segundos, las vacías no se registran.
                logger.log(
                    logging.DEBUG if status == "synced" and not processed else logging.INFO,
                    "gmail_channel_synced channel_id=%s status=%s processed=%s",
                    channel_id,
                    status,
                    processed,
                )
            except (httpx.HTTPError, ValueError) as exc:
                logger.error(
                    "gmail_channel_sync_failed channel_id=%s error=%s",
                    channel_id,
                    type(exc).__name__,
                )
                ok = False
        return ok
    except (httpx.HTTPError, ValueError, AttributeError) as exc:
        logger.error("gmail_sync_failed error=%s", type(exc).__name__)
        return False


def _resolve_interval(raw_option: object, parser: argparse.ArgumentParser) -> float:
    if raw_option is _FROM_ENV:
        raw = os.environ.get(INTERVAL_ENV, "").strip()
        if not raw:
            return float(DEFAULT_INTERVAL_SECONDS)
    else:
        raw = str(raw_option)
    try:
        value = float(raw)
    except (TypeError, ValueError):
        value = 0.0
    if value <= 0:
        parser.error("--intervalo debe ser un número mayor que 0")
    return value


def main(
    argv: list[str] | None = None,
    client: Any | None = None,
    sleep: Callable[[float], None] = time.sleep,
    max_rounds: int | None = None,
) -> int:
    parser = argparse.ArgumentParser(description="Sincroniza los canales Gmail activos.")
    parser.add_argument(
        "--intervalo",
        nargs="?",
        const=_FROM_ENV,
        default=None,
        help=f"segundos entre pasadas; sin valor usa {INTERVAL_ENV} (5)",
    )
    args = parser.parse_args(argv)
    interval = None if args.intervalo is None else _resolve_interval(args.intervalo, parser)

    base_url = os.environ.get("TELEGRAM_GATEWAY_URL", "").rstrip("/")
    token = os.environ.get("SERVICE_TOKEN", "")
    if not base_url or not token:
        logger.error("missing_env vars=TELEGRAM_GATEWAY_URL,SERVICE_TOKEN")
        return 1
    owns_client = client is None
    http = client or httpx.Client()
    try:
        if interval is None:
            return 0 if run(http, base_url, token) else 1
        # En bucle un fallo no detiene el worker: se reintenta en la próxima pasada.
        rounds = 0
        while True:
            try:
                run(http, base_url, token)
            except Exception as exc:  # noqa: BLE001 - el worker no debe morir
                logger.error("gmail_sync_failed error=%s", type(exc).__name__)
            rounds += 1
            if max_rounds is not None and rounds >= max_rounds:
                return 0
            sleep(interval)
    finally:
        if owns_client:
            http.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    sys.exit(main())
