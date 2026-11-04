"""Almacén del último mensaje entrante de WhatsApp (ventana de 24 horas)."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Protocol

KEY_PREFIX = "gw:whatsapp:last_inbound:"


class WhatsAppWindowStore(Protocol):
    def record_inbound(self, wa_id: str, at: datetime) -> None: ...

    def last_inbound(self, wa_id: str) -> datetime | None: ...


class RedisWhatsAppWindowStore:
    def __init__(self, redis_url: str, ttl_seconds: int) -> None:
        import redis

        self._client = redis.Redis.from_url(redis_url)
        self._ttl_seconds = ttl_seconds

    def record_inbound(self, wa_id: str, at: datetime) -> None:
        self._client.set(
            f"{KEY_PREFIX}{wa_id}", at.isoformat(), ex=self._ttl_seconds
        )

    def last_inbound(self, wa_id: str) -> datetime | None:
        raw = self._client.get(f"{KEY_PREFIX}{wa_id}")
        if raw is None:
            return None
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        try:
            value = datetime.fromisoformat(raw)
        except (TypeError, ValueError):
            return None
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value


class FakeWhatsAppWindowStore:
    def __init__(self, fail: bool = False) -> None:
        self.values: dict[str, datetime] = {}
        self.fail = fail

    def record_inbound(self, wa_id: str, at: datetime) -> None:
        if self.fail:
            raise ConnectionError("redis caído")
        self.values[wa_id] = at

    def last_inbound(self, wa_id: str) -> datetime | None:
        if self.fail:
            raise ConnectionError("redis caído")
        return self.values.get(wa_id)
