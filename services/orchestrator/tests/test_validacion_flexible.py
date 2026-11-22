"""Pruebas de la validación sin falsos rechazos (#62)."""
from __future__ import annotations

import json

import pytest
from lazaro_contracts import SearchResult

from orchestrator.domain import LLM_SYSTEM_PROMPT, InvalidAnswer, validate_llm_answer

CHUNK = SearchResult(
    chunk_id="c1",
    manual="Siigo",
    score=0.7,
    text=(
        "Para crear una factura electrónica ingresa al menú Ventas, selecciona "
        "Factura de venta, completa los datos del cliente y presiona Guardar. "
        "El plazo es de 5 días."
    ),
)
OTHER = SearchResult(chunk_id="c2", manual="Siigo", score=0.6, text="Anula la factura desde Consultas.")


def _raw(answer: str, quote: str = "ingresa al menú Ventas", chunk_id: str = "c1") -> str:
    return json.dumps(
        {"answer": answer, "citations": [{"chunk_id": chunk_id, "quote": quote}]},
        ensure_ascii=False,
    )


def _reason(raw: str) -> str:
    with pytest.raises(InvalidAnswer) as exc:
        validate_llm_answer(raw, [CHUNK, OTHER])
    return exc.value.reason


# --- R1, R2: bloque de código ------------------------------------------------------


@pytest.mark.parametrize("fence", ["```json", "```", "```JSON"])
def test_fenced_json_is_accepted(fence):
    """R1"""
    raw = f"{fence}\n{_raw('Ve a Ventas.')}\n```"
    assert validate_llm_answer(raw, [CHUNK]).answer == "Ve a Ventas."


def test_fence_with_invalid_json_is_rejected():
    """R2"""
    assert _reason("```json\nVe a Ventas.\n```") == "invalid_json"
    assert _reason(f"Aquí va: {_raw('Ve a Ventas.')}") == "invalid_json"


# --- R3, R4: pasos numerados -----------------------------------------------------


@pytest.mark.parametrize(
    "answer",
    [
        "Sigue estos pasos:\n1. Ingresa a Ventas.\n2. Selecciona Factura de venta.\n3. Guarda.",
        "1) Ingresa a Ventas\n2) Guarda",
        "Paso 1: Ingresa a Ventas.\nPaso 2: Guarda.",
        "  10. Último paso.",
    ],
)
def test_step_markers_are_not_figures(answer):
    """R3"""
    assert validate_llm_answer(_raw(answer), [CHUNK]).answer == answer


def test_other_figures_must_be_in_citations():
    """R4: el plazo inventado se rechaza aunque haya pasos numerados."""
    assert _reason(_raw("1. Ve a Ventas.\nEl plazo es de 10 días.")) == "number_not_in_citations"
    assert _reason(_raw("Hazlo en 3 pasos.")) == "number_not_in_citations"
    assert _reason(_raw("1.500 pesos")) == "number_not_in_citations"
    assert validate_llm_answer(_raw("1. Ve a Ventas.\nTienes 5 días."), [CHUNK])


# --- R5, R6: citas --------------------------------------------------------------


@pytest.mark.parametrize(
    "quote",
    [
        "ingresa al menu Ventas",
        "INGRESA AL MENÚ VENTAS,",
        "Ventas selecciona Factura de venta",
        "«presiona Guardar»",
    ],
)
def test_quote_ignores_accents_and_punctuation(quote):
    """R5"""
    assert validate_llm_answer(_raw("Ve a Ventas.", quote), [CHUNK])


@pytest.mark.parametrize(
    "quote",
    [
        "Entra al menú Ventas",
        "menú Vent",
        "Anula la factura",
        "",
        "¿?",
    ],
)
def test_paraphrase_partial_word_or_other_chunk_rejected(quote):
    """R6"""
    assert _reason(_raw("Ve a Ventas.", quote)) == "quote_not_literal"


# --- R7: prompt -------------------------------------------------------------------


def test_prompt_allows_numbered_steps_but_not_other_figures():
    """R7"""
    assert "Puedes usar pasos numerados" in LLM_SYSTEM_PROMPT
    assert "cualquier otra cifra de answer debe aparecer en los fragmentos citados" in LLM_SYSTEM_PROMPT
