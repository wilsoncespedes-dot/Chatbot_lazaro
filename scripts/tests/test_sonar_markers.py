"""Marcas `# NOSONAR` justificadas de los falsos positivos de Sonar (#58)."""
from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]

MARKERS = [
    (
        "services/orchestrator/orchestrator/accounts.py",
        'PASSWORD_SCHEME = "pbkdf2_sha256"',
    ),
    (
        "services/orchestrator/orchestrator/bootstrap_admin.py",
        'MSG_PASSWORD_READ_FAILED = "No se pudo leer la contraseña."',
    ),
    (
        "services/orchestrator/orchestrator/bootstrap_admin.py",
        'MSG_PASSWORD_SHORT = "La contraseña no cumple la longitud mínima."',
    ),
    (
        "services/orchestrator/orchestrator/bootstrap_admin.py",
        'MSG_PASSWORD_MISMATCH = "Las contraseñas no coinciden."',
    ),
    (
        "contracts/lazaro_contracts/production.py",
        'return f"http://{text}"',
    ),
]


@pytest.mark.parametrize(("path", "prefix"), MARKERS)
def test_false_positives_are_marked_nosonar(path, prefix):
    """R12: cada línea marcada existe una sola vez y lleva `# NOSONAR` justificado."""
    text = (ROOT / path).read_text(encoding="utf-8")
    lines = [line for line in text.splitlines() if line.strip().startswith(prefix)]
    assert len(lines) == 1, (path, prefix)
    assert re.search(r"# NOSONAR:\s*\S", lines[0])
