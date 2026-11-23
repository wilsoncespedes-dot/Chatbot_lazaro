"""Fase 6: cliente HTTP de TikTok (refresco OAuth y envío) y su doble de test."""
from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any, Protocol

import httpx

logger = logging.getLogger(__name__)

# TikTok documents 40102/40104/40105 as expired, empty or invalid access tokens.
# 40100 is a quota error and must not trigger token rotation.
AUTH_ERROR_CODES: frozenset[int] = frozenset({40102, 40104, 40105})


class TikTokApiError(Exception):
    """Fallo de red o respuesta de error de TikTok (sin datos del cuerpo)."""


class TikTokAuthError(TikTokApiError):
    """El token de acceso venció o fue revocado: hay que refrescar y reintentar."""


class TikTokApi(Protocol):
    def refresh_token(
        self, client_key: str, client_secret: str, refresh_token: str
    ) -> Mapping[str, Any]: ...

    def send_message(self, access_token: str, payload: Mapping[str, Any]) -> None: ...


def _json(response: httpx.Response) -> dict:
    try:
        body = response.json()
    except ValueError:
        return {}
    return body if isinstance(body, dict) else {}


def _error_code(body: Mapping[str, Any]) -> int | None:
    code = body.get("code")
    if isinstance(code, int) and not isinstance(code, bool):
        return code
    error = body.get("error")
    if isinstance(error, Mapping):
        inner = error.get("code")
        if isinstance(inner, int) and not isinstance(inner, bool):
            return inner
    return None


class HttpTikTokApi:
    """httpx contra las URLs configuradas; nunca registra tokens ni cuerpos."""

    def __init__(self, token_url: str, send_url: str, client: httpx.Client) -> None:
        self._token_url = token_url
        self._send_url = send_url
        self._client = client

    def refresh_token(
        self, client_key: str, client_secret: str, refresh_token: str
    ) -> Mapping[str, Any]:
        try:
            response = self._client.post(
                self._token_url,
                json={
                    "client_id": client_key,
                    "client_secret": client_secret,
                    "grant_type": "refresh_token",
                    "refresh_token": refresh_token,
                },
            )
        except httpx.HTTPError as exc:
            raise TikTokApiError(type(exc).__name__) from None
        body = _json(response)
        code = _error_code(body)
        if response.status_code >= 400 or body.get("error") or code != 0:
            logger.warning("tiktok_refresh_failed status=%s", response.status_code)
            raise TikTokApiError(f"refresh_status_{response.status_code}")
        return body

    def send_message(self, access_token: str, payload: Mapping[str, Any]) -> None:
        try:
            response = self._client.post(
                self._send_url,
                json=dict(payload),
                headers={"Access-Token": access_token},
            )
        except httpx.HTTPError as exc:
            raise TikTokApiError(type(exc).__name__) from None
        body = _json(response)
        code = _error_code(body)
        if code in AUTH_ERROR_CODES or (response.status_code == 401 and code is None):
            raise TikTokAuthError("token_invalid")
        if response.status_code >= 400 or code != 0:
            logger.warning(
                "tiktok_send_failed status=%s code=%s", response.status_code, code
            )
            raise TikTokApiError(f"send_status_{response.status_code}")


class FakeTikTokApi:
    """Doble de test: registra llamadas y simula tokens vencidos."""

    def __init__(
        self,
        *,
        refresh_responses: list[Mapping[str, Any]] | None = None,
        valid_tokens: set[str] | None = None,
        fail_send: bool = False,
    ) -> None:
        self.refresh_responses = list(refresh_responses or [])
        self.valid_tokens = valid_tokens
        self.fail_send = fail_send
        self.refresh_calls: list[str] = []
        self.sent: list[tuple[str, dict]] = []
        self.rejected: list[str] = []

    def refresh_token(
        self, client_key: str, client_secret: str, refresh_token: str
    ) -> Mapping[str, Any]:
        self.refresh_calls.append(refresh_token)
        if not self.refresh_responses:
            raise TikTokApiError("no_refresh_response")
        return self.refresh_responses.pop(0)

    def send_message(self, access_token: str, payload: Mapping[str, Any]) -> None:
        if self.valid_tokens is not None and access_token not in self.valid_tokens:
            self.rejected.append(access_token)
            raise TikTokAuthError("token_invalid")
        if self.fail_send:
            raise TikTokApiError("send_failed")
        self.sent.append((access_token, dict(payload)))
