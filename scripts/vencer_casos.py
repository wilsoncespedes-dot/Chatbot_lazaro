"""Llama a POST /cases/check-timeouts de handover: una vez o en bucle.

Uso: python scripts/vencer_casos.py [--intervalo [segundos]]
Requiere `httpx` y las variables de entorno HANDOVER_URL y SERVICE_TOKEN.
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from pathlib import Path
from typing import Callable

import httpx

_CONTRACTS = Path(__file__).resolve().parents[1] / "contracts"
if _CONTRACTS.is_dir() and str(_CONTRACTS) not in sys.path:
    sys.path.insert(0, str(_CONTRACTS))

from lazaro_contracts.production import (  # noqa: E402
    MIN_SERVICE_TOKEN_LENGTH,
    normalize_service_url,
)

DEFAULT_INTERVAL_SECONDS = 60
DEFAULT_HTTP_TIMEOUT_SECONDS = 120
CHECK_TIMEOUTS_PATH = "/cases/check-timeouts"
INTERVAL_ENV = "CHECK_TIMEOUTS_INTERVAL_SECONDS"
HTTP_TIMEOUT_ENV = "CHECK_TIMEOUTS_HTTP_TIMEOUT_SECONDS"

logger = logging.getLogger("vencer_casos")

_FROM_ENV = object()


def _call_once(http: httpx.Client, url: str, token: str, timeout: float) -> bool:
    try:
        response = http.post(
            url,
            json={},
            headers={"X-Service-Token": token},
            timeout=timeout,
        )
    except httpx.HTTPError as exc:
        logger.error("check_timeouts_failed error=%s", type(exc).__name__)
        return False

    if response.status_code == 200:
        try:
            body = response.json()
            count = len(body["timed_out_cases"]) if isinstance(body, dict) else "?"
        except (ValueError, KeyError, TypeError):
            count = "?"
        logger.info("check_timeouts_ok timed_out=%s", count)
        return True

    error = f"http_{response.status_code}"
    try:
        body = response.json()
        if isinstance(body, dict) and body.get("error"):
            error = str(body["error"])
    except ValueError:
        pass
    logger.error("check_timeouts_failed status=%s error=%s", response.status_code, error)
    return False


def _parse_positive(raw: str) -> float:
    value = float(raw)
    if value <= 0:
        raise ValueError("no es mayor que 0")
    return value


def _resolve_interval(raw_option: object, parser: argparse.ArgumentParser) -> float:
    if raw_option is _FROM_ENV:
        raw = os.environ.get(INTERVAL_ENV)
        if raw is None:
            return DEFAULT_INTERVAL_SECONDS
    else:
        raw = str(raw_option)
    try:
        return _parse_positive(raw)
    except (TypeError, ValueError):
        parser.error("--intervalo debe ser un número mayor que 0")


def main(
    argv: list[str] | None = None,
    client: httpx.Client | None = None,
    sleep: Callable[[float], None] = time.sleep,
    max_rounds: int | None = None,
) -> int:
    parser = argparse.ArgumentParser(description="Vence los casos de handover vencidos.")
    parser.add_argument(
        "--intervalo",
        nargs="?",
        const=_FROM_ENV,
        default=None,
        help="segundos entre llamadas; sin valor usa CHECK_TIMEOUTS_INTERVAL_SECONDS",
    )
    args = parser.parse_args(argv)

    loop = args.intervalo is not None
    interval: float | None = None
    if loop:
        interval = _resolve_interval(args.intervalo, parser)

    handover_url = normalize_service_url(os.environ.get("HANDOVER_URL", ""))
    token = os.environ.get("SERVICE_TOKEN", "")
    missing = [
        name
        for name, value in (("HANDOVER_URL", handover_url), ("SERVICE_TOKEN", token))
        if not value
    ]
    if missing:
        logger.error("missing_env vars=%s", ",".join(missing))
        return 1

    if (
        os.environ.get("APP_ENV", "development") == "production"
        and len(token) < MIN_SERVICE_TOKEN_LENGTH
    ):
        logger.error("invalid_env var=SERVICE_TOKEN")
        return 1

    raw_timeout = os.environ.get(HTTP_TIMEOUT_ENV)
    if raw_timeout is None:
        timeout = float(DEFAULT_HTTP_TIMEOUT_SECONDS)
    else:
        try:
            timeout = _parse_positive(raw_timeout)
        except (TypeError, ValueError):
            logger.error("invalid_env var=%s", HTTP_TIMEOUT_ENV)
            return 2

    url = handover_url.rstrip("/") + CHECK_TIMEOUTS_PATH
    owns_client = client is None
    http = client or httpx.Client()
    try:
        if not loop:
            return 0 if _call_once(http, url, token, timeout) else 1

        rounds = 0
        while True:
            try:
                _call_once(http, url, token, timeout)
            except Exception as exc:
                logger.error("check_timeouts_failed error=%s", type(exc).__name__)
            rounds += 1
            if max_rounds is not None and rounds >= max_rounds:
                return 0
            sleep(interval or 0)
    finally:
        if owns_client:
            http.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    sys.exit(main())
