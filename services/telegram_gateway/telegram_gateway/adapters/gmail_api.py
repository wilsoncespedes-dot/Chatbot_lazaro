"""Cliente REST de Gmail con OAuth refresh-token, sin SDK ni datos en logs."""
from __future__ import annotations

import base64
import hashlib
import threading
import time
from collections.abc import Callable, Mapping
from email.message import EmailMessage
from email.utils import parseaddr
from typing import Any, Protocol
from urllib.parse import quote

import httpx

from ..domain import ChannelNotConfigured

GMAIL_API = "https://gmail.googleapis.com/gmail/v1/users/me"
OAUTH_TOKEN_URL = "https://oauth2.googleapis.com/token"
# Google entrega tokens de 3600 s; se renuevan un minuto antes de vencer.
DEFAULT_TOKEN_SECONDS = 3600.0
TOKEN_RENEW_MARGIN_SECONDS = 60.0
# Al responder solo hacen falta estas cabeceras del hilo, no los cuerpos.
REPLY_HEADERS = ("From", "Message-ID", "References", "Subject")


class GmailTokenCache:
    """Tokens de acceso vigentes por credencial, solo en memoria del proceso.

    El canal se construye en cada sincronización y en cada envío; sin caché
    cada uno pedía un token nuevo a Google (una ida y vuelta más). La clave es
    un hash: el refresh token nunca se guarda en claro aquí.
    """

    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._lock = threading.Lock()
        self._tokens: dict[str, tuple[str, float]] = {}

    @staticmethod
    def key(client_id: str, refresh_token: str) -> str:
        return hashlib.sha256(f"{client_id}\0{refresh_token}".encode()).hexdigest()

    def get(self, key: str) -> str | None:
        with self._lock:
            entry = self._tokens.get(key)
            if entry is None:
                return None
            token, valid_until = entry
            if self._clock() >= valid_until:
                del self._tokens[key]
                return None
            return token

    def put(self, key: str, token: str, expires_in: float) -> None:
        lifetime = max(expires_in - TOKEN_RENEW_MARGIN_SECONDS, 0.0)
        with self._lock:
            self._tokens[key] = (token, self._clock() + lifetime)

    def discard(self, key: str) -> None:
        with self._lock:
            self._tokens.pop(key, None)

    def clear(self) -> None:
        with self._lock:
            self._tokens.clear()


# Compartida por los canales Gmail del proceso (sincronización y envíos).
SHARED_TOKEN_CACHE = GmailTokenCache()


def _expires_in(body: Mapping[str, Any]) -> float:
    value = body.get("expires_in")
    if isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0:
        return float(value)
    return DEFAULT_TOKEN_SECONDS


class GmailApiError(Exception):
    """Error sanitizado: nunca conserva el cuerpo del proveedor."""

    def __init__(self, status_code: int, code: str = "gmail_api_error") -> None:
        super().__init__(code)
        self.status_code = status_code
        self.code = code


class GmailTransport(Protocol):
    def request(
        self,
        method: str,
        url: str,
        *,
        headers: Mapping[str, str] | None = None,
        params: Mapping[str, Any] | None = None,
        data: Mapping[str, str] | None = None,
        json_body: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]: ...


class HttpGmailTransport:
    def __init__(self, timeout_seconds: float = 10) -> None:
        self._client = httpx.Client(timeout=timeout_seconds)

    def request(
        self,
        method: str,
        url: str,
        *,
        headers: Mapping[str, str] | None = None,
        params: Mapping[str, Any] | None = None,
        data: Mapping[str, str] | None = None,
        json_body: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        try:
            response = self._client.request(
                method,
                url,
                headers=dict(headers or {}),
                params=dict(params or {}),
                data=dict(data or {}),
                json=json_body,
            )
            response.raise_for_status()
            body = response.json()
        except httpx.HTTPStatusError as exc:
            raise GmailApiError(exc.response.status_code) from None
        except (httpx.HTTPError, ValueError) as exc:
            raise GmailApiError(502, type(exc).__name__) from None
        if not isinstance(body, dict):
            raise GmailApiError(502, "invalid_gmail_response")
        return body


class GmailApiClient:
    def __init__(
        self,
        credentials: Mapping[str, str],
        transport: GmailTransport,
        token_cache: GmailTokenCache | None = None,
    ) -> None:
        self._client_id = credentials.get("client_id", "")
        self._client_secret = credentials.get("client_secret", "")
        self._refresh_token = credentials.get("refresh_token", "")
        if not all((self._client_id, self._client_secret, self._refresh_token)):
            raise ChannelNotConfigured("Faltan credenciales OAuth del canal Gmail.")
        self._transport = transport
        self._access_token: str | None = None
        self._tokens = token_cache if token_cache is not None else GmailTokenCache()
        self._token_key = GmailTokenCache.key(self._client_id, self._refresh_token)

    def _refresh(self) -> str:
        body = self._transport.request(
            "POST",
            OAUTH_TOKEN_URL,
            data={
                "client_id": self._client_id,
                "client_secret": self._client_secret,
                "refresh_token": self._refresh_token,
                "grant_type": "refresh_token",
            },
        )
        token = body.get("access_token")
        if not isinstance(token, str) or not token:
            raise GmailApiError(502, "oauth_token_missing")
        self._access_token = token
        self._tokens.put(self._token_key, token, _expires_in(body))
        return token

    def _token(self) -> str:
        if self._access_token is None:
            self._access_token = self._tokens.get(self._token_key)
        return self._access_token or self._refresh()

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: Mapping[str, Any] | None = None,
        json_body: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        token = self._token()
        try:
            return self._transport.request(
                method,
                f"{GMAIL_API}/{path.lstrip('/')}",
                headers={"Authorization": f"Bearer {token}"},
                params=params,
                json_body=json_body,
            )
        except GmailApiError as exc:
            if exc.status_code != 401:
                raise
            # Token revocado o vencido antes de tiempo: se pide otro una vez.
            self._tokens.discard(self._token_key)
            token = self._refresh()
            return self._transport.request(
                method,
                f"{GMAIL_API}/{path.lstrip('/')}",
                headers={"Authorization": f"Bearer {token}"},
                params=params,
                json_body=json_body,
            )

    def profile(self) -> dict[str, Any]:
        return self._request("GET", "profile")

    def history(self, start_history_id: str, page_token: str | None = None) -> dict[str, Any]:
        params = {
            "startHistoryId": start_history_id,
            "historyTypes": "messageAdded",
        }
        if page_token:
            params["pageToken"] = page_token
        return self._request("GET", "history", params=params)

    def get_message(self, message_id: str) -> dict[str, Any]:
        return self._request(
            "GET", f"messages/{quote(message_id, safe='')}", params={"format": "full"}
        )

    def get_thread(self, thread_id: str) -> dict[str, Any]:
        """Solo las cabeceras que necesita una respuesta: sin cuerpos ni adjuntos."""
        return self._request(
            "GET",
            f"threads/{quote(thread_id, safe='')}",
            params={"format": "metadata", "metadataHeaders": list(REPLY_HEADERS)},
        )

    def send_reply(self, thread_id: str, sender: str, text: str) -> None:
        thread = self.get_thread(thread_id)
        messages = thread.get("messages")
        if not isinstance(messages, list):
            raise GmailApiError(502, "invalid_gmail_thread")
        own_address = sender.casefold()
        latest_external: dict[str, Any] | None = None
        for message in messages:
            if not isinstance(message, dict):
                continue
            headers = _headers(message)
            from_address = parseaddr(headers.get("from", ""))[1]
            if from_address and from_address.casefold() != own_address:
                latest_external = message
        if latest_external is None:
            raise GmailApiError(422, "gmail_reply_recipient_missing")
        source_headers = _headers(latest_external)
        recipient = parseaddr(source_headers.get("from", ""))[1]
        message_id = source_headers.get("message-id", "")
        if not recipient or not message_id:
            raise GmailApiError(422, "gmail_reply_headers_missing")
        original_subject = source_headers.get("subject", "")
        mime = EmailMessage()
        mime["To"] = recipient
        mime["Subject"] = original_subject
        mime["In-Reply-To"] = message_id
        references = source_headers.get("references", "").strip()
        mime["References"] = f"{references} {message_id}".strip()
        mime.set_content(text)
        raw = base64.urlsafe_b64encode(mime.as_bytes()).decode("ascii").rstrip("=")
        self._request(
            "POST",
            "messages/send",
            json_body={"raw": raw, "threadId": thread_id},
        )


def _headers(message: Mapping[str, Any]) -> dict[str, str]:
    payload = message.get("payload")
    raw_headers = payload.get("headers", []) if isinstance(payload, dict) else []
    if not isinstance(raw_headers, list):
        return {}
    return {
        str(item.get("name", "")).casefold(): str(item.get("value", ""))
        for item in raw_headers
        if isinstance(item, dict) and item.get("name")
    }


def _decode_body(data: str) -> str:
    padding = "=" * (-len(data) % 4)
    try:
        return base64.urlsafe_b64decode(data + padding).decode("utf-8", errors="replace")
    except (ValueError, TypeError):
        return ""


def plain_text_body(payload: Mapping[str, Any]) -> str | None:
    """Devuelve solo partes text/plain; nunca descarga adjuntos ni HTML."""
    found: list[str] = []
    stack: list[Mapping[str, Any]] = [payload]
    while stack:
        part = stack.pop()
        mime_type = part.get("mimeType")
        filename = part.get("filename")
        body = part.get("body")
        data = body.get("data") if isinstance(body, dict) else None
        if mime_type == "text/plain" and not filename and isinstance(data, str):
            text = _decode_body(data).strip()
            if text:
                found.append(text)
        children = part.get("parts")
        if isinstance(children, list):
            stack.extend(child for child in children if isinstance(child, dict))
    return "\n\n".join(reversed(found)) or None


def added_message_ids(history: Mapping[str, Any]) -> list[str]:
    """Extrae IDs únicos de eventos messageAdded, preservando su orden."""
    result: list[str] = []
    seen: set[str] = set()
    records = history.get("history", [])
    if not isinstance(records, list):
        return result
    for item in records:
        if not isinstance(item, dict):
            continue
        additions = item.get("messagesAdded", [])
        if not isinstance(additions, list):
            continue
        for addition in additions:
            message = addition.get("message") if isinstance(addition, dict) else None
            message_id = message.get("id") if isinstance(message, dict) else None
            if isinstance(message_id, str) and message_id not in seen:
                result.append(message_id)
                seen.add(message_id)
    return result
