"""Administración de respuestas rápidas del bot (#71)."""
from __future__ import annotations

import pytest

PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 16
JPEG = b"\xff\xd8\xff" + b"0" * 16


def _payload(panel, **overrides) -> dict[str, str]:
    data = {
        "csrf_token": panel.CSRF,
        "name": "Horario",
        "triggers": "horario\nhora",
        "text": "Atendemos de 9 a 5",
        "options": "",
        "link_text": "",
        "link_url": "",
        "image_url": "",
        "image_alt": "",
        "priority": "10",
        "active": "1",
    }
    data.update(overrides)
    return data


def _create(env, panel, **overrides):
    return env.client.post(
        "/admin/respuestas-rapidas",
        data=_payload(panel, **overrides),
        follow_redirects=False,
    )


def _actions(env) -> list[tuple[str, str]]:
    return [(row.action, row.result) for row in env.repo.panel_audit]


def test_admin_creates_and_lists_quick_replies(env_factory, panel):
    """R1, R2, R12: alta válida, persistencia completa y auditoría."""
    env = env_factory()
    panel.login_admin(env)

    created = _create(env, panel)

    assert created.status_code == 303
    assert created.headers["location"] == "/admin/respuestas-rapidas"
    [reply] = env.repo.list_quick_replies()
    assert reply.name == "Horario"
    assert reply.triggers == ("horario", "hora")
    assert reply.blocks[0]["type"] == "text"
    assert reply.image_id is None
    assert reply.active is True
    assert reply.priority == 10
    assert reply.created_at == panel.NOW and reply.updated_at == panel.NOW
    assert ("quick_reply_created", "ok") in _actions(env)

    listed = env.client.get("/admin/respuestas-rapidas")
    assert listed.status_code == 200
    assert "Horario" in listed.text and "Atendemos de 9 a 5" in listed.text


def test_admin_updates_blocks_and_toggles_active(env_factory, panel):
    """R3, R4: edición de disparadores/bloques/prioridad y cambio de estado."""
    env = env_factory()
    panel.login_admin(env)
    assert _create(env, panel).status_code == 303
    [reply] = env.repo.list_quick_replies()

    updated = env.client.post(
        f"/admin/respuestas-rapidas/{reply.id}",
        data=_payload(
            panel,
            name="Horario nuevo",
            triggers="atencion\nhorario",
            text="Nuevo texto",
            options="Uno\nDos",
            link_text="Más",
            link_url="https://example.com/mas",
            priority="30",
            active="0",
        ),
        follow_redirects=False,
    )
    assert updated.status_code == 303
    current = env.repo.get_quick_reply(reply.id)
    assert current.name == "Horario nuevo"
    assert current.triggers == ("atencion", "horario")
    assert current.priority == 30
    assert [block["type"] for block in current.blocks] == ["text", "options", "link"]
    assert current.active is True
    assert ("quick_reply_updated", "ok") in _actions(env)

    off = env.client.post(
        f"/admin/respuestas-rapidas/{reply.id}/activa",
        data={"csrf_token": panel.CSRF, "active": "0"},
        follow_redirects=False,
    )
    assert off.status_code == 303
    assert env.repo.get_quick_reply(reply.id).active is False
    assert ("quick_reply_active_changed", "ok") in _actions(env)


def test_quick_reply_requires_at_least_one_trigger_and_one_block(env_factory, panel):
    """R5: sin disparadores o sin bloques -> 422 `quick_reply_invalid`."""
    env = env_factory()
    panel.login_admin(env)

    no_trigger = _create(env, panel, triggers="")
    no_block = _create(
        env, panel, text="", options="", link_text="", link_url="", image_url=""
    )

    assert no_trigger.status_code == 422
    assert no_block.status_code == 422
    assert "quick_reply_invalid" in no_trigger.text
    assert "quick_reply_invalid" in no_block.text
    assert env.repo.list_quick_replies() == []


@pytest.mark.parametrize(
    "triggers",
    [
        "a",
        "x" * 81,
        ",".join(f"tema{i}" for i in range(21)),
    ],
)
def test_trigger_length_and_count_are_validated(env_factory, panel, triggers):
    """R6: 2..80 caracteres normalizados y como máximo 20 disparadores."""
    env = env_factory()
    panel.login_admin(env)

    response = _create(env, panel, triggers=triggers)

    assert response.status_code == 422
    assert "quick_reply_invalid" in response.text
    assert env.repo.list_quick_replies() == []


def test_link_must_start_with_https(env_factory, panel):
    """R7: un enlace http:// -> 422 `quick_reply_invalid`."""
    env = env_factory()
    panel.login_admin(env)

    response = _create(
        env, panel, link_text="Manual", link_url="http://example.com/manual"
    )

    assert response.status_code == 422
    assert "quick_reply_invalid" in response.text
    assert env.repo.list_quick_replies() == []


@pytest.mark.parametrize("priority", ["x", "-1", "1001"])
def test_priority_must_be_an_integer_between_zero_and_1000(
    env_factory, panel, priority
):
    """R8: prioridad fuera de [0, 1000] -> 422 `quick_reply_invalid`."""
    env = env_factory()
    panel.login_admin(env)

    response = _create(env, panel, priority=priority)

    assert response.status_code == 422
    assert "quick_reply_invalid" in response.text
    assert env.repo.list_quick_replies() == []


@pytest.mark.parametrize("role", ["asesor", "supervisor", "responsable_datos", "cliente"])
def test_non_admin_cannot_read_or_modify_quick_replies(env_factory, panel, role):
    """R9: solo admin; otro rol autenticado recibe 403 y se audita."""
    env = env_factory()
    panel.login(env, role=role)
    env.client.cookies.set("admin_session", f"{role}-session")

    read = env.client.get("/admin/respuestas-rapidas", follow_redirects=False)
    write = _create(env, panel)

    assert (read.status_code, write.status_code) == (403, 403)
    assert env.repo.list_quick_replies() == []
    assert ("quick_reply_viewed", "forbidden") in _actions(env)
    assert ("quick_reply_created", "forbidden") in _actions(env)


def test_quick_reply_routes_require_session(env_factory, panel):
    """R10: sin sesión válida se redirige al inicio de sesión."""
    env = env_factory()

    read = env.client.get("/admin/respuestas-rapidas", follow_redirects=False)
    write = env.client.post(
        "/admin/respuestas-rapidas",
        data=_payload(panel),
        follow_redirects=False,
    )

    assert read.status_code == 303
    assert read.headers["location"] == "/admin/login"
    assert write.status_code == 303
    assert write.headers["location"] == "/admin/login"
    assert env.repo.list_quick_replies() == []


def test_csrf_is_required_for_every_write(env_factory, panel):
    """R11: sin token CSRF válido no se modifica nada."""
    env = env_factory()
    panel.login_admin(env)
    assert _create(env, panel).status_code == 303
    [reply] = env.repo.list_quick_replies()

    created = env.client.post(
        "/admin/respuestas-rapidas",
        data=_payload(panel, csrf_token="otro", name="Nueva"),
        follow_redirects=False,
    )
    edited = env.client.post(
        f"/admin/respuestas-rapidas/{reply.id}",
        data=_payload(panel, csrf_token="otro", text="Cambio"),
        follow_redirects=False,
    )
    toggled = env.client.post(
        f"/admin/respuestas-rapidas/{reply.id}/activa",
        data={"active": "0"},
        follow_redirects=False,
    )

    assert (created.status_code, edited.status_code, toggled.status_code) == (
        403,
        403,
        403,
    )
    [current] = env.repo.list_quick_replies()
    assert current.name == "Horario"
    assert current.blocks[0]["text"] == "Atendemos de 9 a 5"
    assert current.active is True


def test_audit_records_success_and_validation_results(env_factory, panel):
    """R12: cada operación deja acción y resultado, sin guardar contenido."""
    env = env_factory()
    panel.login_admin(env)
    assert _create(env, panel).status_code == 303
    [reply] = env.repo.list_quick_replies()
    env.client.post(
        f"/admin/respuestas-rapidas/{reply.id}/activa",
        data={"csrf_token": panel.CSRF, "active": "0"},
        follow_redirects=False,
    )
    invalid = _create(env, panel, triggers="")

    assert invalid.status_code == 422
    actions = _actions(env)
    assert ("quick_reply_created", "ok") in actions
    assert ("quick_reply_active_changed", "ok") in actions
    assert ("quick_reply_created", "quick_reply_invalid") in actions
    haystack = repr(env.repo.panel_audit)
    assert "Atendemos de 9 a 5" not in haystack
    assert "horario" not in haystack


def test_uploaded_image_is_served_publicly_with_nosniff(env_factory, panel):
    """R24, R26: imagen PNG válida servida en el mismo origen sin autenticación."""
    env = env_factory(identity_public_base_url="https://panel.example")
    panel.login_admin(env)

    created = env.client.post(
        "/admin/respuestas-rapidas",
        data=_payload(panel, image_alt="Código QR"),
        files={"image_file": ("qr.png", PNG, "image/png")},
        follow_redirects=False,
    )

    assert created.status_code == 303
    [reply] = env.repo.list_quick_replies()
    assert reply.image_id is not None
    media = env.client.get(f"/media/respuestas/{reply.image_id}")
    assert media.status_code == 200
    assert media.headers["content-type"].startswith("image/png")
    assert media.headers["x-content-type-options"] == "nosniff"
    assert media.content == PNG
    assert reply.blocks[-1] == {"type": "image", "alt_text": "Código QR"}


@pytest.mark.parametrize(
    ("data", "content_type", "max_bytes"),
    [
        (b"no-es-imagen", "image/png", 2097152),
        (b"", "image/png", 2097152),
        (PNG + b"x" * 2000, "image/png", 1024),
    ],
)
def test_invalid_uploaded_images_are_rejected(
    env_factory, panel, data, content_type, max_bytes
):
    """R25: firma, vacío o tamaño -> 422 `quick_reply_image_invalid` sin guardar."""
    env = env_factory(
        identity_public_base_url="https://panel.example",
        quick_reply_image_max_bytes=max_bytes,
    )
    panel.login_admin(env)

    response = env.client.post(
        "/admin/respuestas-rapidas",
        data=_payload(panel, image_alt="Imagen"),
        files={"image_file": ("qr.png", data, content_type)},
        follow_redirects=False,
    )

    assert response.status_code == 422
    assert "quick_reply_image_invalid" in response.text
    assert env.repo.list_quick_replies() == []
    assert env.repo.quick_reply_images == {}


def test_external_image_url_must_be_https(env_factory, panel):
    """R28: una URL de imagen http:// -> 422 `quick_reply_image_invalid`."""
    env = env_factory()
    panel.login_admin(env)

    response = _create(
        env,
        panel,
        image_url="http://example.com/qr.png",
        image_alt="QR",
    )

    assert response.status_code == 422
    assert "quick_reply_image_invalid" in response.text
    assert env.repo.list_quick_replies() == []


def test_uploading_file_and_url_at_once_is_rejected(env_factory, panel):
    """R29: archivo y URL simultáneos -> 422 `quick_reply_image_invalid`."""
    env = env_factory(identity_public_base_url="https://panel.example")
    panel.login_admin(env)

    response = env.client.post(
        "/admin/respuestas-rapidas",
        data=_payload(
            panel,
            image_alt="QR",
            image_url="https://example.com/qr.png",
        ),
        files={"image_file": ("qr.png", PNG, "image/png")},
        follow_redirects=False,
    )

    assert response.status_code == 422
    assert "quick_reply_image_invalid" in response.text
    assert env.repo.list_quick_replies() == []


def test_upload_requires_https_public_base_url(env_factory, panel):
    """R30: sin `IDENTITY_PUBLIC_BASE_URL` https no se guarda la imagen."""
    env = env_factory()
    panel.login_admin(env)

    response = env.client.post(
        "/admin/respuestas-rapidas",
        data=_payload(panel, image_alt="QR"),
        files={"image_file": ("qr.jpg", JPEG, "image/jpeg")},
        follow_redirects=False,
    )

    assert response.status_code == 422
    assert "quick_reply_image_invalid" in response.text
    assert env.repo.list_quick_replies() == []
    assert env.repo.quick_reply_images == {}


def test_editing_other_fields_keeps_the_uploaded_image(env_factory, panel):
    """R31, R32: editar texto no borra ni pierde la imagen subida."""
    env = env_factory(identity_public_base_url="https://panel.example")
    panel.login_admin(env)
    assert env.client.post(
        "/admin/respuestas-rapidas",
        data=_payload(panel, image_alt="QR original"),
        files={"image_file": ("qr.png", PNG, "image/png")},
        follow_redirects=False,
    ).status_code == 303
    [reply] = env.repo.list_quick_replies()

    edited = env.client.post(
        f"/admin/respuestas-rapidas/{reply.id}",
        data=_payload(panel, text="Texto cambiado", image_alt="QR original"),
        follow_redirects=False,
    )

    assert edited.status_code == 303
    current = env.repo.get_quick_reply(reply.id)
    assert current.image_id == reply.image_id
    assert current.image_id in env.repo.quick_reply_images
    assert {"type": "image", "alt_text": "QR original"} in current.blocks


def test_replacing_or_removing_image_deletes_the_previous_file(env_factory, panel):
    """R31: reemplazar o quitar la imagen borra el archivo anterior."""
    env = env_factory(identity_public_base_url="https://panel.example")
    panel.login_admin(env)
    assert env.client.post(
        "/admin/respuestas-rapidas",
        data=_payload(panel, image_alt="QR"),
        files={"image_file": ("qr.png", PNG, "image/png")},
        follow_redirects=False,
    ).status_code == 303
    [reply] = env.repo.list_quick_replies()
    old_image = reply.image_id
    assert old_image in env.repo.quick_reply_images

    assert env.client.post(
        f"/admin/respuestas-rapidas/{reply.id}",
        data=_payload(panel, image_alt="QR nuevo"),
        files={"image_file": ("qr.jpg", JPEG, "image/jpeg")},
        follow_redirects=False,
    ).status_code == 303
    current = env.repo.get_quick_reply(reply.id)
    assert current.image_id != old_image
    assert old_image not in env.repo.quick_reply_images
    new_image = current.image_id
    assert new_image in env.repo.quick_reply_images

    assert env.client.post(
        f"/admin/respuestas-rapidas/{reply.id}",
        data=_payload(panel, remove_image="1"),
        follow_redirects=False,
    ).status_code == 303
    assert env.repo.get_quick_reply(reply.id).image_id is None
    assert new_image not in env.repo.quick_reply_images


@pytest.mark.parametrize("image_id", ["no-es-hex", "a" * 32])
def test_missing_or_invalid_image_id_returns_404(env_factory, image_id):
    """R27: id inexistente o con otro formato -> 404."""
    env = env_factory()
    response = env.client.get(f"/media/respuestas/{image_id}")
    assert response.status_code == 404
