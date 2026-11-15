"""Etiquetas de caso y filtro de la bandeja (#50)."""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from orchestrator.annotations import normalize_tag_key
from orchestrator.domain import CaseTag, advisor_case_view, advisor_inbox


def _tag(
    env,
    panel,
    tag_id: str = "tag-1",
    name: str = "Urgente",
    active: bool = True,
) -> CaseTag:
    tag = CaseTag(id=tag_id, name=name, active=active)
    assert env.repo.create_case_tag(tag, normalize_tag_key(name), panel.NOW) is True
    return tag


def _assign(env, panel, case_id: str, tag_id: str) -> None:
    contact = panel.link_case(env, case_id)
    env.repo.add_case_tag(case_id, tag_id, contact.id, "700", panel.NOW)


def test_admin_creates_renames_and_toggles_preserving_assignments(env_factory, panel):
    """R14-R16, R33: CRUD de etiquetas conserva id y asignaciones."""
    env = env_factory()
    panel.login_admin(env)

    created = env.client.post(
        "/admin/etiquetas",
        data={"csrf_token": panel.CSRF, "name": "  Pago  "},
        follow_redirects=False,
    )
    assert created.status_code == 303
    [tag] = env.repo.list_case_tags()
    assert (tag.name, tag.active) == ("Pago", True)
    env.repo.add_case_tag("case-1", tag.id, "c1", "700", panel.NOW)

    renamed = env.client.post(
        f"/admin/etiquetas/{tag.id}",
        data={"csrf_token": panel.CSRF, "name": "Cobros"},
        follow_redirects=False,
    )
    assert renamed.status_code == 303
    assert env.repo.get_case_tag(tag.id).name == "Cobros"
    assert env.repo.count_case_tags("case-1") == 1

    off = env.client.post(
        f"/admin/etiquetas/{tag.id}/activa",
        data={"csrf_token": panel.CSRF, "active": "0"},
        follow_redirects=False,
    )
    on = env.client.post(
        f"/admin/etiquetas/{tag.id}/activa",
        data={"csrf_token": panel.CSRF, "active": "1"},
        follow_redirects=False,
    )
    assert (off.status_code, on.status_code) == (303, 303)
    assert env.repo.get_case_tag(tag.id).active is True
    assert env.repo.count_case_tags("case-1") == 1

    actions = [row.action for row in env.repo.panel_audit]
    assert "tag_created" in actions
    assert "tag_renamed" in actions
    assert actions.count("tag_active_changed") == 2
    assert all(row.target == tag.id for row in env.repo.panel_audit if row.target)


def test_duplicate_tag_name_is_case_insensitive(env_factory, panel):
    """R18: nombre repetido sin distinguir mayúsculas -> 409 sin crear."""
    env = env_factory()
    first = _tag(env, panel, name="Urgente")
    panel.login_admin(env)

    response = env.client.post(
        "/admin/etiquetas",
        data={"csrf_token": panel.CSRF, "name": "  urgente "},
        follow_redirects=False,
    )

    assert response.status_code == 409
    assert "tag_name_taken" in response.text
    assert [tag.id for tag in env.repo.list_case_tags()] == [first.id]
    assert env.repo.panel_audit[-1].result == "tag_name_taken"


@pytest.mark.parametrize("name", ["", "   ", "123456", "a\x00b"])
def test_invalid_tag_names_are_rejected(env_factory, panel, name):
    """R17: vacío, control o demasiado largo -> 422 sin crear."""
    env = env_factory(case_tag_name_max_chars=5)
    panel.login_admin(env)

    response = env.client.post(
        "/admin/etiquetas",
        data={"csrf_token": panel.CSRF, "name": name},
        follow_redirects=False,
    )

    assert response.status_code == 422
    assert env.repo.case_tags == {}


def test_non_admin_cannot_manage_tags(env_factory, panel):
    """R19: un perfil no admin recibe 403 y no modifica etiquetas."""
    env = env_factory()
    panel.login(env)
    env.client.cookies.set("admin_session", "asesor-session")

    read = env.client.get("/admin/etiquetas", follow_redirects=False)
    write = env.client.post(
        "/admin/etiquetas",
        data={"csrf_token": panel.CSRF, "name": "No"},
        follow_redirects=False,
    )

    assert read.status_code == 403
    assert write.status_code == 403
    assert env.repo.case_tags == {}


def test_assign_is_idempotent_and_remove_works(env_factory, panel):
    """R20, R21, R33: asignar dos veces no duplica y quitar elimina."""
    env = env_factory()
    profile = panel.login(env)
    panel.link_case(env, "case-1")
    tag = _tag(env, panel)

    for _ in range(2):
        response = env.client.post(
            "/asesor/cases/case-1/tags",
            data={"csrf_token": panel.CSRF, "tag_id": tag.id},
            follow_redirects=False,
        )
        assert response.status_code == 303

    assert env.repo.count_case_tags("case-1") == 1
    assert env.repo.panel_audit[-1].action == "tag_assigned"
    assert env.repo.panel_audit[-1].target == tag.id

    removed = env.client.post(
        f"/asesor/cases/case-1/tags/{tag.id}/remove",
        data={"csrf_token": panel.CSRF},
        follow_redirects=False,
    )
    assert removed.status_code == 303
    assert env.repo.count_case_tags("case-1") == 0
    assert env.repo.panel_audit[-1].action == "tag_removed"
    assert env.repo.panel_audit[-1].target == tag.id
    assert profile.id


def test_disabled_or_missing_tag_cannot_be_assigned(env_factory, panel):
    """R22: etiqueta desactivada o inexistente -> 422 sin asignar."""
    env = env_factory()
    panel.login(env)
    panel.link_case(env, "case-1")
    disabled = _tag(env, panel, tag_id="tag-off", name="Vieja", active=False)

    for tag_id in (disabled.id, "no-existe"):
        response = env.client.post(
            "/asesor/cases/case-1/tags",
            data={"csrf_token": panel.CSRF, "tag_id": tag_id},
            follow_redirects=False,
        )
        assert response.status_code == 422

    assert env.repo.count_case_tags("case-1") == 0
    assert env.repo.panel_audit[-1].result == "validation_error"


def test_case_tag_limit(env_factory, panel):
    """R23: alcanzado CASE_TAGS_MAX_PER_CASE -> 422 sin asignar."""
    env = env_factory(case_tags_max_per_case=1)
    panel.login(env)
    panel.link_case(env, "case-1")
    first = _tag(env, panel, tag_id="tag-1", name="Primera")
    second = _tag(env, panel, tag_id="tag-2", name="Segunda")

    env.client.post(
        "/asesor/cases/case-1/tags",
        data={"csrf_token": panel.CSRF, "tag_id": first.id},
    )
    response = env.client.post(
        "/asesor/cases/case-1/tags",
        data={"csrf_token": panel.CSRF, "tag_id": second.id},
        follow_redirects=False,
    )

    assert response.status_code == 422
    assert env.repo.count_case_tags("case-1") == 1


def test_assign_and_remove_require_case_permission(env_factory, panel):
    """R24: sin permiso sobre el caso no se asigna ni se quita."""
    env = env_factory()
    panel.login(env)
    panel.link_case(env, "case-1")
    tag = _tag(env, panel)
    env.repo.add_case_tag("case-1", tag.id, "c1", "700", panel.NOW)
    env.handover.authorize_error = "forbidden"

    assigned = env.client.post(
        "/asesor/cases/case-1/tags",
        data={"csrf_token": panel.CSRF, "tag_id": tag.id},
        follow_redirects=False,
    )
    removed = env.client.post(
        f"/asesor/cases/case-1/tags/{tag.id}/remove",
        data={"csrf_token": panel.CSRF},
        follow_redirects=False,
    )

    assert assigned.status_code == 403
    assert removed.status_code == 403
    assert env.repo.count_case_tags("case-1") == 1
    assert env.repo.panel_audit[-2].result == "forbidden"
    assert env.repo.panel_audit[-1].result == "forbidden"


def test_tag_filter_combines_with_channel_and_assignment(env_factory, panel):
    """R26, R27: el filtro se combina y se valida antes de consultar handover."""
    env = env_factory()
    panel.login(env)
    panel.link_case(env, "case-tg")
    panel.link_case(env, "case-wa", channel="whatsapp", user="57300", chat="57301")
    selected = _tag(env, panel, "tag-a", "Importante")
    _tag(env, panel, "tag-off", "Antigua", active=False)
    _assign(env, panel, "case-tg", selected.id)
    _assign(env, panel, "case-wa", selected.id)
    env.handover.case_list = [
        panel.case_item("case-tg", "open", created_at=panel.NOW),
        panel.case_item(
            "case-wa",
            "assigned",
            ["reply", "close"],
            created_at=panel.NOW + timedelta(minutes=1),
        ),
    ]

    both = env.client.get(f"/asesor/cases?tag={selected.id}")
    only_telegram = env.client.get(
        f"/asesor/cases?tag={selected.id}&canal=telegram"
    )
    unassigned = env.client.get(
        f"/asesor/cases?tag={selected.id}&asignacion=sin_asignar"
    )

    assert both.status_code == 200
    assert "case-tg" in both.text and "case-wa" in both.text
    assert "case-tg" in only_telegram.text and "case-wa" not in only_telegram.text
    assert "case-tg" in unassigned.text and "case-wa" not in unassigned.text

    listed_before = len(env.handover.listed)
    for invalid in ("tag-off", "no-existe", "x" * 65):
        response = env.client.get(f"/asesor/cases?tag={invalid}")
        assert response.status_code == 422
    assert len(env.handover.listed) == listed_before


def test_case_view_lists_assigned_and_assignable_tags(env_factory, panel):
    """R25: solo las activas sin asignar se ofrecen para asignar."""
    env = env_factory()
    profile = panel.login(env)
    panel.link_case(env, "case-1")
    active = _tag(env, panel, "tag-a", "Activa")
    disabled = _tag(env, panel, "tag-b", "Inactiva", active=False)
    free = _tag(env, panel, "tag-c", "Libre")
    for tag in (active, disabled):
        env.repo.add_case_tag("case-1", tag.id, "c1", "700", panel.NOW)

    view = advisor_case_view("case-1", profile, env.settings, env.adapters)
    page = env.client.get("/asesor/cases/case-1")

    assert [tag.id for tag in view.tags] == ["tag-a", "tag-b"]
    assert [tag.id for tag in view.assignable_tags] == ["tag-c"]
    assert "Activa" in page.text
    assert "Inactiva (inactiva)" in page.text
    assert "Libre" in page.text
    assert free.id in page.text


def test_tag_names_are_escaped(env_factory, panel):
    """R29: el nombre de la etiqueta se escapa al renderizar."""
    env = env_factory()
    _tag(env, panel, name="<script>alert(1)</script>")
    panel.login_admin(env)

    response = env.client.get("/admin/etiquetas")

    assert response.status_code == 200
    assert "<script>alert(1)</script>" not in response.text
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in response.text


def test_tag_routes_require_session_and_csrf(env_factory, panel):
    """R30, R31: sin sesión redirige y sin CSRF responde 403 sin cambios."""
    env = env_factory()
    panel.link_case(env, "case-1")
    tag = _tag(env, panel)

    anonymous = env.client.post(
        "/asesor/cases/case-1/tags",
        data={"tag_id": tag.id},
        follow_redirects=False,
    )
    assert anonymous.status_code == 303
    assert anonymous.headers["location"] == "/asesor/login"
    assert env.repo.count_case_tags("case-1") == 0

    panel.login(env)
    no_csrf = env.client.post(
        "/asesor/cases/case-1/tags",
        data={"tag_id": tag.id},
        follow_redirects=False,
    )
    assert no_csrf.status_code == 403
    assert env.repo.count_case_tags("case-1") == 0

    env2 = env_factory()
    admin_without_session = env2.client.get(
        "/admin/etiquetas", follow_redirects=False
    )
    assert admin_without_session.status_code == 303
    assert admin_without_session.headers["location"] == "/admin/login"


def test_inbox_rows_show_only_active_tag_names(env_factory, panel):
    """R28: las filas muestran solo las etiquetas activas del caso."""
    env = env_factory()
    panel.login(env)
    panel.link_case(env, "case-1")
    active = _tag(env, panel, "tag-a", "Activa")
    disabled = _tag(env, panel, "tag-b", "Inactiva", active=False)
    env.repo.add_case_tag("case-1", active.id, "c1", "700", panel.NOW)
    env.repo.add_case_tag("case-1", disabled.id, "c1", "700", panel.NOW)
    env.handover.case_list = [panel.case_item("case-1", "open", created_at=panel.NOW)]

    rows = advisor_inbox("700", None, None, env.settings, env.adapters)
    page = env.client.get("/asesor/cases")

    assert rows[0].tags == ("Activa",)
    assert "Activa" in page.text
    assert "Inactiva" not in page.text


def test_csrf_failure_on_tag_routes_is_audited_without_changes(env_factory, panel):
    """R34: sin CSRF no se asignan ni quitan etiquetas y se audita `forbidden`."""
    env = env_factory()
    panel.login(env)
    panel.link_case(env, "case-1")
    assigned = _tag(env, panel, "tag-assigned", "Asignada")
    free = _tag(env, panel, "tag-free", "Libre")
    env.repo.add_case_tag("case-1", assigned.id, "c1", "700", panel.NOW)

    assigned_response = env.client.post(
        "/asesor/cases/case-1/tags",
        data={"tag_id": free.id},
        follow_redirects=False,
    )
    removed_response = env.client.post(
        f"/asesor/cases/case-1/tags/{assigned.id}/remove",
        data={"csrf_token": "otro-token"},
        follow_redirects=False,
    )

    assert (assigned_response.status_code, removed_response.status_code) == (403, 403)
    assert [row[1] for row in env.repo.case_tag_assignments] == [assigned.id]
    add_audit, remove_audit = env.repo.panel_audit[-2:]
    assert (add_audit.action, add_audit.result, add_audit.case_id) == (
        "tag_assigned",
        "forbidden",
        "case-1",
    )
    assert (
        remove_audit.action,
        remove_audit.result,
        remove_audit.case_id,
        remove_audit.target,
    ) == ("tag_removed", "forbidden", "case-1", assigned.id)


def test_csrf_failure_on_admin_tag_routes_is_audited_without_changes(
    env_factory, panel
):
    """R34: sin CSRF el admin no crea, renombra ni desactiva; se audita."""
    env = env_factory()
    panel.login_admin(env)
    existing = _tag(env, panel, "tag-admin", "Existente")

    created = env.client.post(
        "/admin/etiquetas",
        data={"name": "Nueva"},
        follow_redirects=False,
    )
    renamed = env.client.post(
        f"/admin/etiquetas/{existing.id}",
        data={"csrf_token": "otro-token", "name": "Renombrada"},
        follow_redirects=False,
    )
    toggled = env.client.post(
        f"/admin/etiquetas/{existing.id}/activa",
        data={"active": "0"},
        follow_redirects=False,
    )

    assert (created.status_code, renamed.status_code, toggled.status_code) == (
        403,
        403,
        403,
    )
    [tag] = env.repo.list_case_tags()
    assert (tag.id, tag.name, tag.active) == ("tag-admin", "Existente", True)
    assert [
        (row.action, row.result, row.target) for row in env.repo.panel_audit
    ] == [
        ("tag_created", "forbidden", None),
        ("tag_renamed", "forbidden", "tag-admin"),
        ("tag_active_changed", "forbidden", "tag-admin"),
    ]
