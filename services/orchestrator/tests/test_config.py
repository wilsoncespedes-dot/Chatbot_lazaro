"""Tests de configuración, .env.example y superficie de la app."""
from __future__ import annotations

import importlib
from pathlib import Path

import pytest
from fastapi.routing import APIRoute
from pydantic import ValidationError

from orchestrator.config import Settings
from orchestrator.main import create_app

ROOT = Path(__file__).resolve().parents[3]
ENV_VARS = [
    "RAG_TOP_K", "NO_ANSWER_REPLY", "HANDOVER_ACK_REPLY", "ERROR_REPLY", "HANDOVER_KEYWORDS",
    "LLM_BASE_URL", "DATABASE_URL", "LLM_API_KEY", "LLM_MODEL", "HTTP_TIMEOUT_SECONDS",
    "PRIVACY_NOTICE_TEXT", "PRIVACY_NOTICE_VERSION", "PRIVACY_ACCEPT_PHRASE",
    "PRIVACY_ACCEPTED_REPLY", "PRIVACY_RETENTION_DAYS",
]


def test_settings_defaults(monkeypatch):
    """R33"""
    for name in ENV_VARS:
        monkeypatch.delenv(name, raising=False)
    s = Settings()
    assert s.rag_top_k == 5 and s.http_timeout_seconds == 10
    assert s.no_answer_reply and s.handover_ack_reply and s.error_reply
    assert "hablar con una persona" in s.handover_keyword_list
    monkeypatch.setenv("HANDOVER_KEYWORDS", "uno, dos ,")
    monkeypatch.setenv("RAG_TOP_K", "9")
    s = Settings()
    assert s.handover_keyword_list == ["uno", "dos"] and s.rag_top_k == 9


@pytest.mark.parametrize("value", [0, 21, -1])
def test_rag_top_k_out_of_range_rejected(value):
    """R33"""
    with pytest.raises(ValidationError):
        Settings(rag_top_k=value)


def test_env_example_lists_all_variables():
    """R42"""
    text = (ROOT / ".env.example").read_text(encoding="utf-8")
    declared = {
        ln.split("=", 1)[0].strip()
        for ln in text.splitlines()
        if "=" in ln and not ln.lstrip().startswith("#")
    }
    for name in ENV_VARS:
        assert name in declared, name


def test_import_main_without_env_does_not_connect(monkeypatch):
    """R34"""
    for name in ENV_VARS + ["SERVICE_TOKEN"]:
        monkeypatch.delenv(name, raising=False)
    import pg8000.dbapi

    def boom(*a, **k):
        raise AssertionError("no debe conectar")

    monkeypatch.setattr(pg8000.dbapi, "connect", boom)
    module = importlib.import_module("orchestrator.main")
    importlib.reload(module)
    assert module.app is not None


def test_only_health_and_messages_routes_exposed():
    """R35"""
    app = create_app(Settings(service_token="t"))
    paths = {r.path for r in app.routes if isinstance(r, APIRoute)}
    # Feature 7 (T30) añade POST /cases/{id}/reply.
    # Feature 20 añade POST /profiles y POST /profiles/{id}/link-token.
    # Feature 21 añade las rutas HTML del panel administrativo.
    # Feature 22 añade las vistas de manuales y fragmentos.
    assert paths == {
        "/health",
        "/messages",
        "/privacy/purge",
        "/cases/{case_id}/reply",
        "/profiles",
        "/profiles/{profile_id}/link-token",
        "/admin",
        "/admin/login",
        "/admin/logout",
        "/admin/static/admin.css",
        "/admin/profiles",
        "/admin/profiles/{profile_id}/role",
        "/admin/profiles/{profile_id}/link-token",
        "/admin/events",
        "/admin/manuals",
        "/admin/manuals/{manual_id}",
        "/admin/chunks/{chunk_id}",
        "/admin/chunks/{chunk_id}/active",
        "/admin/categories",
        "/admin/categories/threshold",
        "/admin/categories/{category_id}",
        "/admin/categories/{category_id}/active",
    }


def test_no_advisors_reply_has_default(monkeypatch):
    """R27: NO_ADVISORS_REPLY se lee del entorno y tiene un valor por defecto no vacío."""
    monkeypatch.delenv("NO_ADVISORS_REPLY", raising=False)
    assert Settings().no_advisors_reply.strip()
    monkeypatch.setenv("NO_ADVISORS_REPLY", "Sin asesores ahora")
    assert Settings().no_advisors_reply == "Sin asesores ahora"
    text = (ROOT / ".env.example").read_text(encoding="utf-8")
    assert any(ln.startswith("NO_ADVISORS_REPLY=") for ln in text.splitlines())


@pytest.mark.parametrize("value", ["0", "-1", "abc", "1.5"])
def test_retention_days_must_be_positive_integer(value):
    """R2: PRIVACY_RETENTION_DAYS no vacío debe ser un entero >= 1 en cualquier entorno."""
    with pytest.raises(ValidationError):
        Settings(privacy_retention_days=value)


def test_notice_must_contain_the_acceptance_phrase():
    """R3: el aviso normalizado debe contener la frase de aceptación normalizada."""
    with pytest.raises(ValidationError):
        Settings(
            privacy_notice_text="Aviso de privacidad.",
            privacy_accept_phrase="Acepto el tratamiento.",
        )


def test_notice_and_phrase_are_compared_normalized():
    """R3: mayúsculas y espacios repetidos no impiden la validación."""
    settings = Settings(
        privacy_notice_text="AVISO.   acepto el tratamiento   de mis datos.",
        privacy_accept_phrase="Acepto el tratamiento de mis datos.",
    )
    assert settings.privacy_configured is False

