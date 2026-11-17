"""HTML propio de la página pública `/acceso` (sin CDN ni recursos externos)."""
from __future__ import annotations

import html

from orchestrator import admin

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
    """#60 R19: misma identidad visual que el acceso de los paneles."""
    return admin.render_auth_page(title, "Acceso de clientes", body)


def render_login_form(token: str, error: str | None = None) -> str:
    """R10: formulario con el token oculto; no consume el enlace."""
    hidden = f'<input type="hidden" name="t" value="{_esc(token)}">'
    body = f"{admin._alert(error)}{admin.login_form('/acceso', hidden)}"
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
