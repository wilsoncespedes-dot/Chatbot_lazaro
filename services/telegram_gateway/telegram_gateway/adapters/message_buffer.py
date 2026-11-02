"""Buffer de mensajes agrupados: Protocol, versión Redis y versión falsa."""
from __future__ import annotations

import json
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable, Protocol, runtime_checkable

from ..domain import BufferedMessage, ClaimedGroup, compute_due

BUF_PREFIX = "gw:grp:buf:"
DUE_KEY = "gw:grp:due"
INFLIGHT_PREFIX = "gw:grp:inflight:"
LEASES_KEY = "gw:grp:leases"
SEQUENCE_KEY = "gw:grp:claimseq"

_FIRST_FIELD = "__first_at"
_LAST_FIELD = "__last_at"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@runtime_checkable
class MessageBuffer(Protocol):
    def append(
        self,
        chat_id: int,
        msg: BufferedMessage,
        window: float,
        max_wait: float,
        ttl_seconds: int,
    ) -> bool:
        """Añade el mensaje; False si su update_id ya estaba en el buffer."""
        ...

    def pending(self, chat_id: int) -> list[BufferedMessage]:
        ...

    def claim_chat(
        self, chat_id: int, now: datetime, lease_seconds: float, ttl_seconds: int
    ) -> ClaimedGroup | None:
        ...

    def claim_due(
        self, now: datetime, lease_seconds: float, ttl_seconds: int, limit: int
    ) -> list[ClaimedGroup]:
        ...

    def ack(self, group: ClaimedGroup) -> None:
        ...

    def release(self, group: ClaimedGroup, now: datetime) -> None:
        ...


@dataclass
class _FakeBuffer:
    messages: dict[int, BufferedMessage]
    first: datetime
    last: datetime
    due: datetime
    expires_at: datetime


@dataclass
class _FakeInflight:
    claim_id: str
    attempts: int
    messages: tuple[BufferedMessage, ...]
    lease_expires_at: datetime
    expires_at: datetime
    ttl_seconds: int


class FakeMessageBuffer:
    """Réplica en memoria de la semántica de Redis para los tests."""

    def __init__(self, clock: Callable[[], datetime] | None = None, fail: bool = False) -> None:
        self._clock = clock or _utcnow
        self.fail = fail
        self._lock = threading.Lock()
        self._buffers: dict[int, _FakeBuffer] = {}
        self._inflight: dict[int, _FakeInflight] = {}

    def _check(self) -> None:
        if self.fail:
            raise ConnectionError("redis caído")

    def _purge(self, now: datetime) -> None:
        for chat_id, buffer in list(self._buffers.items()):
            if buffer.expires_at <= now:
                del self._buffers[chat_id]
        for chat_id, inflight in list(self._inflight.items()):
            if inflight.expires_at <= now:
                del self._inflight[chat_id]

    def append(
        self,
        chat_id: int,
        msg: BufferedMessage,
        window: float,
        max_wait: float,
        ttl_seconds: int,
    ) -> bool:
        with self._lock:
            self._check()
            now = self._clock()
            self._purge(now)
            buffer = self._buffers.get(chat_id)
            if buffer is not None and msg.update_id in buffer.messages:
                return False
            if buffer is None:
                buffer = _FakeBuffer(
                    messages={},
                    first=msg.received_at,
                    last=msg.received_at,
                    due=msg.received_at,
                    expires_at=now + timedelta(seconds=ttl_seconds),
                )
                self._buffers[chat_id] = buffer
            buffer.messages[msg.update_id] = msg
            buffer.last = msg.received_at
            buffer.due = compute_due(buffer.first, buffer.last, window, max_wait)
            buffer.expires_at = now + timedelta(seconds=ttl_seconds)
            return True

    def pending(self, chat_id: int) -> list[BufferedMessage]:
        with self._lock:
            self._check()
            self._purge(self._clock())
            buffer = self._buffers.get(chat_id)
            if buffer is None:
                return []
            return [buffer.messages[key] for key in sorted(buffer.messages)]

    def _claim(
        self, chat_id: int, messages: tuple[BufferedMessage, ...], now: datetime,
        lease_seconds: float, ttl_seconds: int, attempts: int,
    ) -> ClaimedGroup:
        claim_id = uuid.uuid4().hex
        self._inflight[chat_id] = _FakeInflight(
            claim_id=claim_id,
            attempts=attempts,
            messages=messages,
            lease_expires_at=now + timedelta(seconds=lease_seconds),
            expires_at=now + timedelta(seconds=ttl_seconds),
            ttl_seconds=ttl_seconds,
        )
        return ClaimedGroup(
            chat_id=chat_id,
            claim_id=claim_id,
            attempts=attempts,
            messages=messages,
        )

    def claim_chat(
        self, chat_id: int, now: datetime, lease_seconds: float, ttl_seconds: int
    ) -> ClaimedGroup | None:
        with self._lock:
            self._check()
            self._purge(now)
            if chat_id in self._inflight:
                return None
            buffer = self._buffers.pop(chat_id, None)
            if buffer is None:
                return None
            messages = tuple(buffer.messages[key] for key in sorted(buffer.messages))
            return self._claim(chat_id, messages, now, lease_seconds, ttl_seconds, 1)

    def claim_due(
        self, now: datetime, lease_seconds: float, ttl_seconds: int, limit: int
    ) -> list[ClaimedGroup]:
        with self._lock:
            self._check()
            self._purge(now)
            claimed: list[ClaimedGroup] = []
            for chat_id in sorted(self._buffers):
                if len(claimed) >= limit:
                    return claimed
                if chat_id in self._inflight:
                    continue
                buffer = self._buffers[chat_id]
                if buffer.due > now:
                    continue
                del self._buffers[chat_id]
                messages = tuple(
                    buffer.messages[key] for key in sorted(buffer.messages)
                )
                claimed.append(
                    self._claim(chat_id, messages, now, lease_seconds, ttl_seconds, 1)
                )
            for chat_id in sorted(self._inflight):
                if len(claimed) >= limit:
                    return claimed
                inflight = self._inflight[chat_id]
                if inflight.lease_expires_at > now:
                    continue
                attempts = inflight.attempts + 1
                self._inflight.pop(chat_id)
                claimed.append(
                    self._claim(
                        chat_id,
                        inflight.messages,
                        now,
                        lease_seconds,
                        ttl_seconds,
                        attempts,
                    )
                )
            return claimed

    def ack(self, group: ClaimedGroup) -> None:
        with self._lock:
            self._check()
            inflight = self._inflight.get(group.chat_id)
            if inflight is not None and inflight.claim_id == group.claim_id:
                del self._inflight[group.chat_id]

    def release(self, group: ClaimedGroup, now: datetime) -> None:
        with self._lock:
            self._check()
            inflight = self._inflight.get(group.chat_id)
            if inflight is None or inflight.claim_id != group.claim_id:
                return
            inflight.lease_expires_at = now
            inflight.expires_at = now + timedelta(seconds=inflight.ttl_seconds)


_APPEND_LUA = """
if redis.call('HEXISTS', KEYS[1], ARGV[1]) == 1 then
  return 0
end
if redis.call('HEXISTS', KEYS[1], '__first_at') == 0 then
  redis.call('HSET', KEYS[1], '__first_at', ARGV[3])
end
redis.call('HSET', KEYS[1], ARGV[1], ARGV[2])
redis.call('HSET', KEYS[1], '__last_at', ARGV[3])
local first = tonumber(redis.call('HGET', KEYS[1], '__first_at'))
local last = tonumber(ARGV[3])
local due = math.min(last + tonumber(ARGV[4]), first + tonumber(ARGV[5]))
redis.call('ZADD', KEYS[2], due, ARGV[6])
redis.call('EXPIRE', KEYS[1], ARGV[7])
redis.call('EXPIRE', KEYS[2], ARGV[7])
return 1
"""

_CLAIM_CHAT_LUA = """
if redis.call('EXISTS', KEYS[2]) == 1 then
  return nil
end
if redis.call('EXISTS', KEYS[1]) == 0 then
  return nil
end
local ids = {}
for _, field in ipairs(redis.call('HKEYS', KEYS[1])) do
  if string.sub(field, 1, 2) ~= '__' then
    ids[#ids + 1] = field
  end
end
if #ids == 0 then
  redis.call('DEL', KEYS[1])
  redis.call('ZREM', KEYS[3], ARGV[1])
  return nil
end
table.sort(ids, function(a, b) return tonumber(a) < tonumber(b) end)
local messages = {}
for _, id in ipairs(ids) do
  messages[#messages + 1] = redis.call('HGET', KEYS[1], id)
end
local messages_json = '[' .. table.concat(messages, ',') .. ']'
local seq = redis.call('INCR', KEYS[5])
local claim_id = ARGV[1] .. ':' .. tostring(seq)
redis.call('HSET', KEYS[2], 'claim_id', claim_id, 'attempts', 1, 'messages', messages_json, 'ttl', ARGV[4])
redis.call('DEL', KEYS[1])
redis.call('ZREM', KEYS[3], ARGV[1])
redis.call('ZADD', KEYS[4], tonumber(ARGV[2]) + tonumber(ARGV[3]), ARGV[1])
redis.call('EXPIRE', KEYS[2], ARGV[4])
redis.call('EXPIRE', KEYS[4], ARGV[4])
redis.call('EXPIRE', KEYS[5], ARGV[4])
return cjson.encode({claim_id, 1, messages_json})
"""

_CLAIM_DUE_LUA = """
local now = tonumber(ARGV[1])
local lease = tonumber(ARGV[2])
local ttl = ARGV[3]
local limit = tonumber(ARGV[4])
local buf_prefix = ARGV[5]
local inflight_prefix = ARGV[6]
local seq_key = ARGV[7]
local results = {}
local seen = {}
local function new_claim_id(chat)
  local seq = redis.call('INCR', seq_key)
  return chat .. ':' .. tostring(seq)
end
local function buffer_messages(buf_key)
  local ids = {}
  for _, field in ipairs(redis.call('HKEYS', buf_key)) do
    if string.sub(field, 1, 2) ~= '__' then
      ids[#ids + 1] = field
    end
  end
  table.sort(ids, function(a, b) return tonumber(a) < tonumber(b) end)
  local messages = {}
  for _, id in ipairs(ids) do
    messages[#messages + 1] = redis.call('HGET', buf_key, id)
  end
  return '[' .. table.concat(messages, ',') .. ']'
end
local due = redis.call('ZRANGEBYSCORE', KEYS[1], '-inf', now, 'LIMIT', 0, limit)
for _, chat in ipairs(due) do
  if #results < limit and not seen[chat] then
    local buf_key = buf_prefix .. chat
    local inflight_key = inflight_prefix .. chat
    if redis.call('EXISTS', inflight_key) == 0 then
      if redis.call('EXISTS', buf_key) == 1 then
        local messages_json = buffer_messages(buf_key)
        local claim_id = new_claim_id(chat)
        redis.call('HSET', inflight_key, 'claim_id', claim_id, 'attempts', 1, 'messages', messages_json, 'ttl', ttl)
        redis.call('DEL', buf_key)
        redis.call('ZREM', KEYS[1], chat)
        redis.call('ZADD', KEYS[2], now + lease, chat)
        redis.call('EXPIRE', inflight_key, ttl)
        redis.call('EXPIRE', KEYS[2], ttl)
        results[#results + 1] = {chat, claim_id, 1, messages_json}
        seen[chat] = true
      else
        redis.call('ZREM', KEYS[1], chat)
      end
    end
  end
end
local expired = redis.call('ZRANGEBYSCORE', KEYS[2], '-inf', now, 'LIMIT', 0, limit)
for _, chat in ipairs(expired) do
  if #results < limit and not seen[chat] then
    local inflight_key = inflight_prefix .. chat
    if redis.call('EXISTS', inflight_key) == 1 then
      local attempts = tonumber(redis.call('HGET', inflight_key, 'attempts') or '0') + 1
      local messages_json = redis.call('HGET', inflight_key, 'messages') or '[]'
      local claim_id = new_claim_id(chat)
      redis.call('HSET', inflight_key, 'claim_id', claim_id, 'attempts', attempts)
      redis.call('ZADD', KEYS[2], now + lease, chat)
      redis.call('EXPIRE', inflight_key, ttl)
      redis.call('EXPIRE', KEYS[2], ttl)
      results[#results + 1] = {chat, claim_id, attempts, messages_json}
      seen[chat] = true
    else
      redis.call('ZREM', KEYS[2], chat)
    end
  end
end
return cjson.encode(results)
"""

_ACK_LUA = """
if redis.call('HGET', KEYS[1], 'claim_id') == ARGV[2] then
  redis.call('DEL', KEYS[1])
  redis.call('ZREM', KEYS[2], ARGV[1])
  return 1
end
return 0
"""

_RELEASE_LUA = """
if redis.call('HGET', KEYS[1], 'claim_id') ~= ARGV[2] then
  return 0
end
local ttl = redis.call('HGET', KEYS[1], 'ttl') or '300'
redis.call('ZADD', KEYS[2], tonumber(ARGV[3]), ARGV[1])
redis.call('EXPIRE', KEYS[1], ttl)
redis.call('EXPIRE', KEYS[2], ttl)
return 1
"""


def _message_to_json(message: BufferedMessage) -> str:
    return json.dumps(
        {
            "update_id": message.update_id,
            "user_id": message.user_id,
            "text": message.text,
            "received_at": message.received_at.isoformat(),
        },
        ensure_ascii=False,
    )


def _message_from_json(raw: str | bytes | dict) -> BufferedMessage:
    data = raw if isinstance(raw, dict) else json.loads(raw)
    return BufferedMessage(
        update_id=int(data["update_id"]),
        user_id=int(data["user_id"]),
        text=str(data["text"]),
        received_at=datetime.fromisoformat(data["received_at"]),
    )


class RedisMessageBuffer:
    """Buffer atómico sobre Redis; los scripts Lua dan R18 y R19 entre instancias."""

    def __init__(self, redis_url: str) -> None:
        import redis

        self._client = redis.Redis.from_url(redis_url)

    def _run(self, script: str, keys: list[str], args: list[object]):
        return self._client.register_script(script)(keys=keys, args=args)

    def append(
        self,
        chat_id: int,
        msg: BufferedMessage,
        window: float,
        max_wait: float,
        ttl_seconds: int,
    ) -> bool:
        result = self._run(
            _APPEND_LUA,
            [f"{BUF_PREFIX}{chat_id}", DUE_KEY],
            [
                str(msg.update_id),
                _message_to_json(msg),
                msg.received_at.timestamp(),
                window,
                max_wait,
                str(chat_id),
                ttl_seconds,
            ],
        )
        return bool(int(result))

    def pending(self, chat_id: int) -> list[BufferedMessage]:
        raw = self._client.hgetall(f"{BUF_PREFIX}{chat_id}")
        messages = []
        for field, value in raw.items():
            name = field.decode() if isinstance(field, bytes) else field
            if name.startswith("__"):
                continue
            messages.append(_message_from_json(value))
        return sorted(messages, key=lambda message: message.update_id)

    def claim_chat(
        self, chat_id: int, now: datetime, lease_seconds: float, ttl_seconds: int
    ) -> ClaimedGroup | None:
        payload = self._run(
            _CLAIM_CHAT_LUA,
            [
                f"{BUF_PREFIX}{chat_id}",
                f"{INFLIGHT_PREFIX}{chat_id}",
                DUE_KEY,
                LEASES_KEY,
                SEQUENCE_KEY,
            ],
            [str(chat_id), now.timestamp(), lease_seconds, ttl_seconds],
        )
        if payload is None:
            return None
        claim_id, attempts, messages_json = json.loads(payload)
        return _parse_group(chat_id, claim_id, attempts, messages_json)

    def claim_due(
        self, now: datetime, lease_seconds: float, ttl_seconds: int, limit: int
    ) -> list[ClaimedGroup]:
        payload = self._run(
            _CLAIM_DUE_LUA,
            [DUE_KEY, LEASES_KEY],
            [
                now.timestamp(),
                lease_seconds,
                ttl_seconds,
                limit,
                BUF_PREFIX,
                INFLIGHT_PREFIX,
                SEQUENCE_KEY,
            ],
        )
        if not payload:
            return []
        groups = []
        for chat, claim_id, attempts, messages_json in json.loads(payload):
            groups.append(_parse_group(int(chat), claim_id, attempts, messages_json))
        return groups

    def ack(self, group: ClaimedGroup) -> None:
        self._run(
            _ACK_LUA,
            [f"{INFLIGHT_PREFIX}{group.chat_id}", LEASES_KEY],
            [str(group.chat_id), group.claim_id],
        )

    def release(self, group: ClaimedGroup, now: datetime) -> None:
        self._run(
            _RELEASE_LUA,
            [f"{INFLIGHT_PREFIX}{group.chat_id}", LEASES_KEY],
            [str(group.chat_id), group.claim_id, now.timestamp()],
        )


def _parse_group(
    chat_id: int, claim_id: object, attempts: object, messages_json: object
) -> ClaimedGroup:
    messages = tuple(_message_from_json(raw) for raw in json.loads(messages_json))
    return ClaimedGroup(
        chat_id=chat_id,
        claim_id=str(claim_id),
        attempts=int(attempts),
        messages=messages,
    )
