"""Utilidades puras del aviso de privacidad, el consentimiento y los textos fijos."""
from __future__ import annotations

import hashlib
import hmac
import re
import secrets
import threading
from dataclasses import dataclass

PRIVACY_ACCEPT_BUTTON = "privacy.accept"
PRIVACY_REJECT_BUTTON = "privacy.reject"
PRIVACY_BUTTON_IDS = (PRIVACY_ACCEPT_BUTTON, PRIVACY_REJECT_BUTTON)

CONSENT_ACCEPT_LABEL = "Acepto"
CONSENT_REJECT_LABEL = "No acepto"


@dataclass(frozen=True)
class ConversationTexts:
    """Textos del flujo administrados desde el panel (#37).

    Los valores vacíos significan «no configurado»; el orquestador no inventa
    textos legales y falla cerrado si falta el aviso o su versión.
    """

    notice_text: str = ""
    notice_version: str = ""
    greeting: str = ""
    accepted_reply: str = ""
    rejected_reply: str = ""
    login_reminder: str = ""
    suspended_reply: str = ""
    unsupported_reply: str = ""
    active_welcome: str = ""
    confirm_button_reply: str = ""
    login_link_label: str = ""
    session_closed_reply: str = ""
    expiry_notice: str = ""
    out_of_hours_reply: str = ""
    closing_reply: str = ""
    topics_list: str = ""


CONVERSATION_TEXT_FIELDS = tuple(ConversationTexts.__dataclass_fields__)

_SETTING_PREFIX = "conversation_texts."


def conversation_text_key(field: str) -> str:
    return f"{_SETTING_PREFIX}{field}"


def parse_conversation_texts(values: dict[str, str]) -> ConversationTexts:
    """Construye el bloque a partir de las claves de `app_settings`."""
    return ConversationTexts(
        **{
            field: values.get(conversation_text_key(field), "")
            for field in CONVERSATION_TEXT_FIELDS
        }
    )


def conversation_text_settings(
    texts: ConversationTexts,
) -> dict[str, str]:
    return {
        conversation_text_key(field): getattr(texts, field)
        for field in CONVERSATION_TEXT_FIELDS
    }


def normalize_privacy_text(text: str) -> str:
    """Minúsculas y espacios colapsados para comparar el aviso y la frase de aceptación."""
    return " ".join(text.split()).casefold()


def notice_sha256(text: str) -> str:
    """SHA-256 hexadecimal del aviso en UTF-8, como prueba del texto mostrado."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


BUTTON_PROOF_LENGTH = 32


def consent_button_proof(
    secret: str,
    channel: str,
    external_user_id: str,
    external_chat_id: str,
    button_id: str,
    notice_version: str,
    notice_sha: str,
    nonce: str = "",
) -> str:
    """R37, R38, R39, R40: prueba HMAC ligada al chat que recibió el aviso.

    Liga botón, identidad/canal, chat receptor, versión/hash y nonce. El nonce
    aleatorio hace que cada presentación del aviso tenga una prueba distinta.
    Se trunca a 32 hex para que `callback_data` quepa en los 64 bytes de
    Telegram. No contiene datos personales en claro.
    """
    message = (
        f"{channel}:{external_user_id}:{external_chat_id}:{button_id}:"
        f"{notice_version}:{notice_sha}:{nonce}"
    ).encode("utf-8")
    return hmac.new(
        secret.encode("utf-8"), message, hashlib.sha256
    ).hexdigest()[:BUTTON_PROOF_LENGTH]


def is_current_button_proof(
    proof: str | None,
    secret: str,
    channel: str,
    external_user_id: str,
    external_chat_id: str,
    button_id: str,
    notice_version: str,
    notice_sha: str,
    nonce: str = "",
) -> bool:
    """R37: solo una prueba autenticada de la identidad, chat y versión actuales vale."""
    if not proof:
        return False
    expected = consent_button_proof(
        secret,
        channel,
        external_user_id,
        external_chat_id,
        button_id,
        notice_version,
        notice_sha,
        nonce,
    )
    return hmac.compare_digest(proof, expected)


@dataclass(frozen=True)
class ConsentChallenge:
    """R39, R40: desafío efímero de una sola presentación del aviso."""

    notice_version: str
    notice_sha256: str
    nonce: str
    external_chat_id: str = ""


class ConsentChallengeStore:
    """R39: guarda en memoria el desafío pendiente por identidad de canal.

    `consume` comprueba y elimina el desafío bajo el mismo candado, de modo que
    dos clics simultáneos nunca registran dos decisiones.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._pending: dict[tuple[str, str], ConsentChallenge] = {}

    def register(
        self,
        channel: str,
        external_user_id: str,
        external_chat_id: str,
        notice_version: str,
        notice_sha: str,
    ) -> ConsentChallenge:
        challenge = ConsentChallenge(
            notice_version=notice_version,
            notice_sha256=notice_sha,
            nonce=secrets.token_hex(16),
            external_chat_id=external_chat_id,
        )
        with self._lock:
            self._pending[(channel, external_user_id)] = challenge
        return challenge

    def get(self, channel: str, external_user_id: str) -> ConsentChallenge | None:
        with self._lock:
            return self._pending.get((channel, external_user_id))

    def discard(self, channel: str, external_user_id: str) -> None:
        with self._lock:
            self._pending.pop((channel, external_user_id), None)

    def consume(
        self,
        channel: str,
        external_user_id: str,
        external_chat_id: str,
        *,
        button_id: str,
        proof: str | None,
        secret: str,
        notice_version: str,
        notice_sha: str,
    ) -> bool:
        """R39, R40: valida y consume atómicamente el desafío de esta presentación."""
        key = (channel, external_user_id)
        with self._lock:
            challenge = self._pending.get(key)
            if challenge is None or not proof:
                return False
            if (
                challenge.notice_version != notice_version
                or challenge.notice_sha256 != notice_sha
                or challenge.external_chat_id != external_chat_id
            ):
                return False
            expected = consent_button_proof(
                secret,
                channel,
                external_user_id,
                external_chat_id,
                button_id,
                notice_version,
                notice_sha,
                challenge.nonce,
            )
            if not hmac.compare_digest(proof, expected):
                return False
            del self._pending[key]
            return True


def is_acceptance(text: str, phrase: str) -> bool:
    """R12 de #35: la aceptación es igualdad normalizada, no contención."""
    if not phrase.strip():
        return False
    return normalize_privacy_text(text) == normalize_privacy_text(phrase)


def is_acceptance_affirmation(text: str, phrase: str) -> bool:
    """R6: un «sí» textual no concede consentimiento, solo pide usar el botón."""
    normalized = normalize_privacy_text(text)
    if not normalized:
        return False
    if phrase.strip() and normalized == normalize_privacy_text(phrase):
        return True
    cleaned = " ".join(re.sub(r"[^\wáéíóúñ ]", " ", normalized).split())
    return cleaned in {"si", "sí", "si acepto", "sí acepto", "acepto", "claro"} or (
        cleaned.startswith(("si acepto", "sí acepto", "acepto"))
    )
