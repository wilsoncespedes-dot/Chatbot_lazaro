"""Clasificador determinista de consultas por palabras clave (lógica pura)."""
from __future__ import annotations

import math
import re
import unicodedata
from dataclasses import dataclass

UNCLASSIFIED = "sin_clasificar"
CODE_PATTERN = re.compile(r"^[a-z][a-z0-9_]{0,15}$")
MAX_KEYWORDS = 50
MAX_KEYWORD_LENGTH = 60
MAX_NAME_LENGTH = 60
_WORD_SPLIT = re.compile(r"[^a-z0-9]+")


@dataclass(frozen=True)
class Category:
    id: str
    code: str
    name: str
    keywords: tuple[str, ...]
    active: bool


@dataclass(frozen=True)
class Classification:
    category: str
    confidence: float
    scores: dict[str, float]


def normalize_text(text: str) -> str:
    """Minúsculas, sin tildes (NFKD) y espacios colapsados."""
    decomposed = unicodedata.normalize("NFKD", text.lower())
    stripped = "".join(c for c in decomposed if not unicodedata.combining(c))
    return " ".join(stripped.split())


def _phrase(text: str) -> str:
    """Normaliza y reduce a palabras separadas por un espacio (puntuación fuera)."""
    parts = _WORD_SPLIT.split(normalize_text(text))
    return " ".join(part for part in parts if part)


def parse_keywords(raw: str) -> tuple[str, ...]:
    """Separa por coma o salto de línea, normaliza, descarta vacías y deduplica."""
    seen: set[str] = set()
    result: list[str] = []
    for piece in re.split(r"[,\n]", raw):
        keyword = _phrase(piece)
        if not keyword:
            continue
        if len(keyword) > MAX_KEYWORD_LENGTH:
            raise ValueError("keyword demasiado larga")
        if keyword not in seen:
            seen.add(keyword)
            result.append(keyword)
    if not 1 <= len(result) <= MAX_KEYWORDS:
        raise ValueError("número de keywords inválido")
    return tuple(result)


def validate_category_fields(
    code: str | None, name: str, keywords_raw: str
) -> tuple[str | None, str, tuple[str, ...]]:
    """Valida `code` (si se envía), `name` y `keywords`; normaliza los valores."""
    validated_code: str | None = None
    if code is not None:
        if not CODE_PATTERN.fullmatch(code):
            raise ValueError("código inválido")
        validated_code = code
    stripped_name = name.strip()
    if not 1 <= len(stripped_name) <= MAX_NAME_LENGTH:
        raise ValueError("nombre inválido")
    return validated_code, stripped_name, parse_keywords(keywords_raw)


def parse_threshold(raw: str) -> float:
    """Convierte el umbral a decimal finito en [0, 1]; ValueError si no lo es."""
    try:
        value = float(raw)
    except (TypeError, ValueError):
        raise ValueError("umbral inválido") from None
    if not math.isfinite(value) or not 0 <= value <= 1:
        raise ValueError("umbral inválido")
    return value


def _score(text_haystack: str, category: Category) -> int:
    hits = 0
    for keyword in set(category.keywords):
        normalized = _phrase(keyword)
        if normalized and f" {normalized} " in text_haystack:
            hits += 1
    return hits


def classify(
    text: str, categories: list[Category], threshold: float
) -> Classification:
    """Puntúa las categorías activas y aplica umbral y empate según R13–R21."""
    haystack = f" {_phrase(text)} "
    active = [category for category in categories if category.active]
    hits = {category.code: _score(haystack, category) for category in active}
    total = sum(hits.values())
    if not active or total == 0:
        scores = {category.code: 0.0 for category in active}
        return Classification(UNCLASSIFIED, 0.0, scores)

    scores = {code: count / total for code, count in hits.items()}
    best = max(scores.values())
    winners = [code for code, score in scores.items() if score == best]
    if len(winners) > 1:
        return Classification(UNCLASSIFIED, best, scores)
    if best < threshold:
        return Classification(UNCLASSIFIED, best, scores)
    return Classification(winners[0], best, scores)
