"""Estado compartido del roster de asesores en el orquestador (#48)."""
from __future__ import annotations

import pytest

from orchestrator.domain import (
    RosterOutOfSync,
    ensure_roster_ready,
    publish_advisor_roster,
)

PASSWORD = "clave-segura-123"


def test_begin_change_marks_pending_and_publish_marks_synced(env):
    """R13, R34, R50: el cambio de roster queda pendiente hasta publicarlo."""
    generation = env.repo.begin_advisor_roster_change()
    assert (generation, env.repo.advisor_roster_status) == (1, "pending")

    assert publish_advisor_roster(env.adapters) is True

    assert env.repo.advisor_roster_status == "synced"
    assert env.handover.roster_syncs
    assert env.handover.roster_syncs[-1].generation == 1


def test_ensure_roster_ready_syncs_pending_state(env):
    """R13, R37: una sincronización exitosa deja el roster listo."""
    env.repo.begin_advisor_roster_change()

    ensure_roster_ready(env.adapters)

    assert env.repo.advisor_roster_status == "synced"
    assert env.handover.roster_syncs[-1].generation == 1


def test_failed_sync_keeps_pending_and_fails_closed(env):
    """R37: si la sincronización falla, el estado sigue pending."""
    env.repo.begin_advisor_roster_change()
    env.handover.fail_sync = True

    assert publish_advisor_roster(env.adapters) is False
    assert env.repo.advisor_roster_status == "pending"

    with pytest.raises(RosterOutOfSync):
        ensure_roster_ready(env.adapters)
    assert env.repo.advisor_roster_status == "pending"


def test_mark_synced_only_for_current_generation(env):
    """R50: una generación obsoleta no puede marcar el roster como sincronizado."""
    first = env.repo.begin_advisor_roster_change()
    second = env.repo.begin_advisor_roster_change()

    assert env.repo.mark_advisor_roster_synced(first) is False
    assert env.repo.advisor_roster_status == "pending"

    assert env.repo.mark_advisor_roster_synced(second) is True
    assert env.repo.advisor_roster_status == "synced"


def test_handover_with_pending_roster_calls_no_handover(env):
    """R35: con el roster pending el orquestador no llama a handover."""
    env.repo.advisor_roster_status = "pending"
    env.handover.fail_sync = True

    env.post(text="quiero un asesor")

    assert env.handover.requests == []
    assert env.repo.case_links == {}
    assert not [event for event in env.repo.events if event.type == "handover"]


def test_creating_advisor_profile_publishes_the_roster(env):
    """R13, R34: crear un perfil asesor incrementa la generación y la publica."""
    env.settings.password_hash_iterations = 1000

    response = env.client.post(
        "/profiles",
        json={"username": "asesor1", "role": "asesor", "password": PASSWORD},
        headers={"X-Service-Token": env.settings.service_token},
    )

    assert response.status_code == 201
    assert env.repo.advisor_roster_status == "synced"
    assert env.repo.advisor_roster_generation == 1
    published = env.handover.roster_syncs[-1]
    assert published.generation == 1
    assert any(
        entry.profile_id == response.json()["id"] and entry.role == "asesor"
        for entry in published.profiles
    )
