"""Registro efímero de última entrada para la ventana estándar de Meta (24 h)."""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Protocol


class MetaMessageWindowStore(Protocol):
    def record_inbound(self, channel: str, recipient: str, at: datetime) -> None: ...

    def last_inbound(self, channel: str, recipient: str) -> datetime | None: ...


def _key(channel: str, recipient: str) -> str:
    digest = hashlib.sha256(f"{channel}:{recipient}".encode("utf-8")).hexdigest()
    return f"gw:meta:last_inbound:{digest}"


class RedisMetaMessageWindowStore:
    def __init__(self, redis_url: str, ttl_seconds: int) -> None:
        import redis

        self._client = redis.Redis.from_url(redis_url)
        self._ttl_seconds = ttl_seconds

    def record_inbound(self, channel: str, recipient: str, at: datetime) -> None:
        self._client.set(
            _key(channel, recipient), at.isoformat(), ex=self._ttl_seconds
        )

    def last_inbound(self, channel: str, recipient: str) -> datetime | None:
        raw = self._client.get(_key(channel, recipient))
        if raw is None:
            return None
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        try:
            value = datetime.fromisoformat(raw)
        except (TypeError, ValueError):
            return None
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


class FakeMetaMessageWindowStore:
    def __init__(self, fail: bool = False) -> None:
        self.values: dict[tuple[str, str], datetime] = {}
        self.fail = fail

    def record_inbound(self, channel: str, recipient: str, at: datetime) -> None:
        if self.fail:
            raise ConnectionError("redis caído")
        self.values[(channel, recipient)] = at

    def last_inbound(self, channel: str, recipient: str) -> datetime | None:
        if self.fail:
            raise ConnectionError("redis caído")
        return self.values.get((channel, recipient))
