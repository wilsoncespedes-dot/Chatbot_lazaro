"""Compose e imagen del worker que sincroniza Gmail cada 5 s (docs/gmail.md)."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SERVICE_DIR = Path(__file__).resolve().parents[1]


def _block(text: str, key: str, indent: int) -> str:
    """Devuelve las líneas hijas de `key:` situada exactamente en la columna `indent`."""
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


def _worker_block() -> str:
    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    block = _block(_block(compose, "services", 0), "gmail_sync_worker", 2)
    assert block, "gmail_sync_worker no está en docker-compose.yml"
    return block


def test_gmail_worker_runs_sync_script_in_loop_from_gateway_image():
    block = _worker_block()
    env_file = re.search(r"^\s+env_file:\s*\[([^\]]*)\]\s*$", block, re.M)
    assert env_file and ".env" in [i.strip() for i in env_file.group(1).split(",")]
    command = re.search(r"^\s+command:\s*\[([^\]]*)\]\s*$", block, re.M)
    assert command
    assert '"sincronizar_gmail.py"' in command.group(1)
    assert '"--intervalo"' in command.group(1)
    build = re.search(r"^\s+build:\s*\{(.*)\}\s*$", block, re.M)
    assert build
    assert re.search(r"dockerfile:\s*services/telegram_gateway/Dockerfile\s*(,|$)", build.group(1))
    assert re.search(r"^\s+restart:\s*unless-stopped\s*$", block, re.M)


def test_gmail_worker_waits_for_healthy_gateway_and_publishes_no_ports():
    block = _worker_block()
    assert re.search(r"telegram_gateway:\s*\n\s+condition:\s*service_healthy", block)
    assert not re.search(r"^\s+(ports|expose):", block, re.M)


def test_gateway_dockerfile_copies_sync_script_and_keeps_cmd():
    text = (SERVICE_DIR / "Dockerfile").read_text(encoding="utf-8")
    assert re.search(r"^COPY scripts/sincronizar_gmail\.py \./sincronizar_gmail\.py\s*$", text, re.M)
    assert "exec uvicorn telegram_gateway.main:app" in text
