"""Envía un mensaje SIMULADO al webhook genérico firmado de Lázaro.

Uso:
    python scripts/simular_canal.py --canal tiktok-simulado --usuario cliente-demo \
        --texto "Hola" --id-mensaje sim-1

El secreto del canal se lee de `LAZARO_CANAL_SECRETO` (o de la variable indicada
con `--secreto-env`); nunca se acepta como argumento ni se imprime.
"""
from __future__ import annotations

import argparse
import hashlib
import hmac
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Mapping
from urllib.error import HTTPError
from urllib.request import Request, urlopen

_CONTRACTS = Path(__file__).resolve().parents[1] / "contracts"
if _CONTRACTS.is_dir() and str(_CONTRACTS) not in sys.path:
    sys.path.insert(0, str(_CONTRACTS))

from lazaro_contracts import (  # noqa: E402
    LAZARO_SIGNATURE_HEADER,
    LAZARO_TIMESTAMP_HEADER,
    NormalizedMessage,
)

DEFAULT_URL = "http://localhost:8001"
DEFAULT_SECRET_ENV = "LAZARO_CANAL_SECRETO"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def build_body(
    channel: str,
    user: str,
    text: str,
    message_id: str,
    now: datetime,
) -> bytes:
    """Serializa una sola vez el mensaje normalizado que se firmará."""
    message = NormalizedMessage(
        channel=channel,  # type: ignore[arg-type]
        external_user_id=user,
        external_chat_id=user,
        external_message_id=message_id,
        kind="text",
        text=text,
        received_at=now,
    )
    return message.model_dump_json(exclude_none=True).encode("utf-8")


def sign(secret: str, timestamp: int, body: bytes) -> str:
    """HMAC-SHA256 hexadecimal de `<timestamp>.<cuerpo>`."""
    message = f"{timestamp}.".encode("utf-8") + body
    return hmac.new(secret.encode("utf-8"), message, hashlib.sha256).hexdigest()


def urllib_post(url: str, body: bytes, headers: Mapping[str, str]) -> tuple[int, str]:
    request = Request(url, data=body, headers=dict(headers), method="POST")
    try:
        with urlopen(request, timeout=10) as response:
            return response.status, response.read().decode("utf-8", "replace")
    except HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", "replace")


def send(
    url: str,
    channel: str,
    secret: str,
    body: bytes,
    now: datetime,
    post: Callable[[str, bytes, Mapping[str, str]], tuple[int, str]] = urllib_post,
) -> tuple[int, str]:
    timestamp = int(now.timestamp())
    headers = {
        "Content-Type": "application/json",
        LAZARO_TIMESTAMP_HEADER: str(timestamp),
        LAZARO_SIGNATURE_HEADER: sign(secret, timestamp, body),
    }
    target = f"{url.rstrip('/')}/webhooks/{channel}"
    return post(target, body, headers)


def _rejects_secret_argument(argv: list[str]) -> bool:
    for token in argv:
        if token == "--secreto" or token.startswith("--secreto="):
            return True
    return False


def main(
    argv: list[str] | None = None,
    env: Mapping[str, str] | None = None,
    post: Callable[[str, bytes, Mapping[str, str]], tuple[int, str]] = urllib_post,
    now: Callable[[], datetime] = _utcnow,
) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    if _rejects_secret_argument(arguments):
        print(
            "El secreto se lee de una variable de entorno, no de un argumento.",
            file=sys.stderr,
        )
        return 2
    parser = argparse.ArgumentParser(
        description=(
            "Envía un mensaje de prueba por el webhook de un canal SIMULADO. "
            "La firma usa HMAC-SHA256 y el secreto nunca se imprime."
        )
    )
    parser.add_argument("--url", default=DEFAULT_URL, help="URL base del gateway")
    parser.add_argument("--canal", required=True, help="id del canal simulado")
    parser.add_argument("--usuario", required=True, help="id externo de prueba")
    parser.add_argument("--texto", required=True, help="texto que escribe el cliente")
    parser.add_argument("--id-mensaje", default=None, help="id externo del mensaje")
    parser.add_argument(
        "--secreto-env",
        default=DEFAULT_SECRET_ENV,
        help=f"variable de entorno con el secreto (por defecto {DEFAULT_SECRET_ENV})",
    )
    args = parser.parse_args(arguments)
    values = os.environ if env is None else env

    secret = values.get(args.secreto_env, "").strip()
    if not secret:
        print(
            f"Falta la variable de entorno {args.secreto_env} con el secreto del canal.",
            file=sys.stderr,
        )
        return 2

    message_id = args.id_mensaje or f"sim-{os.urandom(8).hex()}"
    current = now()
    body = build_body(args.canal, args.usuario, args.texto, message_id, current)
    try:
        status, response_body = send(
            args.url, args.canal, secret, body, current, post=post
        )
    except Exception as exc:  # noqa: BLE001 - R38 salida 2 sin traza
        print(f"Error de red al enviar el mensaje: {type(exc).__name__}", file=sys.stderr)
        return 2
    print(f"HTTP {status}")
    print(response_body)
    return 0 if status == 200 else 1


if __name__ == "__main__":
    sys.exit(main())
