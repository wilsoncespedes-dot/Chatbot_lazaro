"""Adaptador de deduplicación de update_id en Redis, con versión falsa."""
from __future__ import annotations

from typing import Protocol


class DedupStore(Protocol):
    def mark_if_new(self, update_id: int, ttl_seconds: int) -> bool:
        """True si el update_id es nuevo (y queda marcado); False si ya existía."""
        ...


class RedisDedupStore:
    def __init__(self, redis_url: str) -> None:
        import redis

        self._client = redis.Redis.from_url(redis_url)

    def mark_if_new(self, update_id: int, ttl_seconds: int) -> bool:
        return bool(self._client.set(f"gw:update:{update_id}", 1, nx=True, ex=ttl_seconds))


class FakeDedupStore:
    def __init__(self, fail: bool = False) -> None:
        self.keys: dict[int, int] = {}
        self.fail = fail

    def mark_if_new(self, update_id: int, ttl_seconds: int) -> bool:
        if self.fail:
            raise ConnectionError("redis caído")
        if update_id in self.keys:
            return False
        self.keys[update_id] = ttl_seconds
        return True
