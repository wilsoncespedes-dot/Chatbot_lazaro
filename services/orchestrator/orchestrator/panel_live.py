"""Dominio puro del panel en tiempo real (#53), sin IO."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, MutableSet, Sequence
from urllib.parse import urlsplit

PanelEventKind = Literal[
    "message", "case_created", "case_updated", "purchase_intent"
]

# R20: ventana de solape para no perder eventos con ids confirmados fuera de orden.
PANEL_EVENT_OVERLAP_SECONDS = 5
PANEL_EVENTS_BATCH_LIMIT = 200

_ORIGIN_DEFAULT_PORTS = {"http": 80, "https": 443, "ws": 80, "wss": 443}


@dataclass(frozen=True)
class PanelEvent:
    id: int
    case_id: str
    kind: PanelEventKind


def _origin_parts(origin: str) -> tuple[str, int | None, int | None] | None:
    try:
        parsed = urlsplit(origin)
    except ValueError:
        return None
    host = parsed.hostname
    if not parsed.scheme or not host:
        return None
    default_port = _ORIGIN_DEFAULT_PORTS.get(parsed.scheme.lower())
    try:
        port = parsed.port
    except ValueError:
        return None
    if port is None:
        port = default_port
    return host.lower(), port, default_port


def _host_parts(host: str) -> tuple[str, int | None]:
    text = host.strip().lower()
    if text.startswith("["):
        close = text.find("]")
        if close != -1:
            remainder = text[close + 1:]
            if remainder.startswith(":") and remainder[1:].isdigit():
                return text[: close + 1], int(remainder[1:])
            return text[: close + 1], None
    name, separator, port = text.rpartition(":")
    if separator and port.isdigit():
        return name, int(port)
    return text, None


def origin_allowed(
    origin: str | None, host: str | None, allowed: tuple[str, ...]
) -> bool:
    """R3-R5: exige `Origin` y lo compara con la lista exacta o con `Host`."""
    if not origin:
        return False
    if allowed:
        return origin in allowed
    if not host:
        return False
    parts = _origin_parts(origin)
    if parts is None:
        return False
    origin_host, origin_port, origin_default_port = parts
    host_name, host_port = _host_parts(host)
    if origin_host != host_name:
        return False
    if host_port is None:
        return (
            origin_default_port is not None
            and origin_port == origin_default_port
        )
    return host_port == origin_port


def event_payload(event: PanelEvent) -> dict[str, str | int]:
    """R13: solo el aviso mínimo; nunca texto, tokens ni datos de otros clientes."""
    return {"type": event.kind, "id": event.id, "case_id": event.case_id}


def dedupe_new_events(
    events: Sequence[PanelEvent], seen: MutableSet[int]
) -> list[PanelEvent]:
    """R20: entrega cada id como máximo una vez por conexión."""
    new_events: list[PanelEvent] = []
    for event in events:
        if event.id in seen:
            continue
        seen.add(event.id)
        new_events.append(event)
    return new_events
