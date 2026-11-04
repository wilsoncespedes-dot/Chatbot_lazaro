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
    # Feature 29 añade las rutas HTML del panel de asesores.
    # Feature 38 añade /acceso y las rutas internas /clients.
    assert paths == {
        "/health",
        "/messages",
        "/privacy/purge",
        "/cases/{case_id}/reply",
        "/profiles",
        "/profiles/{profile_id}/link-token",
        "/acceso",
        "/clients",
        "/clients/{profile_id}",
        "/clients/{profile_id}/renew",
        "/clients/{profile_id}/revoke",
        "/clients/{profile_id}/close-session",
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
        "/admin/texts",
        "/admin/texts/{field}/historial",
        "/admin/clientes",
        "/admin/clientes/{profile_id}/renovar",
        "/admin/clientes/{profile_id}/revocar",
        "/admin/clientes/{profile_id}/cerrar-sesion",
        "/admin/plantillas",
        "/admin/plantillas/{name}",
        "/admin/plantillas/{name}/estado",
        "/admin/ajustes",
        "/admin/metricas",
        "/credentials/expiry-notices",
        "/asesor",
        "/asesor/login",
        "/asesor/logout",
        "/asesor/cases",
        "/asesor/cases/{case_id}",
        "/asesor/cases/{case_id}/memoria",
        "/asesor/reply",
        "/asesor/assign",
        "/asesor/close",
        "/asesor/return",
        "/asesor/transfer",
        "/asesor/presence",
        "/asesor/supresiones",
        "/asesor/supresiones/{request_id}/execute",
        "/admin/supresiones",
        "/admin/supresiones/{request_id}/execute",
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


PANEL_ENV_VARS = [
    "WHATSAPP_WINDOW_HOURS",
    "ADVISOR_WHATSAPP_TEMPLATES",
    "ADVISOR_RETURN_REPLY",
    "ADVISOR_HISTORY_LOOKBACK_MINUTES",
    "ADVISOR_HISTORY_MAX_MESSAGES",
    "ADVISOR_PRESENCE_TTL_MINUTES",
    "ADVISOR_INBOX_REFRESH_SECONDS",
    "SUPPRESSION_DEADLINE_BUSINESS_DAYS",
    "SUPPRESSION_DUE_SOON_BUSINESS_DAYS",
    "SUPPRESSION_QUEUE_EXECUTED_LIMIT",
    "SUPPRESSION_DONE_REPLY",
    "SUPPRESSION_RESULT_TEMPLATE",
]


def test_panel_settings_defaults_and_env_example():
    """R71: las variables nuevas tienen sus defaults y figuran en .env.example."""
    settings = Settings()
    assert settings.whatsapp_window_hours == 24
    assert settings.advisor_whatsapp_template_list == ("respuesta_asesor",)
    assert settings.advisor_return_reply.strip()
    assert settings.advisor_history_lookback_minutes == 60
    assert settings.advisor_history_max_messages == 100
    assert settings.advisor_presence_ttl_minutes == 15
    assert settings.advisor_inbox_refresh_seconds == 30
    assert settings.suppression_deadline_business_days == 15
    assert settings.suppression_due_soon_business_days == 3
    assert settings.suppression_queue_executed_limit == 20
    assert settings.suppression_done_reply.strip()
    assert settings.suppression_result_template == "resultado_supresion"
    text = (ROOT / ".env.example").read_text(encoding="utf-8")
    declared = {
        ln.split("=", 1)[0].strip()
        for ln in text.splitlines()
        if "=" in ln and not ln.lstrip().startswith("#")
    }
    for name in PANEL_ENV_VARS:
        assert name in declared, name


@pytest.mark.parametrize(
    "overrides",
    [
        {"whatsapp_window_hours": 0},
        {"whatsapp_window_hours": 25},
        {"advisor_whatsapp_templates": ""},
        {"advisor_whatsapp_templates": "Mayusculas"},
        {"advisor_whatsapp_templates": "a-b"},
        {"advisor_return_reply": ""},
        {"advisor_history_lookback_minutes": -1},
        {"advisor_history_lookback_minutes": 1441},
        {"advisor_history_max_messages": 9},
        {"advisor_history_max_messages": 501},
        {"advisor_presence_ttl_minutes": 0},
        {"advisor_presence_ttl_minutes": 241},
        {"advisor_inbox_refresh_seconds": -1},
        {"advisor_inbox_refresh_seconds": 601},
        {"suppression_deadline_business_days": 0},
        {"suppression_deadline_business_days": 61},
        {"suppression_due_soon_business_days": 31},
        {"suppression_queue_executed_limit": 201},
        {"suppression_done_reply": ""},
        {"suppression_result_template": "MAL"},
    ],
)
def test_panel_settings_reject_invalid_values(overrides):
    """R72: un valor fuera de rango o con forma inválida falla al construir Settings."""
    with pytest.raises(ValidationError):
        Settings(**overrides)


ADMIN_ENV_VARS = [
    "BUSINESS_HOURS_ENABLED",
    "BUSINESS_HOURS_START",
    "BUSINESS_HOURS_END",
    "BUSINESS_HOURS_DAYS",
    "BUSINESS_HOURS_UTC_OFFSET_MINUTES",
    "EXPIRY_NOTICE_ENABLED",
    "EXPIRY_NOTICE_MAX_ATTEMPTS",
    "EXPIRY_NOTICE_INTERVAL_SECONDS",
    "EXPIRY_NOTICE_HTTP_TIMEOUT_SECONDS",
    "ADMIN_TEXT_HISTORY_LIMIT",
    "ADMIN_METRICS_UNANSWERED_LIMIT",
]


def test_admin_settings_defaults_and_env_example():
    """R69: las variables nuevas tienen sus defaults y figuran en .env.example."""
    settings = Settings()
    assert settings.business_hours_enabled is False
    assert settings.business_hours_start == "06:00"
    assert settings.business_hours_end == "21:00"
    assert settings.business_hours_days == "1,2,3,4,5,6,7"
    assert settings.business_hours_utc_offset_minutes == -300
    assert settings.expiry_notice_enabled is True
    assert settings.expiry_notice_max_attempts == 3
    assert settings.admin_text_history_limit == 20
    assert settings.admin_metrics_unanswered_limit == 20
    text = (ROOT / ".env.example").read_text(encoding="utf-8")
    declared = {
        ln.split("=", 1)[0].strip()
        for ln in text.splitlines()
        if "=" in ln and not ln.lstrip().startswith("#")
    }
    for name in ADMIN_ENV_VARS:
        assert name in declared, name


@pytest.mark.parametrize(
    "overrides",
    [
        {"business_hours_start": "6:00"},
        {"business_hours_end": "24:00"},
        {"business_hours_start": "06:00", "business_hours_end": "06:00"},
        {"business_hours_days": ""},
        {"business_hours_days": "0,1"},
        {"business_hours_days": "1,1"},
        {"business_hours_utc_offset_minutes": -721},
        {"business_hours_utc_offset_minutes": 841},
        {"expiry_notice_max_attempts": 0},
        {"expiry_notice_max_attempts": 11},
        {"expiry_notice_interval_seconds": 0},
        {"expiry_notice_http_timeout_seconds": 0},
        {"admin_text_history_limit": 0},
        {"admin_text_history_limit": 201},
        {"admin_metrics_unanswered_limit": -1},
        {"admin_metrics_unanswered_limit": 201},
    ],
)
def test_admin_settings_reject_invalid_values(overrides):
    """R69: fuera de rango o con formato inválido, Settings falla al arrancar."""
    with pytest.raises(ValidationError):
        Settings(**overrides)


def test_notice_and_phrase_are_compared_normalized():
    """R3: mayúsculas y espacios repetidos no impiden la validación."""
    settings = Settings(
        privacy_notice_text="AVISO.   acepto el tratamiento   de mis datos.",
        privacy_accept_phrase="Acepto el tratamiento de mis datos.",
    )
    assert settings.privacy_configured is False

