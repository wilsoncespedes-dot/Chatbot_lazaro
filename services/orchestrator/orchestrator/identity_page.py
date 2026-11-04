"""HTML propio de la página pública `/acceso` (sin CDN ni recursos externos)."""
from __future__ import annotations

import html

_ERRORS = {
    400: "El enlace no es válido o ya se usó.",
    401: "Usuario o contraseña incorrectos.",
    403: "El acceso no está habilitado.",
    409: "Ya hay una sesión activa. Cierra la otra sesión o espera.",
    429: "Demasiados intentos. Inténtalo más tarde.",
}


def _esc(value: object) -> str:
    return html.escape(str(value), quote=True)


def _page(title: str, body: str) -> str:
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
        f"<main>\n<h2>{_esc(title)}</h2>\n{body}\n</main>\n"
        "</body>\n"
        "</html>\n"
    )


def render_login_form(token: str, error: str | None = None) -> str:
    """R10: formulario con el token oculto; no consume el enlace."""
    alert = ""
    if error:
        alert = f'<p class="error" role="alert">{_esc(error)}</p>\n'
    body = (
        f"{alert}"
        '<form method="post" action="/acceso">'
        f'<input type="hidden" name="t" value="{_esc(token)}">'
        '<label>Usuario <input name="username" autocomplete="username" required></label>'
        '<label>Contraseña <input type="password" name="password" '
        'autocomplete="current-password" required></label>'
        '<button type="submit">Entrar</button>'
        "</form>"
    )
    return _page("Iniciar sesión", body)


def render_success() -> str:
    return _page(
        "Sesión iniciada",
        "<p>Ya puedes volver a tu chat y continuar la conversación.</p>",
    )


def render_error(status: int) -> str:
    """R12, R21, R23, R26, R36: mensaje genérico, nunca JSON ni eco de datos."""
    message = _ERRORS.get(status, "No se pudo completar el acceso.")
    return _page(f"Error {status}", f'<p class="error" role="alert">{_esc(message)}</p>')
