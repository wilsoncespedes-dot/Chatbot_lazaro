"""Configuración y documentación del servidor MCP (#74)."""
from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[3]


def _env_names() -> set[str]:
    return {
        line.split("=", 1)[0].strip()
        for line in (ROOT / ".env.example").read_text(encoding="utf-8").splitlines()
        if "=" in line and not line.lstrip().startswith("#")
    }


def _compose() -> dict:
    return yaml.safe_load((ROOT / "docker-compose.yml").read_text(encoding="utf-8"))


def test_env_example_declares_mcp_vars():
    """R30: `.env.example` declara todas las variables MCP."""
    required = {
        "MCP_ENABLED",
        "MCP_URL",
        "MCP_TIMEOUT_SECONDS",
        "MCP_MAX_TOOL_STEPS",
        "MCP_DEMO_NOTICE",
        "MCP_DEMO_SEED",
        "MCP_DATABASE_URL",
    }
    assert required <= _env_names()


def test_ollama_under_profile():
    """R31: `ollama` existe bajo el perfil `ollama` y no arranca sin él."""
    service = _compose()["services"]["ollama"]
    assert service["profiles"] == ["ollama"]
    assert "ports" not in service


def test_docs_mcp_covers_ollama_and_remote():
    """R32: documenta Ollama local y un proveedor remoto."""
    text = (ROOT / "docs" / "mcp.md").read_text(encoding="utf-8")
    assert "Ollama" in text or "ollama" in text
    assert "LLM_BASE_URL" in text
    assert "LLM_MODEL" in text
    assert "proveedor remoto" in text.lower()
