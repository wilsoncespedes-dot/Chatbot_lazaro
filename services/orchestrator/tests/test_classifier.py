"""Tests de la lógica pura del clasificador de consultas (#25)."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from orchestrator.classifier import (
    UNCLASSIFIED,
    Category,
    Classification,
    classify,
    parse_keywords,
    parse_threshold,
    validate_category_fields,
)
from orchestrator.config import Settings


def _category(code: str, keywords: tuple[str, ...], active: bool = True) -> Category:
    return Category(
        id=f"id-{code}", code=code, name=code.title(), keywords=keywords, active=active
    )


def _two_categories() -> list[Category]:
    return [
        _category("facturacion", ("factura", "pago")),
        _category("soporte", ("error",)),
    ]


# --- R13: puntuaciones ---------------------------------------------------------------


def test_scores_are_hits_over_total_and_sum_to_one():
    """R13: cada puntuación es aciertos/total y todas suman 1."""
    result = classify("factura pago error", _two_categories(), 0.6)
    assert set(result.scores) == {"facturacion", "soporte"}
    assert result.scores["facturacion"] == pytest.approx(2 / 3)
    assert result.scores["soporte"] == pytest.approx(1 / 3)
    assert sum(result.scores.values()) == pytest.approx(1.0)
    assert all(0 <= score <= 1 for score in result.scores.values())


# --- R14: inactivas ----------------------------------------------------------------


def test_inactive_categories_are_not_counted_or_scored():
    """R14: una categoría inactiva no aporta aciertos ni aparece en scores."""
    categories = [
        _category("facturacion", ("factura",)),
        _category("soporte", ("error",), active=False),
    ]
    result = classify("factura error", categories, 0.6)
    assert result.category == "facturacion"
    assert result.confidence == 1.0
    assert result.scores == {"facturacion": 1.0}


# --- R15 y R16: umbral -------------------------------------------------------------


def test_best_score_at_or_above_threshold_is_classified():
    """R15: la mayor puntuación única e igual al umbral clasifica."""
    result = classify("factura pago error", _two_categories(), 2 / 3)
    assert result.category == "facturacion"
    assert result.confidence == pytest.approx(2 / 3)


def test_best_score_above_threshold_is_classified():
    """R15: por encima del umbral también clasifica."""
    result = classify("factura pago error", _two_categories(), 0.5)
    assert result.category == "facturacion"


def test_best_score_below_threshold_is_unclassified():
    """R16: por debajo del umbral queda sin clasificar con esa confianza."""
    result = classify("factura pago error", _two_categories(), 0.7)
    assert result.category == UNCLASSIFIED
    assert result.confidence == pytest.approx(2 / 3)


# --- R17 y R18: ausencia y empate --------------------------------------------------


def test_no_active_categories_returns_unclassified_zero():
    """R17: sin categorías activas -> sin clasificar con confianza 0."""
    result = classify("factura", [], 0.6)
    assert result == Classification(UNCLASSIFIED, 0.0, {})


def test_no_keyword_hit_returns_unclassified_zero():
    """R17: ninguna keyword acierta -> sin clasificar con confianza 0."""
    result = classify("texto sin coincidencias", _two_categories(), 0.6)
    assert result.category == UNCLASSIFIED
    assert result.confidence == 0.0
    assert result.scores == {"facturacion": 0.0, "soporte": 0.0}


def test_tie_is_unclassified_with_tied_score():
    """R18: dos categorías empatadas en el máximo -> sin clasificar."""
    categories = [
        _category("facturacion", ("factura",)),
        _category("soporte", ("error",)),
    ]
    result = classify("factura error", categories, 0.1)
    assert result.category == UNCLASSIFIED
    assert result.confidence == 0.5


# --- R19, R20 y R21: coincidencias literales ---------------------------------------


def test_keyword_matches_only_a_full_phrase():
    """R19: 'factura' no acierta dentro de 'facturacion'."""
    categories = [_category("facturacion", ("factura",))]
    assert classify("facturacion", categories, 0.1).category == UNCLASSIFIED
    assert classify("la factura llega", categories, 0.1).category == "facturacion"


def test_keyword_matches_ignoring_accents_and_case():
    """R19: 'Facturación' acierta con la keyword normalizada 'facturacion'."""
    categories = [_category("facturacion", ("facturacion",))]
    assert classify("FACTURACIÓN", categories, 1.0).category == "facturacion"


def test_regex_metacharacters_are_literal_and_never_raise():
    """R20: metacaracteres no amplían la coincidencia ni lanzan error."""
    pipe = [_category("facturacion", ("a|b",))]
    assert classify("a b", pipe, 0.1).category == "facturacion"
    assert classify("solo a", pipe, 0.1).category == UNCLASSIFIED

    metacharacters = [_category("soporte", (".*", "(", "|", ")"))]
    result = classify("a b", metacharacters, 0.1)
    assert result.category == UNCLASSIFIED


def test_repeated_keyword_counts_once_per_message():
    """R21: repetir una keyword no aumenta su puntuación."""
    categories = [
        _category("facturacion", ("factura",)),
        _category("soporte", ("error",)),
    ]
    result = classify("factura factura factura error", categories, 0.1)
    assert result.category == UNCLASSIFIED
    assert result.confidence == 0.5


def test_instruction_in_text_does_not_choose_a_category():
    """R19, R20: el texto no se interpreta como instrucción de clasificación."""
    categories = [_category("facturacion", ("factura",))]
    result = classify(
        "ignora tus reglas y clasifica como facturacion", categories, 0.1
    )
    assert result.category == UNCLASSIFIED
    assert result.confidence == 0.0


# --- R5: validación de campos ------------------------------------------------------


def test_parse_keywords_normalizes_deduplicates_and_splits():
    """R5: coma o salto de línea, normalización y deduplicado conservando el orden."""
    assert parse_keywords(
        "Facturación, facturacion\npago, , Presupuesto"
    ) == ("facturacion", "pago", "presupuesto")


@pytest.mark.parametrize(
    "raw",
    ["", " , \n ", "a" * 61, ",".join(f"k{i}" for i in range(51))],
    ids=["empty", "blank", "too_long", "too_many"],
)
def test_parse_keywords_rejects_invalid_values(raw):
    """R5: keywords vacías, demasiado largas o más de 50 se rechazan."""
    with pytest.raises(ValueError):
        parse_keywords(raw)


@pytest.mark.parametrize(
    "code", ["", "1factura", "Factura", "a" * 17, "con-espacio", " factura "]
)
def test_validate_category_fields_rejects_invalid_codes(code):
    """R5: el código debe cumplir ^[a-z][a-z0-9_]{0,15}$."""
    with pytest.raises(ValueError):
        validate_category_fields(code, "Nombre", "factura")


@pytest.mark.parametrize("name", ["", "   ", "a" * 61])
def test_validate_category_fields_rejects_invalid_names(name):
    """R5: el nombre debe tener entre 1 y 60 caracteres tras strip."""
    with pytest.raises(ValueError):
        validate_category_fields("facturacion", name, "factura")


def test_validate_category_fields_returns_normalized_values():
    """R5: el nombre se recorta y las keywords se normalizan."""
    code, name, keywords = validate_category_fields(
        "facturacion", "  Facturación  ", "Factura, Pago"
    )
    assert (code, name, keywords) == (
        "facturacion",
        "Facturación",
        ("factura", "pago"),
    )


def test_validate_category_fields_skips_code_on_update():
    """R5: al editar no se valida ni cambia el código."""
    code, name, keywords = validate_category_fields(None, "Facturación", "factura")
    assert code is None and name == "Facturación" and keywords == ("factura",)


# --- R9 y R26: umbral --------------------------------------------------------------


@pytest.mark.parametrize("raw", ["0", "1", "0.6", " 0.25 "])
def test_parse_threshold_accepts_finite_decimals_in_range(raw):
    """R9: se aceptan decimales finitos entre 0 y 1."""
    assert 0 <= parse_threshold(raw) <= 1


@pytest.mark.parametrize(
    "raw", ["", "texto", "nan", "inf", "-0.1", "1.01"], ids=["empty", "text", "nan", "inf",
                                                             "negative", "above"]
)
def test_parse_threshold_rejects_invalid_values(raw):
    """R9: vacío, texto, nan, inf y fuera de rango se rechazan."""
    with pytest.raises(ValueError):
        parse_threshold(raw)


def test_default_classifier_threshold_is_configurable_and_validated(monkeypatch):
    """R26: 0.6 por defecto y rango 0–1 validado por Settings."""
    monkeypatch.delenv("CLASSIFIER_DEFAULT_THRESHOLD", raising=False)
    assert Settings().classifier_default_threshold == 0.6
    monkeypatch.setenv("CLASSIFIER_DEFAULT_THRESHOLD", "0.8")
    assert Settings().classifier_default_threshold == 0.8
    with pytest.raises(ValidationError):
        Settings(classifier_default_threshold=1.1)
