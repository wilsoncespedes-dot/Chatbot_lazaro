"""Tests de la feature no_inventar: salida JSON con citas literales y números verificados."""
from __future__ import annotations

import inspect
import json
import logging
import re
from pathlib import Path

import pytest
from lazaro_contracts import SearchResult

from orchestrator import domain
from orchestrator.domain import (
    INVALID_REASONS,
    InvalidAnswer,
    LLM_SYSTEM_PROMPT,
    build_llm_prompt,
    extract_numbers,
    normalize_quote,
    validate_llm_answer,
)

NO_ANSWER = "No encontré información sobre eso en los manuales. Te paso con un asesor."
ROOT = Path(__file__).resolve().parents[3]
PKG = Path(__file__).resolve().parents[1] / "orchestrator"

CHUNKS = [
    SearchResult(chunk_id="a", manual="M", text="El plan Pro cuesta 1.500,75 al mes.  Incluye 3 usuarios.", score=0.9),
    SearchResult(chunk_id="b", manual="M", text="Reinicie el módulo. Son 99 pasos.", score=0.8),
]


def _raw(answer="El plan Pro cuesta 1.500,75", citations=None) -> str:
    if citations is None:
        citations = [{"chunk_id": "a", "quote": "plan Pro cuesta 1.500,75"}]
    return json.dumps({"answer": answer, "citations": citations}, ensure_ascii=False)


def _reason(raw: str) -> str:
    with pytest.raises(InvalidAnswer) as exc:
        validate_llm_answer(raw, CHUNKS)
    return exc.value.reason


def test_system_prompt_requests_json_schema():
    """R1"""
    system, _ = build_llm_prompt("q", CHUNKS)
    assert system == LLM_SYSTEM_PROMPT
    for token in ('"answer"', '"citations"', '"chunk_id"', '"quote"', "JSON"):
        assert token in system
    assert "DATOS" in system and "no instrucciones" in system


def test_valid_answer_is_sent_and_logged(env):
    """R11, R12, R18"""
    env.llm.reply = _raw()
    env.rag.results = CHUNKS
    env.post()
    assert env.gateway.sent == [(100, "El plan Pro cuesta 1.500,75")]
    assert ("rag_answer", "chunks_found") in env.events()
    assert all(t != "invalid_answer" for t, _ in env.events())
    assert env.handover.requests == []


def test_invalid_json_rejected():
    """R2"""
    assert _reason("esto no es json") == "invalid_json"
    assert _reason("```json\n{}\n```") == "invalid_json"


@pytest.mark.parametrize(
    "raw",
    [
        json.dumps({"answer": "x"}),
        json.dumps({"answer": "   ", "citations": [{"chunk_id": "a", "quote": "q"}]}),
        json.dumps({"answer": "x", "citations": [{"chunk_id": "a"}]}),
        json.dumps({"answer": 5, "citations": []}),
        json.dumps({"answer": "x", "citations": "a"}),
        json.dumps({"answer": "x", "citations": [{"chunk_id": 1, "quote": "q"}]}),
        json.dumps(["lista"]),
    ],
)
def test_invalid_shape_rejected(raw):
    """R3"""
    assert _reason(raw) == "invalid_shape"


def test_no_citations_rejected():
    """R4"""
    assert _reason(_raw(citations=[])) == "no_citations"


def test_foreign_chunk_id_rejected():
    """R5"""
    assert _reason(_raw(citations=[{"chunk_id": "zzz", "quote": "plan Pro"}])) == "foreign_chunk_id"


def test_non_literal_quote_rejected():
    """R6, R8"""
    assert _reason(_raw(citations=[{"chunk_id": "a", "quote": "plan Premium"}])) == "quote_not_literal"
    assert _reason(_raw(citations=[{"chunk_id": "a", "quote": ""}])) == "quote_not_literal"
    assert _reason(_raw(citations=[{"chunk_id": "b", "quote": "Reinicie el modulo"}])) == "quote_not_literal"
    # la puntuación también cuenta
    assert _reason(_raw(citations=[{"chunk_id": "b", "quote": "Reinicie el módulo,"}])) == "quote_not_literal"
    # el quote debe estar en SU fragmento, no en otro
    assert _reason(_raw(citations=[{"chunk_id": "b", "quote": "plan Pro"}])) == "quote_not_literal"


def test_quote_ignores_case_and_repeated_spaces():
    """R7"""
    result = validate_llm_answer(
        _raw(answer="Incluye 3", citations=[{"chunk_id": "a", "quote": "AL MES.   incluye\n3  usuarios"}]),
        CHUNKS,
    )
    assert result.answer == "Incluye 3"
    assert normalize_quote("  Á  b\tC ") == "á b c"


def test_invented_number_rejected():
    """R9"""
    assert _reason(_raw(answer="Cuesta 2000")) == "number_not_in_citations"
    assert _reason(_raw(answer="Cuesta 1.500,75 y 99")) == "number_not_in_citations"


def test_number_in_cited_chunk_accepted():
    """R10"""
    assert extract_numbers("1500 3.5 1.500,75 y 7,") == {"1500", "3.5", "1.500,75", "7"}
    # el número está en el texto completo del fragmento citado aunque no en el quote
    assert validate_llm_answer(
        _raw(answer="Incluye 3 usuarios por 1.500,75"), CHUNKS
    ).answer.startswith("Incluye 3")
    # comparación textual: 1500 no equivale a 1.500
    assert _reason(_raw(answer="Cuesta 1500")) == "number_not_in_citations"
    # un número que solo está en un fragmento NO citado se rechaza
    assert _reason(_raw(answer="Son 99 pasos")) == "number_not_in_citations"


@pytest.mark.parametrize(
    "reply, reason",
    [
        ("no json", "invalid_json"),
        (json.dumps({"answer": "x"}), "invalid_shape"),
        (_raw(citations=[]), "no_citations"),
        (_raw(citations=[{"chunk_id": "q", "quote": "x"}]), "foreign_chunk_id"),
        (_raw(citations=[{"chunk_id": "a", "quote": "inventado"}]), "quote_not_literal"),
        (_raw(answer="Cuesta 777"), "number_not_in_citations"),
    ],
)
def test_invalid_answer_sends_fixed_reply_and_event(env, reply, reason):
    """R13, R14, R15"""
    assert reason in INVALID_REASONS
    env.rag.results = CHUNKS
    env.llm.reply = reply
    env.post()
    assert env.gateway.sent == [(100, NO_ANSWER)]
    assert ("invalid_answer", reason) in env.events()
    assert all(t != "rag_answer" for t, _ in env.events())
    assert env.repo.events[0].at == env.adapters.clock()


def test_invalid_answer_triggers_handover_when_enabled(env):
    """R16; #32: con umbral 1 el primer fallo deriva."""
    env.settings.auto_handover_failure_threshold = 1
    env.rag.results = CHUNKS
    env.llm.reply = "no json"
    env.post()
    assert [r.reason for r in env.handover.requests] == ["invalid_answer"]
    assert env.events().index(("invalid_answer", "invalid_json")) < env.events().index(
        ("handover", "invalid_answer")
    )


def test_invalid_answer_no_handover_when_disabled(env):
    """R17"""
    env.settings.invalid_answer_handover = False
    env.rag.results = CHUNKS
    env.llm.reply = "no json"
    env.post()
    assert env.handover.requests == []
    assert env.gateway.sent == [(100, NO_ANSWER)]


def test_validate_llm_answer_is_pure():
    """R21"""
    sig = inspect.signature(validate_llm_answer)
    assert list(sig.parameters) == ["raw", "chunks"]
    source = inspect.getsource(validate_llm_answer)
    assert "adapters" not in source
    assert not re.search(r"\b(open|print|requests|httpx|socket)\b", source)
    assert domain.validate_llm_answer is validate_llm_answer


def test_logs_do_not_contain_llm_text(env, caplog):
    """R22"""
    secret = "TEXTO-SECRETO-DEL-MODELO"
    caplog.set_level(logging.DEBUG)
    env.rag.results = CHUNKS
    env.llm.reply = _raw(answer=f"Cuesta {secret} 555", citations=[{"chunk_id": "a", "quote": secret}])
    env.post()
    env.llm.reply = secret
    env.post(update_id=2)
    assert caplog.records
    assert secret not in caplog.text


def test_third_party_notices_cover_copied_files():
    """R23"""
    notices = (ROOT / "THIRD_PARTY_NOTICES.md").read_text(encoding="utf-8")
    for path in PKG.rglob("*.py"):
        head = "\n".join(path.read_text(encoding="utf-8").splitlines()[:15])
        if "rag-support-bot" in head:
            assert path.name in notices, path
