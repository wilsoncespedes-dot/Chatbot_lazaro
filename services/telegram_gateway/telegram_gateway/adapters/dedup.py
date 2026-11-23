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

    def forget_message(self, channel: str, external_message_id: str) -> None:
        """Quita la marca de un mensaje que no se pudo entregar ni guardar."""
        ...

    def ping(self, timeout_seconds: float) -> bool:
        """Comprueba Redis con PING y un timeout acotado (healthcheck, solo lectura)."""
        ...


class RedisDedupStore:
    def __init__(self, redis_url: str) -> None:
        import redis

        self._redis_url = redis_url
        self._client = redis.Redis.from_url(redis_url)

    def ping(self, timeout_seconds: float) -> bool:
        # Cliente independiente solo para el probe: los límites de conexión y
        # socket no alteran el timeout de las operaciones de negocio.
        import redis

        probe = redis.Redis.from_url(
            self._redis_url,
            socket_connect_timeout=timeout_seconds,
            socket_timeout=timeout_seconds,
        )
        try:
            return bool(probe.ping())
        finally:
            probe.close()

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

    def forget_message(self, channel: str, external_message_id: str) -> None:
        """Quita la marca para que el reenvío del canal se procese (fase 2)."""
        keys = [f"gw:message:{channel}:{external_message_id}"]
        if channel == "telegram":
            keys.append(f"gw:update:{external_message_id}")
        self._client.delete(*keys)


class FakeDedupStore:
    def __init__(
        self,
        fail: bool = False,
        ping_ok: bool = True,
        ping_error: BaseException | None = None,
    ) -> None:
        # `keys` conserva la forma histórica (update_id -> ttl) para Telegram.
        self.keys: dict[int, int] = {}
        self.message_keys: set[tuple[str, str]] = set()
        self.fail = fail
        self.ping_ok = ping_ok
        self.ping_error = ping_error
        self.ping_calls: list[float] = []

    def ping(self, timeout_seconds: float) -> bool:
        self.ping_calls.append(timeout_seconds)
        if self.ping_error is not None:
            raise self.ping_error
        return self.ping_ok

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

    def forget_message(self, channel: str, external_message_id: str) -> None:
        if self.fail:
            raise ConnectionError("redis caído")
        self.message_keys.discard((channel, external_message_id))
        if channel == "telegram":
            try:
                self.keys.pop(int(external_message_id), None)
            except ValueError:
                pass
