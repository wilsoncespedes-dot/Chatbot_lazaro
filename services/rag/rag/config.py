"""Configuración del servicio rag leída de variables de entorno."""
from __future__ import annotations

from lazaro_contracts.production import (
    ProductionConfigError,
    parse_app_env,
    production_problems,
)
from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

REQUIRED_IN_PRODUCTION = (
    "SERVICE_TOKEN",
    "DATABASE_URL",
    "EMBEDDINGS_API_KEY",
    "EMBEDDINGS_MODEL",
)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore", hide_input_in_errors=True)

    app_env: str = "development"
    service_token: str = ""
    database_url: str = "postgresql://lazaro:lazaro@postgres:5432/lazaro"
    embeddings_base_url: str = "https://api.openai.com/v1"
    embeddings_api_key: str = ""
    embeddings_model: str = ""
    embeddings_dim: int = 1536
    chunk_size: int = 1000
    chunk_overlap: int = 200
    rag_similarity_threshold: float = 0.75
    rag_hybrid_enabled: bool = False
    rag_hybrid_candidate_limit: int = 50
    http_timeout_seconds: float = 10

    @model_validator(mode="after")
    def _validate_production(self) -> "Settings":
        self.app_env = parse_app_env(self.app_env)
        if self.app_env != "production":
            return self
        problems = production_problems(self.model_dump(), REQUIRED_IN_PRODUCTION)
        if problems:
            raise ProductionConfigError(problems)
        return self
