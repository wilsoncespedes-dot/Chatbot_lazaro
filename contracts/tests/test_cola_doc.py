"""R42: documentación de la cola de entrada y outbox (#64)."""
from __future__ import annotations

import re
from pathlib import Path

DOC_PATH = Path(__file__).resolve().parent.parent / "CONTRATOS.md"
HEADING = "## Cola de entrada y outbox"


def _section() -> str:
    text = DOC_PATH.read_text(encoding="utf-8")
    start = text.index(HEADING)
    rest = text[start + len(HEADING):]
    match = re.search(r"^## ", rest, re.MULTILINE)
    return rest[: match.start()] if match else rest


def test_documents_202_at_least_once_duplicate_window_and_order():
    """R42: semántica 202, entrega al menos una vez, duplicado y bloqueo por orden."""
    section = _section()
    for fragment in (
        "202",
        "al menos una vez",
        "duplicado",
        "bloquea",
        "conversation_key",
        "destination_key",
        "FOR UPDATE SKIP LOCKED",
    ):
        assert fragment in section, fragment


def test_documents_queue_variables_and_retry_rules():
    """R42: variables de la cola y reglas de reintento/no reintento."""
    section = _section()
    for name in (
        "INBOX_MAX_ATTEMPTS",
        "INBOX_BACKOFF_BASE_SECONDS",
        "OUTBOX_MAX_ATTEMPTS",
        "OUTBOX_BACKOFF_BASE_SECONDS",
        "OUTBOX_BACKOFF_MAX_SECONDS",
        "OUTBOX_BACKOFF_JITTER",
        "WORKER_POLL_SECONDS",
        "WORKER_LEASE_SECONDS",
    ):
        assert name in section, name
    assert "ChannelRejected" in section
    assert "outbox_retry" in section
