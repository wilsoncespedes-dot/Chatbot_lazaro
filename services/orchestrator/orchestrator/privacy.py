"""Utilidades puras del aviso de privacidad y del consentimiento (#27)."""
from __future__ import annotations

import hashlib


def normalize_privacy_text(text: str) -> str:
    """Minúsculas y espacios colapsados para comparar el aviso y la frase de aceptación."""
    return " ".join(text.split()).casefold()


def notice_sha256(text: str) -> str:
    """SHA-256 hexadecimal del aviso en UTF-8, como prueba del texto mostrado."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def is_acceptance(text: str, phrase: str) -> bool:
    """R12: la aceptación es igualdad normalizada, no una comprobación de contención."""
    if not phrase.strip():
        return False
    return normalize_privacy_text(text) == normalize_privacy_text(phrase)
