"""R1, R2: documentación y ejemplos firmados del webhook genérico (#62)."""
from __future__ import annotations

import hashlib
import hmac
import re
from pathlib import Path

DOC_PATH = Path(__file__).resolve().parent.parent / "CONTRATOS.md"
GENERIC_HEADING = "## Canal genérico (webhook firmado)"


def _doc() -> str:
    return DOC_PATH.read_text(encoding="utf-8")


def _generic() -> str:
    text = _doc()
    start = text.index(GENERIC_HEADING)
    rest = text[start + len(GENERIC_HEADING) :]
    match = re.search(r"^## ", rest, re.MULTILINE)
    return rest[: match.start()] if match else rest


def _http_blocks(section: str) -> list[tuple[str, dict[str, str], str]]:
    blocks = []
    for block in re.findall(r"```http\n(.*?)\n```", section, re.DOTALL):
        lines = block.splitlines()
        headers: dict[str, str] = {}
        for line in lines[1:-1]:
            if ":" in line:
                name, _, value = line.partition(":")
                headers[name.strip().lower()] = value.strip()
        blocks.append((lines[0], headers, lines[-1]))
    return blocks


def test_generic_section_documents_contract():
    """R1: tipo, callback_url, orden de errores, filas 413/503, ajustes y SSRF."""
    section = _generic()
    for fragment in (
        "webhook_generico",
        "config.callback_url",
        "https",
        "2048",
        "payload_too_large",
        "channel_store_unavailable",
        "channel_secrets_unavailable",
        "WEBHOOK_SIGNATURE_WINDOW_SECONDS",
        "WEBHOOK_MAX_BODY_BYTES",
        "WEBHOOK_ALLOW_PRIVATE_CALLBACKS",
        "SSRF",
        "502 upstream_error",
        "169.254.169.254",
    ):
        assert fragment in section, fragment
    assert "hasta entonces no existen" not in section

    flat = re.sub(r"\s+", " ", section)
    assert re.search(
        r"Los errores se aplican en este orden: `404`.*?`413`.*?`401`.*?`422`",
        flat,
    )


def test_both_signed_examples_are_verifiable_with_the_documented_secret():
    """R2: HMAC-SHA256 de <timestamp>.<cuerpo> coincide en los dos ejemplos."""
    section = _generic()
    secret_match = re.search(r"secreto de ejemplo `([^`]+)`", section)
    assert secret_match
    secret = secret_match.group(1)
    assert secret == "secreto-de-ejemplo"
    blocks = _http_blocks(section)
    assert len(blocks) == 2
    for _, headers, body in blocks:
        timestamp = headers["x-lazaro-timestamp"]
        signature = headers["x-lazaro-signature"]
        expected = hmac.new(
            secret.encode("utf-8"),
            f"{timestamp}.".encode("utf-8") + body.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        assert signature == expected
