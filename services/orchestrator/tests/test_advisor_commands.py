"""Tests de los comandos de asesor por Telegram (feature #16)."""
from __future__ import annotations

import inspect
import logging
from datetime import datetime, timezone

import pytest

from orchestrator.adapters.gateway import FakeGatewayClient
from orchestrator.domain import (
    AdvisorCommand,
    MalformedCommand,
    ServiceUnavailable,
    parse_advisor_command,
)

FIXED_NOW = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)


def _link(env, case_id: str = "case-1", user: int = 10, chat: int = 100):
    contact = env.repo.get_or_create_contact(user, chat, FIXED_NOW)
    env.repo.link_case(case_id, contact.id, FIXED_NOW)
    return contact


def _sender_messages(env, user: int = 111):
    contact = env.repo.contacts.get(user)
    if contact is None:
        return []
    return [m for m in env.repo.messages if m.contact_id == contact.id]


# --- parse_advisor_command ---------------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "hola",
        "/start",
        "hola /responder case-1 x",
        "responder case-1 x",
        "/responde case-1",
        "   ",
        "",
    ],
)
def test_parse_returns_none_for_non_commands(text):
    """conversacion_cliente_asesor R1: no es intento de comando → None."""
    assert parse_advisor_command(text) is None


@pytest.mark.parametrize(
    ("text", "case_id", "expected_text"),
    [
        ("/responder case-1 hola", "case-1", "hola"),
        ("  /responder   case-1   hola  mundo  ", "case-1", "hola  mundo"),
        ("/responder case-1 línea1\nlínea2", "case-1", "línea1\nlínea2"),
        ("/responder case-1 111 hola", "case-1", "111 hola"),
        ("/responder " + "x" * 64 + " hola", "x" * 64, "hola"),
    ],
)
def test_parse_reply_command(text, case_id, expected_text):
    """conversacion_cliente_asesor R2: /responder <case_id> <texto>."""
    assert parse_advisor_command(text) == AdvisorCommand("reply", case_id, expected_text)


@pytest.mark.parametrize("text", ["/cerrar case-1", "  /cerrar   case-1  "])
def test_parse_close_command(text):
    """conversacion_cliente_asesor R3: /cerrar <case_id>."""
    assert parse_advisor_command(text) == AdvisorCommand("close", "case-1", None)


@pytest.mark.parametrize(
    "text",
    [
        "/responder",
        "/responder case-1",
        "/responder   case-1   ",
        "/cerrar",
        "/cerrar case-1 ya",
        "/Responder case-1 hola",
        "/CERRAR case-1",
        "/responder@LazaroBot case-1 hola",
        "/cerrarlo case-1",
        "/responder " + "x" * 65 + " hola",
        "/cerrar " + "x" * 65,
    ],
)
def test_parse_malformed_commands(text):
    """conversacion_cliente_asesor R4: intento de comando con forma inválida."""
    assert parse_advisor_command(text) == MalformedCommand()


def test_parse_advisor_command_is_pure():
    """conversacion_cliente_asesor R5: solo recibe el texto y no usa adaptadores."""
    assert list(inspect.signature(parse_advisor_command).parameters) == ["text"]
    assert parse_advisor_command("/cerrar case-1") == parse_advisor_command("/cerrar case-1")
    source = inspect.getsource(parse_advisor_command)
    for name in ("adapters", "settings", "clock", "logger"):
        assert name not in source


# --- Enrutado de comandos ----------------------------------------------------------------


def _setup_command(env, mode: str) -> str:
    if mode == "reply_ok":
        return "/responder case-1 quiero un asesor"
    if mode == "reply_forbidden":
        env.handover.authorize_error = "forbidden"
        return "/responder case-1 quiero un asesor"
    if mode == "close_ok":
        return "/cerrar case-1"
    if mode == "close_forbidden":
        env.handover.authorize_error = "forbidden"
        return "/cerrar case-1"
    if mode == "fail_authorize":
        env.handover.fail_authorize = True
        return "/responder case-1 quiero un asesor"
    return "/cerrar case-1 ya quiero un asesor"


@pytest.mark.parametrize(
    "mode",
    [
        "reply_ok",
        "reply_forbidden",
        "close_ok",
        "close_forbidden",
        "fail_authorize",
        "malformed",
    ],
)
def test_command_never_calls_rag_llm_or_handover_request(env, mode):
    """conversacion_cliente_asesor R6: un comando nunca pasa por RAG, LLM ni /handover."""
    text = _setup_command(env, mode)
    env.post(text=text, user=111, chat=111)
    assert env.rag.calls == []
    assert env.llm.calls == []
    assert env.handover.requests == []


@pytest.mark.parametrize(
    "mode",
    [
        "reply_ok",
        "reply_forbidden",
        "close_ok",
        "close_forbidden",
        "fail_authorize",
        "malformed",
    ],
)
def test_command_message_is_not_stored_in_sender_history(env, mode):
    """conversacion_cliente_asesor R7: el comando no se guarda en el historial del remitente."""
    text = _setup_command(env, mode)
    env.post(text=text, user=111, chat=111)
    assert _sender_messages(env, 111) == []


def test_command_from_client_with_assigned_case_is_not_forwarded(env):
    """conversacion_cliente_asesor R8: un comando nunca se reenvía como mensaje de cliente."""
    _link(env)
    env.handover.client_message_status = "forwarded"
    env.handover.authorize_error = "forbidden"
    env.post(text="/cerrar case-1", user=10, chat=100)
    assert env.handover.client_messages == []
    assert env.gateway.sent == [(100, env.settings.advisor_command_forbidden_reply)]


def test_malformed_command_sends_help_without_calling_handover(env):
    """conversacion_cliente_asesor R9: comando mal formado → ayuda fija, sin handover."""
    env.post(text="/responder case-1", user=111, chat=111)
    assert env.gateway.sent == [(111, env.settings.advisor_command_help)]
    assert env.handover.authorized == []
    assert env.handover.assigned == []
    assert env.handover.closed == []
    assert env.handover.client_messages == []


@pytest.mark.parametrize("user_id", [-1003, 0])
@pytest.mark.parametrize("text", ["/responder case-1 hola", "/cerrar case-1"])
def test_command_from_non_positive_sender_is_forbidden_without_calling_handover(
    env, user_id, text
):
    """conversacion_cliente_asesor R10, R24: id no positivo → texto de no autorizado."""
    env.post(text=text, user=user_id, chat=-1003)
    assert env.gateway.sent == [(-1003, env.settings.advisor_command_forbidden_reply)]
    assert env.handover.authorized == []
    assert env.handover.closed == []
    event = env.repo.events[-1]
    assert (event.type, event.reason) == (
        "advisor_forbidden",
        f"command:{'responder' if text.startswith('/responder') else 'cerrar'} "
        f"case:case-1 advisor:{user_id} code:sender_not_user",
    )


def test_command_uses_sender_telegram_user_id_not_chat_id(env):
    """conversacion_cliente_asesor R11: el advisor_id es el telegram_user_id del remitente."""
    _link(env)
    env.post(text="/responder case-1 hola", user=111, chat=-1003)
    assert env.handover.authorized == [("case-1", "111", "reply")]
    assert env.handover.assigned == [("case-1", "111")]
    assert (-1003, env.settings.advisor_reply_confirmation) in env.gateway.sent

    env.post(text="/cerrar case-1", user=111, chat=-1003, update_id=2)
    assert env.handover.authorized[-1] == ("case-1", "111", "close")
    assert env.handover.closed == [("case-1", "111")]
    assert env.gateway.sent[-1] == (-1003, env.settings.advisor_close_confirmation)


# --- /responder --------------------------------------------------------------------------


def test_responder_runs_reply_to_case_flow(env):
    """conversacion_cliente_asesor R12: /responder tiene los mismos efectos que reply."""
    _link(env)
    env.post(text="/responder case-1 Ya está resuelto", user=111, chat=111)
    assert (100, "Ya está resuelto") in env.gateway.sent
    advisor = [m for m in env.repo.messages if m.role == "advisor"]
    assert [(m.text, m.at) for m in advisor] == [("Ya está resuelto", FIXED_NOW)]
    assert ("advisor_reply", "advisor:111") in env.events()
    assert env.handover.assigned == [("case-1", "111")]


def test_responder_sends_confirmation_to_sender_chat(env):
    """conversacion_cliente_asesor R13: el asesor recibe la confirmación fija."""
    _link(env)
    env.post(text="/responder case-1 Ya está resuelto", user=111, chat=111)
    assert env.gateway.sent[-1] == (111, env.settings.advisor_reply_confirmation)


def test_responder_forbidden_sends_fixed_text(env):
    """conversacion_cliente_asesor R14: 403 de authorize → texto de no autorizado."""
    _link(env)
    env.handover.authorize_error = "forbidden"
    env.post(text="/responder case-1 hola", user=111, chat=111)
    assert env.gateway.sent == [(111, env.settings.advisor_command_forbidden_reply)]
    assert all(chat != 100 for chat, _ in env.gateway.sent)
    assert [m for m in env.repo.messages if m.role == "advisor"] == []
    assert env.handover.assigned == []


@pytest.mark.parametrize(
    "mode", ["not_found", "fail_authorize", "send_failed", "unlinked"]
)
def test_responder_not_found_or_upstream_sends_failed_text(env, mode):
    """conversacion_cliente_asesor R15: caso inexistente o handover caído → texto de fallo."""
    if mode == "not_found":
        _link(env)
        env.handover.authorize_error = "not_found"
    elif mode == "fail_authorize":
        _link(env)
        env.handover.fail_authorize = True
    elif mode == "send_failed":
        _link(env)
        env.gateway.fail_for = {100}
    env.post(text="/responder case-1 hola", user=111, chat=111)
    assert env.gateway.sent[-1] == (111, env.settings.advisor_command_failed_reply)
    assert all(chat != 100 for chat, _ in env.gateway.sent)


# --- /cerrar -----------------------------------------------------------------------------


def test_cerrar_authorizes_before_close(env):
    """conversacion_cliente_asesor R16, R17: authorize(close) se llama antes que close."""
    calls = []
    original_authorize = env.handover.authorize
    original_close = env.handover.close

    def authorize(*args, **kwargs):
        calls.append("authorize")
        return original_authorize(*args, **kwargs)

    def close(*args, **kwargs):
        calls.append("close")
        return original_close(*args, **kwargs)

    env.handover.authorize = authorize
    env.handover.close = close
    env.post(text="/cerrar case-1", user=111, chat=111)
    assert calls == ["authorize", "close"]
    assert env.handover.authorized == [("case-1", "111", "close")]
    assert env.handover.closed == [("case-1", "111")]


def test_cerrar_closes_case_and_notifies_client(env):
    """conversacion_cliente_asesor R17, R18: cierra y avisa al cliente, guardándolo."""
    contact = _link(env)
    env.post(text="/cerrar case-1", user=111, chat=111)
    assert env.handover.closed == [("case-1", "111")]
    assert (100, env.settings.case_closed_reply) in env.gateway.sent
    stored = [
        m for m in env.repo.messages
        if m.contact_id == contact.id and m.role == "bot"
    ]
    assert [(m.text, m.at) for m in stored] == [(env.settings.case_closed_reply, FIXED_NOW)]


def test_cerrar_sends_confirmation_to_sender(env):
    """conversacion_cliente_asesor R19: el asesor recibe la confirmación de cierre."""
    _link(env)
    env.post(text="/cerrar case-1", user=111, chat=111)
    assert env.gateway.sent[-1] == (111, env.settings.advisor_close_confirmation)


def test_cerrar_unlinked_case_logs_and_notifies_nobody(env, caplog):
    """conversacion_cliente_asesor R20: caso sin contacto vinculado → solo log y confirmación."""
    caplog.set_level(logging.DEBUG)
    env.post(text="/cerrar case-x", user=111, chat=111)
    assert env.gateway.sent == [(111, env.settings.advisor_close_confirmation)]
    assert any(
        record.getMessage() == "case_closed_unlinked case_id=case-x"
        for record in caplog.records
    )


@pytest.mark.parametrize("mode", ["authorize_forbidden", "close_forbidden"])
def test_cerrar_forbidden_sends_fixed_text_without_notice(env, mode):
    """conversacion_cliente_asesor R21: 403 → texto de no autorizado, sin aviso al cliente."""
    _link(env)
    if mode == "authorize_forbidden":
        env.handover.authorize_error = "forbidden"
    else:
        env.handover.close_error = "forbidden"
    env.post(text="/cerrar case-1", user=111, chat=111)
    assert env.gateway.sent == [(111, env.settings.advisor_command_forbidden_reply)]


@pytest.mark.parametrize(
    "kwargs",
    [
        {"authorize_error": "forbidden"},
        {"authorize_error": "case_closed"},
        {"authorize_error": "not_found"},
        {"fail_authorize": True},
    ],
)
def test_cerrar_failed_authorize_never_calls_close(env, kwargs):
    """conversacion_cliente_asesor R22: si authorize no da 200, no se llama a close."""
    for key, value in kwargs.items():
        setattr(env.handover, key, value)
    env.post(text="/cerrar case-1", user=111, chat=111)
    assert env.handover.closed == []


@pytest.mark.parametrize(
    "mode", ["not_found", "fail_authorize", "close_not_found", "fail_close"]
)
def test_cerrar_not_found_or_unavailable_sends_failed_text(env, mode):
    """conversacion_cliente_asesor R23: caso inexistente o handover caído → texto de fallo."""
    _link(env)
    if mode == "not_found":
        env.handover.authorize_error = "not_found"
    elif mode == "fail_authorize":
        env.handover.fail_authorize = True
    elif mode == "close_not_found":
        env.handover.close_error = "not_found"
    else:
        env.handover.fail_close = True
    env.post(text="/cerrar case-1", user=111, chat=111)
    assert env.gateway.sent == [(111, env.settings.advisor_command_failed_reply)]


# --- Denegaciones, respuestas y logs -----------------------------------------------------


@pytest.mark.parametrize(
    ("text", "setup", "expected"),
    [
        ("/responder case-1 hola", {"authorize_error": "forbidden"},
         "command:responder case:case-1 advisor:20 code:forbidden"),
        ("/cerrar case-1", {"authorize_error": "forbidden"},
         "command:cerrar case:case-1 advisor:20 code:forbidden"),
        ("/cerrar case-1", {"close_error": "forbidden"},
         "command:cerrar case:case-1 advisor:20 code:forbidden"),
    ],
)
def test_command_denials_record_advisor_forbidden_on_sender(env, text, setup, expected):
    """conversacion_cliente_asesor R24: un 403 deja el evento en el contacto remitente."""
    contact = env.repo.get_or_create_contact(20, 200, FIXED_NOW)
    for key, value in setup.items():
        setattr(env.handover, key, value)
    env.post(text=text, user=20, chat=200)
    events = [
        e for e in env.repo.events
        if e.contact_id == contact.id and e.type == "advisor_forbidden"
    ]
    assert [(e.reason, e.at) for e in events] == [(expected, FIXED_NOW)]


@pytest.mark.parametrize(
    ("text", "setup", "attr"),
    [
        ("/responder case-1", {}, "advisor_command_help"),
        ("/responder case-1 hola", {"authorize_error": "forbidden"},
         "advisor_command_forbidden_reply"),
        ("/responder case-1 hola", {"authorize_error": "not_found"},
         "advisor_command_failed_reply"),
        ("/responder case-1 hola", {"authorize_error": "case_closed"},
         "advisor_command_case_closed_reply"),
        ("/responder case-1 hola", {"link": True}, "advisor_reply_confirmation"),
        ("/cerrar case-1", {"link": True}, "advisor_close_confirmation"),
    ],
)
def test_command_replies_are_not_stored_in_sender_history(env, text, setup, attr):
    """conversacion_cliente_asesor R25: las respuestas fijas al asesor no se guardan."""
    if setup.get("link"):
        _link(env)
    for key, value in setup.items():
        if key != "link":
            setattr(env.handover, key, value)
    env.post(text=text, user=111, chat=111)
    assert (111, getattr(env.settings, attr)) in env.gateway.sent
    assert _sender_messages(env, 111) == []


@pytest.mark.parametrize("mode", ["reply_ok", "reply_forbidden", "fail_authorize", "malformed"])
def test_command_logs_do_not_contain_text(env, caplog, mode):
    """conversacion_cliente_asesor R26: el texto del comando nunca aparece en el log."""
    secret = "SECRETO-CLIENTE-123"
    if mode == "reply_forbidden":
        env.handover.authorize_error = "forbidden"
        text = f"/responder case-1 {secret}"
    elif mode == "fail_authorize":
        env.handover.fail_authorize = True
        text = f"/responder case-1 {secret}"
    elif mode == "malformed":
        text = f"/cerrar case-1 {secret}"
    else:
        text = f"/responder case-1 {secret}"
    caplog.set_level(logging.DEBUG)
    env.post(text=text, user=111, chat=111)
    assert caplog.records
    assert secret not in caplog.text


# --- Fake del gateway --------------------------------------------------------------------


def test_fake_gateway_fail_for_fails_only_listed_chats():
    """conversacion_cliente_asesor R15, R58: fail_for solo afecta a los chats listados."""
    gateway = FakeGatewayClient(fail_for={100})
    with pytest.raises(ServiceUnavailable):
        gateway.send(100, "texto")
    gateway.send(111, "texto")
    assert gateway.sent == [(111, "texto")]

    default = FakeGatewayClient()
    default.send(100, "texto")
    assert default.sent == [(100, "texto")]


# --- Comandos sobre un caso cerrado ------------------------------------------------------


def test_responder_closed_case_sends_case_closed_text(env):
    """conversacion_cliente_asesor R60: 409 case_closed → texto de caso cerrado, sin envío."""
    _link(env)
    env.handover.authorize_error = "case_closed"
    env.post(text="/responder case-1 hola", user=111, chat=111)
    assert env.gateway.sent == [(111, env.settings.advisor_command_case_closed_reply)]
    assert all(chat != 100 for chat, _ in env.gateway.sent)
    assert [m for m in env.repo.messages if m.role == "advisor"] == []
    assert ("advisor_reply", "advisor:111") not in env.events()
    assert env.handover.assigned == []


@pytest.mark.parametrize("mode", ["authorize", "close"])
def test_cerrar_closed_case_sends_case_closed_text_without_notice(env, mode):
    """conversacion_cliente_asesor R61, R22: caso cerrado → texto propio, sin avisos."""
    _link(env)
    if mode == "authorize":
        env.handover.authorize_error = "case_closed"
    else:
        env.handover.close_error = "case_closed"
    env.post(text="/cerrar case-1", user=111, chat=111)
    assert env.gateway.sent == [(111, env.settings.advisor_command_case_closed_reply)]
    assert (100, env.settings.case_closed_reply) not in env.gateway.sent
    assert (111, env.settings.advisor_close_confirmation) not in env.gateway.sent
    if mode == "authorize":
        assert env.handover.closed == []


@pytest.mark.parametrize("mode", ["responder_closed", "cerrar_authorize", "cerrar_close"])
def test_closed_case_commands_record_no_advisor_forbidden(env, caplog, mode):
    """conversacion_cliente_asesor R62: un 409 no registra advisor_forbidden."""
    _link(env)
    if mode == "responder_closed":
        env.handover.authorize_error = "case_closed"
        text = "/responder case-1 hola"
    elif mode == "cerrar_authorize":
        env.handover.authorize_error = "case_closed"
        text = "/cerrar case-1"
    else:
        env.handover.close_error = "case_closed"
        text = "/cerrar case-1"
    caplog.set_level(logging.DEBUG)
    env.post(text=text, user=111, chat=111)
    assert [e for e in env.repo.events if e.type == "advisor_forbidden"] == []
    assert "advisor_forbidden" not in caplog.text
