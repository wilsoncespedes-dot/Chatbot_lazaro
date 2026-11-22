"""Cliente de administración de canales del gateway (#66).

El panel `/admin/canales` nunca toca la tabla `canales`: usa las rutas
`/channels…` del gateway con `X-Service-Token`. Nunca registra secretos ni
credenciales en los logs.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Protocol

import httpx
from lazaro_contracts import (
    SERVICE_TOKEN_HEADER,
    ChannelActiveRequest,
    ChannelCreateRequest,
    ChannelCreateResponse,
    ChannelInfo,
    ChannelListResponse,
    ChannelSecretResponse,
    ChannelUpdateRequest,
    credential_hint,
)
from pydantic import BaseModel, ValidationError

from ..domain import ServiceUnavailable

logger = logging.getLogger(__name__)


class ChannelAdminError(Exception):
    """El gateway rechazó la operación con un 4xx (salvo 401)."""

    def __init__(self, status: int, code: str) -> None:
        super().__init__(code)
        self.status = status
        self.code = code


class ChannelAdminUnavailable(ServiceUnavailable):
    """El gateway no responde, responde 5xx/401 o un cuerpo inválido."""


class ChannelAdminClient(Protocol):
    def list(self) -> ChannelListResponse: ...

    def create(self, request: ChannelCreateRequest) -> ChannelCreateResponse: ...

    def update(self, channel_id: str, request: ChannelUpdateRequest) -> ChannelInfo: ...

    def set_active(self, channel_id: str, active: bool) -> ChannelInfo: ...

    def reveal_secret(self, channel_id: str) -> ChannelSecretResponse: ...

    def regenerate_secret(self, channel_id: str) -> ChannelSecretResponse: ...


class HttpChannelAdminClient:
    def __init__(
        self,
        base_url: str,
        service_token: str,
        timeout: float = 10,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._service_token = service_token
        self._timeout = timeout
        self._transport = transport

    def _request(self, method: str, path: str, body: BaseModel | None = None) -> Any:
        headers = {SERVICE_TOKEN_HEADER: self._service_token}
        kwargs: dict[str, Any] = {}
        if body is not None:
            headers["Content-Type"] = "application/json"
            kwargs["content"] = body.model_dump_json(exclude_unset=True)
        try:
            with httpx.Client(
                timeout=self._timeout, transport=self._transport, follow_redirects=False
            ) as client:
                response = client.request(
                    method, f"{self._base_url}{path}", headers=headers, **kwargs
                )
        except (httpx.HTTPError, ValueError) as exc:
            logger.error("channel_admin_failed code=%s", type(exc).__name__)
            raise ChannelAdminUnavailable("El gateway no está disponible.") from None
        status = response.status_code
        if 400 <= status < 500 and status != 401:
            try:
                code = str(response.json().get("error") or "validation_error")
            except (ValueError, AttributeError):
                code = "validation_error"
            raise ChannelAdminError(status, code)
        if not 200 <= status < 300:
            logger.error("channel_admin_failed status=%s", status)
            raise ChannelAdminUnavailable("El gateway no está disponible.")
        try:
            return response.json()
        except ValueError:
            raise ChannelAdminUnavailable("El gateway no está disponible.") from None

    @staticmethod
    def _parse(model, payload):
        try:
            return model.model_validate(payload)
        except (TypeError, ValueError, ValidationError):
            raise ChannelAdminUnavailable("El gateway no está disponible.") from None

    def list(self) -> ChannelListResponse:
        return self._parse(ChannelListResponse, self._request("GET", "/channels"))

    def create(self, request: ChannelCreateRequest) -> ChannelCreateResponse:
        return self._parse(
            ChannelCreateResponse, self._request("POST", "/channels", request)
        )

    def update(self, channel_id: str, request: ChannelUpdateRequest) -> ChannelInfo:
        return self._parse(
            ChannelInfo, self._request("PATCH", f"/channels/{channel_id}", request)
        )

    def set_active(self, channel_id: str, active: bool) -> ChannelInfo:
        return self._parse(
            ChannelInfo,
            self._request(
                "PATCH",
                f"/channels/{channel_id}/active",
                ChannelActiveRequest(active=active),
            ),
        )

    def reveal_secret(self, channel_id: str) -> ChannelSecretResponse:
        return self._parse(
            ChannelSecretResponse, self._request("GET", f"/channels/{channel_id}/secret")
        )

    def regenerate_secret(self, channel_id: str) -> ChannelSecretResponse:
        return self._parse(
            ChannelSecretResponse, self._request("POST", f"/channels/{channel_id}/secret")
        )


_FAKE_CREATED = datetime(2026, 1, 1, tzinfo=timezone.utc)


class FakeChannelAdminClient:
    """Gateway en memoria para pruebas: imita las reglas de /channels…"""

    def __init__(
        self,
        channels: list[ChannelInfo] | None = None,
        adapter_types: list[str] | None = None,
        *,
        fail: bool = False,
        error: ChannelAdminError | None = None,
    ) -> None:
        self.channels: dict[str, ChannelInfo] = {c.id: c for c in channels or []}
        self.adapter_types = list(adapter_types or [])
        self.secrets: dict[str, str] = {}
        self.fail = fail
        self.error = error
        self.calls: list[tuple] = []
        self._counter = 0

    def _check(self, *call) -> None:
        self.calls.append(call)
        if self.fail:
            raise ChannelAdminUnavailable("gateway caído")
        if self.error is not None and call[0] != "list":
            raise self.error

    def _get(self, channel_id: str) -> ChannelInfo:
        if channel_id not in self.channels:
            raise ChannelAdminError(404, "not_found")
        return self.channels[channel_id]

    def _new_secret(self) -> str:
        self._counter += 1
        return (f"S{self._counter}" + "x" * 43)[:43]

    def list(self) -> ChannelListResponse:
        self._check("list")
        return ChannelListResponse(
            channels=list(self.channels.values()), adapter_types=self.adapter_types
        )

    def create(self, request: ChannelCreateRequest) -> ChannelCreateResponse:
        self._check("create", request)
        if request.id in self.channels:
            raise ChannelAdminError(409, "channel_exists")
        if request.adapter_type not in self.adapter_types:
            raise ChannelAdminError(422, "validation_error")
        info = ChannelInfo(
            id=request.id,
            name=request.name,
            adapter_type=request.adapter_type,
            icon=request.icon,
            color=request.color,
            config=dict(request.config),
            active=request.active,
            configured=True,
            has_secrets=True,
            managed_by_environment=False,
            created_at=_FAKE_CREATED,
            credential_hints={k: credential_hint(v) for k, v in request.credentials.items()},
        )
        self.channels[info.id] = info
        secret = self._new_secret()
        self.secrets[info.id] = secret
        return ChannelCreateResponse(channel=info, secret=secret)

    def update(self, channel_id: str, request: ChannelUpdateRequest) -> ChannelInfo:
        self._check("update", channel_id, request)
        current = self._get(channel_id)
        fields = request.model_fields_set
        if "credentials" in fields and current.managed_by_environment:
            raise ChannelAdminError(409, "channel_managed_by_environment")
        changes: dict[str, Any] = {
            name: getattr(request, name)
            for name in ("name", "icon", "color", "config")
            if name in fields
        }
        if "credentials" in fields:
            changes["credential_hints"] = {
                k: credential_hint(v) for k, v in (request.credentials or {}).items()
            }
        updated = current.model_copy(update=changes)
        self.channels[channel_id] = updated
        return updated

    def set_active(self, channel_id: str, active: bool) -> ChannelInfo:
        self._check("set_active", channel_id, active)
        updated = self._get(channel_id).model_copy(update={"active": active})
        self.channels[channel_id] = updated
        return updated

    def _secret_channel(self, channel_id: str) -> ChannelInfo:
        info = self._get(channel_id)
        if info.managed_by_environment:
            raise ChannelAdminError(409, "channel_managed_by_environment")
        return info

    def reveal_secret(self, channel_id: str) -> ChannelSecretResponse:
        self._check("reveal_secret", channel_id)
        self._secret_channel(channel_id)
        if channel_id not in self.secrets:
            raise ChannelAdminError(404, "not_found")
        return ChannelSecretResponse(channel_id=channel_id, secret=self.secrets[channel_id])

    def regenerate_secret(self, channel_id: str) -> ChannelSecretResponse:
        self._check("regenerate_secret", channel_id)
        self._secret_channel(channel_id)
        secret = self._new_secret()
        self.secrets[channel_id] = secret
        return ChannelSecretResponse(channel_id=channel_id, secret=secret)
