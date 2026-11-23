"""R36–R38, R40: herramienta scripts/simular_canal.py."""
from __future__ import annotations

import hashlib
import hmac
import importlib.util
import re
from datetime import datetime, timezone
from pathlib import Path

import pytest

from telegram_gateway.signature import verify_signature

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "simular_canal.py"
DOC = ROOT / "contracts" / "CONTRATOS.md"
_spec = importlib.util.spec_from_file_location("simular_canal", SCRIPT)
simular = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(simular)

NOW = datetime(2026, 11, 21, 15, 0, tzinfo=timezone.utc)
SECRET = "secreto-de-ejemplo"
CHANNEL = "tiktok-simulado"
USER = "cliente-demo"
TEXT = "Hola, quiero información"
MESSAGE_ID = "sim-1"
BASE_URL = "http://localhost:8001"


class _Post:
    def __init__(self, status: int = 200, body: str = '{"status":"accepted"}') -> None:
        self.status = status
        self.body = body
        self.calls: list[tuple[str, bytes, dict[str, str]]] = []

    def __call__(self, url, body, headers):
        self.calls.append((url, body, dict(headers)))
        return self.status, self.body


def _run(post=None, env=None, argv=None, now=lambda: NOW) -> int:
    return simular.main(
        argv
        if argv is not None
        else [
            "--url",
            BASE_URL,
            "--canal",
            CHANNEL,
            "--usuario",
            USER,
            "--texto",
            TEXT,
            "--id-mensaje",
            MESSAGE_ID,
        ],
        env=env if env is not None else {"LAZARO_CANAL_SECRETO": SECRET},
        post=post or _Post(),
        now=now,
    )


def _generic_section() -> str:
    text = DOC.read_text(encoding="utf-8")
    heading = "## Canal genérico (webhook firmado)"
    start = text.index(heading)
    rest = text[start + len(heading) :]
    match = re.search(r"^## ", rest, re.MULTILINE)
    return rest[: match.start()] if match else rest


def _documented_example() -> tuple[str, str, str]:
    section = _generic_section()
    match = re.search(r"secreto de ejemplo `([^`]+)`", section)
    assert match
    secret = match.group(1)
    block = re.search(r"```http\n(.*?)\n```", section, re.DOTALL)
    assert block
    lines = block.group(1).splitlines()
    headers = {}
    for line in lines[1:-1]:
        if ":" in line:
            name, _, value = line.partition(":")
            headers[name.strip().lower()] = value.strip()
    return secret, headers["x-lazaro-timestamp"], lines[-1]


def test_build_body_is_a_normalized_inbound_message():
    """R36: el cuerpo es un NormalizedMessage inbound con los datos pedidos."""
    body = simular.build_body(CHANNEL, USER, TEXT, MESSAGE_ID, NOW).decode("utf-8")
    from lazaro_contracts import NormalizedMessage

    message = NormalizedMessage.model_validate_json(body)
    assert message.channel == CHANNEL
    assert message.external_user_id == message.external_chat_id == USER
    assert message.external_message_id == MESSAGE_ID
    assert message.kind == "text"
    assert message.text == TEXT
    assert message.direction == "inbound"
    assert message.received_at == NOW


def test_signature_is_verified_by_the_gateway():
    """R36, R38: verify_signature del gateway acepta la firma del script."""
    body = simular.build_body(CHANNEL, USER, TEXT, MESSAGE_ID, NOW)
    timestamp = int(NOW.timestamp())
    signature = simular.sign(SECRET, timestamp, body)
    assert verify_signature(
        SECRET, str(timestamp), signature, body, NOW, 300
    )


def test_signature_matches_the_signed_example_of_the_contract():
    """R38: la firma coincide con el ejemplo firmado de CONTRATOS.md."""
    secret, timestamp, documented_body = _documented_example()
    body = documented_body.encode("utf-8")
    expected = hmac.new(
        secret.encode("utf-8"),
        f"{timestamp}.".encode("utf-8") + body,
        hashlib.sha256,
    ).hexdigest()
    assert simular.sign(secret, int(timestamp), body) == expected


def test_send_signs_exactly_the_bytes_it_sends():
    """R36, R38: el cuerpo firmado y el enviado son los mismos bytes."""
    post = _Post()
    body = simular.build_body(CHANNEL, USER, TEXT, MESSAGE_ID, NOW)
    status, _ = simular.send(BASE_URL, CHANNEL, SECRET, body, NOW, post=post)
    assert status == 200
    url, sent_body, headers = post.calls[0]
    assert url == f"{BASE_URL}/webhooks/{CHANNEL}"
    assert sent_body == body
    assert headers["Content-Type"] == "application/json"
    timestamp = headers["X-Lazaro-Timestamp"]
    assert headers["X-Lazaro-Signature"] == simular.sign(
        SECRET, int(timestamp), sent_body
    )


@pytest.mark.parametrize("status,expected", [(200, 0), (400, 1), (500, 1)])
def test_main_exit_code_depends_on_http_status(status, expected):
    """R36: 0 si 200; 1 con cualquier otro código."""
    post = _Post(status=status)
    assert _run(post=post) == expected


def test_main_reads_secret_from_environment_and_never_prints_it(capsys):
    """R37: el secreto sale del entorno y no aparece en la salida."""
    post = _Post()
    assert _run(post=post) == 0
    captured = capsys.readouterr()
    assert SECRET not in captured.out
    assert SECRET not in captured.err
    assert "HTTP 200" in captured.out


def test_main_accepts_an_alternate_secret_variable(capsys):
    """R37: --secreto-env indica otra variable de entorno."""
    post = _Post()
    assert (
        _run(
            post=post,
            env={"OTRO_SECRETO": SECRET},
            argv=[
                "--canal",
                CHANNEL,
                "--usuario",
                USER,
                "--texto",
                TEXT,
                "--secreto-env",
                "OTRO_SECRETO",
            ],
        )
        == 0
    )
    assert SECRET not in capsys.readouterr().out


def test_missing_secret_exits_two_without_printing_a_value(capsys):
    """R37: si falta la variable, sale con 2 y sin el valor."""
    assert _run(post=_Post(), env={}) == 2
    captured = capsys.readouterr()
    assert "LAZARO_CANAL_SECRETO" in captured.err
    assert SECRET not in captured.out + captured.err


def test_secret_is_not_accepted_as_a_command_line_argument(capsys):
    """R37: --secreto se rechaza sin imprimir su valor."""
    argv = [
        "--canal",
        CHANNEL,
        "--usuario",
        USER,
        "--texto",
        TEXT,
        "--secreto",
        SECRET,
    ]
    assert _run(post=_Post(), argv=argv) == 2
    captured = capsys.readouterr()
    assert SECRET not in captured.out + captured.err
    assert "variable de entorno" in captured.err


def test_network_error_exits_two_without_traceback(capsys):
    """R38: un fallo de red sale con 2 y sin traza."""

    def post(url, body, headers):
        raise RuntimeError(f"sin conexión a {SECRET}")

    assert _run(post=post) == 2
    captured = capsys.readouterr()
    assert "RuntimeError" in captured.err
    assert "Traceback" not in captured.err
    assert SECRET not in captured.out + captured.err


def test_same_message_id_produces_the_same_body():
    """R38: reenviar el mismo --id-mensaje repite el cuerpo para provocar duplicate."""
    post = _Post()
    assert _run(post=post) == 0
    assert _run(post=post) == 0
    assert post.calls[0][1] == post.calls[1][1]


def test_default_message_id_is_prefixed_sim():
    """R20, R38: sin --id-mensaje se usa un id único con prefijo sim-."""
    post = _Post()
    argv = [
        "--canal",
        CHANNEL,
        "--usuario",
        USER,
        "--texto",
        TEXT,
    ]
    assert _run(post=post, argv=argv) == 0
    from lazaro_contracts import NormalizedMessage

    message = NormalizedMessage.model_validate_json(post.calls[0][1])
    assert message.external_message_id.startswith("sim-")


def test_help_and_docstring_contain_simulado(capsys):
    """R40: --help y el docstring del script muestran SIMULADO."""
    assert "SIMULADO" in simular.__doc__
    with pytest.raises(SystemExit) as error:
        simular.main(["--help"], env={})
    assert error.value.code == 0
    assert "SIMULADO" in capsys.readouterr().out


# ── Fase 6: TikTok con su propio formato y firma ────────────────────────────

TIKTOK_SECRET = "tiktok-webhook-secret-de-prueba"
TIKTOK_BUSINESS = "business-open-id"
TIKTOK_APP_KEY = "tiktok-app-key"


def test_tiktok_mode_builds_a_signed_event_the_gateway_accepts(capsys):
    """Fase 6: --canal tiktok firma con TIKTOK_WEBHOOK_SECRET y el gateway lo normaliza."""
    from telegram_gateway.tiktok import parse_tiktok_webhook, verify_tiktok_signature

    post = _Post()
    argv = ["--canal", "tiktok", "--usuario", USER, "--texto", TEXT, "--id-mensaje", "tt-1"]
    env = {
        "TIKTOK_WEBHOOK_SECRET": TIKTOK_SECRET,
        "TIKTOK_BUSINESS_ID": TIKTOK_BUSINESS,
        "TIKTOK_CLIENT_KEY": TIKTOK_APP_KEY,
    }
    assert _run(post=post, env=env, argv=argv) == 0

    url, body, headers = post.calls[0]
    assert url == f"{BASE_URL}/webhooks/tiktok"
    assert verify_tiktok_signature(TIKTOK_SECRET, body, headers["TikTok-Signature"], NOW)
    payload = __import__("json").loads(body)
    assert payload["client_key"] == TIKTOK_APP_KEY
    [message] = parse_tiktok_webhook(payload, TIKTOK_BUSINESS, NOW)
    assert message.channel == "tiktok"
    assert message.external_user_id == USER
    assert message.external_message_id == "tt-1"
    assert message.text == TEXT
    assert TIKTOK_SECRET not in capsys.readouterr().out


def test_tiktok_mode_requires_its_own_secret_and_account(capsys):
    """Fase 6: sin TIKTOK_WEBHOOK_SECRET o sin cuenta sale con 2 y no envía nada."""
    post = _Post()
    argv = ["--canal", "tiktok", "--usuario", USER, "--texto", TEXT]
    assert _run(post=post, env={"LAZARO_CANAL_SECRETO": SECRET}, argv=argv) == 2
    assert "TIKTOK_WEBHOOK_SECRET" in capsys.readouterr().err
    assert _run(post=post, env={"TIKTOK_WEBHOOK_SECRET": TIKTOK_SECRET}, argv=argv) == 2
    assert "TIKTOK_BUSINESS_ID" in capsys.readouterr().err
    assert post.calls == []


# ── Fase 7: Messenger e Instagram con el formato y la firma de Meta ─────────

META_SECRET = "meta-app-secret-de-prueba"


@pytest.mark.parametrize(
    ("channel", "account_env", "account", "object_type"),
    [
        ("facebook", "META_PAGE_ID", "page-123", "page"),
        ("instagram", "META_INSTAGRAM_ACCOUNT_ID", "ig-456", "instagram"),
    ],
)
def test_meta_mode_builds_a_signed_notification_the_gateway_accepts(
    channel, account_env, account, object_type, capsys
):
    """Fase 7: --canal facebook/instagram firma con META_APP_SECRET y va a /webhooks/messenger."""
    import json

    from telegram_gateway.meta_messaging import parse_meta_webhook
    from telegram_gateway.whatsapp_cloud import verify_signature as verify_meta

    post = _Post()
    argv = ["--canal", channel, "--usuario", USER, "--texto", TEXT, "--id-mensaje", "mid-1"]
    env = {"META_APP_SECRET": META_SECRET, account_env: account}
    assert _run(post=post, env=env, argv=argv) == 0

    url, body, headers = post.calls[0]
    assert url == f"{BASE_URL}/webhooks/messenger"
    assert verify_meta(META_SECRET, body, headers["X-Hub-Signature-256"])
    payload = json.loads(body)
    assert payload["object"] == object_type
    page_id = account if channel == "facebook" else ""
    instagram_id = account if channel == "instagram" else ""
    [message] = parse_meta_webhook(payload, channel, page_id, instagram_id, NOW)
    assert message.channel == channel
    assert message.external_user_id == USER
    assert message.external_message_id == "mid-1"
    assert message.text == TEXT
    assert META_SECRET not in capsys.readouterr().out


def test_meta_mode_requires_app_secret_and_account(capsys):
    """Fase 7: sin META_APP_SECRET o sin cuenta sale con 2 y no envía nada."""
    post = _Post()
    argv = ["--canal", "facebook", "--usuario", USER, "--texto", TEXT]
    assert _run(post=post, env={"LAZARO_CANAL_SECRETO": SECRET}, argv=argv) == 2
    assert "META_APP_SECRET" in capsys.readouterr().err
    assert _run(post=post, env={"META_APP_SECRET": META_SECRET}, argv=argv) == 2
    assert "META_PAGE_ID" in capsys.readouterr().err
    assert post.calls == []
