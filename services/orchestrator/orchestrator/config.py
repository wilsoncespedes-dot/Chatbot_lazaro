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
_RLS_SETTING = re.compile(r"^[a-z_][a-z0-9_]*\.[a-z_][a-z0-9_]*$")

AUTO_HANDOVER_FAILURE_ALLOWED_REASONS = ("no_relevant_chunks", "invalid_answer")


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
    auto_handover_failure_threshold: int = Field(default=3, ge=1)
    auto_handover_failure_reasons: str = "no_relevant_chunks,invalid_answer"
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
    # harness de IA por estado (#39)
    harness_router_enabled: bool = False
    harness_max_input_chars: int = Field(default=2000, ge=100, le=4096)
    harness_injection_patterns: str = (
        "ignora tus instrucciones,ignora tus reglas,ignora las instrucciones,"
        "olvida tus reglas,ignore previous instructions,system prompt,"
        "prompt de sistema,actua como administrador,modo desarrollador,jailbreak"
    )
    harness_frustration_escalation: bool = True
    harness_frustration_keywords: str = (
        "no me sirves,no me estas ayudando,esto no sirve,estoy harto,estoy harta,"
        "pesimo servicio,que mal servicio"
    )
    harness_suppression_keywords: str = (
        "borrar mis datos,borren mis datos,suprimir mis datos,eliminar mis datos,"
        "eliminen mis datos"
    )
    harness_input_too_long_reply: str = (
        "Tu mensaje es muy largo. Escríbelo en un mensaje más corto, por favor."
    )
    harness_tool_denied_reply: str = (
        "No puedo hacer eso en este momento. Si necesitas ayuda, puedo pasarte con "
        "un asesor."
    )
    suppression_request_reply: str = (
        "Registramos tu solicitud de supresión de datos con el número {request_id}. "
        "Una persona autorizada la atenderá y te informará el resultado."
    )
    # datos propios del cliente (#39)
    client_data_enabled: bool = False
    client_data_database_url: str = ""
    client_data_views_schema: str = "mis_datos"
    client_data_allowlist: str = ""
    client_data_rls_setting: str = "lazaro.cliente_id"
    client_data_max_rows: int = Field(default=20, ge=1, le=200)
    client_data_timeout_ms: int = Field(default=5000, ge=100, le=30000)
    client_data_max_joins: int = Field(default=1, ge=0, le=3)
    client_data_max_reply_chars: int = Field(default=3500, ge=200, le=4000)
    client_data_truncated_note: str = (
        "Mostrando solo las primeras filas; hay más resultados."
    )
    client_data_disabled_reply: str = (
        "La consulta de tus datos no está disponible por ahora."
    )
    client_data_rejected_reply: str = (
        "No pude construir una consulta segura para esa pregunta. Intenta formularla "
        "de otra forma."
    )
    client_data_unavailable_reply: str = (
        "No se pudo consultar tus datos. Inténtalo de nuevo más tarde."
    )
    # memoria por cliente (#40)
    memory_enabled: bool = False
    memory_max_items: int = Field(default=20, ge=1, le=100)
    memory_item_max_chars: int = Field(default=300, ge=50, le=1000)
    memory_summary_max_chars: int = Field(default=1500, ge=200, le=4000)
    memory_input_max_messages: int = Field(default=200, ge=10, le=1000)
    memory_context_messages: int = Field(default=6, ge=0, le=20)
    memory_panel_summaries: int = Field(default=5, ge=1, le=50)
    memory_sensitive_min_digits: int = Field(default=6, ge=4, le=20)
    memory_sensitive_keywords: str = (
        "contraseña,contrasena,password,clave,pin,token,codigo de verificacion,cvv,"
        "tarjeta,cuenta bancaria,cedula,pasaporte,diagnostico,enfermedad,salud,"
        "medicamento,embarazo,discapacidad,religion,orientacion sexual,vida sexual,"
        "partido politico,afiliacion politica,sindicato,origen etnico,raza,biometric,"
        "huella"
    )
    suppression_executor_roles: str = "admin"
    privacy_notice_text: str = ""
    privacy_notice_version: str = ""
    privacy_accept_phrase: str = ""
    privacy_accepted_reply: str = ""
    privacy_retention_days: str = ""
    conversation_greeting: str = (
        "Hola. Antes de continuar necesitamos tu consentimiento para tratar tus datos."
    )
    conversation_rejected_reply: str = (
        "Entendido. No trataremos tus datos. Si quieres empezar de nuevo, escríbenos."
    )
    conversation_login_reminder: str = (
        "Para continuar, inicia sesión con el enlace que te enviamos desde el chat."
    )
    conversation_suspended_reply: str = (
        "El servicio está suspendido por falta de pago. Puedes hablar con un asesor "
        "o pedir que borren tus datos."
    )
    conversation_unsupported_reply: str = "Por ahora solo puedo leer mensajes de texto."
    conversation_active_welcome: str = (
        "Bienvenido. Puedes preguntarme sobre los temas disponibles."
    )
    conversation_confirm_button_reply: str = (
        "Para aceptar el tratamiento de tus datos, pulsa el botón Acepto."
    )
    identity_public_base_url: str = ""
    identity_link_signing_key: str = ""
    identity_login_required: bool = True
    identity_link_ttl_minutes: int = Field(default=15, ge=1, le=1440)
    identity_session_idle_minutes: int = Field(default=60, ge=5, le=1440)
    identity_login_max_attempts: int = Field(default=5, ge=1, le=100)
    identity_lockout_minutes: int = Field(default=15, ge=1, le=1440)
    credential_validity_days: int = Field(default=30, ge=1, le=366)
    credential_expiry_notice_days: int = Field(default=5, ge=0, le=60)
    identity_logout_commands: str = "/salir,cerrar sesion,cerrar sesión"
    password_scrypt_n: int = Field(default=32768, ge=16384)
    # panel de asesores multicanal (#41)
    whatsapp_window_hours: int = Field(default=24, ge=1, le=24)
    advisor_whatsapp_templates: str = "respuesta_asesor"
    advisor_return_reply: str = Field(
        default=(
            "Te devolvemos al asistente virtual. Puedes seguir escribiendo aquí."
        ),
        min_length=1,
        max_length=4096,
    )
    advisor_history_lookback_minutes: int = Field(default=60, ge=0, le=1440)
    advisor_history_max_messages: int = Field(default=100, ge=10, le=500)
    advisor_presence_ttl_minutes: int = Field(default=15, ge=1, le=240)
    advisor_inbox_refresh_seconds: int = Field(default=30, ge=0, le=600)
    suppression_deadline_business_days: int = Field(default=15, ge=1, le=60)
    suppression_due_soon_business_days: int = Field(default=3, ge=0, le=30)
    suppression_queue_executed_limit: int = Field(default=20, ge=0, le=200)
    suppression_done_reply: str = Field(
        default="Tu solicitud de supresión de datos fue atendida.",
        min_length=1,
        max_length=4096,
    )
    suppression_result_template: str = Field(
        default="resultado_supresion", pattern=r"^[a-z0-9_]{1,64}$"
    )
    # administración y avisos (#42)
    business_hours_enabled: bool = False
    business_hours_start: str = "06:00"
    business_hours_end: str = "21:00"
    business_hours_days: str = "1,2,3,4,5,6,7"
    business_hours_utc_offset_minutes: int = Field(default=-300, ge=-720, le=840)
    expiry_notice_enabled: bool = True
    expiry_notice_max_attempts: int = Field(default=3, ge=1, le=10)
    expiry_notice_interval_seconds: int = Field(default=3600, ge=1)
    expiry_notice_http_timeout_seconds: int = Field(default=120, ge=1)
    admin_text_history_limit: int = Field(default=20, ge=1, le=200)
    admin_metrics_unanswered_limit: int = Field(default=20, ge=0, le=200)

    @field_validator("business_hours_start", "business_hours_end")
    @classmethod
    def _validate_business_time(cls, value: str) -> str:
        if not re.fullmatch(r"^([01]\d|2[0-3]):[0-5]\d$", value):
            raise ValueError("BUSINESS_HOURS_START/END deben tener formato HH:MM")
        return value

    @field_validator("business_hours_days")
    @classmethod
    def _validate_business_days(cls, value: str) -> str:
        tokens = [token.strip() for token in value.split(",") if token.strip()]
        try:
            numbers = [int(token) for token in tokens]
        except ValueError:
            raise ValueError("BUSINESS_HOURS_DAYS debe ser una lista de enteros 1-7") from None
        if not numbers or any(number < 1 or number > 7 for number in numbers):
            raise ValueError("BUSINESS_HOURS_DAYS debe contener valores 1-7")
        if len(set(numbers)) != len(numbers):
            raise ValueError("BUSINESS_HOURS_DAYS no admite duplicados")
        return ",".join(str(number) for number in numbers)

    @model_validator(mode="after")
    def _validate_business_range(self) -> "Settings":
        if self.business_hours_start == self.business_hours_end:
            raise ValueError("BUSINESS_HOURS_START y BUSINESS_HOURS_END deben ser distintos")
        return self

    @field_validator("password_scrypt_n")
    @classmethod
    def _validate_scrypt_n(cls, value: int) -> int:
        if value & (value - 1):
            raise ValueError("PASSWORD_SCRYPT_N debe ser una potencia de 2")
        return value

    @field_validator("auto_handover_failure_threshold")
    @classmethod
    def _validate_auto_handover_threshold(cls, value: int) -> int:
        if value < 1:
            raise ValueError(
                "AUTO_HANDOVER_FAILURE_THRESHOLD debe ser un entero >= 1"
            )
        return value

    @field_validator("auto_handover_failure_reasons")
    @classmethod
    def _validate_auto_handover_reasons(cls, value: str) -> str:
        tokens = [token.strip() for token in value.split(",") if token.strip()]
        invalid = [
            token
            for token in tokens
            if token not in AUTO_HANDOVER_FAILURE_ALLOWED_REASONS
        ]
        if invalid:
            raise ValueError(
                "AUTO_HANDOVER_FAILURE_REASONS contiene un motivo no permitido; "
                "usa no_relevant_chunks o invalid_answer"
            )
        return ",".join(dict.fromkeys(tokens))

    @field_validator("suppression_request_reply")
    @classmethod
    def _validate_suppression_reply(cls, value: str) -> str:
        if "{request_id}" not in value:
            raise ValueError(
                "SUPPRESSION_REQUEST_REPLY debe contener {request_id}"
            )
        return value

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

    @field_validator("memory_sensitive_keywords")
    @classmethod
    def _validate_memory_keywords(cls, value: str) -> str:
        tokens = [token.strip() for token in value.split(",") if token.strip()]
        if not tokens:
            raise ValueError("MEMORY_SENSITIVE_KEYWORDS no puede estar vacío")
        return ",".join(dict.fromkeys(tokens))

    @field_validator("advisor_whatsapp_templates")
    @classmethod
    def _validate_advisor_templates(cls, value: str) -> str:
        tokens = [token.strip() for token in value.split(",") if token.strip()]
        if not tokens:
            raise ValueError("ADVISOR_WHATSAPP_TEMPLATES no puede estar vacío")
        pattern = re.compile(r"^[a-z0-9_]{1,64}$")
        invalid = [token for token in tokens if not pattern.fullmatch(token)]
        if invalid:
            raise ValueError(
                "ADVISOR_WHATSAPP_TEMPLATES contiene un nombre de plantilla inválido"
            )
        return ",".join(dict.fromkeys(tokens))

    @field_validator("suppression_executor_roles")
    @classmethod
    def _validate_suppression_roles(cls, value: str) -> str:
        tokens = [token.strip() for token in value.split(",") if token.strip()]
        if not tokens:
            raise ValueError("SUPPRESSION_EXECUTOR_ROLES no puede estar vacío")
        invalid = [token for token in tokens if token not in ("admin", "asesor")]
        if invalid:
            raise ValueError(
                "SUPPRESSION_EXECUTOR_ROLES solo admite admin o asesor"
            )
        return ",".join(dict.fromkeys(tokens))

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
    def _validate_client_data(self) -> "Settings":
        if not self.client_data_enabled:
            return self
        dsn = self.client_data_database_url.strip()
        forbidden = {self.database_url.strip(), self.db_query_database_url.strip()}
        if not dsn or dsn in forbidden:
            raise ValueError(
                "CLIENT_DATA_DATABASE_URL debe ser una conexión de solo lectura "
                "distinta de DATABASE_URL y DB_QUERY_DATABASE_URL"
            )
        if not _DB_QUERY_IDENTIFIER.fullmatch(self.client_data_views_schema):
            raise ValueError("CLIENT_DATA_VIEWS_SCHEMA debe ser un identificador válido")
        if not _RLS_SETTING.fullmatch(self.client_data_rls_setting):
            raise ValueError("CLIENT_DATA_RLS_SETTING debe tener forma esquema.clave")
        _parse_db_query_allowlist(
            self.client_data_allowlist, self.client_data_views_schema
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
        if not self.identity_public_base_url.strip().startswith("https://"):
            problems.append("IDENTITY_PUBLIC_BASE_URL")
        if len(self.identity_link_signing_key) < 32:
            problems.append("IDENTITY_LINK_SIGNING_KEY")
        if not self.identity_login_required:
            problems.append("IDENTITY_LOGIN_REQUIRED")
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
    def identity_logout_command_list(self) -> tuple[str, ...]:
        return tuple(
            command.strip()
            for command in self.identity_logout_commands.split(",")
            if command.strip()
        )

    @property
    def auto_handover_failure_reason_set(self) -> set[str]:
        return {
            reason.strip()
            for reason in self.auto_handover_failure_reasons.split(",")
            if reason.strip()
        }

    @property
    def effective_auto_handover_failure_reasons(self) -> set[str]:
        reasons = self.auto_handover_failure_reason_set
        if not self.invalid_answer_handover:
            reasons.discard("invalid_answer")
        return reasons

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

    @property
    def harness_injection_pattern_list(self) -> list[str]:
        return [item.strip() for item in self.harness_injection_patterns.split(",")
                if item.strip()]

    @property
    def harness_frustration_keyword_list(self) -> list[str]:
        return [item.strip() for item in self.harness_frustration_keywords.split(",")
                if item.strip()]

    @property
    def harness_suppression_keyword_list(self) -> list[str]:
        return [item.strip() for item in self.harness_suppression_keywords.split(",")
                if item.strip()]

    @property
    def memory_sensitive_keyword_list(self) -> tuple[str, ...]:
        return tuple(
            token.strip()
            for token in self.memory_sensitive_keywords.split(",")
            if token.strip()
        )

    @property
    def advisor_whatsapp_template_list(self) -> tuple[str, ...]:
        return tuple(
            token.strip()
            for token in self.advisor_whatsapp_templates.split(",")
            if token.strip()
        )

    @property
    def suppression_executor_role_set(self) -> frozenset[str]:
        return frozenset(
            token.strip()
            for token in self.suppression_executor_roles.split(",")
            if token.strip()
        )

    @property
    def client_data_allowlist_map(self) -> dict[str, tuple[str, ...]]:
        if not self.client_data_allowlist.strip():
            return {}
        return _parse_db_query_allowlist(
            self.client_data_allowlist, self.client_data_views_schema
        )
