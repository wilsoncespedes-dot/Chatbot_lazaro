"""Función pura de estados visibles de la bandeja (#68 R1, R6)."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from orchestrator.conversations import (
    CONVERSATION_STATUSES,
    derive_conversation_status,
    is_listable_state,
)
from orchestrator.states import ConversationState

NOW = datetime(2026, 1, 2, 3, 0, tzinfo=timezone.utc)


def test_advisor_wins_when_open_case_has_advisor():
    """R1: un caso abierto asignado es `atendida_por_asesor`."""
    assert (
        derive_conversation_status(
            ConversationState.WITH_ADVISOR, "assigned", "700", None, NOW
        )
        == "atendida_por_asesor"
    )
    assert (
        derive_conversation_status(ConversationState.ACTIVE, "open", "700", None, NOW)
        == "atendida_por_asesor"
    )


def test_pending_when_open_case_has_no_advisor():
    """R1: un caso abierto sin asesor es `pendiente`."""
    for status in ("open", "timed_out", "assigned"):
        assert (
            derive_conversation_status(
                ConversationState.ACTIVE, status, None, None, NOW
            )
            == "pendiente"
        )


def test_pending_when_with_advisor_without_case():
    """R1: `with_advisor` sin caso asignado es `pendiente`."""
    assert (
        derive_conversation_status(
            ConversationState.WITH_ADVISOR, None, None, None, NOW
        )
        == "pendiente"
    )


def test_closed_when_resolved_after_last_user_message():
    """R1: un cierre de asesor posterior al último mensaje deja `cerrada`."""
    earlier = datetime(2026, 1, 2, 2, 0, tzinfo=timezone.utc)
    assert (
        derive_conversation_status(
            ConversationState.ACTIVE, None, None, NOW, earlier
        )
        == "cerrada"
    )
    assert (
        derive_conversation_status(
            ConversationState.ACTIVE, None, None, NOW, None
        )
        == "cerrada"
    )


def test_bot_after_client_writes_again():
    """R1: si el cliente escribió después del cierre, vuelve a `atendida_por_bot`."""
    later = datetime(2026, 1, 2, 4, 0, tzinfo=timezone.utc)
    assert (
        derive_conversation_status(
            ConversationState.ACTIVE, None, None, NOW, later
        )
        == "atendida_por_bot"
    )


def test_bot_without_closed_case():
    """R1: sin caso abierto ni cierre previo es `atendida_por_bot`."""
    assert (
        derive_conversation_status(ConversationState.ACTIVE, None, None, None, NOW)
        == "atendida_por_bot"
    )


def test_closed_case_does_not_count_as_open():
    """R1: un caso `closed` no decide asesor/pendiente."""
    assert (
        derive_conversation_status(
            ConversationState.ACTIVE, "closed", "700", None, None
        )
        == "atendida_por_bot"
    )


@pytest.mark.parametrize(
    ("state", "expected"),
    [
        (ConversationState.ACTIVE, True),
        (ConversationState.AWAITING_LOGIN, True),
        (ConversationState.NO_ACCESS, True),
        (ConversationState.WITH_ADVISOR, True),
        (ConversationState.NEW, False),
        (ConversationState.AWAITING_CONSENT, False),
        (ConversationState.CLOSED, False),
        (None, False),
    ],
)
def test_only_states_with_content_are_listable(state, expected):
    """R6: se excluyen new, awaiting_consent, closed y la ausencia de estado."""
    assert is_listable_state(state) is expected


def test_status_vocabulary_has_exactly_four_values():
    """R1: el vocabulario de estados visibles es el aprobado."""
    assert CONVERSATION_STATUSES == (
        "atendida_por_bot",
        "atendida_por_asesor",
        "pendiente",
        "cerrada",
    )
