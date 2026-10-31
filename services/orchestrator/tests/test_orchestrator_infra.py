"""Tests de los artefactos globales del repo: compose, SQL, .env.example, CI y requirements-dev."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SERVICES = ("telegram_gateway", "orchestrator", "rag", "handover")


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


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def _compose_service(name: str) -> str:
    block = _block(_block(_read("docker-compose.yml"), "services", 0), name, 2)
    assert block, f"{name} no está en docker-compose.yml"
    return block


def _env_names() -> set[str]:
    return {
        ln.split("=", 1)[0].strip()
        for ln in _read(".env.example").splitlines()
        if "=" in ln and not ln.lstrip().startswith("#")
    }


def test_compose_defines_all_services():
    """R21: compose define postgres, redis y los 4 servicios."""
    for name in ("postgres", "redis", *SERVICES):
        assert _compose_service(name)


def test_postgres_uses_pgvector_image():
    """R22: postgres usa una imagen pgvector."""
    match = re.search(r"^\s+image:\s*(\S+)\s*$", _compose_service("postgres"), re.M)
    assert match and "pgvector" in match.group(1)


def test_redis_uses_bsd_licensed_image():
    """R23: redis usa redis:7.2-alpine."""
    match = re.search(r"^\s+image:\s*(\S+)\s*$", _compose_service("redis"), re.M)
    assert match and match.group(1) == "redis:7.2-alpine"


def test_postgres_reads_env_file():
    """R25: postgres declara env_file con .env."""
    match = re.search(r"^\s+env_file:\s*\[([^\]]*)\]\s*$", _compose_service("postgres"), re.M)
    assert match
    assert ".env" in [item.strip() for item in match.group(1).split(",")]


def test_init_sql_enables_vector():
    """R28: el script SQL crea la extensión vector."""
    assert "CREATE EXTENSION IF NOT EXISTS vector;" in _read("scripts/db/init/01_extensions.sql")


def test_postgres_mounts_init_scripts():
    """R29: postgres monta ./scripts/db/init en initdb.d."""
    assert "./scripts/db/init:/docker-entrypoint-initdb.d" in _compose_service("postgres")


def test_compose_interpolated_vars_are_in_env_example():
    """R31: toda ${VAR} del compose está en .env.example."""
    variables = set(re.findall(r"(?<!\$)\$\{([A-Z0-9_]+)", _read("docker-compose.yml")))
    assert variables <= _env_names()


def test_env_example_has_postgres_vars():
    """R32: .env.example incluye las variables de Postgres."""
    assert {"POSTGRES_USER", "POSTGRES_PASSWORD", "POSTGRES_DB"} <= _env_names()


def test_ci_triggers_on_push_and_pull_request():
    """R33: CI se dispara en push y pull_request."""
    on_block = _block(_read(".github/workflows/ci.yml"), "on", 0)
    assert re.search(r"^\s+push:", on_block, re.M)
    assert re.search(r"^\s+pull_request:", on_block, re.M)


def test_ci_installs_dev_requirements():
    """R34: CI instala requirements-dev.txt."""
    assert "pip install -r requirements-dev.txt" in _read(".github/workflows/ci.yml")


def test_ci_runs_pytest():
    """R35: CI ejecuta python -m pytest."""
    assert re.search(r"^\s*-?\s*run:.*python -m pytest", _read(".github/workflows/ci.yml"), re.M)


def test_ci_uses_python_312():
    """R36: CI fija Python 3.12 con setup-python."""
    ci = _read(".github/workflows/ci.yml")
    assert "actions/setup-python@" in ci
    assert re.search(r"python-version:\s*[\"']?3\.12[\"']?", ci)


def test_dev_requirements_include_every_service():
    """R37: requirements-dev incluye el requirements.txt de cada servicio."""
    lines = {ln.strip() for ln in _read("requirements-dev.txt").splitlines()}
    for name in SERVICES:
        assert f"-r services/{name}/requirements.txt" in lines
