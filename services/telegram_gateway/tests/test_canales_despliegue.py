"""R34, R52, R53: configuración y dependencias para el registro de canales."""
from __future__ import annotations

import re
from pathlib import Path

import yaml
from pydantic import SecretStr

from telegram_gateway.config import Settings

ROOT = Path(__file__).resolve().parents[3]
SERVICE_DIR = Path(__file__).resolve().parents[1]
VALID_PRODUCTION = {
    "app_env": "production",
    "service_token": "s" * 40,
    "telegram_bot_token": "123456:BOT-TOKEN",
    "telegram_webhook_secret": "w" * 40,
    "redis_url": "redis://redis:6379/0",
    "orchestrator_url": "http://orchestrator:8000",
}


def test_gateway_requirements_match_channel_registry_design():
    """R52: las ocho dependencias están declaradas con cotas inferior y superior."""
    lines = [
        line.strip()
        for line in (SERVICE_DIR / "requirements.txt").read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    names = sorted(re.split(r"[<>=]", line)[0] for line in lines)
    assert names == [
        "cryptography",
        "fastapi",
        "httpx",
        "pg8000",
        "pydantic",
        "pydantic-settings",
        "redis",
        "uvicorn",
    ]
    assert all(">=" in line and "<" in line for line in lines)
    assert "pg8000>=1.31,<2" in lines
    assert "cryptography>=44,<48" in lines


def test_database_and_secret_key_settings_are_declared_and_empty_by_default(monkeypatch):
    """R53: DSN y clave son opcionales; la clave usa SecretStr."""
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("CHANNEL_SECRETS_KEY", raising=False)
    settings = Settings()
    assert settings.database_url == ""
    assert isinstance(settings.channel_secrets_key, SecretStr)
    assert settings.channel_secrets_key.get_secret_value() == ""


def test_database_and_secret_key_settings_read_environment(monkeypatch):
    """R53: Settings lee DATABASE_URL y CHANNEL_SECRETS_KEY del entorno."""
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@db/lazaro")
    monkeypatch.setenv("CHANNEL_SECRETS_KEY", "clave-no-validada-en-config")
    settings = Settings()
    assert settings.database_url == "postgresql://user:pass@db/lazaro"
    assert settings.channel_secrets_key.get_secret_value() == "clave-no-validada-en-config"


def test_production_settings_remain_valid_without_channel_secrets_key():
    """R34: APP_ENV=production sigue arrancando si falta la clave opcional."""
    settings = Settings(**VALID_PRODUCTION)
    assert settings.app_env == "production"
    assert settings.channel_secrets_key.get_secret_value() == ""


def test_env_example_documents_empty_key_and_generation_command():
    """R53: .env.example deja la clave vacía y documenta cómo generar una Fernet."""
    text = (ROOT / ".env.example").read_text(encoding="utf-8")
    gateway = text.split("# telegram_gateway", 1)[1].split("\n# eval", 1)[0]
    assert re.search(r"^CHANNEL_SECRETS_KEY=$", gateway, re.M)
    assert "Fernet.generate_key().decode()" in gateway


def test_compose_gateway_waits_for_healthy_postgres_and_redis():
    """R51: telegram_gateway espera PostgreSQL sano y conserva Redis."""
    compose = yaml.safe_load((ROOT / "docker-compose.yml").read_text(encoding="utf-8"))
    dependencies = compose["services"]["telegram_gateway"]["depends_on"]
    assert dependencies == {
        "postgres": {"condition": "service_healthy"},
        "redis": {"condition": "service_healthy"},
    }


def test_render_gateway_uses_shared_postgres_and_external_secret_key():
    """R54: Render injects DATABASE_URL from its DB and leaves Fernet key external."""
    blueprint = yaml.safe_load((ROOT / "render.yaml").read_text(encoding="utf-8"))
    gateway = next(
        service
        for service in blueprint["services"]
        if service["name"] == "telegram-gateway"
    )
    variables = {item["key"]: item for item in gateway["envVars"] if "key" in item}
    assert variables["DATABASE_URL"]["fromDatabase"] == {
        "name": "lazaro-postgres",
        "property": "connectionString",
    }
    assert variables["CHANNEL_SECRETS_KEY"]["sync"] is False
