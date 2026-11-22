"""Cifrado autenticado de secretos y credenciales de canales con Fernet."""
from __future__ import annotations

import json
from typing import Literal

from cryptography.fernet import Fernet, InvalidToken

from .domain import ChannelSecrets, ChannelSecretsUnavailable


class SecretCipher:
    def __init__(self, key: str) -> None:
        self.status: Literal["ok", "missing", "invalid"]
        self._fernet: Fernet | None = None
        if not key:
            self.status = "missing"
            return
        try:
            self._fernet = Fernet(key.encode("ascii"))
        except (UnicodeEncodeError, TypeError, ValueError):
            self.status = "invalid"
            return
        self.status = "ok"

    @property
    def available(self) -> bool:
        return self._fernet is not None

    def encrypt(self, secrets: ChannelSecrets) -> str:
        if self._fernet is None:
            raise ChannelSecretsUnavailable("Los secretos del canal no están disponibles.")
        payload = {
            "secret": secrets.secret,
            "credentials": dict(secrets.credentials),
        }
        try:
            raw = json.dumps(
                payload, ensure_ascii=False, separators=(",", ":"), allow_nan=False
            ).encode("utf-8")
            return self._fernet.encrypt(raw).decode("ascii")
        except (TypeError, ValueError, UnicodeEncodeError) as exc:
            raise ChannelSecretsUnavailable(
                "Los secretos del canal no están disponibles."
            ) from exc

    def decrypt(self, token: str) -> ChannelSecrets:
        if self._fernet is None:
            raise ChannelSecretsUnavailable("Los secretos del canal no están disponibles.")
        try:
            raw = self._fernet.decrypt(token.encode("ascii"))
            payload = json.loads(raw.decode("utf-8"))
        except (InvalidToken, UnicodeDecodeError, UnicodeEncodeError, TypeError, ValueError) as exc:
            raise ChannelSecretsUnavailable(
                "Los secretos del canal no están disponibles."
            ) from exc
        if not isinstance(payload, dict) or set(payload) != {"secret", "credentials"}:
            raise ChannelSecretsUnavailable("Los secretos del canal no están disponibles.")
        secret = payload["secret"]
        credentials = payload["credentials"]
        if (secret is not None and not isinstance(secret, str)) or not isinstance(
            credentials, dict
        ):
            raise ChannelSecretsUnavailable("Los secretos del canal no están disponibles.")
        if any(
            not isinstance(name, str) or not isinstance(value, str)
            for name, value in credentials.items()
        ):
            raise ChannelSecretsUnavailable("Los secretos del canal no están disponibles.")
        return ChannelSecrets(secret=secret, credentials=credentials)

    def __repr__(self) -> str:
        return f"SecretCipher(status={self.status!r})"
