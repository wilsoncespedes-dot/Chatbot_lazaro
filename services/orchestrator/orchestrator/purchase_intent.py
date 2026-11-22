"""Detección pura de intención de compra (#70): frases, intervalo y marca."""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Sequence

from .classifier import normalize_text

MAX_PHRASES = 30
MIN_PHRASE_CHARS = 3
MAX_PHRASE_CHARS = 80


def _has_control(text: str) -> bool:
    return any(ord(char) < 32 or ord(char) == 127 for char in text)


def parse_phrases(raw: str) -> tuple[str, ...]:
    """Divide por coma, normaliza, descarta vacías y deduplica conservando el orden."""
    phrases: list[str] = []
    seen: set[str] = set()
    for piece in raw.split(","):
        phrase = normalize_text(piece)
        if phrase and phrase not in seen:
            seen.add(phrase)
            phrases.append(phrase)
    return tuple(phrases)


def phrases_valid(raw: str) -> bool:
    """R2, R3: la lista no queda vacía, admite hasta 30 frases y no tiene controles."""
    pieces = [piece.strip() for piece in raw.split(",") if piece.strip()]
    if not pieces or any(_has_control(piece) for piece in pieces):
        return False
    phrases = parse_phrases(raw)
    if not 1 <= len(phrases) <= MAX_PHRASES:
        return False
    return all(
        MIN_PHRASE_CHARS <= len(phrase) <= MAX_PHRASE_CHARS for phrase in phrases
    )


def matches_purchase_phrase(text: str, phrases: Sequence[str]) -> bool:
    """R5, R22: comparación por subcadena normalizada, sin interpretar el texto."""
    normalized = normalize_text(text)
    for phrase in phrases:
        key = normalize_text(phrase)
        if key and key in normalized:
            return True
    return False


def within_interval(last: datetime | None, now: datetime, minutes: int) -> bool:
    """R19, R20: True mientras no haya pasado el intervalo desde la última detección."""
    if last is None:
        return False
    return now - last < timedelta(minutes=minutes)


def has_purchase_interest(
    last_intent: datetime | None,
    last_closed: datetime | None,
    status: str,
    now: datetime,
    mark_hours: int,
) -> bool:
    """R13: detección posterior al último cierre, dentro de la ventana y no cerrada."""
    if status == "cerrada" or last_intent is None:
        return False
    if last_closed is not None and last_intent <= last_closed:
        return False
    return now - last_intent <= timedelta(hours=mark_hours)
