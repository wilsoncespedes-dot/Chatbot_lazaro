"""Configuración del servicio rag leída de variables de entorno."""
from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")

    service_token: str = ""
    database_url: str = "postgresql://lazaro:lazaro@postgres:5432/lazaro"
    embeddings_base_url: str = "https://api.openai.com/v1"
    embeddings_api_key: str = ""
    embeddings_model: str = ""
    embeddings_dim: int = 1536
    chunk_size: int = 1000
    chunk_overlap: int = 200
    rag_similarity_threshold: float = 0.75
    http_timeout_seconds: float = 10
