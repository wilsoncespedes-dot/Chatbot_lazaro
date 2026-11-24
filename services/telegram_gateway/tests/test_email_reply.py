"""Respuesta de correo sin cita ni firma: el bot ve solo lo que escribió el cliente."""
from __future__ import annotations

import base64
from datetime import datetime, timezone

import pytest

from telegram_gateway.adapters.channels.gmail import GmailChannel
from telegram_gateway.adapters.email_reply import latest_reply_text

NOTICE_QUOTE = (
    "> Antes de continuar, lee el aviso de privacidad.\n"
    "> Para aceptar, responde ACEPTO. Para rechazar, responde NO ACEPTO.\n"
)


@pytest.mark.parametrize(
    "body",
    [
        # Gmail en español: la atribución larga se parte en dos líneas.
        "Acepto\n\nEl lun, 23 nov 2026 a las 18:45, Soporte Lázaro (<soporte@example.com>)\n"
        "escribió:\n\n" + NOTICE_QUOTE,
        # Gmail en inglés, atribución en una línea.
        "Acepto\r\n\r\nOn Mon, Nov 23, 2026 at 6:45 PM Soporte <soporte@example.com> wrote:\r\n"
        + NOTICE_QUOTE,
        # Solo la cita con «>».
        "Acepto\n" + NOTICE_QUOTE,
        # Outlook: bloque de cabeceras.
        "Acepto\n\nDe: Soporte Lázaro <soporte@example.com>\nEnviado: lunes, 23 de noviembre\n"
        "Para: cliente@example.com\nAsunto: Hola\n\nAntes de continuar…",
        "Acepto\n\n-----Mensaje original-----\nDe: Soporte\nAntes de continuar…",
        "Acepto\n\n________________________________\nFrom: Soporte\nSent: Monday",
        # Firmas.
        "Acepto\n\nEnviado desde mi iPhone",
        "Acepto\n-- \nAna Pérez\nGerente",
    ],
)
def test_reply_keeps_only_the_new_text(body):
    assert latest_reply_text(body) == "Acepto"


def test_message_without_quote_is_unchanged():
    body = "Hola,\n\nmi impresora no imprime.\nEl modelo es X200.\n\nGracias"
    assert latest_reply_text(body) == body


def test_multi_paragraph_reply_keeps_all_its_paragraphs():
    body = (
        "Hola, quiero saber el precio.\n\nTambién el horario.\n\n"
        "El mar, 24 nov 2026 a las 9:00, Soporte <soporte@example.com> escribió:\n"
        "> Cuéntanos en qué te ayudamos."
    )
    assert latest_reply_text(body) == "Hola, quiero saber el precio.\n\nTambién el horario."


def test_body_that_is_all_quote_is_kept_whole():
    """Sin texto propio (p. ej. un reenvío) no se pierde el mensaje."""
    body = "> línea citada\n> otra línea"
    assert latest_reply_text(body) == body


def test_sentence_starting_with_el_is_not_an_attribution():
    body = "El pedido no llegó.\nEl número es 123."
    assert latest_reply_text(body) == body


def _encoded(text: str) -> str:
    return base64.urlsafe_b64encode(text.encode()).decode().rstrip("=")


def test_gmail_channel_delivers_only_the_reply_text():
    """La respuesta «Acepto» con el aviso citado llega al orquestador como «Acepto»."""
    channel = GmailChannel(
        "soporte-gmail",
        "soporte@example.com",
        client=object(),
        clock=lambda: datetime(2026, 11, 23, tzinfo=timezone.utc),
    )
    body = (
        "Acepto\n\nEl lun, 23 nov 2026 a las 18:45, Soporte (<soporte@example.com>)\n"
        "escribió:\n\n" + NOTICE_QUOTE
    )
    message = channel.recibir_mensaje({
        "id": "m-2",
        "threadId": "t-1",
        "internalDate": "1795470000000",
        "payload": {
            "mimeType": "text/plain",
            "headers": [
                {"name": "From", "value": "Cliente <cliente@example.com>"},
                {"name": "Subject", "value": "Re: Hola"},
            ],
            "body": {"data": _encoded(body)},
        },
    })
    assert message is not None
    assert message.text == "Acepto"
    assert message.external_chat_id == "t-1"
