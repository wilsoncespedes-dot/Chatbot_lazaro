"""Funciones puras de intención de compra (#70)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from orchestrator.purchase_intent import (
    MAX_PHRASE_CHARS,
    MAX_PHRASES,
    MIN_PHRASE_CHARS,
    has_purchase_interest,
    matches_purchase_phrase,
    parse_phrases,
    phrases_valid,
    within_interval,
)

NOW = datetime(2026, 1, 2, 12, 0, tzinfo=timezone.utc)


def test_parse_phrases_normalizes_accents_case_and_drops_empties():
    """R2, R5: las frases se normalizan (tildes, mayúsculas) y se deduplican."""
    assert parse_phrases(" Me Interesa, ,QUIERO reservar,me interesa ") == (
        "me interesa",
        "quiero reservar",
    )


@pytest.mark.parametrize(
    "text",
    ["Me interesa mucho", "QUIERO RESERVAR una mesa", "quiero comprar ya"],
)
def test_matches_purchase_phrase_compares_normalized_substring(text):
    """R5, R22: la coincidencia es por subcadena normalizada."""
    phrases = ("me interesa", "quiero reservar", "quiero comprar")
    assert matches_purchase_phrase(text, phrases)


def test_matches_purchase_phrase_ignores_text_without_any_phrase():
    """R5: un texto sin frases configuradas no dispara la detección."""
    assert not matches_purchase_phrase("¿Cómo instalo el módulo?", ("me interesa",))
    assert not matches_purchase_phrase("me interesa", ())


@pytest.mark.parametrize(
    "raw",
    [
        "",
        " , , ",
        "a",
        "x" * (MAX_PHRASE_CHARS + 1),
        ",".join(f"frase {index}" for index in range(MAX_PHRASES + 1)),
        "me interesa,\x00quiero comprar",
    ],
)
def test_phrases_valid_rejects_invalid_lists(raw):
    """R2, R3: vacía, fuera de longitud, más de 30 frases o con controles."""
    assert not phrases_valid(raw)


def test_phrases_valid_accepts_boundaries_and_deduplicates():
    """R2: se aceptan los límites de longitud y hasta 30 frases únicas."""
    assert phrases_valid("abc")
    assert phrases_valid("x" * MAX_PHRASE_CHARS)
    assert phrases_valid(",".join(f"frase numero {index}" for index in range(MAX_PHRASES)))
    assert phrases_valid("me interesa,me interesa,quiero comprar")
    assert MIN_PHRASE_CHARS == 3


def test_within_interval_blocks_inside_and_allows_after_the_boundary():
    """R19, R20: dentro del intervalo no hay aviso nuevo; al cumplirlo, sí."""
    assert within_interval(NOW - timedelta(minutes=59), NOW, 60)
    assert not within_interval(NOW - timedelta(minutes=60), NOW, 60)
    assert not within_interval(NOW - timedelta(minutes=61), NOW, 60)
    assert not within_interval(None, NOW, 60)


def test_has_purchase_interest_window_status_and_case_closed():
    """R13: marca vigente dentro de la ventana, salvo cierre o estado cerrado."""
    last_intent = NOW - timedelta(hours=10)
    last_closed = NOW - timedelta(hours=20)
    assert has_purchase_interest(last_intent, last_closed, "atendida_por_bot", NOW, 72)
    assert not has_purchase_interest(
        last_intent, last_closed, "cerrada", NOW, 72
    )
    assert not has_purchase_interest(
        last_intent, NOW - timedelta(hours=5), "atendida_por_bot", NOW, 72
    )
    closed_before = NOW - timedelta(hours=80)
    assert has_purchase_interest(
        NOW - timedelta(hours=72), closed_before, "pendiente", NOW, 72
    )
    assert not has_purchase_interest(
        NOW - timedelta(hours=73), closed_before, "pendiente", NOW, 72
    )
    assert not has_purchase_interest(None, last_closed, "pendiente", NOW, 72)
