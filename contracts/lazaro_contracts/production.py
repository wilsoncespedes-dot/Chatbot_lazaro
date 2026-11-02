"""Utilidades puras para validar la configuración de arranque en producción.

No hacen IO ni cambian ningún contrato HTTP: solo normalizan valores y devuelven
los nombres de las variables que impiden arrancar. Los mensajes nunca incluyen
los valores (R20).
"""
from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from typing import Literal, cast

PLACEHOLDERS: frozenset[str] = frozenset(
    {"cambia-esto", "changeme", "change-me", "placeholder", "secret", "test", "xxx"}
)
MIN_SERVICE_TOKEN_LENGTH = 32
DEVELOPMENT_DATABASE_MARKER = "lazaro:lazaro@"
WEBHOOK_SECRET_PATTERN = re.compile(r"^[A-Za-z0-9_-]{32,256}$")

AppEnv = Literal["development", "production"]


class ProductionConfigError(ValueError):
    """Configuración de producción inválida; solo se nombran las variables."""

    def __init__(self, names: Iterable[str]) -> None:
        self.names = list(dict.fromkeys(names))
        super().__init__(
            "Configuración de producción inválida: " + ", ".join(self.names)
        )


def normalize_service_url(value: str) -> str:
    """Convierte `host:puerto` en `http://host:puerto`; un valor vacío se conserva."""
    text = value.strip()
    if not text:
        return ""
    if "://" in text:
        return text
    return f"http://{text}"


def parse_app_env(value: str) -> AppEnv:
    """Devuelve APP_ENV validado; cualquier otro valor lanza ValueError (R13)."""
    if value not in ("development", "production"):
        raise ValueError("APP_ENV debe ser development o production")
    return cast(AppEnv, value)


def is_valid_webhook_secret(value: str) -> bool:
    """Comprueba el formato que exige Telegram para `secret_token` (R18)."""
    return WEBHOOK_SECRET_PATTERN.fullmatch(value) is not None


def _value_for(values: Mapping[str, object], name: str) -> object:
    """Busca la variable por su nombre de entorno o por su campo de Settings."""
    if name in values:
        return values[name]
    return values.get(name.lower(), "")


def production_problems(
    values: Mapping[str, object], required: Iterable[str]
) -> list[str]:
    """Nombres de las variables obligatorias que no son válidas en producción."""
    problems: list[str] = []
    for name in required:
        raw = _value_for(values, name)
        text = raw if isinstance(raw, str) else str(raw)
        candidate = text.strip()
        if not candidate:
            problems.append(name)
            continue
        if candidate.lower() in PLACEHOLDERS:
            problems.append(name)
            continue
        if name == "SERVICE_TOKEN" and len(text) < MIN_SERVICE_TOKEN_LENGTH:
            problems.append(name)
            continue
        if name == "DATABASE_URL" and DEVELOPMENT_DATABASE_MARKER in text:
            problems.append(name)
    return list(dict.fromkeys(problems))
