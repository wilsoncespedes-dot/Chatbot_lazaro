"""Métricas del panel administrativo (#42)."""
from __future__ import annotations

from datetime import timedelta

import pytest

from orchestrator import admin
from orchestrator.domain import admin_metrics

NOW = None


@pytest.fixture()
def env(env_factory, panel):
    env = env_factory(admin_cookie_secure=False, password_hash_iterations=100000)
    panel.login_admin(env)
    return env


def _catalog(env):
    now = env.adapters.clock()
    c1 = env.repo.get_or_create_channel_contact("telegram", "10", "100", now)
    c2 = env.repo.get_or_create_channel_contact("telegram", "11", "101", now)
    env.repo.link_case("case-1", c1.id, now - timedelta(days=2))
    env.repo.link_case("case-2", c2.id, now - timedelta(days=1))
    env.repo.add_message(c1.id, "user", "hola", now - timedelta(days=2))
    env.repo.add_message(
        c1.id, "advisor", "respuesta", now - timedelta(days=2) + timedelta(minutes=10)
    )
    return now, c1, c2


def test_first_response_average_median_and_unanswered(env):
    """R63: casos, promedio, mediana y casos sin respuesta."""
    now, c1, c2 = _catalog(env)
    metrics = admin_metrics(7, env.settings, env.adapters)
    assert metrics.first_response.cases == 2
    assert metrics.first_response.answered == 1
    assert metrics.first_response.unanswered == 1
    assert metrics.first_response.avg_minutes == 10
    assert metrics.first_response.median_minutes == 10


def test_conversations_per_advisor_use_username_or_reference(env):
    """R64: cuenta contactos distintos por asesor y etiqueta con el usuario."""
    now, c1, c2 = _catalog(env)
    profile = env.repo.create_profile("ana", "asesor", "hash", now)
    env.repo.profiles[profile.id].telegram_user_id = 700
    at = now - timedelta(minutes=5)
    env.repo.add_event(c1.id, "advisor_reply", "advisor:700", at)
    env.repo.add_event(c1.id, "advisor_reply", "advisor:700", at)
    env.repo.add_event(c2.id, "advisor_reply", "advisor:701", at)
    metrics = admin_metrics(7, env.settings, env.adapters)
    assert metrics.per_advisor == (("ana", 1), ("701", 1))


def test_escalation_reasons_and_unanswered_totals(env):
    """R65, R66: motivos de escalamiento y total de preguntas sin respuesta."""
    now, c1, c2 = _catalog(env)
    at = now - timedelta(minutes=5)
    env.repo.add_event(c1.id, "handover", "user_request", at)
    env.repo.add_event(c2.id, "handover", "user_request", at)
    env.repo.add_event(c1.id, "handover", "no_relevant_chunks", at)
    env.repo.add_message(c1.id, "user", "<b>sin respuesta</b>", at - timedelta(minutes=1))
    env.repo.add_event(c1.id, "no_results", "x", at)
    env.repo.add_message(c2.id, "user", "otra pregunta", at - timedelta(minutes=1))
    env.repo.add_event(c2.id, "invalid_answer", "y", at)
    metrics = admin_metrics(7, env.settings, env.adapters)
    assert metrics.escalation_reasons == (
        ("user_request", 2),
        ("no_relevant_chunks", 1),
    )
    assert metrics.unanswered_total == 2
    assert any("<b>sin respuesta</b>" in text for _, text in metrics.unanswered_samples)


def test_unanswered_samples_are_truncated_escaped_and_limit_zero_hides_texts(
    env, monkeypatch
):
    """R66, R68: truncado y escape; con límite 0 no se consultan textos."""
    now, c1, _ = _catalog(env)
    long_text = "<" * 400
    at = now - timedelta(minutes=5)
    env.repo.add_message(c1.id, "user", long_text, at - timedelta(minutes=1))
    env.repo.add_event(c1.id, "no_results", "x", at)
    metrics = admin_metrics(7, env.settings, env.adapters)
    _, text = metrics.unanswered_samples[0]
    assert len(text) == 300
    rendered = admin.render_metrics(metrics, "csrf")
    assert "&lt;" in rendered and "<" * 10 not in rendered

    env.settings.admin_metrics_unanswered_limit = 0

    def boom(*args, **kwargs):
        raise AssertionError("no debe consultar textos")

    monkeypatch.setattr(env.repo, "unanswered_samples", boom)
    metrics = admin_metrics(7, env.settings, env.adapters)
    assert metrics.unanswered_samples == ()
    assert metrics.unanswered_total == 1


def test_invalid_days_returns_422_without_repository(env, monkeypatch):
    """R67: dias fuera de 1..90 responde 422 antes de consultar el repositorio."""
    def boom(*args, **kwargs):
        raise AssertionError("no debe consultar")

    monkeypatch.setattr(env.repo, "case_first_responses", boom)
    for value in ("0", "91", "abc"):
        response = env.client.get(f"/admin/metricas?dias={value}")
        assert response.status_code == 422


def test_metrics_view_is_audited(env):
    """R44: consultar métricas deja metrics_viewed en panel_audit."""
    _catalog(env)
    response = env.client.get("/admin/metricas?dias=7")
    assert response.status_code == 200
    assert any(
        row.action == "metrics_viewed" for row in env.repo.panel_audit
    )
