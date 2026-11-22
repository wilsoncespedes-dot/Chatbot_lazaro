"""Panel de envíos fallidos (#64, R29-R34)."""
from __future__ import annotations

from datetime import timedelta

from lazaro_contracts import TextBlock

from orchestrator.accounts import hash_token
from orchestrator.domain import OutboxEntry, destination_key


def _login(env, panel, role: str = "admin"):
    if role == "admin":
        return panel.login_admin(env)
    profile = panel.make_profile(env, f"{role}1", role, telegram_user_id=None)
    token = f"{role}-admin-session"
    env.repo.create_session(
        hash_token(token),
        profile.id,
        panel.CSRF,
        panel.NOW + timedelta(hours=1),
    )
    env.client.cookies.set("admin_session", token)
    return profile


def _failed(env, text: str = "hola", destination: str = "1234567890") -> int:
    row_id = env.repo.enqueue_outbound(
        OutboxEntry(
            contact_id=None,
            destination_key=destination_key("telegram", destination),
            channel="telegram",
            destination=destination,
            kind="notice",
            blocks=[TextBlock(type="text", text=text)],
        )
    )
    env.repo.fail_outbound(row_id, env.adapters.clock(), "ServiceUnavailable")
    return row_id


def _audits(env) -> list[tuple[str, str, str | None]]:
    return [(row.action, row.result, row.target) for row in env.repo.panel_audit]


def test_list_shows_failed_rows_most_recent_first(env_factory, panel):
    """R29: admin y supervisor listan los fallidos, el más reciente primero."""
    env = env_factory()
    _login(env, panel, "admin")
    first = _failed(env, "primero")
    second = _failed(env, "segundo")
    response = env.client.get("/admin/envios")
    assert response.status_code == 200
    assert "Envíos fallidos" in response.text
    assert response.text.index(f"<td>{second}</td>") < response.text.index(
        f"<td>{first}</td>"
    )

    supervisor = env_factory()
    _login(supervisor, panel, "supervisor")
    assert supervisor.client.get("/admin/envios").status_code == 200

    asesor = env_factory()
    _login(asesor, panel, "asesor")
    assert asesor.client.get("/admin/envios").status_code == 403

    anonymous = env_factory()
    redirect = anonymous.client.get("/admin/envios", follow_redirects=False)
    assert redirect.status_code == 303


def test_list_hides_text_and_full_destination(env_factory, panel):
    """R30: el listado no muestra texto ni el destino completo."""
    env = env_factory()
    _login(env, panel, "admin")
    _failed(env, text="TEXTO-SECRETO", destination="1234567890")
    response = env.client.get("/admin/envios")
    assert "TEXTO-SECRETO" not in response.text
    assert "1234567890" not in response.text
    assert "****7890" in response.text


def test_manual_retry_requires_csrf_and_requeues(env_factory, panel):
    """R31, R32: el reintento con CSRF vuelve a pending y queda en auditoría."""
    env = env_factory()
    _login(env, panel, "admin")
    row_id = _failed(env)
    forbidden = env.client.post(f"/admin/envios/{row_id}/reintentar", data={})
    assert forbidden.status_code == 403
    assert ("outbox_retry", "forbidden", str(row_id)) in _audits(env)
    assert env.repo.outbox[row_id]["status"] == "failed"

    response = env.client.post(
        f"/admin/envios/{row_id}/reintentar",
        data={"csrf_token": panel.CSRF},
        follow_redirects=False,
    )
    assert response.status_code == 303
    row = env.repo.outbox[row_id]
    assert row["status"] == "pending"
    assert row["attempts"] == 0
    assert ("outbox_retry", "ok", str(row_id)) in _audits(env)


def test_retry_not_found_and_not_failed(env_factory, panel):
    """R34: 404 si no existe y 409 si no está failed, sin modificar filas."""
    env = env_factory()
    _login(env, panel, "admin")
    missing = env.client.post(
        "/admin/envios/999/reintentar",
        data={"csrf_token": panel.CSRF},
        follow_redirects=False,
    )
    assert missing.status_code == 404
    assert ("outbox_retry", "not_found", "999") in _audits(env)

    pending = env.repo.enqueue_outbound(
        OutboxEntry(
            contact_id=None,
            destination_key="telegram:100",
            channel="telegram",
            destination="100",
            kind="notice",
            blocks=[TextBlock(type="text", text="hola")],
        )
    )
    not_failed = env.client.post(
        f"/admin/envios/{pending}/reintentar",
        data={"csrf_token": panel.CSRF},
        follow_redirects=False,
    )
    assert not_failed.status_code == 409
    assert env.repo.outbox[pending]["status"] == "pending"
    assert ("outbox_retry", "not_failed", str(pending)) in _audits(env)


def test_asesor_retry_is_forbidden_and_does_not_modify(env_factory, panel):
    """R33: un asesor no puede reintentar ni modificar la fila."""
    env = env_factory()
    _login(env, panel, "asesor")
    row_id = _failed(env)
    response = env.client.post(
        f"/admin/envios/{row_id}/reintentar",
        data={"csrf_token": panel.CSRF},
        follow_redirects=False,
    )
    assert response.status_code == 403
    assert env.repo.outbox[row_id]["status"] == "failed"
    assert ("outbox_retry", "forbidden", str(row_id)) in _audits(env)
