"""Configuración del servicio orchestrator leída de variables de entorno."""
from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_HANDOVER_KEYWORDS = (
    "hablar con una persona,hablar con un asesor,hablar con un humano,"
    "quiero un asesor,quiero un agente,agente humano"
)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")

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

    @property
    def handover_keyword_list(self) -> list[str]:
        return [k.strip() for k in self.handover_keywords.split(",") if k.strip()]
