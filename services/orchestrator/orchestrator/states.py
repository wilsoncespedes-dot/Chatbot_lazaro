"""Máquina de estados de la conversación, aislada para evitar importaciones circulares."""
from __future__ import annotations

from enum import StrEnum


class ConversationState(StrEnum):
    """Siete estados de la conversación de cliente (R1)."""

    NEW = "new"
    AWAITING_CONSENT = "awaiting_consent"
    CLOSED = "closed"
    AWAITING_LOGIN = "awaiting_login"
    ACTIVE = "active"
    WITH_ADVISOR = "with_advisor"
    NO_ACCESS = "no_access"


class ConversationEvent(StrEnum):
    FIRST_MESSAGE = "first_message"
    ACCEPT_BUTTON = "accept_button"
    REJECT_BUTTON = "reject_button"
    POLICY_QUESTION = "policy_question"
    UNCONFIRMED_ACCEPTANCE = "unconfirmed_acceptance"
    RESTART_MESSAGE = "restart_message"
    ESCALATION_REQUESTED = "escalation_requested"
    SUPPRESSION_REQUESTED = "suppression_requested"
    LOGIN_VALID = "login_valid"
    LOGIN_EXPIRED = "login_expired"
    CREDENTIAL_EXPIRED = "credential_expired"
    CREDENTIAL_RENEWED = "credential_renewed"
    ESCALATED = "escalated"
    ADVISOR_RESOLVED = "advisor_resolved"
    ADVISOR_RETURNED = "advisor_returned"
    SESSION_CLOSED = "session_closed"
    SESSION_IDLE_TIMEOUT = "session_idle_timeout"
    UNSUPPORTED_MESSAGE = "unsupported_message"


_TRANSITIONS: dict[tuple[ConversationState, ConversationEvent], ConversationState] = {
    (ConversationState.NEW, ConversationEvent.FIRST_MESSAGE):
        ConversationState.AWAITING_CONSENT,
    (ConversationState.AWAITING_CONSENT, ConversationEvent.ACCEPT_BUTTON):
        ConversationState.AWAITING_LOGIN,
    (ConversationState.AWAITING_CONSENT, ConversationEvent.REJECT_BUTTON):
        ConversationState.CLOSED,
    (ConversationState.AWAITING_CONSENT, ConversationEvent.POLICY_QUESTION):
        ConversationState.AWAITING_CONSENT,
    (ConversationState.AWAITING_CONSENT, ConversationEvent.UNCONFIRMED_ACCEPTANCE):
        ConversationState.AWAITING_CONSENT,
    (ConversationState.CLOSED, ConversationEvent.RESTART_MESSAGE):
        ConversationState.NEW,
    (ConversationState.AWAITING_LOGIN, ConversationEvent.LOGIN_VALID):
        ConversationState.ACTIVE,
    (ConversationState.AWAITING_LOGIN, ConversationEvent.LOGIN_EXPIRED):
        ConversationState.NO_ACCESS,
    (ConversationState.ACTIVE, ConversationEvent.ESCALATED):
        ConversationState.WITH_ADVISOR,
    (ConversationState.ACTIVE, ConversationEvent.CREDENTIAL_EXPIRED):
        ConversationState.NO_ACCESS,
    (ConversationState.ACTIVE, ConversationEvent.SESSION_CLOSED):
        ConversationState.AWAITING_LOGIN,
    (ConversationState.ACTIVE, ConversationEvent.SESSION_IDLE_TIMEOUT):
        ConversationState.AWAITING_LOGIN,
    (ConversationState.WITH_ADVISOR, ConversationEvent.ADVISOR_RESOLVED):
        ConversationState.ACTIVE,
    (ConversationState.WITH_ADVISOR, ConversationEvent.ADVISOR_RETURNED):
        ConversationState.ACTIVE,
    (ConversationState.NO_ACCESS, ConversationEvent.CREDENTIAL_RENEWED):
        ConversationState.ACTIVE,
    (ConversationState.NO_ACCESS, ConversationEvent.SESSION_CLOSED):
        ConversationState.AWAITING_LOGIN,
    (ConversationState.NO_ACCESS, ConversationEvent.SESSION_IDLE_TIMEOUT):
        ConversationState.AWAITING_LOGIN,
    (ConversationState.NO_ACCESS, ConversationEvent.ESCALATION_REQUESTED):
        ConversationState.WITH_ADVISOR,
    (ConversationState.NO_ACCESS, ConversationEvent.SUPPRESSION_REQUESTED):
        ConversationState.WITH_ADVISOR,
}


def transition_state(
    state: ConversationState, event: ConversationEvent
) -> ConversationState:
    """R1: reductor puro `(estado, evento) -> estado`; lo no permitido no cambia."""
    if event == ConversationEvent.UNSUPPORTED_MESSAGE:
        return state
    return _TRANSITIONS.get((state, event), state)
