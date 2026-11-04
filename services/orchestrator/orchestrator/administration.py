"""Funciones puras de administración: ajustes, horario, plantillas y métricas (#42)."""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from typing import Literal, Sequence

from .config import Settings
from .identity import POLICY_FIELDS, IdentityPolicy, resolve_identity_policy

logger = logging.getLogger(__name__)

DEFAULT_BUSINESS_START = "06:00"
DEFAULT_BUSINESS_END = "21:00"
DEFAULT_BUSINESS_DAYS = "1,2,3,4,5,6,7"

_TIME_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
_TEMPLATE_NAME_RE = re.compile(r"^[a-z0-9_]{1,64}$")
_TEMPLATE_LANGUAGE_RE = re.compile(r"^[a-z]{2}(_[A-Z]{2})?$")

TEMPLATE_PURPOSES = ("advisor_reply", "suppression_result", "expiry_notice")
TEMPLATE_STATUSES = ("draft", "pending", "approved", "rejected", "paused")
ALLOWED_TRANSITIONS: frozenset[tuple[str, str]] = frozenset(
    {
        ("draft", "pending"),
        ("pending", "approved"),
        ("pending", "rejected"),
        ("approved", "paused"),
        ("paused", "approved"),
        ("rejected", "draft"),
    }
)

_IDENTITY_DEFAULT_ATTRS = {
    "link_ttl_minutes": "identity_link_ttl_minutes",
    "session_idle_minutes": "identity_session_idle_minutes",
    "login_max_attempts": "identity_login_max_attempts",
    "lockout_minutes": "identity_lockout_minutes",
    "validity_days": "credential_validity_days",
    "expiry_notice_days": "credential_expiry_notice_days",
}


class SettingsFormInvalid(ValueError):
    """El formulario de ajustes contiene al menos una clave inválida (R38)."""

    def __init__(self, keys: Sequence[str]) -> None:
        self.keys = tuple(keys)
        super().__init__("Ajustes inválidos: " + ", ".join(self.keys))


@dataclass(frozen=True)
class SettingSpec:
    key: str
    kind: Literal["int", "bool", "time", "days"]
    minimum: int | None
    maximum: int | None
    default_attr: str


OPERATIONAL_SETTINGS: tuple[SettingSpec, ...] = tuple(
    SettingSpec(key, "int", minimum, maximum, _IDENTITY_DEFAULT_ATTRS[field])
    for key, (field, minimum, maximum) in POLICY_FIELDS.items()
) + (
    SettingSpec("expiry_notice.enabled", "bool", None, None, "expiry_notice_enabled"),
    SettingSpec("business_hours.enabled", "bool", None, None, "business_hours_enabled"),
    SettingSpec("business_hours.start", "time", None, None, "business_hours_start"),
    SettingSpec("business_hours.end", "time", None, None, "business_hours_end"),
    SettingSpec("business_hours.days", "days", None, None, "business_hours_days"),
    SettingSpec(
        "business_hours.utc_offset_minutes",
        "int",
        -720,
        840,
        "business_hours_utc_offset_minutes",
    ),
    SettingSpec(
        "suppression.deadline_business_days",
        "int",
        1,
        60,
        "suppression_deadline_business_days",
    ),
    SettingSpec(
        "suppression.due_soon_business_days",
        "int",
        0,
        30,
        "suppression_due_soon_business_days",
    ),
)

OPERATIONAL_SETTINGS_BY_KEY = {spec.key: spec for spec in OPERATIONAL_SETTINGS}
OPERATIONAL_PREFIXES = ("identity.", "expiry_notice.", "business_hours.", "suppression.")


@dataclass(frozen=True)
class BusinessHours:
    enabled: bool
    start: time
    end: time
    days: frozenset[int]
    utc_offset_minutes: int


@dataclass(frozen=True)
class OperationalSettings:
    identity: IdentityPolicy
    expiry_notice_enabled: bool
    hours: BusinessHours
    suppression_deadline_business_days: int
    suppression_due_soon_business_days: int


def _default_value(spec: SettingSpec, settings: Settings) -> str:
    value = getattr(settings, spec.default_attr, "")
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _valid_time(raw: str) -> bool:
    return bool(_TIME_RE.fullmatch(raw.strip()))


def _parse_time(raw: str) -> time:
    hour, minute = raw.strip().split(":")
    return time(int(hour), int(minute))


def _valid_days(raw: str) -> bool:
    tokens = [token.strip() for token in raw.split(",") if token.strip()]
    if not tokens:
        return False
    try:
        numbers = [int(token) for token in tokens]
    except ValueError:
        return False
    return all(1 <= number <= 7 for number in numbers) and len(set(numbers)) == len(numbers)


def _valid_value(spec: SettingSpec, raw: str) -> bool:
    value = raw.strip()
    if spec.kind == "bool":
        return value in ("true", "false")
    if spec.kind == "time":
        return _valid_time(value)
    if spec.kind == "days":
        return _valid_days(value)
    try:
        number = int(value)
    except (TypeError, ValueError):
        return False
    if spec.minimum is not None and number < spec.minimum:
        return False
    if spec.maximum is not None and number > spec.maximum:
        return False
    return True


def _normalized_value(spec: SettingSpec, raw: str) -> str:
    value = raw.strip()
    if spec.kind == "bool":
        return value.lower()
    if spec.kind == "days":
        return ",".join(str(int(token)) for token in value.split(",") if token.strip())
    return value


def _hours_from_values(values: dict[str, str], settings: Settings) -> BusinessHours:
    def value(key: str) -> str:
        return values.get(key, _default_value(OPERATIONAL_SETTINGS_BY_KEY[key], settings))

    def number(key: str) -> int:
        try:
            return int(value(key))
        except (TypeError, ValueError):
            return int(_default_value(OPERATIONAL_SETTINGS_BY_KEY[key], settings))

    return BusinessHours(
        enabled=value("business_hours.enabled") == "true",
        start=_parse_time(value("business_hours.start")),
        end=_parse_time(value("business_hours.end")),
        days=frozenset(
            int(token)
            for token in value("business_hours.days").split(",")
            if token.strip()
        ),
        utc_offset_minutes=number("business_hours.utc_offset_minutes"),
    )


def resolve_operational_settings(
    settings: Settings, overrides: dict[str, str]
) -> OperationalSettings:
    """R39: el valor válido de `app_settings` gana; uno inválido cae al default."""
    valid: dict[str, str] = {}
    for key, raw in overrides.items():
        spec = OPERATIONAL_SETTINGS_BY_KEY.get(key)
        if spec is None:
            continue
        if _valid_value(spec, raw):
            valid[key] = _normalized_value(spec, raw)
        else:
            logger.warning("operational_setting_invalid key=%s", key)
    identity_overrides = {
        key: value for key, value in valid.items() if key.startswith("identity.")
    }
    identity = resolve_identity_policy(settings, identity_overrides)
    hours = _hours_from_values(valid, settings)
    expiry_enabled = valid.get(
        "expiry_notice.enabled",
        _default_value(OPERATIONAL_SETTINGS_BY_KEY["expiry_notice.enabled"], settings),
    ) == "true"
    deadline = int(
        valid.get(
            "suppression.deadline_business_days",
            _default_value(
                OPERATIONAL_SETTINGS_BY_KEY["suppression.deadline_business_days"],
                settings,
            ),
        )
    )
    due_soon = int(
        valid.get(
            "suppression.due_soon_business_days",
            _default_value(
                OPERATIONAL_SETTINGS_BY_KEY["suppression.due_soon_business_days"],
                settings,
            ),
        )
    )
    return OperationalSettings(
        identity=identity,
        expiry_notice_enabled=expiry_enabled,
        hours=hours,
        suppression_deadline_business_days=deadline,
        suppression_due_soon_business_days=due_soon,
    )


def validate_settings_form(
    form: dict[str, str], settings: Settings, current: dict[str, str]
) -> tuple[dict[str, str], tuple[str, ...]]:
    """R37, R38, R74: devuelve (valores a guardar, claves a borrar) o falla."""
    upserts: dict[str, str] = {}
    deletes: list[str] = []
    invalid: list[str] = []
    for spec in OPERATIONAL_SETTINGS:
        raw = form.get(spec.key, "")
        if isinstance(raw, str) and not raw.strip():
            deletes.append(spec.key)
            continue
        raw = str(raw)
        if not _valid_value(spec, raw):
            invalid.append(spec.key)
            continue
        upserts[spec.key] = _normalized_value(spec, raw)

    merged = dict(current)
    for key in deletes:
        merged.pop(key, None)
    merged.update(upserts)
    try:
        effective = resolve_operational_settings(settings, merged)
    except (TypeError, ValueError):
        invalid.append("business_hours")
        effective = None
    if effective is not None:
        if effective.hours.start == effective.hours.end:
            invalid.extend(("business_hours.start", "business_hours.end"))
        if (
            effective.suppression_due_soon_business_days
            >= effective.suppression_deadline_business_days
        ):
            invalid.append("suppression.due_soon_business_days")
    if invalid:
        raise SettingsFormInvalid(tuple(dict.fromkeys(invalid)))
    return upserts, tuple(deletes)


def within_business_hours(now: datetime, hours: BusinessHours) -> bool:
    """R41: día ISO y hora local, incluido el rango que cruza medianoche."""
    local = now + timedelta(minutes=hours.utc_offset_minutes)
    if local.isoweekday() not in hours.days:
        return False
    current = local.time().replace(tzinfo=None)
    if hours.start < hours.end:
        return hours.start <= current < hours.end
    return current >= hours.start or current < hours.end


def format_local_date(at: datetime, utc_offset_minutes: int) -> str:
    """R45: `dd/mm/aaaa` en la hora local configurada."""
    return (at + timedelta(minutes=utc_offset_minutes)).strftime("%d/%m/%Y")


def render_expiry_notice(template_text: str, days: int, date_text: str) -> str:
    """R50: reemplaza `{dias}` y `{fecha}` sin interpretar el resto del texto."""
    return template_text.replace("{dias}", str(days)).replace("{fecha}", date_text)


def validate_template_fields(
    name: str, purpose: str, language: str, variables: str, body: str
) -> tuple[str, str, str, int, str]:
    """R26: valida nombre, propósito, idioma, variables y texto de referencia."""
    normalized_name = name.strip()
    if not _TEMPLATE_NAME_RE.fullmatch(normalized_name):
        raise ValueError("nombre")
    if purpose not in TEMPLATE_PURPOSES:
        raise ValueError("purpose")
    normalized_language = language.strip()
    if not _TEMPLATE_LANGUAGE_RE.fullmatch(normalized_language):
        raise ValueError("language")
    try:
        count = int(variables)
    except (TypeError, ValueError):
        raise ValueError("variables") from None
    if count < 0 or count > 10:
        raise ValueError("variables")
    reference = body.strip()
    if len(reference) < 1 or len(reference) > 1024:
        raise ValueError("body")
    return normalized_name, purpose, normalized_language, count, reference


def effective_templates(
    purpose: str,
    registered: Sequence[object],
    env_fallback: Sequence[str],
) -> tuple[str, ...]:
    """R32, R33: solo aprobadas si hay registro; sin registro, respaldo de entorno."""
    own = [template for template in registered if template.purpose == purpose]
    if own:
        return tuple(
            sorted(
                template.name
                for template in own
                if template.status == "approved"
            )
        )
    if purpose == "expiry_notice":
        return ()
    return tuple(env_fallback)


def median_minutes(values: Sequence[float]) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return float(ordered[middle])
    return (ordered[middle - 1] + ordered[middle]) / 2


@dataclass(frozen=True)
class FirstResponseSummary:
    cases: int
    answered: int
    unanswered: int
    avg_minutes: float | None
    median_minutes: float | None


def first_response_summary(
    rows: Sequence[tuple[datetime, datetime | None]]
) -> FirstResponseSummary:
    """R63: minutos entre la creación del caso y su primer mensaje de asesor."""
    durations: list[float] = []
    for created_at, first_reply in rows:
        if first_reply is None or first_reply < created_at:
            continue
        durations.append((first_reply - created_at).total_seconds() / 60)
    cases = len(rows)
    answered = len(durations)
    average = sum(durations) / answered if answered else None
    return FirstResponseSummary(
        cases=cases,
        answered=answered,
        unanswered=cases - answered,
        avg_minutes=average,
        median_minutes=median_minutes(durations),
    )
