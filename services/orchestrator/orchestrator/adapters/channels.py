"""Directorio de canales: lee `GET /channels` del gateway con caché (#65).

El orquestador nunca lee la tabla `canales`: pregunta al gateway por HTTP con
`X-Service-Token` y guarda una copia por proceso durante el TTL configurado.
"""
from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable, Sequence
from typing import ClassVar, Protocol

import httpx
from lazaro_contracts import SERVICE_TOKEN_HEADER, ChannelInfo, ChannelListResponse

from ..channels import ChannelPolicy, default_policy, policy_from_info
from ..domain import ServiceUnavailable

logger = logging.getLogger(__name__)


class ChannelDirectory(Protocol):
    def policy(self, channel_id: str) -> ChannelPolicy: ...

    def list_policies(self) -> list[ChannelPolicy]: ...


def _ordered(infos: Sequence[ChannelInfo]) -> list[ChannelPolicy]:
    """Activos primero; dentro de cada grupo, por creación e id."""
    ordered = sorted(infos, key=lambda info: (not info.active, info.created_at, info.id))
    return [policy_from_info(info) for info in ordered]


class _PolicyLookup:
    def _policies(self) -> list[ChannelPolicy]:  # pragma: no cover - abstracto
        raise NotImplementedError

    def policy(self, channel_id: str) -> ChannelPolicy:
        for policy in self._policies():
            if policy.id == channel_id:
                return policy
        return default_policy(channel_id)

    def list_policies(self) -> list[ChannelPolicy]:
        return list(self._policies())


class HttpChannelDirectory(_PolicyLookup):
    def __init__(
        self,
        base_url: str,
        service_token: str,
        ttl_seconds: float,
        timeout: float = 10,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._service_token = service_token
        self._ttl = ttl_seconds
        self._timeout = timeout
        self._clock = clock
        self._lock = threading.Lock()
        self._cached: list[ChannelPolicy] | None = None
        self._fetched_at = 0.0

    def _fetch(self) -> list[ChannelPolicy]:
        response = httpx.get(
            f"{self._base_url}/channels",
            headers={SERVICE_TOKEN_HEADER: self._service_token},
            timeout=self._timeout,
        )
        response.raise_for_status()
        return _ordered(ChannelListResponse.model_validate(response.json()).channels)

    def _policies(self) -> list[ChannelPolicy]:
        with self._lock:
            now = self._clock()
            if self._cached is not None and now - self._fetched_at < self._ttl:
                return self._cached
            try:
                policies = self._fetch()
            except Exception as exc:  # noqa: BLE001 - red, HTTP o respuesta inválida
                if self._cached is not None:
                    logger.warning(
                        "channel_directory_stale code=%s", type(exc).__name__
                    )
                    return self._cached
                raise ServiceUnavailable("directorio de canales no disponible") from exc
            self._cached = policies
            self._fetched_at = now
            return policies


class FakeChannelDirectory(_PolicyLookup):
    """Directorio en memoria. Sin nombres de canal: las pruebas pueblan `default_infos`."""

    default_infos: ClassVar[Sequence[ChannelInfo]] = ()

    def __init__(
        self, infos: Sequence[ChannelInfo] | None = None, fail: bool = False
    ) -> None:
        self._infos = list(infos) if infos is not None else list(type(self).default_infos)
        self.fail = fail
        self.calls = 0

    def set_infos(self, infos: Sequence[ChannelInfo]) -> None:
        self._infos = list(infos)

    def _policies(self) -> list[ChannelPolicy]:
        self.calls += 1
        if self.fail:
            raise ServiceUnavailable("directorio de canales no disponible")
        return _ordered(self._infos)
