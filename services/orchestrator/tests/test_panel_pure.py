"""Tests de las funciones puras del panel multicanal (#41)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from orchestrator.panel import (
    business_deadline,
    business_days_left,
    case_wait,
    channel_window,
    effective_presence,
    history_visible,
    mask_external_id,
    suppression_priority,
)

NOW = datetime(2026, 1, 2, 10, 0, tzinfo=timezone.utc)


def test_channel_window_boundaries_and_telegram():
    """R5: WhatsApp cierra al cumplirse 24 h; Telegram no aplica."""
    assert channel_window("telegram", NOW, NOW, 24) == "not_applicable"
    assert channel_window("whatsapp", None, NOW, 24) == "closed"
    assert channel_window(
        "whatsapp", NOW - timedelta(hours=23, minutes=59), NOW, 24
    ) == "open"
    assert channel_window(
        "whatsapp", NOW - timedelta(hours=24), NOW, 24
    ) == "closed"


def test_case_wait_three_branches():
    """R4: espera desde el vínculo, desde el último usuario o sin espera."""
    link = NOW - timedelta(minutes=30)
    assert case_wait(link, None, None, NOW) == timedelta(minutes=30)
    assert case_wait(
        link,
        NOW - timedelta(minutes=20),
        NOW - timedelta(minutes=25),
        NOW,
    ) == timedelta(minutes=20)
    assert case_wait(
        link,
        NOW - timedelta(minutes=25),
        NOW - timedelta(minutes=20),
        NOW,
    ) is None


def test_business_deadline_skips_weekend():
    """R63: sumar días hábiles salta sábado y domingo conservando la hora."""
    friday = datetime(2026, 1, 2, 10, 0, tzinfo=timezone.utc)
    assert business_deadline(friday, 1) == datetime(
        2026, 1, 5, 10, 0, tzinfo=timezone.utc
    )
    assert business_deadline(friday, 5) == datetime(
        2026, 1, 9, 10, 0, tzinfo=timezone.utc
    )


def test_business_days_left_and_priority_three_branches():
    """R64: vencida, urgente y alta según la fecha límite."""
    assert business_days_left(NOW, NOW - timedelta(days=1)) == 0
    assert business_days_left(
        NOW, datetime(2026, 1, 6, 10, 0, tzinfo=timezone.utc)
    ) == 2
    assert suppression_priority(
        NOW, NOW - timedelta(seconds=1), 3
    ) == "vencida"
    assert suppression_priority(
        NOW, datetime(2026, 1, 6, 10, 0, tzinfo=timezone.utc), 3
    ) == "urgente"
    assert suppression_priority(
        NOW, datetime(2026, 1, 16, 10, 0, tzinfo=timezone.utc), 3
    ) == "alta"


def test_effective_presence_expires_and_requires_available():
    """R34: `available` caduca con el TTL; cualquier otro estado es `away`."""
    assert effective_presence("available", NOW - timedelta(minutes=15), NOW, 15) == (
        "available"
    )
    assert effective_presence("available", NOW - timedelta(minutes=16), NOW, 15) == (
        "away"
    )
    assert effective_presence("away", NOW, NOW, 15) == "away"
    assert effective_presence(None, None, NOW, 15) == "away"


def test_mask_external_id_keeps_the_last_four_characters():
    """R46: el identificador externo se muestra enmascarado."""
    assert mask_external_id("573001234") == "…1234"
    assert mask_external_id("") == "—"


def test_history_visible_excludes_foreign_session_windows():
    """R44: los mensajes dentro de la ventana de sesión ajena no son visibles."""
    window = (NOW - timedelta(hours=1), NOW + timedelta(hours=1), NOW)
    assert history_visible(NOW - timedelta(minutes=45), [window]) is False
    assert history_visible(NOW + timedelta(minutes=1), [window]) is True
    assert history_visible(NOW - timedelta(hours=2), [window]) is True
