"""Tomar conversación: atómica, idempotente, permisos y auditoría (#68 R3, R5)."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import pytest
from lazaro_contracts import CaseListItem

from orchestrator.domain import CaseChanged, take_conversation
from orchestrator.states import ConversationState


_NOW = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)


def _contact(env, user: str = "10", chat: str = "100"):
    return env.repo.get_or_create_channel_contact(
        "telegram", user, chat, env.clock()
    )


def _bot_conversation(env):
    contact = _contact(env)
    env.repo.set_conversation_state(contact.id, ConversationState.ACTIVE, env.clock())
    env.repo.add_message(contact.id, "user", "hola", env.clock())
    return contact


def _case(case_id: str, status: str, advisor_id: str | None = None) -> CaseListItem:
    return CaseListItem(
        case_id=case_id,
        status=status,  # type: ignore[arg-type]
        created_at=_NOW,
        actions=[],
        advisor_id=advisor_id,
    )


def _take(env, contact_id: str, csrf: str, follow_redirects: bool = False):
    return env.client.post(
        f"/asesor/conversaciones/{contact_id}/tomar",
        data={"csrf_token": csrf},
        follow_redirects=follow_redirects,
    )


def test_take_creates_links_and_moves_to_with_advisor(env_factory, panel):
    """R3: crea caso, lo vincula, cambia estado y audita."""
    env = env_factory()
    profile = panel.login(env)
    contact = _bot_conversation(env)
    env.handover.take_case_id = "case-new"
    env.handover.take_created = True

    response = _take(env, contact.id, panel.CSRF)

    assert response.status_code == 303
    assert response.headers["location"] == "/asesor/cases/case-new"
    assert len(env.handover.taken) == 1
    assert env.handover.taken[0].contact_id == contact.id
    assert env.handover.taken[0].advisor_id == profile.id
    assert env.repo.case_links["case-new"] == contact.id
    assert env.repo.get_conversation_state(contact.id) == ConversationState.WITH_ADVISOR
    assert any(
        event.type == "advisor_taken"
        and event.reason == "case:case-new advisor:700"
        for event in env.repo.events
    )
    audit = env.repo.panel_audit[-1]
    assert audit.action == "conversation_take"
    assert audit.result == "ok"
    assert audit.target == f"conversation:{contact.id}"
    assert env.gateway.sent == []


def test_take_pending_case_assigns_without_creating_another(env_factory, panel):
    """R3: un caso abierto sin asesor se asigna, created=false."""
    env = env_factory()
    panel.login(env)
    contact = _bot_conversation(env)
    env.repo.set_conversation_state(contact.id, ConversationState.WITH_ADVISOR, env.clock())
    env.repo.link_case("case-open", contact.id, env.clock())
    env.handover.case_list = [_case("case-open", "open", None)]
    env.handover.take_case_id = "case-open"
    env.handover.take_created = False

    response = _take(env, contact.id, panel.CSRF)

    assert response.status_code == 303
    assert response.headers["location"] == "/asesor/cases/case-open"
    assert len(env.handover.taken) == 1
    assert len(env.repo.case_links) == 1
    assert env.repo.case_links["case-open"] == contact.id
    assert env.repo.get_conversation_state(contact.id) == ConversationState.WITH_ADVISOR


def test_take_is_idempotent_after_the_advisor_already_took(env_factory, panel):
    """R3: repetir la toma del mismo asesor no crea otro caso."""
    env = env_factory()
    panel.login(env)
    contact = _bot_conversation(env)
    env.repo.set_conversation_state(contact.id, ConversationState.WITH_ADVISOR, env.clock())
    env.repo.link_case("case-1", contact.id, env.clock())
    env.handover.case_list = [_case("case-1", "assigned", "700")]

    response = _take(env, contact.id, panel.CSRF)

    assert response.status_code == 303
    assert response.headers["location"] == "/asesor/cases/case-1"
    assert env.handover.taken == []


def test_take_assigned_to_another_advisor_is_409(env_factory, panel):
    """R3, R5: un caso de otro asesor responde 409 sin modificarlo."""
    env = env_factory()
    panel.login(env)
    contact = _bot_conversation(env)
    env.repo.set_conversation_state(contact.id, ConversationState.WITH_ADVISOR, env.clock())
    env.repo.link_case("case-other", contact.id, env.clock())
    env.handover.case_list = [_case("case-other", "assigned", "701")]

    response = _take(env, contact.id, panel.CSRF)

    assert response.status_code == 409
    assert 'data-code="case_changed"' in response.text
    assert env.handover.taken == []
    assert env.repo.panel_audit[-1].result == "case_changed"


def test_two_advisors_concurrently_only_one_takes(env_factory, panel):
    """R3: dos asesores a la vez dejan un único caso y el otro recibe 409."""
    env = env_factory()
    panel.make_profile(env, "asesor1", "asesor", 701)
    panel.make_profile(env, "asesor2", "asesor", 702)
    contact = _bot_conversation(env)
    first = env.repo.get_profile("701")
    second = env.repo.get_profile("702")

    def attempt(profile):
        try:
            return take_conversation(contact.id, profile, env.settings, env.adapters)
        except CaseChanged as exc:
            return exc

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(attempt, (first, second)))

    conflicts = [result for result in results if isinstance(result, CaseChanged)]
    winners = [result for result in results if isinstance(result, str)]
    assert len(conflicts) == 1
    assert len(winners) == 1
    assert len(env.repo.case_links) == 1
    assert env.repo.get_conversation_state(contact.id) == ConversationState.WITH_ADVISOR


def test_handover_unavailable_returns_502_without_changing_state(env_factory, panel):
    """R3: un fallo de handover no cambia la conversación."""
    env = env_factory()
    panel.login(env)
    contact = _bot_conversation(env)
    env.handover.fail_take = True

    response = _take(env, contact.id, panel.CSRF)

    assert response.status_code == 502
    assert 'data-code="upstream_error"' in response.text
    assert env.repo.get_conversation_state(contact.id) == ConversationState.ACTIVE
    assert env.repo.case_links == {}
    assert not any(event.type == "advisor_taken" for event in env.repo.events)
    assert env.repo.panel_audit[-1].result == "upstream_error"


@pytest.mark.parametrize(
    ("take_error", "status", "code"),
    [("forbidden", 403, "forbidden"), ("case_changed", 409, "case_changed")],
)
def test_take_maps_handover_denials(env_factory, panel, take_error, status, code):
    """R3, R5: los rechazos de handover se traducen a la página fija."""
    env = env_factory()
    panel.login(env)
    contact = _bot_conversation(env)
    env.handover.take_error = take_error

    response = _take(env, contact.id, panel.CSRF)

    assert response.status_code == status
    assert f'data-code="{code}"' in response.text
    assert env.repo.get_conversation_state(contact.id) == ConversationState.ACTIVE


def test_take_excluded_state_is_404_without_creating_case(env_factory, panel):
    """R3, R6: un estado excluido responde 404 y no crea caso."""
    env = env_factory()
    panel.login(env)
    contact = _contact(env)
    env.repo.set_conversation_state(contact.id, ConversationState.NEW, env.clock())
    env.repo.add_message(contact.id, "user", "no listable", env.clock())

    response = _take(env, contact.id, panel.CSRF)

    assert response.status_code == 404
    assert env.handover.taken == []
    assert env.repo.case_links == {}


def test_take_bot_is_403_when_visibility_is_disabled(env_factory, panel):
    """R5: con la visibilidad desactivada no se puede tomar una conversación bot."""
    env = env_factory(panel_bot_conversations_visible=False)
    panel.login(env)
    contact = _bot_conversation(env)

    response = _take(env, contact.id, panel.CSRF)

    assert response.status_code == 403
    assert env.handover.taken == []
    assert env.repo.get_conversation_state(contact.id) == ConversationState.ACTIVE


def test_take_without_valid_csrf_is_403_without_effects(env_factory, panel):
    """R3: sin CSRF válido responde 403 y no llama a handover."""
    env = env_factory()
    panel.login(env)
    contact = _bot_conversation(env)

    response = env.client.post(
        f"/asesor/conversaciones/{contact.id}/tomar",
        data={"csrf_token": "incorrecto"},
        follow_redirects=False,
    )

    assert response.status_code == 403
    assert env.handover.taken == []
    assert env.repo.get_conversation_state(contact.id) == ConversationState.ACTIVE
    assert env.repo.panel_audit[-1].action == "conversation_take"
    assert env.repo.panel_audit[-1].result == "forbidden"


def test_unlinked_advisor_can_take(env_factory, panel):
    """R2, R3: un asesor sin Telegram vinculado puede tomar una conversación."""
    env = env_factory()
    profile = panel.login(env, telegram_user_id=None)
    contact = _bot_conversation(env)
    env.handover.take_case_id = "case-new"
    env.handover.take_created = True

    response = _take(env, contact.id, panel.CSRF)

    assert response.status_code == 303
    assert response.headers["location"] == "/asesor/cases/case-new"
    assert len(env.handover.taken) == 1
    assert env.handover.taken[0].advisor_id == profile.id
    assert env.repo.get_conversation_state(contact.id) == ConversationState.WITH_ADVISOR


def test_non_advisor_role_is_denied(env_factory, panel):
    """R5: un rol que no es asesor ni supervisor no accede a las rutas nuevas."""
    env = env_factory()
    panel.login(env, role="responsable_datos")
    contact = _bot_conversation(env)

    response = _take(env, contact.id, panel.CSRF)

    assert response.status_code == 403
    assert env.handover.taken == []


def test_supervisor_cannot_take_another_advisors_conversation(env_factory, panel):
    """R3, R5: el supervisor no toma un caso ya asignado; usa la reasignación."""
    env = env_factory()
    panel.login(env, role="supervisor")
    contact = _bot_conversation(env)
    env.repo.set_conversation_state(contact.id, ConversationState.WITH_ADVISOR, env.clock())
    env.repo.link_case("case-other", contact.id, env.clock())
    env.handover.case_list = [_case("case-other", "assigned", "701")]

    response = _take(env, contact.id, panel.CSRF)

    assert response.status_code == 409
    assert 'data-code="case_changed"' in response.text
    assert env.handover.reassigned == []
    assert env.handover.taken == []


def test_bot_is_silent_after_take(env_factory, panel):
    """R3, R4: tras tomar, el mensaje del cliente va al asesor y no al RAG/LLM."""
    env = env_factory()
    panel.login(env)
    contact = _bot_conversation(env)
    env.handover.take_case_id = "case-new"
    env.handover.client_message_status = "available_in_panel"
    assert _take(env, contact.id, panel.CSRF).status_code == 303
    env.llm.calls.clear()

    env.post("sigo aquí", update_id=2, user=10, chat=100)

    assert env.llm.calls == []
    assert env.rag.calls == []
    assert env.handover.client_messages
    assert any(
        event.type == "forwarded_to_advisor" for event in env.repo.events
    )


def test_new_routes_do_not_expose_suppression_execution(env_factory, panel):
    """R5: las rutas nuevas no ejecutan ni muestran la cola de supresión."""
    env = env_factory()
    panel.login(env)
    contact = _bot_conversation(env)

    page = env.client.get(f"/asesor/conversaciones/{contact.id}").text

    assert "/supresiones/" not in page
    assert "Ejecutar supresión" not in page
