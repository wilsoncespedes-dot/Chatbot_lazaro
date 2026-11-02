"""Plantillas HTML del panel de asesores (renderizado en el servidor, sin JS)."""
from __future__ import annotations

import html

from . import admin

ERROR_MESSAGES = {
    "forbidden": "No tienes permiso para realizar esa acción.",
    "not_found": "El caso no existe.",
    "case_closed": "El caso ya está cerrado.",
    "validation_error": "Los datos enviados no son válidos.",
    "upstream_error": "El servicio de casos no está disponible.",
    "telegram_not_linked": "Tu perfil no tiene una cuenta de Telegram vinculada.",
}

OK_MESSAGES = {
    "reply": "Respuesta enviada al cliente.",
    "assign": "Caso asignado.",
    "close": "Caso cerrado.",
}


def _esc(value: object) -> str:
    return html.escape(str(value), quote=True)


def _page(title: str, body_html: str, csrf: str | None = None) -> str:
    logout = ""
    navigation = ""
    if csrf is not None:
        logout = (
            '<form method="post" action="/asesor/logout">'
            f"{admin.csrf_field(csrf)}"
            '<button type="submit">Salir</button>'
            "</form>"
        )
        navigation = (
            '<nav><ul>'
            '<li><a href="/asesor">Inicio</a></li>'
            '<li><a href="/asesor/cases">Casos</a></li>'
            "</ul></nav>\n"
        )
    return (
        "<!DOCTYPE html>\n"
        '<html lang="es">\n'
        "<head>\n"
        '<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f"<title>{_esc(title)}</title>\n"
        '<link rel="stylesheet" href="/admin/static/admin.css">\n'
        "</head>\n"
        "<body>\n"
        f"<header><h1>Panel de asesores</h1>{logout}</header>\n"
        f"<main>\n{navigation}<h2>{_esc(title)}</h2>\n{body_html}\n</main>\n"
        "</body>\n"
        "</html>\n"
    )


def render_advisor_login(message: str | None = None) -> str:
    error = ""
    if message:
        error = f'<p class="error" role="alert">{_esc(message)}</p>\n'
    body = (
        f"{error}"
        '<form method="post" action="/asesor/login">'
        '<label>Usuario <input name="username" autocomplete="username" required></label>'
        '<label>Contraseña <input type="password" name="password" '
        'autocomplete="current-password" required></label>'
        '<button type="submit">Entrar</button>'
        "</form>"
    )
    return _page("Iniciar sesión", body)


def render_advisor_home(csrf: str, ok: str | None = None, linked: bool = True) -> str:
    ok_html = ""
    if ok in OK_MESSAGES:
        ok_html = f'<p class="ok" role="status">{_esc(OK_MESSAGES[ok])}</p>\n'
    if not linked:
        warning = (
            '<p class="error" role="alert">'
            "Tu perfil no tiene una cuenta de Telegram vinculada. Pide a un "
            "administrador que genere tu enlace de vinculación."
            "</p>\n"
        )
        return _page("Inicio", f"{ok_html}{warning}", csrf)

    reply = (
        '<h3>Responder a un caso</h3>'
        '<form method="post" action="/asesor/reply">'
        f"{admin.csrf_field(csrf)}"
        '<label>Caso <input name="case_id" maxlength="64" required></label>'
        '<label>Respuesta <textarea name="text" maxlength="4096" required></textarea></label>'
        '<button type="submit">Enviar respuesta</button>'
        "</form>"
    )
    assign = (
        '<h3>Asignarme un caso</h3>'
        '<form method="post" action="/asesor/assign">'
        f"{admin.csrf_field(csrf)}"
        '<label>Caso <input name="case_id" maxlength="64" required></label>'
        '<button type="submit">Asignar</button>'
        "</form>"
    )
    close = (
        '<h3>Cerrar un caso</h3>'
        '<form method="post" action="/asesor/close">'
        f"{admin.csrf_field(csrf)}"
        '<label>Caso <input name="case_id" maxlength="64" required></label>'
        '<button type="submit">Cerrar caso</button>'
        "</form>"
    )
    return _page("Inicio", f"{ok_html}{reply}\n{assign}\n{close}", csrf)


def render_advisor_cases(items, csrf: str) -> str:
    rows = "".join(
        "<tr>"
        f"<td>{_esc(item.case_id)}</td>"
        f"<td>{_esc(item.status)}</td>"
        f"<td>{_esc(item.created_at.isoformat())}</td>"
        f"<td>{_esc(', '.join(item.actions))}</td>"
        "</tr>"
        for item in items
    )
    body = (
        "<table><thead><tr><th>Caso</th><th>Estado</th><th>Creado</th>"
        f"<th>Acciones</th></tr></thead><tbody>{rows}</tbody></table>"
    )
    return _page("Casos", body, csrf)


def render_advisor_error(status: int, code: str, csrf: str | None = None) -> str:
    message = ERROR_MESSAGES.get(code, "No se pudo completar la operación.")
    body = (
        f'<p class="error" role="alert" data-code="{_esc(code)}">'
        f"{_esc(message)}</p>"
    )
    return _page(f"Error {status}", body, csrf)
