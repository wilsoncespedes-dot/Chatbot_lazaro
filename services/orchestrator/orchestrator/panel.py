"""Funciones puras del panel de asesores multicanal (#41): sin IO."""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Literal, Sequence

from .memory import in_window

WindowState = Literal["open", "closed", "not_applicable"]
PresenceState = Literal["available", "away"]
SuppressionPriority = Literal["vencida", "urgente", "alta"]


def channel_window(
    channel: str, last_user_at: datetime | None, now: datetime, hours: int
) -> WindowState:
    """Ventana de texto libre: Telegram nunca aplica y WhatsApp dura `hours`."""
    if channel != "whatsapp":
        return "not_applicable"
    if last_user_at is None:
        return "closed"
    return "open" if now - last_user_at < timedelta(hours=hours) else "closed"


def case_wait(
    link_created_at: datetime,
    last_user_at: datetime | None,
    last_advisor_at: datetime | None,
    now: datetime,
) -> timedelta | None:
    """Espera del caso según el último mensaje relevante (None si no hay espera)."""
    if last_advisor_at is None:
        return now - link_created_at
    if last_user_at is not None and last_user_at > last_advisor_at:
        return now - last_user_at
    return None


def business_deadline(created_at: datetime, business_days: int) -> datetime:
    """Suma días hábiles (lunes a viernes), conservando la hora; sin festivos."""
    current = created_at
    remaining = business_days
    while remaining > 0:
        current += timedelta(days=1)
        if current.weekday() < 5:
            remaining -= 1
    return current


def business_days_left(now: datetime, deadline: datetime) -> int:
    """Días hábiles completos que quedan; 0 si el plazo ya venció."""
    if now >= deadline:
        return 0
    total = 0
    current = now
    while current.date() < deadline.date():
        current += timedelta(days=1)
        if current.weekday() < 5:
            total += 1
    return total


def suppression_priority(
    now: datetime, deadline: datetime, due_soon_days: int
) -> SuppressionPriority:
    if now > deadline:
        return "vencida"
    if business_days_left(now, deadline) <= due_soon_days:
        return "urgente"
    return "alta"


def effective_presence(
    status: str | None,
    last_seen_at: datetime | None,
    now: datetime,
    ttl_minutes: int,
) -> PresenceState:
    if (
        status == "available"
        and last_seen_at is not None
        and now - last_seen_at <= timedelta(minutes=ttl_minutes)
    ):
        return "available"
    return "away"


def mask_external_id(value: str) -> str:
    if not value:
        return "—"
    return "…" + value[-4:]


def history_visible(
    at: datetime, foreign_windows: Sequence[tuple[datetime, datetime, datetime]]
) -> bool:
    """False si el mensaje cae dentro de la ventana de sesión de otro cliente."""
    return not any(in_window(at, window) for window in foreign_windows)
