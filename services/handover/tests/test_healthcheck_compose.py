"""Healthchecks de Docker Compose para servicios de aplicación y Redis (#47)."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SERVICES = ("telegram_gateway", "orchestrator", "rag", "handover")


def _block(text: str, key: str, indent: int) -> str:
    lines = text.splitlines()
    prefix = " " * indent + key + ":"
    for i, line in enumerate(lines):
        stripped = line.split("#", 1)[0].rstrip()
        if stripped == prefix or stripped.startswith(prefix + " "):
            block = [line]
            for nxt in lines[i + 1:]:
                if nxt.strip() and (len(nxt) - len(nxt.lstrip())) <= indent:
                    break
                block.append(nxt)
            return "\n".join(block)
    return ""


def _services() -> str:
    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    return _block(compose, "services", 0)


def _service(name: str) -> str:
    block = _block(_services(), name, 2)
    assert block, f"{name} no está en docker-compose.yml"
    return block


def _healthcheck(block: str) -> str:
    match = re.search(r"^\s+healthcheck:\s*$", block, re.M)
    assert match, "falta healthcheck"
    start = block[: match.start()].count("\n")
    lines = block.splitlines()
    collected = [lines[start]]
    for line in lines[start + 1:]:
        if line.strip() and (len(line) - len(line.lstrip())) <= 4:
            break
        collected.append(line)
    return "\n".join(collected)


def test_redis_healthcheck_uses_ping() -> None:
    """R6, R7: Redis expone un healthcheck con redis-cli ping."""
    health = _healthcheck(_service("redis"))
    assert "redis-cli" in health
    assert "ping" in health


def test_every_application_service_has_http_healthcheck() -> None:
    """R6, R7: los cuatro servicios de aplicación consultan su /health por HTTP."""
    for name in SERVICES:
        health = _healthcheck(_service(name))
        assert "urllib.request" in health, name
        assert "http://127.0.0.1:8000/health" in health, name
        assert "timeout=3" in health, name


def test_startup_dependencies_wait_for_healthy_dependencies() -> None:
    """R6, R7: el arranque espera a que Redis y PostgreSQL estén saludables."""
    gateway = _service("telegram_gateway")
    assert re.search(
        r"depends_on:\s*\n\s+redis:\s*\n\s+condition:\s*service_healthy", gateway
    )
    orchestrator = _service("orchestrator")
    assert re.search(
        r"depends_on:\s*\n\s+postgres:\s*\n\s+condition:\s*service_healthy"
        r"\s*\n\s+redis:\s*\n\s+condition:\s*service_healthy",
        orchestrator,
    )


def test_env_example_declares_healthcheck_timeout() -> None:
    """R5: .env.example documenta el límite del probe con su valor por defecto."""
    text = (ROOT / ".env.example").read_text(encoding="utf-8")
    lines = {
        line.split("=", 1)[0].strip(): line.split("=", 1)[1].strip()
        for line in text.splitlines()
        if "=" in line and not line.lstrip().startswith("#")
    }
    assert lines["HEALTHCHECK_TIMEOUT_SECONDS"] == "2"
