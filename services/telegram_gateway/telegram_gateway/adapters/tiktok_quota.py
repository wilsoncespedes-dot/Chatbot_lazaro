"""Cuota atómica de mensajes TikTok por conversación en cada ventana de 48 h."""
from __future__ import annotations

import hashlib
from typing import Protocol

TIKTOK_WINDOW_SECONDS = 48 * 60 * 60
TIKTOK_MESSAGES_PER_WINDOW = 10

_RESERVE_SCRIPT = """
if redis.call('EXISTS', KEYS[2]) == 0 then
    return 0
end
local count = tonumber(redis.call('GET', KEYS[1]) or '0')
if count >= tonumber(ARGV[1]) then
    return 0
end
local next_count = redis.call('INCR', KEYS[1])
if next_count == 1 then
    redis.call('EXPIRE', KEYS[1], tonumber(ARGV[2]))
end
return 1
"""

_RECORD_INBOUND_SCRIPT = """
redis.call('DEL', KEYS[1])
redis.call('SET', KEYS[2], '1', 'EX', tonumber(ARGV[1]))
return 1
"""


class TikTokMessageQuotaStore(Protocol):
    def record_inbound(self, conversation_id: str) -> None: ...

    def reserve_send(self, conversation_id: str, limit: int) -> bool: ...


def _key(conversation_id: str) -> str:
    digest = hashlib.sha256(conversation_id.encode("utf-8")).hexdigest()
    return f"gw:tiktok:sent:{digest}"


def _window_key(conversation_id: str) -> str:
    digest = hashlib.sha256(conversation_id.encode("utf-8")).hexdigest()
    return f"gw:tiktok:window:{digest}"


class RedisTikTokMessageQuotaStore:
    def __init__(self, redis_url: str) -> None:
        import redis

        self._client = redis.Redis.from_url(redis_url)

    def record_inbound(self, conversation_id: str) -> None:
        self._client.eval(
            _RECORD_INBOUND_SCRIPT,
            2,
            _key(conversation_id),
            _window_key(conversation_id),
            TIKTOK_WINDOW_SECONDS,
        )

    def reserve_send(self, conversation_id: str, limit: int) -> bool:
        result = self._client.eval(
            _RESERVE_SCRIPT,
            2,
            _key(conversation_id),
            _window_key(conversation_id),
            limit,
            TIKTOK_WINDOW_SECONDS,
        )
        return result == 1


class FakeTikTokMessageQuotaStore:
    def __init__(self) -> None:
        self.values: dict[str, int] = {}

    def record_inbound(self, conversation_id: str) -> None:
        self.values[conversation_id] = 0

    def reserve_send(self, conversation_id: str, limit: int) -> bool:
        if conversation_id not in self.values:
            return False
        count = self.values.get(conversation_id, 0)
        if count >= limit:
            return False
        self.values[conversation_id] = count + 1
        return True
