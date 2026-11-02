"""Tests de agrupación de mensajes consecutivos (#30)."""
from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient
from pydantic import ValidationError

from telegram_gateway.adapters.dedup import FakeDedupStore
from telegram_gateway.adapters.message_buffer import FakeMessageBuffer
from telegram_gateway.adapters.orchestrator import FakeOrchestratorClient
from telegram_gateway.adapters.telegram import FakeTelegramClient
from telegram_gateway.config import Settings
from telegram_gateway.domain import Adapters, BufferedMessage
from telegram_gateway.grouping import GroupingWorker, flush_chat, flush_due
from telegram_gateway.main import create_app

SERVICE_TOKEN = "svc-token"
WEBHOOK_SECRET = "hook-secret"
BOT_TOKEN = "123456:BOT-TOKEN-SECRETO"
FIXED_NOW = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
URL = "/telegram/webhook"
HOOK = {"X-Telegram-Bot-Api-Secret-Token": WEBHOOK_SECRET}
ROOT = Path(__file__).resolve().parents[3]


class FakeClock:
    def __init__(self, now: datetime) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += timedelta(seconds=seconds)


@dataclass
class GroupEnv:
    client: TestClient
    settings: Settings
    clock: FakeClock
    telegram: FakeTelegramClient
    dedup: FakeDedupStore
    orchestrator: FakeOrchestratorClient
    buffer: FakeMessageBuffer | None


def make_env(*, with_buffer: bool = True, **overrides) -> GroupEnv:
    clock = FakeClock(FIXED_NOW)
    settings = Settings(
        service_token=SERVICE_TOKEN,
        telegram_webhook_secret=WEBHOOK_SECRET,
        telegram_bot_token=BOT_TOKEN,
        http_timeout_seconds=10,
        **overrides,
    )
    telegram = FakeTelegramClient()
    dedup = FakeDedupStore()
    orchestrator = FakeOrchestratorClient()
    buffer = FakeMessageBuffer(clock=clock) if with_buffer else None
    adapters = Adapters(telegram, dedup, orchestrator, clock=clock, buffer=buffer)
    return GroupEnv(
        client=TestClient(create_app(settings, adapters)),
        settings=settings,
        clock=clock,
        telegram=telegram,
        dedup=dedup,
        orchestrator=orchestrator,
        buffer=buffer,
    )


def text_update(update_id=1, text="hola", chat_id=77, user_id=55):
    return {
        "update_id": update_id,
        "message": {
            "message_id": 1,
            "from": {"id": user_id},
            "chat": {"id": chat_id},
            "text": text,
        },
    }


def post(env: GroupEnv, **kwargs):
    return env.client.post(URL, json=text_update(**kwargs), headers=HOOK)


def log_text(caplog) -> str:
    return "\n".join(record.getMessage() for record in caplog.records)


# ---------------------------------------------------------------------------
# R1, R2, R3 — configuración
# ---------------------------------------------------------------------------


def test_grouping_settings_defaults(monkeypatch):
    """R1: los valores por defecto son los del design."""
    for name in (
        "MESSAGE_GROUPING_ENABLED",
        "MESSAGE_GROUPING_WINDOW_SECONDS",
        "MESSAGE_GROUPING_MAX_WAIT_SECONDS",
        "MESSAGE_GROUPING_MAX_MESSAGES",
        "MESSAGE_GROUPING_BUFFER_TTL_SECONDS",
        "MESSAGE_GROUPING_LEASE_SECONDS",
        "MESSAGE_GROUPING_MAX_ATTEMPTS",
        "MESSAGE_GROUPING_POLL_SECONDS",
        "MESSAGE_GROUPING_ACCEPT_PHRASE",
        "HTTP_TIMEOUT_SECONDS",
    ):
        monkeypatch.delenv(name, raising=False)
    settings = Settings()
    assert settings.message_grouping_enabled is True
    assert settings.message_grouping_window_seconds == 2.0
    assert settings.message_grouping_max_wait_seconds == 8.0
    assert settings.message_grouping_max_messages == 10
    assert settings.message_grouping_buffer_ttl_seconds == 300
    assert settings.message_grouping_lease_seconds == 30.0
    assert settings.message_grouping_max_attempts == 3
    assert settings.message_grouping_poll_seconds == 0.5
    assert settings.message_grouping_accept_phrase == ""


def test_grouping_settings_read_from_environment(monkeypatch):
    """R1: las variables MESSAGE_GROUPING_* se leen del entorno."""
    monkeypatch.setenv("MESSAGE_GROUPING_ENABLED", "false")
    monkeypatch.setenv("MESSAGE_GROUPING_WINDOW_SECONDS", "3")
    monkeypatch.setenv("MESSAGE_GROUPING_MAX_WAIT_SECONDS", "9")
    monkeypatch.setenv("MESSAGE_GROUPING_MAX_MESSAGES", "4")
    monkeypatch.setenv("MESSAGE_GROUPING_BUFFER_TTL_SECONDS", "400")
    monkeypatch.setenv("MESSAGE_GROUPING_LEASE_SECONDS", "40")
    monkeypatch.setenv("MESSAGE_GROUPING_MAX_ATTEMPTS", "2")
    monkeypatch.setenv("MESSAGE_GROUPING_POLL_SECONDS", "0.2")
    monkeypatch.setenv("MESSAGE_GROUPING_ACCEPT_PHRASE", "acepto")
    monkeypatch.setenv("HTTP_TIMEOUT_SECONDS", "10")
    settings = Settings()
    assert settings.message_grouping_enabled is False
    assert settings.message_grouping_window_seconds == 3
    assert settings.message_grouping_max_wait_seconds == 9
    assert settings.message_grouping_max_messages == 4
    assert settings.message_grouping_buffer_ttl_seconds == 400
    assert settings.message_grouping_lease_seconds == 40
    assert settings.message_grouping_max_attempts == 2
    assert settings.message_grouping_poll_seconds == 0.2
    assert settings.message_grouping_accept_phrase == "acepto"


@pytest.mark.parametrize(
    ("variable", "override"),
    [
        ("MESSAGE_GROUPING_WINDOW_SECONDS", {"message_grouping_window_seconds": 0}),
        ("MESSAGE_GROUPING_MAX_WAIT_SECONDS", {"message_grouping_max_wait_seconds": 1}),
        ("MESSAGE_GROUPING_MAX_MESSAGES", {"message_grouping_max_messages": 0}),
        ("MESSAGE_GROUPING_MAX_ATTEMPTS", {"message_grouping_max_attempts": 0}),
        ("MESSAGE_GROUPING_POLL_SECONDS", {"message_grouping_poll_seconds": 0}),
        ("MESSAGE_GROUPING_LEASE_SECONDS", {"message_grouping_lease_seconds": 10}),
        ("MESSAGE_GROUPING_BUFFER_TTL_SECONDS", {"message_grouping_buffer_ttl_seconds": 30}),
    ],
)
def test_invalid_grouping_settings_fail_with_variable_name(variable, override):
    """R2: una combinación inválida impide construir Settings y nombra la variable."""
    with pytest.raises(ValidationError) as error:
        Settings(**override)
    assert variable in str(error.value)


def test_env_example_lists_grouping_variables_with_defaults():
    """R3: .env.example declara todas las variables y la herencia de la frase."""
    text = (ROOT / ".env.example").read_text(encoding="utf-8")
    declared = {}
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        declared[key] = value
    expected = {
        "MESSAGE_GROUPING_ENABLED": "true",
        "MESSAGE_GROUPING_WINDOW_SECONDS": "2.0",
        "MESSAGE_GROUPING_MAX_WAIT_SECONDS": "8.0",
        "MESSAGE_GROUPING_MAX_MESSAGES": "10",
        "MESSAGE_GROUPING_BUFFER_TTL_SECONDS": "300",
        "MESSAGE_GROUPING_LEASE_SECONDS": "30",
        "MESSAGE_GROUPING_MAX_ATTEMPTS": "3",
        "MESSAGE_GROUPING_POLL_SECONDS": "0.5",
        "MESSAGE_GROUPING_ACCEPT_PHRASE": "",
    }
    for key, value in expected.items():
        assert declared.get(key) == value, key
    assert "PRIVACY_ACCEPT_PHRASE" in text


def test_render_references_accept_phrase_from_orchestrator():
    """R3: el gateway hereda MESSAGE_GROUPING_ACCEPT_PHRASE del orchestrator."""
    blueprint = yaml.safe_load((ROOT / "render.yaml").read_text(encoding="utf-8"))
    gateway = next(
        service for service in blueprint["services"] if service["name"] == "telegram-gateway"
    )
    variable = next(
        var for var in gateway["envVars"] if var.get("key") == "MESSAGE_GROUPING_ACCEPT_PHRASE"
    )
    assert variable["fromService"] == {
        "type": "web",
        "name": "orchestrator",
        "envVarKey": "PRIVACY_ACCEPT_PHRASE",
    }


# ---------------------------------------------------------------------------
# R4, R5 — ventana
# ---------------------------------------------------------------------------


def test_two_texts_within_window_are_grouped_when_due():
    """R4, R5: el webhook no llama al orquestador y el grupo sale al vencer."""
    env = make_env()
    assert post(env, update_id=1, text="hola").status_code == 200
    env.clock.advance(1)
    assert post(env, update_id=2, text="qué tal").status_code == 200
    assert env.orchestrator.received == []
    assert [m.text for m in env.buffer.pending(77)] == ["hola", "qué tal"]

    env.clock.advance(1.9)
    adapters = Adapters(
        env.telegram, env.dedup, env.orchestrator, clock=env.clock, buffer=env.buffer
    )
    assert flush_due(env.settings, adapters) == 0
    assert env.orchestrator.received == []

    env.clock.advance(0.1)
    flush_due(
        env.settings,
        Adapters(env.telegram, env.dedup, env.orchestrator, clock=env.clock, buffer=env.buffer),
    )
    assert len(env.orchestrator.received) == 1
    assert env.orchestrator.received[0].text == "hola\nqué tal"


def test_flush_chat_sends_pending_buffer_without_waiting():
    """R4: flush_chat envía el buffer pendiente cuando se le pide explícitamente."""
    env = make_env()
    post(env, update_id=1, text="hola")
    adapters = Adapters(
        env.telegram, env.dedup, env.orchestrator, clock=env.clock, buffer=env.buffer
    )
    flush_chat(77, env.settings, adapters)
    assert [m.text for m in env.orchestrator.received] == ["hola"]
    assert env.buffer.pending(77) == []


def test_gap_larger_than_window_produces_separate_groups():
    """R5: un mensaje posterior al vencimiento forma otro grupo."""
    env = make_env()
    post(env, update_id=1, text="uno")
    env.clock.advance(2)
    flush_due(
        env.settings,
        Adapters(env.telegram, env.dedup, env.orchestrator, clock=env.clock, buffer=env.buffer),
    )
    env.clock.advance(0.1)
    post(env, update_id=2, text="dos")
    env.clock.advance(2)
    flush_due(
        env.settings,
        Adapters(env.telegram, env.dedup, env.orchestrator, clock=env.clock, buffer=env.buffer),
    )
    assert [m.text for m in env.orchestrator.received] == ["uno", "dos"]


def test_long_burst_is_cut_at_max_wait():
    """R5: una ráfaga continua no espera más de MAX_WAIT."""
    env = make_env()
    for index in range(6):
        post(env, update_id=index + 1, text=f"m{index}")
        if index < 5:
            env.clock.advance(1.5)
    adapters = Adapters(
        env.telegram, env.dedup, env.orchestrator, clock=env.clock, buffer=env.buffer
    )
    env.clock.advance(0.4)  # t=7.9; el vencimiento es t=8 por MAX_WAIT
    assert flush_due(env.settings, adapters) == 0
    env.clock.advance(0.1)
    assert flush_due(env.settings, adapters) == 1
    assert env.orchestrator.received[0].text == "\n".join(f"m{i}" for i in range(6))
    post(env, update_id=7, text="después")
    env.clock.advance(2)
    flush_due(env.settings, adapters)
    assert env.orchestrator.received[-1].text == "después"


# ---------------------------------------------------------------------------
# R6, R7 — orden y forma del grupo
# ---------------------------------------------------------------------------


def test_group_is_ordered_by_update_id_and_uses_expected_fields():
    """R6, R7: textos ordenados; menor update_id y received_at del último del grupo."""
    env = make_env()
    post(env, update_id=1, text="a")
    env.clock.advance(0.1)
    post(env, update_id=3, text="c")
    env.clock.advance(0.1)
    post(env, update_id=2, text="b")
    env.clock.advance(2)
    flush_due(
        env.settings,
        Adapters(env.telegram, env.dedup, env.orchestrator, clock=env.clock, buffer=env.buffer),
    )
    message = env.orchestrator.received[0]
    assert message.text == "a\nb\nc"
    assert message.update_id == 1
    assert message.telegram_user_id == 55
    assert message.chat_id == 77
    assert message.received_at == FIXED_NOW + timedelta(seconds=0.1)


# ---------------------------------------------------------------------------
# R8, R9, R10 — aislamiento y límites
# ---------------------------------------------------------------------------


def test_chats_are_isolated():
    """R8: dos chats intercalados producen dos grupos sin mezcla."""
    env = make_env()
    post(env, update_id=1, text="A1", chat_id=100)
    post(env, update_id=2, text="B1", chat_id=200)
    post(env, update_id=3, text="A2", chat_id=100)
    post(env, update_id=4, text="B2", chat_id=200)
    env.clock.advance(2)
    flush_due(
        env.settings,
        Adapters(env.telegram, env.dedup, env.orchestrator, clock=env.clock, buffer=env.buffer),
    )
    by_chat = {m.chat_id: m.text for m in env.orchestrator.received}
    assert by_chat == {100: "A1\nA2", 200: "B1\nB2"}


def test_other_user_forces_previous_buffer_flush():
    """R9: un usuario distinto en el mismo chat separa los grupos."""
    env = make_env()
    post(env, update_id=1, text="a", chat_id=77, user_id=100)
    env.clock.advance(0.1)
    post(env, update_id=2, text="b", chat_id=77, user_id=200)
    assert [m.text for m in env.orchestrator.received] == ["a"]
    assert [m.text for m in env.buffer.pending(77)] == ["b"]


def test_max_messages_forces_previous_buffer_flush():
    """R9: el mensaje 11 provoca el envío de los 10 anteriores."""
    env = make_env(message_grouping_max_messages=10)
    for index in range(10):
        post(env, update_id=index + 1, text=f"m{index}")
    assert env.orchestrator.received == []
    post(env, update_id=11, text="m10")
    assert len(env.orchestrator.received) == 1
    assert env.orchestrator.received[0].text.count("\n") == 9
    assert [m.text for m in env.buffer.pending(77)] == ["m10"]


def test_combined_length_over_contract_limit_forces_flush():
    """R9: un grupo que superaría 4096 caracteres se parte."""
    env = make_env()
    first = "a" * 2100
    post(env, update_id=1, text=first)
    env.clock.advance(0.1)
    post(env, update_id=2, text="b" * 2100)
    assert [m.text for m in env.orchestrator.received] == [first]
    assert [m.text for m in env.buffer.pending(77)] == ["b" * 2100]


def test_single_message_longer_than_contract_limit_is_not_buffered(caplog):
    """R10: un texto de más de 4096 se trata como hoy y no entra al buffer."""
    env = make_env()
    with caplog.at_level(logging.ERROR):
        response = post(env, update_id=9, text="x" * 4097)
    assert response.status_code == 200
    assert env.orchestrator.received == []
    assert env.buffer.pending(77) == []
    assert "update_id=9" in log_text(caplog)
    assert "x" * 4097 not in log_text(caplog)


# ---------------------------------------------------------------------------
# R11, R12 — deduplicación
# ---------------------------------------------------------------------------


def test_duplicate_update_is_not_buffered():
    """R11: un update_id ya marcado no se añade al buffer."""
    env = make_env()
    post(env, update_id=5, text="hola")
    post(env, update_id=5, text="hola")
    assert [m.update_id for m in env.buffer.pending(77)] == [5]


def test_duplicate_append_keeps_a_single_copy_when_dedup_is_down():
    """R12: con Redis de dedup caído, el buffer sigue teniendo una sola copia."""
    env = make_env()
    env.dedup.fail = True
    post(env, update_id=6, text="hola")
    post(env, update_id=6, text="hola")
    assert [m.update_id for m in env.buffer.pending(77)] == [6]


# ---------------------------------------------------------------------------
# R13, R14, R20 — mensajes inmediatos y carrera en vuelo
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("text", ["/responder 3 hola", "/cerrar 3", "/start algo"])
def test_commands_flush_buffer_then_are_sent_individually(text):
    """R13, R14: el comando no se concatena con el buffer previo."""
    env = make_env()
    post(env, update_id=1, text="pregunta")
    env.clock.advance(0.1)
    post(env, update_id=2, text=text)
    assert [m.text for m in env.orchestrator.received] == ["pregunta", text]
    assert [m.update_id for m in env.orchestrator.received] == [1, 2]


def test_accept_phrase_is_immediate_after_normalization():
    """R13, R14: la frase de aceptación normalizada no se agrupa."""
    env = make_env(message_grouping_accept_phrase="Acepto los términos")
    post(env, update_id=1, text="antes")
    env.clock.advance(0.1)
    post(env, update_id=2, text="  ACEPTO   los   Términos ")
    assert [m.text for m in env.orchestrator.received] == ["antes", "  ACEPTO   los   Términos "]


def test_immediate_message_is_sent_alone_when_group_is_inflight(caplog):
    """R20: con un grupo en vuelo, el inmediato sale solo y se registra la carrera."""
    env = make_env()
    chat_id = 77
    post(env, update_id=1, text="texto-privado")
    env.buffer.claim_chat(
        chat_id, env.clock.now, env.settings.message_grouping_lease_seconds,
        env.settings.message_grouping_buffer_ttl_seconds,
    )
    post(env, update_id=2, text="otro-mensaje")
    with caplog.at_level(logging.WARNING):
        post(env, update_id=3, text="/start")
    assert [m.text for m in env.orchestrator.received] == ["/start"]
    log = log_text(caplog)
    assert "grouping_inflight_race" in log and "update_id=3" in log
    assert "texto-privado" not in log and "otro-mensaje" not in log


# ---------------------------------------------------------------------------
# R15, R16 — compatibilidad
# ---------------------------------------------------------------------------


def test_non_text_update_keeps_buffer_untouched():
    """R15: un update sin texto responde NON_TEXT_REPLY y no toca el buffer."""
    env = make_env()
    post(env, update_id=1, text="hola")
    update = {"update_id": 2, "message": {"from": {"id": 55}, "chat": {"id": 77}, "voice": {}}}
    response = env.client.post(URL, json=update, headers=HOOK)
    assert response.status_code == 200
    assert env.telegram.sent == [(77, env.settings.non_text_reply)]
    assert [m.text for m in env.buffer.pending(77)] == ["hola"]


def test_grouping_disabled_forwards_directly():
    """R16: con la agrupación desactivada se reenvía cada texto como antes."""
    env = make_env(message_grouping_enabled=False)
    post(env, update_id=1, text="hola")
    assert env.orchestrator.received[0].text == "hola"
    assert env.buffer.pending(77) == []


def test_without_buffer_adapter_forwards_directly():
    """R16: sin adaptador de buffer también se reenvía individualmente."""
    env = make_env(with_buffer=False)
    post(env, update_id=1, text="hola")
    assert env.orchestrator.received[0].text == "hola"


# ---------------------------------------------------------------------------
# R17, R21, R22, R28 — fallos, reintentos y descarte
# ---------------------------------------------------------------------------


def test_redis_failure_falls_back_to_individual_forward(caplog):
    """R17: si Redis falla al bufferizar, el mensaje se reenvía solo y se registra."""
    env = make_env()
    env.buffer.fail = True
    with caplog.at_level(logging.ERROR):
        response = post(env, update_id=8, text="texto-secreto")
    assert response.status_code == 200
    assert [m.text for m in env.orchestrator.received] == ["texto-secreto"]
    log = log_text(caplog)
    assert "grouping_redis_error update_id=8" in log
    assert "texto-secreto" not in log


def test_orchestrator_failure_releases_group_and_retries_same_messages(caplog):
    """R21: un fallo no agota intentos y conserva los mensajes para reintentar."""
    env = make_env()
    post(env, update_id=1, text="pregunta")
    env.clock.advance(2)
    adapters = Adapters(
        env.telegram, env.dedup, env.orchestrator, clock=env.clock, buffer=env.buffer
    )
    env.orchestrator.fail = True
    with caplog.at_level(logging.WARNING):
        flush_due(env.settings, adapters)
    assert "grouping_retry" in log_text(caplog) and "attempts=1" in log_text(caplog)
    env.orchestrator.fail = False
    env.clock.advance(env.settings.message_grouping_lease_seconds + 1)
    flush_due(env.settings, adapters)
    assert [m.text for m in env.orchestrator.received] == ["pregunta"]


def test_group_is_discarded_after_max_attempts(caplog):
    """R22: al agotar MAX_ATTEMPTS se descarta con log sin texto."""
    env = make_env(message_grouping_max_attempts=1)
    post(env, update_id=1, text="privado-max")
    env.clock.advance(2)
    adapters = Adapters(
        env.telegram, env.dedup, env.orchestrator, clock=env.clock, buffer=env.buffer
    )
    env.orchestrator.fail = True
    with caplog.at_level(logging.ERROR):
        flush_due(env.settings, adapters)
    log = log_text(caplog)
    assert "grouping_discarded" in log and "reason=max_attempts" in log
    assert "update_ids=1" in log and "privado-max" not in log
    assert env.buffer.claim_due(
        env.clock.now, 30, 300, 10
    ) == []


def test_group_that_fails_contract_validation_is_discarded(caplog):
    """R22: un grupo inválido para MessageRequest se descarta."""
    env = make_env()
    window = env.settings.message_grouping_window_seconds
    max_wait = env.settings.message_grouping_max_wait_seconds
    ttl = env.settings.message_grouping_buffer_ttl_seconds
    for index in (1, 2):
        env.buffer.append(
            77,
            BufferedMessage(index, 55, "z" * 3000, env.clock.now),
            window,
            max_wait,
            ttl,
        )
    env.clock.advance(2)
    adapters = Adapters(
        env.telegram, env.dedup, env.orchestrator, clock=env.clock, buffer=env.buffer
    )
    with caplog.at_level(logging.ERROR):
        flush_due(env.settings, adapters)
    assert env.orchestrator.received == []
    log = log_text(caplog)
    assert "grouping_discarded" in log and "reason=validation" in log
    assert "z" * 10 not in log


# ---------------------------------------------------------------------------
# R18, R19 — concurrencia y grupo en vuelo
# ---------------------------------------------------------------------------


def test_eight_threads_claim_the_same_group_only_once():
    """R18: solo un worker reclama y envía el mismo grupo."""
    env = make_env()
    post(env, update_id=1, text="hola")
    env.clock.advance(2)
    adapters = Adapters(
        env.telegram, env.dedup, env.orchestrator, clock=env.clock, buffer=env.buffer
    )
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _: flush_due(env.settings, adapters), range(8)))
    assert sum(results) == 1
    assert len(env.orchestrator.received) == 1


def test_group_in_flight_blocks_other_claims_of_same_chat():
    """R19: mientras un grupo no se confirma no se reclama otro buffer del chat."""
    env = make_env()
    post(env, update_id=1, text="primero")
    env.clock.advance(2)
    claimed = env.buffer.claim_due(
        env.clock.now,
        env.settings.message_grouping_lease_seconds,
        env.settings.message_grouping_buffer_ttl_seconds,
        10,
    )
    assert len(claimed) == 1
    post(env, update_id=2, text="segundo")
    adapters = Adapters(
        env.telegram, env.dedup, env.orchestrator, clock=env.clock, buffer=env.buffer
    )
    env.clock.advance(2)
    assert flush_due(env.settings, adapters) == 0
    assert env.orchestrator.received == []
    env.clock.advance(env.settings.message_grouping_lease_seconds)
    flush_due(env.settings, adapters)
    assert len(env.orchestrator.received) == 1


@pytest.mark.parametrize("reason", ["max_messages", "length"])
def test_limit_while_inflight_sends_new_message_individually(reason, caplog):
    """R20: si el límite coincide con un grupo en vuelo, el nuevo mensaje sale solo."""
    env = make_env(message_grouping_max_messages=2)
    if reason == "length":
        post(env, update_id=1, text="a" * 2100)
    else:
        post(env, update_id=1, text="primero")
        post(env, update_id=2, text="segundo")
    env.buffer.claim_chat(
        77,
        env.clock.now,
        env.settings.message_grouping_lease_seconds,
        env.settings.message_grouping_buffer_ttl_seconds,
    )
    env.clock.advance(0.1)
    with caplog.at_level(logging.WARNING):
        if reason == "length":
            post(env, update_id=3, text="b" * 2100)
            post(env, update_id=4, text="c" * 2100)
            expected = "c" * 2100
        else:
            post(env, update_id=5, text="nuevo1")
            post(env, update_id=6, text="nuevo2")
            post(env, update_id=7, text="nuevo3")
            expected = "nuevo3"
    assert [m.text for m in env.orchestrator.received] == [expected]
    log = log_text(caplog)
    assert "grouping_inflight_race" in log
    assert "privado" not in log and "nuevo1" not in log


# ---------------------------------------------------------------------------
# R23, R24 — lease, reinicio y TTL simulado
# ---------------------------------------------------------------------------


def test_expired_lease_reclaims_until_max_attempts_then_discards(caplog):
    """R23: el lease vencido reenvía con intento creciente y descarta al agotar."""
    env = make_env()
    post(env, update_id=1, text="pendiente")
    env.clock.advance(2)
    lease = env.settings.message_grouping_lease_seconds
    ttl = env.settings.message_grouping_buffer_ttl_seconds
    for _ in range(3):
        claimed = env.buffer.claim_due(env.clock.now, lease, ttl, 10)
        assert len(claimed) == 1
        env.clock.advance(lease + 1)
    adapters = Adapters(
        env.telegram, env.dedup, env.orchestrator, clock=env.clock, buffer=env.buffer
    )
    with caplog.at_level(logging.ERROR):
        flush_due(env.settings, adapters)
    assert env.orchestrator.received == []
    assert "grouping_discarded" in log_text(caplog)
    assert "attempts=4" in log_text(caplog)


def test_buffer_and_group_expire_after_ttl():
    """R24: buffer y grupo reclamado caducan pasados BUFFER_TTL_SECONDS."""
    env = make_env()
    ttl = env.settings.message_grouping_buffer_ttl_seconds
    lease = env.settings.message_grouping_lease_seconds
    post(env, update_id=1, text="hola")
    env.clock.advance(ttl + 1)
    assert env.buffer.pending(77) == []
    assert env.buffer.claim_due(env.clock.now, lease, ttl, 10) == []

    post(env, update_id=2, text="otra")
    env.clock.advance(2)
    claimed = env.buffer.claim_due(env.clock.now, lease, ttl, 10)
    assert len(claimed) == 1
    env.clock.advance(ttl + 1)
    assert env.buffer.claim_due(env.clock.now, lease, ttl, 10) == []


# ---------------------------------------------------------------------------
# R25, R26, R27 — worker y ciclo de vida
# ---------------------------------------------------------------------------


def test_worker_logs_iteration_errors_and_keeps_running(monkeypatch, caplog):
    """R25: una excepción en flush_due se registra y el bucle continúa."""
    calls = {"count": 0}

    def boom(settings, adapters):
        calls["count"] += 1
        raise RuntimeError("detalle-con-texto")

    monkeypatch.setattr("telegram_gateway.grouping.flush_due", boom)
    env = make_env(message_grouping_poll_seconds=0.01)
    worker = GroupingWorker(
        env.settings,
        Adapters(env.telegram, env.dedup, env.orchestrator, clock=env.clock, buffer=env.buffer),
    )
    with caplog.at_level(logging.ERROR):
        worker.start()
        time.sleep(0.06)
        worker.stop()
    assert calls["count"] >= 2
    log = log_text(caplog)
    assert "grouping_worker_error" in log and "RuntimeError" in log
    assert "detalle-con-texto" not in log


def test_app_starts_and_stops_grouping_worker(monkeypatch):
    """R26, R27: el lifespan arranca y detiene el worker."""
    events = []

    class FakeWorker:
        def __init__(self, settings, adapters):
            events.append("init")

        def start(self):
            events.append("start")

        def stop(self, timeout=5):
            events.append("stop")

    monkeypatch.setattr("telegram_gateway.main.GroupingWorker", FakeWorker)
    env = make_env()
    app = create_app(
        env.settings,
        Adapters(env.telegram, env.dedup, env.orchestrator, clock=env.clock, buffer=env.buffer),
    )
    with TestClient(app) as client:
        assert client.get("/health").status_code == 200
        assert events == ["init", "start"]
    assert events == ["init", "start", "stop"]


def test_app_does_not_start_worker_when_grouping_is_disabled(monkeypatch):
    """R16, R26: sin agrupación activa no se arranca el worker."""
    events = []

    class FakeWorker:
        def __init__(self, settings, adapters):
            events.append("init")

        def start(self):
            events.append("start")

        def stop(self, timeout=5):
            events.append("stop")

    monkeypatch.setattr("telegram_gateway.main.GroupingWorker", FakeWorker)
    env = make_env(message_grouping_enabled=False)
    app = create_app(
        env.settings,
        Adapters(env.telegram, env.dedup, env.orchestrator, clock=env.clock, buffer=env.buffer),
    )
    with TestClient(app):
        pass
    assert events == []


# ---------------------------------------------------------------------------
# R28 — privacidad de los logs
# ---------------------------------------------------------------------------


def test_error_logs_do_not_include_texts_or_accept_phrase(caplog):
    """R28: ni el texto ni la frase aparecen en los logs de agrupación."""
    phrase = "frase-muy-privada"
    env = make_env(message_grouping_accept_phrase=phrase, message_grouping_max_attempts=1)
    env.buffer.fail = True
    with caplog.at_level(logging.DEBUG):
        post(env, update_id=21, text="texto-privado-21")
        post(env, update_id=22, text=phrase)
    log = log_text(caplog)
    assert "texto-privado-21" not in log
    assert phrase not in log
    assert SERVICE_TOKEN not in log


def test_worker_does_not_start_real_threads_without_buffer():
    """R29: sin adaptador de buffer no hay hilo ni acceso a Redis."""
    env = make_env(with_buffer=False)
    assert env.buffer is None
    adapters = Adapters(env.telegram, env.dedup, env.orchestrator, clock=env.clock)
    assert flush_due(env.settings, adapters) == 0
