"""Estados visibles de la bandeja unificada de conversaciones (#68). Puro y sin IO."""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from .states import ConversationState

ConversationStatus = Literal[
    "atendida_por_bot", "atendida_por_asesor", "pendiente", "cerrada"
]
CONVERSATION_STATUSES: tuple[ConversationStatus, ...] = (
    "atendida_por_bot",
    "atendida_por_asesor",
    "pendiente",
    "cerrada",
)
LISTABLE_STATES: frozenset[str] = frozenset(
    {
        ConversationState.ACTIVE.value,
        ConversationState.AWAITING_LOGIN.value,
        ConversationState.NO_ACCESS.value,
        ConversationState.WITH_ADVISOR.value,
    }
)


def _state_value(state: ConversationState | str | None) -> str | None:
    if state is None:
        return None
    if isinstance(state, ConversationState):
        return state.value
    return str(state)


def is_listable_state(state: ConversationState | str | None) -> bool:
    """R6: solo las conversaciones con contenido y atención posible."""
    value = _state_value(state)
    return value is not None and value in LISTABLE_STATES


def derive_conversation_status(
    state: ConversationState | str | None,
    open_case_status: str | None,
    open_case_advisor: str | None,
    last_closed_at: datetime | None,
    last_user_at: datetime | None,
) -> ConversationStatus:
    """R1: deriva el estado visible: asesor > pendiente > cerrada > bot."""
    if open_case_status is not None and open_case_status != "closed":
        if open_case_advisor:
            return "atendida_por_asesor"
        return "pendiente"
    if _state_value(state) == ConversationState.WITH_ADVISOR:
        return "pendiente"
    if last_closed_at is not None and (
        last_user_at is None or last_user_at <= last_closed_at
    ):
        return "cerrada"
    return "atendida_por_bot"
