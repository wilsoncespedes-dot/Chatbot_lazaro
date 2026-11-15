"""Notas internas del panel de asesores (#50)."""
from __future__ import annotations

from orchestrator.domain import CaseNote


def _note(
    env,
    panel,
    note_id: str,
    case_id: str = "case-1",
    author_profile_id: str = "700",
    author_username: str = "asesor1",
    body: str = "nota interna",
) -> CaseNote:
    contact = env.repo.get_case_contact(case_id)
    assert contact is not None
    note = CaseNote(
        id=note_id,
        case_id=case_id,
        author_profile_id=author_profile_id,
        author_username=author_username,
        body=body,
        created_at=panel.NOW,
    )
    env.repo.add_case_note(note, contact.id)
    return note


def test_add_note_redirects_and_audits_without_text(env_factory, panel):
    """R1, R32: guarda la nota, redirige al caso y audita sin copiar el texto."""
    env = env_factory()
    profile = panel.login(env)
    panel.link_case(env, "case-1")

    response = env.client.post(
        "/asesor/cases/case-1/notes",
        data={"csrf_token": panel.CSRF, "text": "  gestión interna  "},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/asesor/cases/case-1"
    [(note, contact_id)] = env.repo.case_notes
    assert note.body == "gestión interna"
    assert note.case_id == "case-1"
    assert note.author_profile_id == profile.id
    assert not env.repo.messages and not env.repo.events
    audit = env.repo.panel_audit[-1]
    assert (audit.action, audit.result, audit.case_id) == (
        "note_added",
        "ok",
        "case-1",
    )
    assert audit.target == note.id
    assert "gestión interna" not in str(audit)
    assert contact_id


def test_case_view_shows_notes_separate_from_history(env_factory, panel):
    """R2, R29: notas con autor y fecha en una sección propia."""
    env = env_factory()
    panel.login(env)
    contact = panel.link_case(env, "case-1")
    env.repo.add_message(contact.id, "user", "hola", panel.NOW)
    _note(env, panel, "note-1", body="dato interno")

    response = env.client.get("/asesor/cases/case-1")

    assert response.status_code == 200
    assert "Notas internas" in response.text
    assert "dato interno" in response.text
    assert "asesor1" in response.text
    assert panel.NOW.isoformat() in response.text
    assert response.text.index("Historial") < response.text.index("Notas internas")


def test_view_and_add_require_permission_without_reading_or_writing(env_factory, panel):
    """R3, R4: sin permiso sobre el caso se rechaza con el error de la vista."""
    env = env_factory()
    profile = panel.login(env)
    panel.link_case(env, "case-x")
    panel.link_case(env, "case-y")
    env.repo.add_case_note(
        CaseNote(
            id="note-x",
            case_id="case-x",
            author_profile_id=profile.id,
            author_username=profile.username,
            body="solo caso X",
            created_at=panel.NOW,
        ),
        env.repo.get_case_contact("case-x").id,
    )
    env.handover.authorize_error = "forbidden"

    added = env.client.post(
        "/asesor/cases/case-y/notes",
        data={"csrf_token": panel.CSRF, "text": "no permitida"},
        follow_redirects=False,
    )
    viewed = env.client.get("/asesor/cases/case-y")

    assert added.status_code == 403
    assert viewed.status_code == 403
    assert [note.case_id for note, _ in env.repo.case_notes] == ["case-x"]
    assert "solo caso X" not in viewed.text


def test_note_validation_rejects_empty_and_too_long(env_factory, panel):
    """R5: texto vacío o demasiado largo -> 422 sin guardar."""
    env = env_factory(case_note_max_chars=4)
    panel.login(env)
    panel.link_case(env, "case-1")

    for text in ("   ", "12345"):
        response = env.client.post(
            "/asesor/cases/case-1/notes",
            data={"csrf_token": panel.CSRF, "text": text},
            follow_redirects=False,
        )
        assert response.status_code == 422
        assert 'data-code="validation_error"' in response.text

    assert env.repo.case_notes == []


def test_note_per_case_limit(env_factory, panel):
    """R6: alcanzado CASE_NOTES_MAX_PER_CASE -> 422 sin guardar otra."""
    env = env_factory(case_notes_max_per_case=1)
    panel.login(env)
    panel.link_case(env, "case-1")
    first = env.client.post(
        "/asesor/cases/case-1/notes",
        data={"csrf_token": panel.CSRF, "text": "primera"},
        follow_redirects=False,
    )
    second = env.client.post(
        "/asesor/cases/case-1/notes",
        data={"csrf_token": panel.CSRF, "text": "segunda"},
        follow_redirects=False,
    )

    assert first.status_code == 303
    assert second.status_code == 422
    assert len(env.repo.case_notes) == 1
    assert env.repo.case_notes[0][0].body == "primera"


def test_author_deletes_own_note_and_audits(env_factory, panel):
    """R7, R32: el autor borra la nota y queda auditado con su id."""
    env = env_factory()
    profile = panel.login(env)
    panel.link_case(env, "case-1")
    _note(env, panel, "note-1", author_profile_id=profile.id)

    response = env.client.post(
        "/asesor/cases/case-1/notes/note-1/delete",
        data={"csrf_token": panel.CSRF},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert env.repo.case_notes == []
    audit = env.repo.panel_audit[-1]
    assert (audit.action, audit.result, audit.target) == (
        "note_deleted",
        "ok",
        "note-1",
    )


def test_other_author_cannot_delete_note(env_factory, panel):
    """R8: borrar una nota ajena -> 403 sin borrarla."""
    env = env_factory()
    panel.login(env)
    panel.link_case(env, "case-1")
    _note(env, panel, "note-1", author_profile_id="otro", author_username="otro")

    response = env.client.post(
        "/asesor/cases/case-1/notes/note-1/delete",
        data={"csrf_token": panel.CSRF},
        follow_redirects=False,
    )

    assert response.status_code == 403
    assert len(env.repo.case_notes) == 1
    assert env.repo.panel_audit[-1].result == "forbidden"


def test_missing_note_or_note_from_another_case_returns_404(env_factory, panel):
    """R9: nota inexistente o de otro caso -> 404 sin cambios."""
    env = env_factory(case_notes_max_per_case=50)
    profile = panel.login(env)
    panel.link_case(env, "case-1")
    panel.link_case(env, "case-2")
    _note(env, panel, "note-2", case_id="case-2", author_profile_id=profile.id)

    other_case = env.client.post(
        "/asesor/cases/case-1/notes/note-2/delete",
        data={"csrf_token": panel.CSRF},
        follow_redirects=False,
    )
    missing = env.client.post(
        "/asesor/cases/case-1/notes/no-existe/delete",
        data={"csrf_token": panel.CSRF},
        follow_redirects=False,
    )

    assert other_case.status_code == 404
    assert missing.status_code == 404
    assert "note_not_found" in other_case.text
    assert len(env.repo.case_notes) == 1


def test_note_text_and_author_are_escaped(env_factory, panel):
    """R29: texto de nota y nombre de autor se escapan al renderizar."""
    env = env_factory()
    panel.login(env)
    panel.link_case(env, "case-1")
    author = panel.make_profile(env, "<b>autor</b>", telegram_user_id=701)
    _note(
        env,
        panel,
        "note-1",
        author_profile_id=author.id,
        author_username="<b>autor</b>",
        body="<script>alert(1)</script>",
    )

    response = env.client.get("/asesor/cases/case-1")

    assert "<script>alert(1)</script>" not in response.text
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in response.text
    assert "<b>autor</b>" not in response.text
    assert "&lt;b&gt;autor&lt;/b&gt;" in response.text


def test_notes_require_session_and_csrf(env_factory, panel):
    """R30, R31: sin sesión redirige y sin CSRF responde 403 sin guardar."""
    env = env_factory()
    panel.link_case(env, "case-1")

    anonymous = env.client.post(
        "/asesor/cases/case-1/notes",
        data={"text": "sin sesión"},
        follow_redirects=False,
    )
    assert anonymous.status_code == 303
    assert anonymous.headers["location"] == "/asesor/login"
    assert env.repo.case_notes == []

    panel.login(env)
    no_csrf = env.client.post(
        "/asesor/cases/case-1/notes",
        data={"text": "sin csrf"},
        follow_redirects=False,
    )
    assert no_csrf.status_code == 403
    assert env.repo.case_notes == []


def test_validation_failure_is_audited(env_factory, panel):
    """R34: un fallo de validación queda auditado con su código."""
    env = env_factory(case_note_max_chars=4)
    panel.login(env)
    panel.link_case(env, "case-1")

    env.client.post(
        "/asesor/cases/case-1/notes",
        data={"csrf_token": panel.CSRF, "text": "12345"},
        follow_redirects=False,
    )

    audit = env.repo.panel_audit[-1]
    assert (audit.action, audit.result) == ("note_added", "validation_error")


def test_csrf_failure_is_audited_without_changes(env_factory, panel):
    """R34: sin CSRF no se crea ni borra y queda auditado `forbidden`."""
    env = env_factory()
    profile = panel.login(env)
    panel.link_case(env, "case-1")
    _note(env, panel, "note-1", author_profile_id=profile.id)

    added = env.client.post(
        "/asesor/cases/case-1/notes",
        data={"text": "sin csrf"},
        follow_redirects=False,
    )
    deleted = env.client.post(
        "/asesor/cases/case-1/notes/note-1/delete",
        data={"csrf_token": "otro-token"},
        follow_redirects=False,
    )

    assert (added.status_code, deleted.status_code) == (403, 403)
    assert [note.id for note, _ in env.repo.case_notes] == ["note-1"]
    add_audit, delete_audit = env.repo.panel_audit[-2:]
    assert (add_audit.action, add_audit.result, add_audit.case_id) == (
        "note_added",
        "forbidden",
        "case-1",
    )
    assert (
        delete_audit.action,
        delete_audit.result,
        delete_audit.case_id,
        delete_audit.target,
    ) == ("note_deleted", "forbidden", "case-1", "note-1")
    assert "sin csrf" not in str(add_audit)
