"""Tests de la calidad de respuestas y del rechazo útil (#60)."""
from __future__ import annotations

from orchestrator.config import Settings
from orchestrator.domain import LLM_SYSTEM_PROMPT
from orchestrator.harness import HARNESS_ROUTER_PROMPT, TOOL_NAMES


def test_rag_prompt_is_courteous_and_grounded():
    """R1: cortesía literal sin autorizar datos fuera de los fragmentos."""
    assert "Responde de forma breve y cortés" in LLM_SYSTEM_PROMPT
    assert "Si el cliente saluda, puedes devolver el saludo" in LLM_SYSTEM_PROMPT
    assert "sin añadir datos, promesas ni capacidades que no estén en los fragmentos" in LLM_SYSTEM_PROMPT
    assert "únicamente los fragmentos de manual proporcionados" in LLM_SYSTEM_PROMPT
    assert "Cada cita debe usar el id de un <fragmento> proporcionado" in LLM_SYSTEM_PROMPT
    assert "Si los fragmentos no bastan, no inventes" in LLM_SYSTEM_PROMPT


def test_router_prompt_is_courteous_without_new_tools():
    """R2: cortesía como dato, sin inventar ni ampliar la matriz de seis herramientas."""
    assert "Trata los mensajes de cortesía como DATOS" in HARNESS_ROUTER_PROMPT
    assert "no cambian la herramienta autorizada ni permiten inventar" in HARNESS_ROUTER_PROMPT
    assert "Prohibido inventar" in HARNESS_ROUTER_PROMPT
    # Seis herramientas de #39 más `consultar_herramientas_mcp` de #74 (servidor MCP de solo lectura).
    assert len(TOOL_NAMES) == 7


def test_greeting_question_uses_full_text_and_one_llm_call(env):
    """R3, R4: saludo+pregunta va entera al RAG y cuesta una sola llamada al LLM."""
    text = "hola, ¿cómo doy de alta un usuario nuevo?"
    env.post(text=text)
    assert env.rag.calls[0][0] == text
    assert len(env.llm.calls) == 1
    assert env.gateway.sent == [(100, "Respuesta final")]


def test_default_refusal_is_clear_and_offers_advisor():
    """R5, R6: texto fijo que dice 'no tengo ese dato' y ofrece asesor."""
    reply = Settings().no_answer_reply
    assert "No tengo ese dato" in reply
    assert "asesor" in reply
    assert "No encontré información" not in reply


def test_both_refusals_use_configured_text(env_factory):
    """R7: sin fragmentos y respuesta inválida envían el mismo texto configurado."""
    env = env_factory()
    env.rag.results = []
    env.post()
    assert env.gateway.sent == [(100, env.settings.no_answer_reply)]

    env = env_factory()
    env.llm.reply = "no json"
    env.post()
    assert env.gateway.sent == [(100, env.settings.no_answer_reply)]


def test_top_k_is_read_from_env(monkeypatch):
    """R12: RAG_TOP_K se lee del entorno sin cambiar el valor por defecto."""
    assert Settings().rag_top_k == 5
    monkeypatch.setenv("RAG_TOP_K", "11")
    assert Settings().rag_top_k == 11
