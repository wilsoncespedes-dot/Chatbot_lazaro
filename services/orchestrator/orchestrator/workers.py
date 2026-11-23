"""Workers de la cola: `procesar_entrantes` y `enviar_salientes` (#64)."""
from __future__ import annotations

import argparse
import logging
import time

from lazaro_contracts.production import require_service_token

from .config import Settings
from .main import build_default_adapters
from .queue import run_inbox_once, run_outbox_once

logger = logging.getLogger(__name__)

MODES = ("procesar_entrantes", "enviar_salientes")


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Worker de la cola del orquestador")
    parser.add_argument("modo", choices=MODES)
    parser.add_argument("--una-vez", action="store_true", dest="una_vez")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = _parse_args(argv)
    settings = Settings()
    require_service_token(settings.service_token)
    adapters = build_default_adapters(settings)
    runner = run_inbox_once if args.modo == "procesar_entrantes" else run_outbox_once
    if args.una_vez:
        while runner(settings, adapters):
            pass
        return
    while True:
        try:
            processed = runner(settings, adapters)
        except Exception as exc:  # noqa: BLE001 - el bucle nunca muere
            logger.error(
                "worker_loop_error mode=%s code=%s", args.modo, type(exc).__name__
            )
            processed = False
        if not processed:
            time.sleep(settings.worker_poll_seconds)


if __name__ == "__main__":
    main()
