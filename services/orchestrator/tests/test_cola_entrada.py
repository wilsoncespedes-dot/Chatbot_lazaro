"""Cola de entrada de POST /messages (#64, R1-R8)."""
from __future__ import annotations

import ast
from pathlib import Path

import orchestrator.main as main_module
from orchestrator.privacy import notice_sha256

SERVICE_TOKEN = "svc-token"
HEADERS = {"X-Service-Token": SERVICE_TOKEN}
RECEIVED_AT = "2026-01-02T03:04:00+00:00"


def _legacy(update_id: int = 1, user: int = 10, chat: int = 100, text: str = "Hola"):
    return {
        "update_id": update_id,
        "telegram_user_id": user,
        "chat_id": chat,
        "text": text,
        "received_at": RECEIVED_AT,
    }


def _canonical(text: str = "Hola", message_id: str = "m1", channel: str = "telegram"):
    return {
        "channel": channel,
        "external_user_id": "10" if channel == "telegram" else "57300",
        "external_chat_id": "100" if channel == "telegram" else "57300",
        "external_message_id": message_id,
        "kind": "text",
        "text": text,
        "received_at": RECEIVED_AT,
    }


def _consent(env, user: int = 10, channel: str = "telegram") -> None:
    env.repo.add_channel_privacy_consent(
        channel,
        str(user) if channel == "telegram" else "57300",
        env.settings.privacy_notice_version,
        notice_sha256(env.settings.privacy_notice_text),
        env.adapters.clock(),
    )


def _post(env, body: dict):
    return env.client.post("/messages", json=body, headers=HEADERS)


def test_post_messages_enqueues_and_returns_202(env):
    """R1, R2: guarda en inbox y responde 202 sin ejecutar el flujo."""
    _consent(env)
    response = _post(env, _legacy())
    assert response.status_code == 202
    assert response.json() == {"status": "accepted"}
    assert len(env.repo.inbox) == 1
    row = next(iter(env.repo.inbox.values()))
    assert row["status"] == "pending"
    assert env.repo.messages == []
    assert env.rag.calls == []


def test_post_messages_does_not_run_flow_in_request(env):
    """R2: ni el bot, ni RAG, ni LLM se ejecutan dentro de la petición."""
    _consent(env)
    _post(env, _legacy())
    assert env.repo.contacts == {}
    assert env.repo.messages == []
    assert env.rag.calls == []
    assert env.llm.calls == []
    assert env.gateway.sent == []


def test_main_does_not_import_background_tasks():
    """R3: `main.py` no usa `BackgroundTasks`."""
    tree = ast.parse(Path(main_module.__file__).read_text(encoding="utf-8"))
    names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
    imports = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
    }
    assert "BackgroundTasks" not in names
    assert "BackgroundTasks" not in imports


def test_duplicate_returns_duplicate_without_row(env):
    """R4: un mensaje ya deduplicado responde duplicate y no inserta fila."""
    _consent(env)
    first = _post(env, _legacy())
    second = _post(env, _legacy())
    assert first.json() == {"status": "accepted"}
    assert second.json() == {"status": "duplicate"}
    assert len(env.repo.inbox) == 1


def test_dedup_and_insert_roll_back_together(env):
    """R5: si falla el INSERT, la marca de dedup se revierte y responde 500."""
    _consent(env)
    env.repo.fail_inbox_insert = True
    response = _post(env, _legacy())
    assert response.status_code == 500
    assert response.json()["error"] == "internal_error"
    assert 1 not in env.repo.processed
    assert ("telegram", "1") not in env.repo.processed_messages
    env.repo.fail_inbox_insert = False
    retry = _post(env, _legacy())
    assert retry.json() == {"status": "accepted"}
    assert len(env.repo.inbox) == 1


def test_consent_acceptance_runs_in_request(env):
    """R6: la aceptación de consentimiento no pasa por la cola."""
    env.present()
    before = len(env.repo.inbox)
    response = _post(
        env,
        _canonical(env.settings.consent_accept_phrase, message_id="accept-1"),
    )
    assert response.json() == {"status": "accepted"}
    assert len(env.repo.inbox) == before
    assert any(c.result == "accepted" for c in env.repo.privacy_consents)


def test_unconsented_message_enqueued_without_dedup_mark(env):
    """R7: sin consentimiento se encola, pero no se persiste la clave."""
    first = _post(env, _canonical("Hola", message_id="m1"))
    second = _post(env, _canonical("Hola", message_id="m1"))
    assert first.json() == {"status": "accepted"}
    assert second.json() == {"status": "accepted"}
    assert len(env.repo.inbox) == 2
    assert ("telegram", "m1") not in env.repo.processed_messages


def test_inbox_row_stores_key_channel_kind_payload(env):
    """R8: la fila guarda clave, canal, id externo, tipo y carga."""
    _consent(env)
    _post(env, _legacy(update_id=9))
    row = next(iter(env.repo.inbox.values()))
    assert row["conversation_key"] == "telegram:10"
    assert row["channel"] == "telegram"
    assert row["external_user_id"] == "10"
    assert row["payload_kind"] == "legacy"
    assert row["payload"]["update_id"] == 9
