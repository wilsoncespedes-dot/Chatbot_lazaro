"""Supresión y retención de notas y asignaciones de etiquetas (#50)."""
from __future__ import annotations

from datetime import timedelta

from orchestrator.adapters.repository import PostgresRepository
from orchestrator.domain import CaseNote, CaseTag, ClientSession, execute_suppression


def _note(env, panel, note_id: str, case_id: str, contact_id: str, at=None):
    note = CaseNote(
        id=note_id,
        case_id=case_id,
        author_profile_id="700",
        author_username="asesor1",
        body=f"nota {note_id}",
        created_at=at or panel.NOW,
    )
    env.repo.add_case_note(note, contact_id)
    return note


def _tag(env, panel, tag_id: str = "tag-1", name: str = "Urgente") -> CaseTag:
    tag = CaseTag(id=tag_id, name=name, active=True)
    env.repo.create_case_tag(tag, name.casefold(), panel.NOW)
    return tag


def test_suppression_deletes_notes_and_assignments_of_client_contacts(env_factory, panel):
    """R35, R36: borra notas/asignaciones del cliente y conserva el resto."""
    env = env_factory()
    client = env.repo.create_profile("cliente1", "cliente", "hash", panel.NOW)
    admin = env.repo.create_profile("admin1", "admin", "hash", panel.NOW)
    target = panel.link_case(env, "case-1", user="10", chat="100")
    other = panel.link_case(env, "case-2", user="11", chat="101")
    tag = _tag(env, panel)
    _note(env, panel, "note-target", "case-1", target.id)
    _note(env, panel, "note-other", "case-2", other.id)
    for case_id, contact in (("case-1", target), ("case-2", other)):
        env.repo.add_case_tag(case_id, tag.id, contact.id, "700", panel.NOW)
    env.repo.client_sessions["s1"] = ClientSession(
        id="s1",
        profile_id=client.id,
        contact_id=target.id,
        started_at=panel.NOW - timedelta(hours=1),
        last_activity_at=panel.NOW,
    )
    env.repo.create_or_get_pending_suppression(
        "req-1", client.id, target.id, "telegram", panel.NOW
    )

    execution = execute_suppression("req-1", admin.id, env.settings, env.adapters)

    assert execution.deleted["case_notes"] == 1
    assert [note.id for note, _ in env.repo.case_notes] == ["note-other"]
    assert env.repo.count_case_tags("case-1") == 0
    assert env.repo.count_case_tags("case-2") == 1
    assert env.repo.get_case_tag(tag.id) is not None


def test_retention_purge_deletes_old_and_inactive_notes(env_factory, panel):
    """R37: borra notas antiguas y las de contactos inactivos, con conteo."""
    env = env_factory()
    active = panel.link_case(env, "case-1", user="10", chat="100")
    inactive = panel.link_case(
        env,
        "case-2",
        user="11",
        chat="101",
        created_at=panel.NOW - timedelta(days=40),
    )
    env.repo.contact_created_at[inactive.id] = panel.NOW - timedelta(days=40)
    tag = _tag(env, panel)
    _note(
        env,
        panel,
        "note-old",
        "case-1",
        active.id,
        at=panel.NOW - timedelta(days=31),
    )
    _note(env, panel, "note-recent", "case-1", active.id)
    _note(env, panel, "note-inactive", "case-2", inactive.id)
    env.repo.add_case_tag("case-1", tag.id, active.id, "700", panel.NOW)
    env.repo.add_case_tag("case-2", tag.id, inactive.id, "700", panel.NOW)

    counts = env.repo.purge_personal_data(
        panel.NOW - timedelta(days=30), panel.NOW
    )

    assert counts["case_notes"] == 2
    assert [note.id for note, _ in env.repo.case_notes] == ["note-recent"]
    assert env.repo.count_case_tags("case-1") == 1
    assert env.repo.count_case_tags("case-2") == 0


def test_rejected_privacy_notice_deletes_notes_and_assignments(env_factory, panel):
    """R38: el borrado del contenido del contacto elimina notas y asignaciones."""
    env = env_factory()
    contact = panel.link_case(env, "case-1", user="10", chat="100")
    tag = _tag(env, panel)
    _note(env, panel, "note-1", "case-1", contact.id)
    env.repo.add_case_tag("case-1", tag.id, contact.id, "700", panel.NOW)

    env.repo.delete_contact_content("telegram", "10")

    assert env.repo.case_notes == []
    assert env.repo.case_tag_assignments == []
    assert env.repo.get_case_tag(tag.id) is not None


class _Cursor:
    def __init__(self, log: list) -> None:
        self.log = log

    def execute(self, sql: str, params=()) -> None:
        self.log.append((sql, tuple(params)))

    def fetchall(self):
        sql = self.log[-1][0]
        if sql.startswith("SELECT id, external_chat_id, chat_id FROM contacts"):
            return [("c1", "100", 100)]
        return []


class _Conn:
    def __init__(self, log: list) -> None:
        self.log = log

    def cursor(self):
        return _Cursor(self.log)

    def commit(self) -> None:
        pass

    def rollback(self) -> None:
        pass


def test_postgres_delete_contact_content_removes_annotations_with_parameters():
    """R38: el borrado Postgres es parametrizado y toca las tablas nuevas."""
    log: list = []
    repo = PostgresRepository("postgresql://x", connect=lambda: _Conn(log))

    repo.delete_contact_content("telegram", "10")

    statements = [(sql, params) for sql, params in log if not sql.startswith("CREATE")]
    notes = next(sql for sql, _ in statements if sql.startswith("DELETE FROM case_notes"))
    assignments = next(
        sql
        for sql, _ in statements
        if sql.startswith("DELETE FROM case_tag_assignments")
    )
    assert "contact_id = %s" in notes
    assert "contact_id = %s" in assignments
    assert all("10" not in sql for sql, _ in statements)
