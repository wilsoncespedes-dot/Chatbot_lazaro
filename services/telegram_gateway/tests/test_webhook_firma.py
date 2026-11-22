"""R3-R5: firma HMAC-SHA256 y ventana anti-repetición del webhook genérico."""
from __future__ import annotations

import hashlib
import hmac
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from telegram_gateway import signature as signature_module
from telegram_gateway.signature import sign_payload, verify_signature

ROOT = Path(__file__).resolve().parents[3]
DOC = ROOT / "contracts" / "CONTRATOS.md"
SECRET = "secreto-de-ejemplo"
NOW = datetime(2026, 11, 21, 15, 0, tzinfo=timezone.utc)
BODY = b'{"channel":"canal-externo","external_message_id":"msg-1"}'


def _doc_http_blocks() -> list[tuple[str, dict[str, str], str]]:
    text = DOC.read_text(encoding="utf-8")
    start = text.index("## Canal genérico (webhook firmado)")
    section = text[start:]
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


def _timestamp(now: datetime) -> str:
    return str(int(now.timestamp()))


def test_sign_payload_reproduces_both_documented_signatures():
    """R3: las dos firmas de CONTRATOS.md se reproducen con secreto-de-ejemplo."""
    blocks = _doc_http_blocks()
    assert len(blocks) == 2
    for _, headers, body in blocks:
        timestamp = headers["x-lazaro-timestamp"]
        assert sign_payload(SECRET, timestamp, body.encode("utf-8")) == headers[
            "x-lazaro-signature"
        ]


def test_sign_payload_returns_lowercase_sha256_hex():
    """R3: 64 caracteres hexadecimales en minúsculas sobre `<timestamp>.<cuerpo>`."""
    result = sign_payload("secreto", 123, b"cuerpo")
    expected = hmac.new(
        b"secreto", b"123.cuerpo", hashlib.sha256
    ).hexdigest()
    assert result == expected
    assert len(result) == 64
    assert result == result.lower()
    assert re.fullmatch(r"[0-9a-f]{64}", result)


def test_valid_signature_within_window_is_accepted():
    """R4: firma correcta y timestamp dentro de la ventana devuelve verdadero."""
    timestamp = _timestamp(NOW)
    signature = sign_payload(SECRET, timestamp, BODY)
    assert verify_signature(SECRET, timestamp, signature, BODY, NOW, 300) is True


def test_missing_header_or_bad_format_is_rejected_without_raising():
    """R4: encabezados ausentes, no decimales o de longitud distinta son falsos."""
    timestamp = _timestamp(NOW)
    signature = sign_payload(SECRET, timestamp, BODY)
    assert verify_signature(SECRET, None, signature, BODY, NOW, 300) is False
    assert verify_signature(SECRET, timestamp, None, BODY, NOW, 300) is False
    assert verify_signature(SECRET, "12a", signature, BODY, NOW, 300) is False
    assert verify_signature(SECRET, "-12", signature, BODY, NOW, 300) is False
    assert verify_signature(SECRET, timestamp, signature[:-1], BODY, NOW, 300) is False
    assert verify_signature(SECRET, timestamp, signature + "0", BODY, NOW, 300) is False


def test_wrong_secret_or_body_is_rejected():
    """R4: la firma corresponde al secreto y al cuerpo exacto recibido."""
    timestamp = _timestamp(NOW)
    signature = sign_payload(SECRET, timestamp, BODY)
    assert verify_signature("otro-secreto", timestamp, signature, BODY, NOW, 300) is False
    assert verify_signature(SECRET, timestamp, signature, BODY + b" ", NOW, 300) is False


@pytest.mark.parametrize(
    "delta", [timedelta(seconds=-301), timedelta(seconds=301)]
)
def test_timestamp_outside_window_is_rejected_even_with_valid_signature(delta):
    """R5: fuera de la ventana en el pasado o en el futuro es falso."""
    event_time = NOW + delta
    timestamp = _timestamp(event_time)
    signature = sign_payload(SECRET, timestamp, BODY)
    assert verify_signature(SECRET, timestamp, signature, BODY, NOW, 300) is False


def test_timestamp_exactly_on_window_boundary_is_accepted():
    """R4, R5: el borde |ahora - timestamp| == ventana es válido."""
    event_time = NOW - timedelta(seconds=300)
    timestamp = _timestamp(event_time)
    signature = sign_payload(SECRET, timestamp, BODY)
    assert verify_signature(SECRET, timestamp, signature, BODY, NOW, 300) is True


def test_verify_signature_uses_constant_time_comparison(monkeypatch):
    """R4: la comparación de la firma usa hmac.compare_digest."""
    calls: list[tuple[str, str]] = []
    real = hmac.compare_digest

    def _spy(first, second):
        calls.append((first, second))
        return real(first, second)

    monkeypatch.setattr(signature_module.hmac, "compare_digest", _spy)
    timestamp = _timestamp(NOW)
    signature = sign_payload(SECRET, timestamp, BODY)
    assert verify_signature(SECRET, timestamp, signature, BODY, NOW, 300) is True
    assert calls
