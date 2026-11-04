"""Lógica pura de WhatsApp Cloud API (sin IO): firma, webhook, cuerpos y errores."""
from __future__ import annotations

import hashlib
import hmac
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Mapping, Sequence, cast

from lazaro_contracts import (
    MAX_LIST_OPTIONS,
    MAX_OPTION_COUNT,
    MIN_LIST_OPTIONS,
    DeliveryStatus,
    LinkBlock,
    ListBlock,
    NormalizedMessage,
    OptionsBlock,
    ResponseBlock,
    TemplateBlock,
    TextBlock,
)
from pydantic import ValidationError

from .adapters.telegram import render_blocks
from .domain import (
    ChannelSendFailed,
    ChannelWindowClosed,
    TemplateNotApproved,
)

logger = logging.getLogger(__name__)

SIGNATURE_HEADER = "X-Hub-Signature-256"
WINDOW_CLOSED_CODES: frozenset[int] = frozenset({131047})
TEMPLATE_ERROR_CODES: frozenset[int] = frozenset(
    {132000, 132001, 132005, 132007, 132012, 132015, 132016}
)
MAX_REPLY_ID_LENGTH = 256
MAX_INTERACTIVE_BODY = 1024
WHATSAPP_OBJECT = "whatsapp_business_account"


def _sha256_hex(app_secret: str, body: bytes) -> str:
    return hmac.new(app_secret.encode("utf-8"), body, hashlib.sha256).hexdigest()


def verify_signature(app_secret: str, body: bytes, header: str | None) -> bool:
    """R12, R13: compara la firma sobre los bytes crudos en tiempo constante."""
    if not app_secret or not header or not header.startswith("sha256="):
        return False
    received = header[len("sha256=") :]
    if not received:
        return False
    expected = _sha256_hex(app_secret, body)
    return hmac.compare_digest(received.lower(), expected)


def verify_subscription(params: Mapping[str, str], verify_token: str) -> str | None:
    """R8, R9: devuelve el challenge si la verificación GET es válida."""
    mode = params.get("hub.mode")
    token = params.get("hub.verify_token")
    challenge = params.get("hub.challenge")
    if mode != "subscribe" or not verify_token or token is None or not challenge:
        return None
    if not hmac.compare_digest(token, verify_token):
        return None
    return challenge


@dataclass(frozen=True)
class CloudStatus:
    wamid: str
    status: str
    error_codes: tuple[int, ...]


@dataclass(frozen=True)
class CloudWebhook:
    messages: tuple[NormalizedMessage, ...]
    inbound_wa_ids: tuple[str, ...]
    statuses: tuple[CloudStatus, ...]
    discarded: int


def split_button_id(raw: str) -> tuple[str, str | None]:
    """R17, R18: separa `<button_id>[:<proof>]` por el primer `:`."""
    button_id, separator, proof = raw.partition(":")
    return button_id, proof if separator and proof else None


def _as_text(value: Any) -> str | None:
    if isinstance(value, str) and value:
        return value
    return None


def _message_button_id(message: dict) -> str | None:
    message_type = message.get("type")
    if message_type == "interactive":
        interactive = message.get("interactive")
        if not isinstance(interactive, dict):
            return None
        for key in ("button_reply", "list_reply"):
            reply = interactive.get(key)
            if isinstance(reply, dict):
                value = _as_text(reply.get("id"))
                if value is not None:
                    return value
        return None
    if message_type == "button":
        button = message.get("button")
        if isinstance(button, dict):
            return _as_text(button.get("payload"))
    return None


def normalize_message(
    message: object, received_at: datetime
) -> NormalizedMessage | None:
    """Traduce un objeto `message` de Meta; None si es inválido o reacción."""
    if not isinstance(message, dict):
        return None
    message_type = message.get("type")
    if message_type == "reaction":
        return None
    sender = _as_text(message.get("from"))
    message_id = _as_text(message.get("id"))
    if sender is None or message_id is None:
        return None
    try:
        if message_type == "text":
            text = message.get("text")
            body = _as_text(text.get("body")) if isinstance(text, dict) else None
            if body is None or not body.strip():
                return None
            return NormalizedMessage(
                channel="whatsapp",
                external_user_id=sender,
                external_chat_id=sender,
                external_message_id=message_id,
                kind="text",
                text=body,
                received_at=received_at,
            )
        if message_type in ("interactive", "button"):
            raw_id = _message_button_id(message)
            if raw_id is None:
                return None
            button_id, proof = split_button_id(raw_id)
            return NormalizedMessage(
                channel="whatsapp",
                external_user_id=sender,
                external_chat_id=sender,
                external_message_id=message_id,
                kind="button",
                button_id=button_id,
                button_proof=proof,
                received_at=received_at,
            )
        return NormalizedMessage(
            channel="whatsapp",
            external_user_id=sender,
            external_chat_id=sender,
            external_message_id=message_id,
            kind="unsupported",
            text=None,
            received_at=received_at,
        )
    except ValidationError:
        return None


def parse_webhook(
    payload: object, phone_number_id: str, received_at: datetime
) -> CloudWebhook:
    """R14-R22, R47, R51, R52: filtra cambios y normaliza el lote en orden."""
    messages: list[NormalizedMessage] = []
    inbound: list[str] = []
    statuses: list[CloudStatus] = []
    discarded = 0
    if not isinstance(payload, dict) or payload.get("object") != WHATSAPP_OBJECT:
        return CloudWebhook((), (), (), 0)
    entries = payload.get("entry")
    if not isinstance(entries, list):
        return CloudWebhook((), (), (), 0)
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        changes = entry.get("changes")
        if not isinstance(changes, list):
            continue
        for change in changes:
            if not isinstance(change, dict) or change.get("field") != "messages":
                continue
            value = change.get("value")
            if not isinstance(value, dict):
                continue
            metadata = value.get("metadata")
            if not isinstance(metadata, dict):
                continue
            if metadata.get("phone_number_id") != phone_number_id:
                continue
            raw_messages = value.get("messages")
            if isinstance(raw_messages, list):
                for raw in raw_messages:
                    if not isinstance(raw, dict):
                        discarded += 1
                        continue
                    sender = _as_text(raw.get("from"))
                    if sender is not None:
                        inbound.append(sender)
                    normalized = normalize_message(raw, received_at)
                    if normalized is None:
                        if raw.get("type") != "reaction":
                            discarded += 1
                        continue
                    messages.append(normalized)
            raw_statuses = value.get("statuses")
            if isinstance(raw_statuses, list):
                for raw in raw_statuses:
                    if not isinstance(raw, dict):
                        continue
                    codes: list[int] = []
                    errors = raw.get("errors")
                    if isinstance(errors, list):
                        for error in errors:
                            if not isinstance(error, dict):
                                continue
                            code = error.get("code")
                            if isinstance(code, int) and not isinstance(code, bool):
                                codes.append(code)
                    statuses.append(
                        CloudStatus(
                            wamid=_as_text(raw.get("id")) or "",
                            status=_as_text(raw.get("status")) or "",
                            error_codes=tuple(codes),
                        )
                    )
    return CloudWebhook(
        messages=tuple(messages),
        inbound_wa_ids=tuple(inbound),
        statuses=tuple(statuses),
        discarded=discarded,
    )


def _text_payload(destination: str, text: str, *, preview_url: bool) -> dict:
    return {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": destination,
        "type": "text",
        "text": {"body": text, "preview_url": preview_url},
    }


def _base_payload(destination: str, message_type: str) -> dict:
    return {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": destination,
        "type": message_type,
    }


def _template_payload(
    destination: str, block: TemplateBlock, template_language: str
) -> dict:
    template: dict = {
        "name": block.name,
        "language": {"code": template_language},
    }
    if block.variables:
        template["components"] = [
            {
                "type": "body",
                "parameters": [
                    {"type": "text", "text": variable} for variable in block.variables
                ],
            }
        ]
    payload = _base_payload(destination, "template")
    payload["template"] = template
    return payload


def _interactive_payload(
    destination: str, block: OptionsBlock, body_text: str
) -> dict:
    option_ids = block.option_ids or []
    proofs = block.option_proofs or [None for _ in option_ids]
    buttons: list[dict] = []
    for label, option_id, proof in zip(block.options, option_ids, proofs):
        reply_id = option_id if not proof else f"{option_id}:{proof}"
        if len(reply_id) > MAX_REPLY_ID_LENGTH:
            raise ChannelSendFailed("La opción no cabe en el límite de WhatsApp.")
        buttons.append(
            {
                "type": "reply",
                "reply": {"id": reply_id, "title": label},
            }
        )
    payload = _base_payload(destination, "interactive")
    payload["interactive"] = {
        "type": "button",
        "body": {"text": body_text},
        "action": {"buttons": buttons},
    }
    return payload


def build_send_payloads(
    destination: str,
    blocks: Sequence[ResponseBlock],
    template_language: str,
    interactive_body_text: str,
) -> list[dict]:
    """R32-R40, R54, R55: un cuerpo de Meta por bloque (con la fusión de R37)."""
    block_list = list(blocks)
    payloads: list[dict] = []
    for index, block in enumerate(block_list):
        if isinstance(block, TextBlock):
            following = block_list[index + 1] if index + 1 < len(block_list) else None
            if (
                isinstance(following, OptionsBlock)
                and following.option_ids is not None
                and len(block.text) <= MAX_INTERACTIVE_BODY
            ):
                # R37, R54: este texto será el cuerpo interactivo, no un envío aparte.
                continue
            payloads.append(_text_payload(destination, block.text, preview_url=False))
        elif isinstance(block, OptionsBlock):
            if block.option_ids is None:
                payloads.append(
                    _text_payload(
                        destination, render_blocks([block]), preview_url=False
                    )
                )
                continue
            previous = block_list[index - 1] if index > 0 else None
            if (
                isinstance(previous, TextBlock)
                and len(previous.text) <= MAX_INTERACTIVE_BODY
            ):
                body_text = previous.text
            else:
                body_text = interactive_body_text
            payloads.append(_interactive_payload(destination, block, body_text))
        elif isinstance(block, TemplateBlock):
            payloads.append(
                _template_payload(destination, block, template_language)
            )
        elif isinstance(block, LinkBlock):
            payloads.append(
                _text_payload(
                    destination, render_blocks([block]), preview_url=True
                )
            )
        elif isinstance(block, ListBlock):
            payloads.append(
                _text_payload(destination, render_blocks([block]), preview_url=False)
            )
    return payloads


def _error_details(body: object) -> tuple[int | None, int | None, str | None]:
    if not isinstance(body, dict):
        return None, None, None
    error = body.get("error")
    if not isinstance(error, dict):
        return None, None, None
    code = error.get("code")
    subcode = error.get("error_subcode")
    fbtrace_id = error.get("fbtrace_id")
    return (
        code if isinstance(code, int) and not isinstance(code, bool) else None,
        subcode if isinstance(subcode, int) and not isinstance(subcode, bool) else None,
        fbtrace_id if isinstance(fbtrace_id, str) else None,
    )


def translate_error(status_code: int, body: object) -> Exception:
    """R43-R46, R59: traduce la respuesta de Meta sin filtrar su cuerpo."""
    code, subcode, fbtrace_id = _error_details(body)
    if status_code == 401 or code == 190:
        logger.error(
            "whatsapp_auth_error status=%s code=%s error_subcode=%s fbtrace_id=%s",
            status_code,
            code,
            subcode,
            fbtrace_id,
        )
    else:
        logger.error(
            "whatsapp_error status=%s code=%s error_subcode=%s fbtrace_id=%s",
            status_code,
            code,
            subcode,
            fbtrace_id,
        )
    if code in WINDOW_CLOSED_CODES:
        return ChannelWindowClosed(
            "La ventana de atención de WhatsApp está cerrada."
        )
    if code in TEMPLATE_ERROR_CODES:
        return TemplateNotApproved(
            "Meta rechazó la plantilla de WhatsApp."
        )
    return ChannelSendFailed("Meta rechazó el envío de WhatsApp.")


def to_delivery_status(raw: str) -> DeliveryStatus:
    """R48: vocabulario cerrado de estados de entrega."""
    normalized = raw.strip().lower()
    if normalized in ("sent", "delivered", "read", "failed"):
        return cast(DeliveryStatus, normalized)
    return "failed"


def whatsapp_capabilities(*, window_open: bool) -> dict:
    """Capacidades comunes a WhatsApp con la ventana indicada."""
    return {
        "free_text_allowed": window_open,
        "max_options": MAX_OPTION_COUNT,
        "min_list_options": MIN_LIST_OPTIONS,
        "max_list_options": MAX_LIST_OPTIONS,
        "supports_links": True,
        "requires_template": not window_open,
    }
