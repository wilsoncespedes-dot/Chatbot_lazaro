"""Compose, imagen y configuración del worker de vencimiento (feature #12)."""
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
    services = _block(compose, "services", 0)
    block = _block(services, "timeouts_worker", 2)
    assert block, "timeouts_worker no está en docker-compose.yml"
    return block


def test_compose_has_timeouts_worker_running_script_in_loop():
    """R13: el servicio construye la imagen de handover y ejecuta el script en bucle."""
    block = _worker_block()
    match = re.search(r"^\s+env_file:\s*\[([^\]]*)\]\s*$", block, re.M)
    assert match
    assert ".env" in [item.strip() for item in match.group(1).split(",")]

    command = re.search(r"^\s+command:\s*\[([^\]]*)\]\s*$", block, re.M)
    assert command
    assert "vencer_casos.py" in command.group(1)
    assert "--intervalo" in command.group(1)

    build = re.search(r"^\s+build:\s*\{(.*)\}\s*$", block, re.M)
    assert build
    assert re.search(r"dockerfile:\s*services/handover/Dockerfile\s*(,|$)", build.group(1))


def test_timeouts_worker_publishes_no_ports():
    """R14: el worker no publica puertos."""
    block = _worker_block()
    assert not re.search(r"^\s+ports:", block, re.M)


def test_handover_dockerfile_copies_worker_script():
    """R15: la imagen de handover contiene scripts/vencer_casos.py y conserva su CMD."""
    text = (SERVICE_DIR / "Dockerfile").read_text(encoding="utf-8")
    assert "COPY scripts/vencer_casos.py ./vencer_casos.py" in text
    assert (
        'CMD ["sh", "-c", "exec uvicorn handover.main:app --host 0.0.0.0 '
        '--port ${PORT:-8000}"]' in text
    )


def test_env_example_declares_worker_variables():
    """R16: .env.example declara el intervalo inicial y el timeout HTTP."""
    text = (ROOT / ".env.example").read_text(encoding="utf-8")
    lines = {
        line.split("=", 1)[0].strip(): line.split("=", 1)[1].strip()
        for line in text.splitlines()
        if "=" in line and not line.lstrip().startswith("#")
    }
    assert lines["CHECK_TIMEOUTS_INTERVAL_SECONDS"] == "60"
    assert lines["CHECK_TIMEOUTS_HTTP_TIMEOUT_SECONDS"] == "120"


def _retention_worker_block() -> str:
    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    services = _block(compose, "services", 0)
    block = _block(services, "retention_worker", 2)
    assert block, "retention_worker no está en docker-compose.yml"
    return block


def test_retention_worker_runs_the_purge_script_in_a_loop():
    """R47: el servicio usa la imagen de handover y ejecuta purgar_datos.py --intervalo."""
    block = _retention_worker_block()
    match = re.search(r"^\s+env_file:\s*\[([^\]]*)\]\s*$", block, re.M)
    assert match
    assert ".env" in [item.strip() for item in match.group(1).split(",")]

    command = re.search(r"^\s+command:\s*\[([^\]]*)\]\s*$", block, re.M)
    assert command
    assert "purgar_datos.py" in command.group(1)
    assert "--intervalo" in command.group(1)

    build = re.search(r"^\s+build:\s*\{(.*)\}\s*$", block, re.M)
    assert build
    assert re.search(r"dockerfile:\s*services/handover/Dockerfile\s*(,|$)", build.group(1))
    assert re.search(r"depends_on:\s*\[orchestrator,\s*handover\]", block)


def test_retention_worker_publishes_no_ports():
    """R49: el worker de retención no publica puertos."""
    assert not re.search(r"^\s+ports:", _retention_worker_block(), re.M)


def test_handover_dockerfile_copies_the_purge_script():
    """R48: la imagen de handover contiene scripts/purgar_datos.py."""
    text = (SERVICE_DIR / "Dockerfile").read_text(encoding="utf-8")
    assert "COPY scripts/purgar_datos.py ./purgar_datos.py" in text


def test_env_example_declares_privacy_variables_empty():
    """R50: las seis variables aprobadas se declaran vacías y el worker tiene sus valores."""
    text = (ROOT / ".env.example").read_text(encoding="utf-8")
    lines = {
        line.split("=", 1)[0].strip(): line.split("=", 1)[1].strip()
        for line in text.splitlines()
        if "=" in line and not line.lstrip().startswith("#")
    }
    for name in (
        "PRIVACY_NOTICE_TEXT",
        "PRIVACY_NOTICE_VERSION",
        "PRIVACY_ACCEPT_PHRASE",
        "PRIVACY_ACCEPTED_REPLY",
        "PRIVACY_RETENTION_DAYS",
        "PRIVACY_ACTIVE_CASE_MAX_DAYS",
    ):
        assert lines[name] == ""
    assert lines["PRIVACY_PURGE_INTERVAL_SECONDS"] == "86400"
    assert lines["PRIVACY_PURGE_HTTP_TIMEOUT_SECONDS"] == "120"
