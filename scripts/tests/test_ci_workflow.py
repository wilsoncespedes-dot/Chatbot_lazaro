"""Tests del workflow de CI: tests y construcción Docker (#24)."""
from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"
SERVICES = {"telegram_gateway", "orchestrator", "rag", "handover"}


def _workflow() -> dict:
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))


def test_r21_ci_runs_pytest_on_push_and_pull_request():
    """R21: push y pull_request ejecutan python -m pytest."""
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "push:" in text and "pull_request:" in text
    jobs = _workflow()["jobs"]
    assert "tests" in jobs
    runs = [step.get("run", "") for step in jobs["tests"]["steps"]]
    assert any("python -m pytest" in run for run in runs)


def test_r22_ci_builds_every_service_image_without_publishing():
    """R22: un job en matriz construye los cuatro Dockerfiles."""
    job = _workflow()["jobs"]["docker-build"]
    matrix = job["strategy"]["matrix"]["service"]
    assert set(matrix) == SERVICES
    runs = [step.get("run", "") for step in job["steps"]]
    assert any(
        "docker build -f services/${{ matrix.service }}/Dockerfile ." in run
        for run in runs
    )
    assert all("docker push" not in run for run in runs)
