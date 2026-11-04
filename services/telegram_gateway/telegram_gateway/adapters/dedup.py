"""Adaptador de deduplicación por `(canal, mensaje_externo_id)`, con versión falsa."""
from __future__ import annotations

from typing import Protocol


class DedupStore(Protocol):
    def mark_if_new(self, update_id: int, ttl_seconds: int) -> bool:
        """Compatibilidad: True si el update_id de Telegram es nuevo."""
        ...

    def mark_message_if_new(
        self, channel: str, external_message_id: str, ttl_seconds: int
    ) -> bool:
        """True si el par (canal, mensaje externo) es nuevo (y queda marcado)."""
        ...


class RedisDedupStore:
    def __init__(self, redis_url: str) -> None:
        import redis

        self._client = redis.Redis.from_url(redis_url)

    def mark_if_new(self, update_id: int, ttl_seconds: int) -> bool:
        return self.mark_message_if_new("telegram", str(update_id), ttl_seconds)

    def mark_message_if_new(
        self, channel: str, external_message_id: str, ttl_seconds: int
    ) -> bool:
        key = f"gw:message:{channel}:{external_message_id}"
        legacy_key = (
            f"gw:update:{external_message_id}" if channel == "telegram" else None
        )
        if legacy_key is not None and self._client.exists(legacy_key):
            # Migra la marca histórica a la clave compuesta sin reprocesar (R5, R6).
            self._client.set(key, 1, nx=True, ex=ttl_seconds)
            return False
        created = bool(self._client.set(key, 1, nx=True, ex=ttl_seconds))
        if created and legacy_key is not None:
            self._client.set(legacy_key, 1, nx=True, ex=ttl_seconds)
        return created


class FakeDedupStore:
    def __init__(self, fail: bool = False) -> None:
        # `keys` conserva la forma histórica (update_id -> ttl) para Telegram.
        self.keys: dict[int, int] = {}
        self.message_keys: set[tuple[str, str]] = set()
        self.fail = fail

    def mark_if_new(self, update_id: int, ttl_seconds: int) -> bool:
        return self.mark_message_if_new("telegram", str(update_id), ttl_seconds)

    def mark_message_if_new(
        self, channel: str, external_message_id: str, ttl_seconds: int
    ) -> bool:
        if self.fail:
            raise ConnectionError("redis caído")
        key = (channel, external_message_id)
        if key in self.message_keys:
            return False
        legacy_id: int | None = None
        if channel == "telegram":
            try:
                legacy_id = int(external_message_id)
            except ValueError:
                legacy_id = None
            if legacy_id is not None and legacy_id in self.keys:
                # Una clave histórica ya procesada también es duplicado (R5).
                self.message_keys.add(key)
                return False
        self.message_keys.add(key)
        if legacy_id is not None:
            self.keys[legacy_id] = ttl_seconds
        return True
