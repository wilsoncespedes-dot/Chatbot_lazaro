"""HTML escapado de las páginas del segundo factor del panel (#54)."""
from __future__ import annotations

import html

from . import admin, advisor_panel


def _esc(value: object) -> str:
    return html.escape(str(value), quote=True)


def _page(panel: str, title: str, body_html: str, csrf: str) -> str:
    if panel == "admin":
        return admin.render_page(title, body_html, csrf)
    return advisor_panel._page(title, body_html, csrf)


def _path(panel: str, suffix: str = "") -> str:
    return f"/{panel}/2fa{suffix}"


def render_status(
    panel: str,
    csrf: str,
    *,
    enabled: bool,
    pending: bool,
    error: str | None = None,
    error_code: str | None = None,
) -> str:
    """R28: el estado nunca incluye el secreto ni los códigos de recuperación."""
    error_html = ""
    if error:
        data = f' data-error="{_esc(error_code)}"' if error_code else ""
        error_html = f'<p class="error" role="alert"{data}>{_esc(error)}</p>\n'
    if enabled:
        body = (
            f"{error_html}"
            "<p>El segundo factor está activo.</p>"
            "<p>Para desactivarlo o regenerar códigos, pide a un administrador que "
            "lo restablezca.</p>"
        )
        return _page(panel, "Verificación en dos pasos", body, csrf)
    if pending:
        body = (
            f"{error_html}"
            "<p>Tienes un registro pendiente.</p>"
f'<form method="post" action="{_path(panel, '/confirm')}">'
            f"{admin.csrf_field(csrf)}"
            '<label>Código de verificación '
            '<input name="code" inputmode="numeric" autocomplete="one-time-code" '
            'required></label>'
            '<button type="submit">Confirmar</button>'
            "</form>"
f'<form method="post" action="{_path(panel, '/start')}">'
            f"{admin.csrf_field(csrf)}"
            '<button type="submit">Generar un secreto nuevo</button>'
            "</form>"
        )
        return _page(panel, "Verificación en dos pasos", body, csrf)
    body = (
        f"{error_html}"
        "<p>El segundo factor no está activo.</p>"
        f'<form method="post" action="{_path(panel, '/start')}">'
        f"{admin.csrf_field(csrf)}"
        '<button type="submit">Iniciar registro</button>'
        "</form>"
    )
    return _page(panel, "Verificación en dos pasos", body, csrf)


def render_enrollment(
    panel: str, csrf: str, secret: str, uri: str
) -> str:
    """R5, R28: secreto y URI visibles únicamente en esta respuesta."""
    body = (
        "<p>Guarda el secreto en tu aplicación autenticadora.</p>"
        f"<p>Secreto: <code>{_esc(secret)}</code></p>"
        f"<p>URI: <code>{_esc(uri)}</code></p>"
        "<p>Este secreto no volverá a mostrarse.</p>"
        f'<form method="post" action="{_path(panel, '/confirm')}">'
        f"{admin.csrf_field(csrf)}"
        '<label>Código de verificación '
        '<input name="code" inputmode="numeric" autocomplete="one-time-code" '
        'required></label>'
        '<button type="submit">Confirmar</button>'
        "</form>"
    )
    return _page(panel, "Registrar verificación en dos pasos", body, csrf)


def render_recovery(panel: str, csrf: str, codes: list[str]) -> str:
    """R6, R28: los códigos en claro se muestran una sola vez."""
    rows = "".join(f"<li><code>{_esc(code)}</code></li>" for code in codes)
    body = (
        "<p>El segundo factor quedó activo. Guarda estos códigos de recuperación: "
        "no volverán a mostrarse.</p>"
        f"<ul>{rows}</ul>"
        f'<p><a href="{_esc(_path(panel))}">Volver</a></p>'
    )
    return _page(panel, "Códigos de recuperación", body, csrf)


def render_unavailable(panel: str, csrf: str, message: str) -> str:
    return render_status(
        panel, csrf, enabled=False, pending=False, error=message
    )
