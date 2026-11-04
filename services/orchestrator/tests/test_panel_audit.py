"""Auditoría del panel multicanal (#41)."""
from __future__ import annotations


def _post(env, path: str, data: dict):
    return env.client.post(path, data=data, follow_redirects=False)


def _actions(env) -> list[tuple[str, str, str | None]]:
    return [(row.action, row.result, row.case_id) for row in env.repo.panel_audit]


def test_reads_record_one_audit_row_each(env_factory, panel):
    """R50: bandeja, vista, memoria y cola dejan su fila con case_id."""
    env = env_factory(suppression_executor_roles="admin,asesor")
    panel.login(env)
    panel.link_case(env, "case-1")
    env.handover.case_list = []

    assert env.client.get("/asesor/cases").status_code == 200
    assert ("inbox_viewed", "ok", None) in _actions(env)
    assert env.client.get("/asesor/cases/case-1").status_code == 200
    assert ("case_viewed", "ok", "case-1") in _actions(env)
    assert env.client.get("/asesor/cases/case-1/memoria").status_code == 200
    assert env.client.get("/asesor/supresiones").status_code == 200

    actions = _actions(env)
    assert ("memory_viewed", "ok", "case-1") in actions
    assert ("suppression_queue_viewed", "ok", None) in actions


def test_actions_record_ok(env_factory, panel):
    """R51: las acciones del panel registran su fila con resultado ok."""
    env = env_factory()
    panel.login(env)
    panel.link_case(env, "case-1")
    target = panel.make_profile(env, "destino", "asesor", 222)
    panel.set_presence(env, target.id, "available")

    _post(env, "/asesor/reply", {"csrf_token": panel.CSRF, "case_id": "case-1", "text": "hola"})
    _post(env, "/asesor/assign", {"csrf_token": panel.CSRF, "case_id": "case-1"})
    _post(env, "/asesor/presence", {"csrf_token": panel.CSRF, "status": "available"})
    _post(env, "/asesor/transfer", {"csrf_token": panel.CSRF, "case_id": "case-1",
                                     "target_profile_id": target.id})
    _post(env, "/asesor/return", {"csrf_token": panel.CSRF, "case_id": "case-1"})

    actions = [row.action for row in env.repo.panel_audit]
    for expected in ("reply", "assign", "presence", "transfer", "return"):
        assert (expected, "ok") in [(row.action, row.result) for row in env.repo.panel_audit]
    assert actions.count("reply") == 1


def test_domain_errors_record_their_code(env_factory, panel):
    """R52: un error de dominio deja su código como resultado."""
    env = env_factory()
    panel.login(env)
    panel.link_case(env, "case-1")
    env.handover.authorize_error = "forbidden"
    response = _post(
        env, "/asesor/reply", {"csrf_token": panel.CSRF, "case_id": "case-1", "text": "hola"}
    )
    assert response.status_code == 403
    assert env.repo.panel_audit[-1].action == "reply"
    assert env.repo.panel_audit[-1].result == "forbidden"
    assert any(event.type == "advisor_forbidden" for event in env.repo.events)


def test_audit_never_stores_client_text_username_external_id_or_note(env_factory, panel):
    """R53: la auditoría solo guarda ids internos, acción, destino y resultado."""
    env = env_factory(suppression_executor_roles="admin,asesor")
    panel.login(env)
    client = env.repo.create_profile("cliente-secreto", "cliente", "hash", panel.NOW)
    contact = panel.link_case(
        env, "case-1", channel="whatsapp", user="573001234", chat="573001235",
        profile_id=client.id,
    )
    secret = "TEXTO-SECRETO-DEL-CLIENTE"
    _post(env, "/asesor/reply", {"csrf_token": panel.CSRF, "case_id": "case-1", "text": secret})
    env.repo.create_or_get_pending_suppression(
        "req-1", client.id, contact.id, "whatsapp", env.adapters.clock()
    )
    env.client.get("/asesor/supresiones")

    haystack = " ".join(
        str(value)
        for row in env.repo.panel_audit
        for value in (
            row.actor_profile_id,
            row.actor_role,
            row.action,
            row.case_id,
            row.request_id,
            row.target,
            row.result,
        )
    )
    for value in (secret, "cliente-secreto", "573001234", "573001235"):
        assert value not in haystack
