"""Configuración del servicio orchestrator leída de variables de entorno."""
from __future__ import annotations

import json
import re

from lazaro_contracts.production import (
    ProductionConfigError,
    normalize_service_url,
    parse_app_env,
    production_problems,
)
from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from .privacy import normalize_privacy_text

DEFAULT_HANDOVER_KEYWORDS = (
    "hablar con una persona,hablar con un asesor,hablar con un humano,"
    "quiero un asesor,quiero un agente,agente humano"
)

REQUIRED_IN_PRODUCTION = (
    "SERVICE_TOKEN",
    "DATABASE_URL",
    "RAG_URL",
    "HANDOVER_URL",
    "TELEGRAM_GATEWAY_URL",
    "LLM_API_KEY",
    "LLM_MODEL",
    "PRIVACY_NOTICE_TEXT",
    "PRIVACY_NOTICE_VERSION",
    "PRIVACY_ACCEPT_PHRASE",
    "PRIVACY_ACCEPTED_REPLY",
    "PRIVACY_RETENTION_DAYS",
)

_DB_QUERY_IDENTIFIER = re.compile(r"^[a-z_][a-z0-9_]{0,62}$")


def _parse_db_query_allowlist(
    raw: str, schema: str
) -> dict[str, tuple[str, ...]]:
    """JSON `{"<schema>.<vista>": ["col", ...]}` a mapa de columnas allowlisted."""
    text = raw.strip()
    if not text:
        raise ValueError("DB_QUERY_ALLOWLIST no puede estar vacío")
    try:
        data = json.loads(text)
    except ValueError:
        raise ValueError("DB_QUERY_ALLOWLIST no es un JSON válido") from None
    if not isinstance(data, dict) or not data:
        raise ValueError("DB_QUERY_ALLOWLIST debe ser un objeto JSON no vacío")
    prefix = f"{schema}."
    parsed: dict[str, tuple[str, ...]] = {}
    for qualified, columns in data.items():
        if not isinstance(qualified, str) or not qualified.startswith(prefix):
            raise ValueError("DB_QUERY_ALLOWLIST contiene una vista fuera del esquema")
        view = qualified[len(prefix):]
        if not _DB_QUERY_IDENTIFIER.fullmatch(view):
            raise ValueError("DB_QUERY_ALLOWLIST contiene un identificador inválido")
        if not isinstance(columns, list) or not all(
            isinstance(column, str) and _DB_QUERY_IDENTIFIER.fullmatch(column)
            for column in columns
        ):
            raise ValueError("DB_QUERY_ALLOWLIST contiene columnas inválidas")
        parsed[qualified] = tuple(columns)
    return parsed


class Settings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore", hide_input_in_errors=True)

    app_env: str = "development"
    service_token: str = ""
    database_url: str = ""
    rag_url: str = ""
    handover_url: str = ""
    telegram_gateway_url: str = ""
    llm_api_key: str = ""
    llm_model: str = ""
    llm_base_url: str = "https://api.openai.com/v1"
    http_timeout_seconds: float = 10
    rag_top_k: int = Field(default=5, ge=1, le=20)
    no_answer_reply: str = (
        "No encontré información sobre eso en los manuales. Te paso con un asesor."
    )
    handover_ack_reply: str = "Avisé a un asesor; te responderá por aquí en cuanto pueda."
    error_reply: str = "Tuve un problema para responderte. Inténtalo de nuevo en unos minutos."
    no_advisors_reply: str = (
        "En este momento no hay asesores disponibles. Tu consulta quedó registrada y te "
        "escribiremos en cuanto haya alguien."
    )
    invalid_answer_handover: bool = True
    handover_keywords: str = DEFAULT_HANDOVER_KEYWORDS
    advisor_reply_confirmation: str = "Respuesta enviada al cliente."
    advisor_close_confirmation: str = "Caso cerrado."
    case_closed_reply: str = (
        "Tu caso con el asesor quedó cerrado. Si necesitas algo más, escríbenos por aquí."
    )
    forward_failed_reply: str = (
        "No pude hacer llegar tu mensaje al asesor. Inténtalo de nuevo en unos minutos."
    )
    advisor_command_help: str = (
        "Comandos de asesor: /responder <case_id> <texto> para responder al cliente y "
        "/cerrar <case_id> para cerrar el caso."
    )
    advisor_command_forbidden_reply: str = (
        "No tienes permiso para usar ese comando sobre ese caso."
    )
    advisor_command_failed_reply: str = (
        "No se pudo completar el comando. Revisa el número de caso o inténtalo de nuevo "
        "en unos minutos."
    )
    advisor_command_case_closed_reply: str = "Ese caso ya está cerrado."
    link_token_ttl_minutes: int = Field(default=15, ge=1, le=1440)
    password_hash_iterations: int = Field(default=600000, ge=100000)
    profile_password_min_length: int = Field(default=12, ge=1)
    telegram_bot_username: str = ""
    link_success_reply: str = "Tu cuenta de Telegram quedó vinculada a tu perfil."
    link_failed_reply: str = (
        "No se pudo vincular la cuenta. Pide un enlace nuevo a tu administrador."
    )
    admin_session_ttl_minutes: int = Field(default=60, ge=5, le=1440)
    admin_cookie_secure: bool = True
    admin_events_limit: int = Field(default=100, ge=1, le=500)
    admin_login_max_attempts: int = Field(default=5, ge=1, le=100)
    admin_login_window_minutes: int = Field(default=15, ge=1, le=1440)
    admin_trust_proxy_headers: bool = False
    admin_manual_max_bytes: int = Field(default=20971520, ge=1, le=104857600)
    classifier_default_threshold: float = Field(default=0.6, ge=0, le=1)
    db_query_enabled: bool = False
    db_query_database_url: str = ""
    db_query_views_schema: str = "consultas"
    db_query_allowlist: str = ""
    db_query_max_rows: int = Field(default=50, ge=1, le=200)
    db_query_timeout_ms: int = Field(default=5000, ge=100, le=30000)
    db_query_max_joins: int = Field(default=1, ge=0, le=3)
    db_query_max_question_length: int = Field(default=500, ge=1, le=2000)
    db_query_max_reply_chars: int = Field(default=3500, ge=200, le=4000)
    db_query_help_reply: str = (
        "Uso: /consultar <pregunta>. Ejemplo: /consultar cuántos pedidos hay pendientes."
    )
    db_query_forbidden_reply: str = (
        "No tienes permiso para consultar datos. Esta función es solo para asesores "
        "verificados."
    )
    db_query_disabled_reply: str = (
        "Las consultas de datos están deshabilitadas en este momento."
    )
    db_query_rejected_reply: str = (
        "No pude construir una consulta segura para esa pregunta. Reformúlala o "
        "consulta una vista permitida."
    )
    db_query_unavailable_reply: str = (
        "No se pudo completar la consulta de datos. Inténtalo de nuevo más tarde."
    )
    db_query_truncated_note: str = (
        "Mostrando solo las primeras filas; hay más resultados."
    )
    privacy_notice_text: str = ""
    privacy_notice_version: str = ""
    privacy_accept_phrase: str = ""
    privacy_accepted_reply: str = ""
    privacy_retention_days: str = ""

    @field_validator("privacy_retention_days")
    @classmethod
    def _validate_retention_days(cls, value: str) -> str:
        text = value.strip()
        if not text:
            return ""
        try:
            days = int(text)
        except ValueError:
            raise ValueError("PRIVACY_RETENTION_DAYS debe ser un entero >= 1") from None
        if days < 1:
            raise ValueError("PRIVACY_RETENTION_DAYS debe ser un entero >= 1")
        return text

    @model_validator(mode="after")
    def _validate_notice_phrase(self) -> "Settings":
        if self.privacy_notice_text.strip() and self.privacy_accept_phrase.strip():
            phrase = normalize_privacy_text(self.privacy_accept_phrase)
            notice = normalize_privacy_text(self.privacy_notice_text)
            if phrase not in notice:
                raise ValueError(
                    "PRIVACY_ACCEPT_PHRASE debe aparecer en PRIVACY_NOTICE_TEXT"
                )
        return self

    @model_validator(mode="after")
    def _validate_production(self) -> "Settings":
        self.app_env = parse_app_env(self.app_env)
        self.rag_url = normalize_service_url(self.rag_url)
        self.handover_url = normalize_service_url(self.handover_url)
        self.telegram_gateway_url = normalize_service_url(self.telegram_gateway_url)
        if self.db_query_enabled:
            self._validate_db_query()
        if self.app_env != "production":
            return self
        problems = production_problems(self.model_dump(), REQUIRED_IN_PRODUCTION)
        if not self.admin_cookie_secure and "ADMIN_COOKIE_SECURE" not in problems:
            problems.append("ADMIN_COOKIE_SECURE")
        if problems:
            raise ProductionConfigError(problems)
        return self

    def _validate_db_query(self) -> None:
        dsn = self.db_query_database_url.strip()
        if not dsn or dsn == self.database_url.strip():
            raise ValueError(
                "DB_QUERY_DATABASE_URL debe ser una conexión de solo lectura distinta "
                "de DATABASE_URL"
            )
        if not _DB_QUERY_IDENTIFIER.fullmatch(self.db_query_views_schema):
            raise ValueError("DB_QUERY_VIEWS_SCHEMA debe ser un identificador válido")
        _parse_db_query_allowlist(self.db_query_allowlist, self.db_query_views_schema)

    @property
    def handover_keyword_list(self) -> list[str]:
        return [k.strip() for k in self.handover_keywords.split(",") if k.strip()]

    @property
    def retention_days(self) -> int | None:
        if not self.privacy_retention_days.strip():
            return None
        return int(self.privacy_retention_days)

    @property
    def privacy_configured(self) -> bool:
        return bool(
            self.privacy_notice_text.strip()
            and self.privacy_notice_version.strip()
            and self.privacy_accept_phrase.strip()
            and self.privacy_accepted_reply.strip()
            and self.retention_days is not None
        )

    @property
    def db_query_allowlist_map(self) -> dict[str, tuple[str, ...]]:
        if not self.db_query_allowlist.strip():
            return {}
        return _parse_db_query_allowlist(
            self.db_query_allowlist, self.db_query_views_schema
        )
