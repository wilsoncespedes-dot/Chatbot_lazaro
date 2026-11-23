"""Sincroniza todos los canales Gmail activos mediante el gateway.

Uso: python scripts/sincronizar_gmail.py
Requiere `TELEGRAM_GATEWAY_URL` y `SERVICE_TOKEN`; ejecútalo con un scheduler.
"""
from __future__ import annotations

import logging
import os
import sys
from typing import Any

import httpx

logger = logging.getLogger("sincronizar_gmail")


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
                logger.info(
                    "gmail_channel_synced channel_id=%s status=%s processed=%s",
                    channel_id,
                    body.get("status") if isinstance(body, dict) else "unknown",
                    body.get("processed", 0) if isinstance(body, dict) else 0,
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


def main(client: Any | None = None) -> int:
    base_url = os.environ.get("TELEGRAM_GATEWAY_URL", "").rstrip("/")
    token = os.environ.get("SERVICE_TOKEN", "")
    if not base_url or not token:
        logger.error("missing_env vars=TELEGRAM_GATEWAY_URL,SERVICE_TOKEN")
        return 1
    owns_client = client is None
    http = client or httpx.Client()
    try:
        return 0 if run(http, base_url, token) else 1
    finally:
        if owns_client:
            http.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    sys.exit(main())
