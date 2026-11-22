"""Utilidades puras y plantillas HTML del panel administrativo."""
from __future__ import annotations

import html
import re
import secrets
from datetime import datetime
from urllib.parse import quote

CSP = "default-src 'self'; form-action 'self'; frame-ancestors 'none'"
PANEL_CSP = (
    "default-src 'self'; script-src 'self'; connect-src 'self'; "
    "form-action 'self'; frame-ancestors 'none'; base-uri 'none'; "
    "object-src 'none'"
)
REDACTED = "[redactado]"

ERROR_MESSAGES = {
    "not_found": "No se encontró el manual o el fragmento.",
    "unsupported_format": "El archivo no es PDF ni DOCX.",
    "validation_error": "Los datos enviados no son válidos.",
    "empty_document": "El archivo está vacío o no contiene texto.",
    "upstream_error": "El servicio de manuales no está disponible.",
    "client_not_found": "El cliente no existe.",
    "credential_revoked": "La credencial está revocada.",
    "template_exists": "Ya existe una plantilla con ese nombre.",
    "template_not_found": "La plantilla no existe.",
    "invalid_transition": "La transición de estado no está permitida.",
    "notice_version_required": "Debes indicar una versión nueva al cambiar el texto legal.",
    "tag_name_taken": "Ya existe una etiqueta con ese nombre.",
    "tag_not_found": "La etiqueta no existe.",
    "saved_reply_not_found": "La respuesta guardada no existe.",
    "saved_reply_variables_not_allowed": (
        "Las respuestas guardadas son texto plano y no admiten variables."
    ),
}

_LONG_DIGITS_RE = re.compile(r"\d{6,}")
_LONG_TOKEN_RE = re.compile(r"[A-Za-z0-9_-]{20,}")

ADMIN_CSS = """
:root {
  color-scheme: light;
  --bg: #f4f6fa;
  --surface: #ffffff;
  --text: #1b2733;
  --muted: #4a5568;
  --primary: #1d4ed8;
  --primary-contrast: #ffffff;
  --border: #6b7a8d;
  --focus: #0b63ce;
  --ok: #14532d;
  --ok-bg: #e6f4ea;
  --warn: #7c4a03;
  --warn-bg: #fff4d6;
  --danger: #8a1c1c;
  --danger-bg: #fdecec;
  --info: #0b4f6c;
  --info-bg: #e6f2f8;
  --stripe: #f8fafc;
  --hover: #eef2f7;
  --radius: 0.5rem;
  --space-1: 0.25rem;
  --space-2: 0.5rem;
  --space-3: 1rem;
  --space-4: 1.5rem;
  --shadow: 0 1px 2px rgba(16, 24, 40, 0.08), 0 2px 8px rgba(16, 24, 40, 0.06);
  --font: system-ui, -apple-system, "Segoe UI", sans-serif;
}
* { box-sizing: border-box; }
body { font-family: var(--font); margin: 0; background: var(--bg); color: var(--text);
  line-height: 1.5; }
h1, h2, h3 { line-height: 1.2; margin: 0 0 var(--space-2); }
h1 { font-size: 1.5rem; letter-spacing: 0.02em; }
h2 { font-size: 1.25rem; border-bottom: 2px solid var(--border);
  padding-bottom: var(--space-1); }
h3 { font-size: 1rem; text-transform: uppercase; letter-spacing: 0.05em;
  color: var(--muted); }
a { color: var(--primary); }
a:hover { color: var(--text); }
.site-header { background: var(--primary); color: var(--primary-contrast);
  display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between;
  gap: var(--space-2); padding: var(--space-2) var(--space-3); }
.site-header h1 { color: var(--primary-contrast); margin: 0; }
.site-nav ul { list-style: none; padding: 0; margin: 0 0 var(--space-3);
  display: flex; flex-direction: column; gap: var(--space-1); }
.site-nav a { display: block; padding: var(--space-1) var(--space-2);
  border-radius: var(--radius); text-decoration: none; color: var(--primary); }
.site-nav a:hover { background: var(--hover); color: var(--text); }
.site-nav a:disabled { opacity: 0.55; cursor: not-allowed; }
.site-nav a[aria-current="page"] { background: var(--primary);
  color: var(--primary-contrast); font-weight: 600; }
.skip-link { position: absolute; left: -9999px; top: 0; background: var(--surface);
  color: var(--text); padding: var(--space-2) var(--space-3);
  border-radius: var(--radius); }
.skip-link:focus { left: var(--space-2); z-index: 10; }
main { max-width: 64rem; margin: 0 auto; padding: var(--space-3); }
main.wide { max-width: 90rem; }
.card { background: var(--surface); border: 1px solid var(--border);
  border-radius: var(--radius); box-shadow: var(--shadow); padding: var(--space-3);
  margin: 0 0 var(--space-3); }
form { display: flex; flex-direction: column; gap: var(--space-2);
  align-items: stretch; margin: var(--space-3) 0; }
label { display: flex; flex-direction: column; font-size: 0.9rem;
  gap: var(--space-1); }
input, select, textarea, button { font: inherit; padding: var(--space-2);
  border-radius: var(--radius); border: 1px solid var(--border);
  background: var(--surface); color: var(--text); }
textarea { min-height: 4rem; }
button, .btn { cursor: pointer; background: var(--primary);
  color: var(--primary-contrast); border: 1px solid var(--primary);
  font-weight: 600; }
button:hover, .btn:hover { filter: brightness(1.08); }
button:disabled, .btn:disabled { opacity: 0.55; cursor: not-allowed; }
.btn-secondary { background: var(--surface); color: var(--primary);
  border-color: var(--primary); }
.btn-danger { background: var(--danger); border-color: var(--danger);
  color: var(--surface); }
.badge { display: inline-block; padding: 0.1rem var(--space-2);
  border-radius: 999px; border: 1px solid var(--border);
  background: var(--surface); color: var(--text); font-size: 0.85rem;
  font-weight: 600; }
.badge-ok { background: var(--ok-bg); color: var(--ok); border-color: var(--ok); }
.badge-warn { background: var(--warn-bg); color: var(--warn);
  border-color: var(--warn); }
.badge-error { background: var(--danger-bg); color: var(--danger);
  border-color: var(--danger); }
.badge-info { background: var(--info-bg); color: var(--info);
  border-color: var(--info); }
.error, .ok { padding: var(--space-2); border-radius: var(--radius);
  border: 1px solid var(--border); border-left-width: 6px;
  margin: var(--space-2) 0; }
.error { background: var(--danger-bg); color: var(--danger);
  border-left-color: var(--danger); }
.ok { background: var(--ok-bg); color: var(--ok); border-left-color: var(--ok); }
.error::before { content: "Atención: "; font-weight: 700; }
.ok::before { content: "Hecho: "; font-weight: 700; }
input:user-invalid, select:user-invalid, textarea:user-invalid,
[aria-invalid="true"] { border: 2px solid var(--danger); border-left-width: 6px; }
.table-wrap { overflow-x: auto; max-width: 100%; margin: 0 0 var(--space-3); }
table { width: 100%; border-collapse: collapse; background: var(--surface); }
th, td { border: 1px solid var(--border); padding: var(--space-2);
  text-align: left; vertical-align: top; }
thead th { background: var(--bg); font-weight: 700; }
tbody tr:nth-child(even) { background: var(--stripe); }
tbody tr:hover { background: var(--hover); }
code { background: var(--bg); padding: 0.1rem 0.3rem;
  border-radius: var(--radius); }
.chat { background: var(--surface); border: 1px solid var(--border);
  border-radius: var(--radius); box-shadow: var(--shadow); display: flex;
  flex-direction: column; margin: 0 0 var(--space-3); }
.chat-header, .chat-tools, .chat-composer { padding: var(--space-2) var(--space-3);
  border-bottom: 1px solid var(--border); margin: 0; }
.chat-log { background: var(--bg); max-height: 60vh; min-height: 12rem;
  overflow-y: auto; padding: var(--space-2); }
.chat-messages { list-style: none; padding: 0; margin: 0; display: flex;
  flex-direction: column; gap: var(--space-2); }
.chat-msg { max-width: 85%; align-self: flex-start; background: var(--surface);
  color: var(--text); border: 1px solid var(--border);
  border-radius: var(--radius); padding: var(--space-2); display: flex;
  flex-direction: column; gap: var(--space-1); }
.chat-msg-advisor { align-self: flex-end; background: var(--ok-bg); }
.chat-msg-bot { align-self: flex-end; background: var(--info-bg); }
.chat-author, .chat-time { color: var(--muted); font-size: 0.8rem; }
.chat-time { align-self: flex-end; }
.chat-text { margin: 0; white-space: pre-wrap; overflow-wrap: anywhere; }
.chat-empty { margin: 0; color: var(--muted); }
.chat-title { margin: 0; color: var(--muted); }
.chat-field { flex: 1 1 16rem; }
.chat-field textarea, .chat-field select { width: 100%; }
a:focus-visible, button:focus-visible, input:focus-visible,
select:focus-visible, textarea:focus-visible, .chat-log:focus-visible {
  outline: 3px solid var(--focus); outline-offset: 2px;
}
@media (max-width: 48rem) {
  .site-header { flex-direction: column; align-items: stretch; }
  .site-nav ul { flex-direction: column; }
  form { flex-direction: column; align-items: stretch; }
  input, select, textarea, button, .btn { width: 100%; }
}
@media (min-width: 48.01rem) {
  .site-header { flex-direction: row; align-items: center; }
  .site-nav ul { flex-direction: row; flex-wrap: wrap; }
  form { flex-direction: row; flex-wrap: wrap; align-items: end; }
  input, select, textarea, button, .btn { width: auto; }
}
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after { animation: none !important;
    transition: none !important; scroll-behavior: auto !important; }
}
"""


def _redact_emails(text: str) -> str:
    output: list[str] = []
    for token in re.split(r"(\s+)", text):
        if not token or token.isspace():
            output.append(token)
            continue
        parts = token.split("@")
        index = 0
        while index < len(parts):
            if index + 1 < len(parts) and parts[index] and parts[index + 1]:
                output.append(REDACTED)
                index += 2
            else:
                output.append(parts[index])
                index += 1
            if index < len(parts):
                output.append("@")
    return "".join(output)


def redact_reason(reason: str) -> str:
    """Oculta correos, secuencias de 6+ dígitos y cadenas URL-safe de 20+ caracteres."""
    reason = _redact_emails(reason)
    reason = _LONG_DIGITS_RE.sub(REDACTED, reason)
    return _LONG_TOKEN_RE.sub(REDACTED, reason)


def short_id(value: str | None) -> str:
    return (value or "")[:8]


def new_session_token() -> str:
    return secrets.token_urlsafe(32)


def security_headers() -> dict[str, str]:
    return {
        "Content-Security-Policy": CSP,
        "X-Content-Type-Options": "nosniff",
        "Cache-Control": "no-store",
    }


def panel_security_headers() -> dict[str, str]:
    """R29: CSP estricta del panel de asesores, sin scripts inline."""
    return {
        "Content-Security-Policy": PANEL_CSP,
        "X-Content-Type-Options": "nosniff",
        "Cache-Control": "no-store",
    }


def _esc(value: object) -> str:
    return html.escape(str(value), quote=True)


def csrf_field(csrf: str) -> str:
    return f'<input type="hidden" name="csrf_token" value="{_esc(csrf)}">'


def _table_wrap(table_html: str) -> str:
    """R8: contiene cada tabla en su propio contenedor con desplazamiento."""
    return f'<div class="table-wrap">{table_html}</div>'


def _toggle_class(active: bool) -> str:
    """R4: desactivar es destructivo; activar es una acción secundaria."""
    return "btn-danger" if active else "btn-secondary"


def _skip_link() -> str:
    """R15: primer elemento enfocable del cuerpo, apunta al contenido."""
    return '<a class="skip-link" href="#contenido">Saltar al contenido</a>'


def _nav_html(
    links: list[tuple[str, str]],
    current: str | None = None,
    label: str = "Navegación",
) -> str:
    """R3, R16: misma cabecera y navegación para ambos paneles.

    `advisor_panel` importa estos helpers privados a propósito para compartir la
    estructura visual (decisión de #56).
    """
    items = []
    for href, text in links:
        is_current = bool(current) and (
            current == href
            or (href not in ("/admin", "/asesor") and current.startswith(f"{href}/"))
        )
        marker = ' aria-current="page"' if is_current else ""
        items.append(
            f'<li><a href="{_esc(href)}"{marker}>{_esc(text)}</a></li>'
        )
    return (
        f'<nav class="site-nav" aria-label="{_esc(label)}"><ul>'
        f"{''.join(items)}</ul></nav>\n"
    )


ADMIN_NAV_LINKS = [
    ("/admin", "Inicio"),
    ("/admin/profiles", "Perfiles y roles"),
    ("/admin/events", "Eventos recientes"),
    ("/admin/manuals", "Manuales"),
    ("/admin/categories", "Categorías"),
    ("/admin/etiquetas", "Etiquetas"),
    ("/admin/respuestas", "Respuestas guardadas"),
    ("/admin/texts", "Textos del flujo"),
    ("/admin/clientes", "Clientes"),
    ("/admin/plantillas", "Plantillas"),
    ("/admin/ajustes", "Ajustes"),
    ("/admin/metricas", "Métricas"),
    ("/admin/simulador", "Simulador"),
    ("/admin/supresiones", "Supresiones"),
    ("/admin/envios", "Envíos fallidos"),
    ("/admin/canales", "Canales"),
]


def render_page(
    title: str,
    body_html: str,
    csrf: str | None = None,
    current_path: str | None = None,
) -> str:
    logout = ""
    navigation = ""
    if csrf is not None:
        logout = (
            '<form method="post" action="/admin/logout">'
            f"{csrf_field(csrf)}"
            '<button type="submit" class="btn-secondary">Salir</button>'
            "</form>"
        )
        navigation = _nav_html(
            ADMIN_NAV_LINKS, current_path, "Navegación administrativa"
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
        f"{_skip_link()}\n"
        f'<header class="site-header"><h1>Panel administrativo</h1>{logout}</header>\n'
        f'<main id="contenido">\n{navigation}<h2>{_esc(title)}</h2>\n{body_html}\n</main>\n'
        "</body>\n"
        "</html>\n"
    )


def render_login(message: str | None = None, code: str | None = None) -> str:
    error = ""
    if message:
        data = f' data-error="{_esc(code)}"' if code else ""
        error = f'<p class="error" role="alert"{data}>{_esc(message)}</p>\n'
    body = (
        f"{error}"
        '<form method="post" action="/admin/login" class="card">'
        '<label>Usuario <input name="username" autocomplete="username" required></label>'
        '<label>Contraseña <input type="password" name="password" '
        'autocomplete="current-password" required></label>'
        '<button type="submit">Entrar</button>'
        "</form>"
    )
    return render_page("Iniciar sesión", body)


def render_home(csrf: str) -> str:
    return render_page(
        "Inicio",
        "<p>Selecciona una sección del panel.</p>",
        csrf,
        current_path="/admin",
    )


STAFF_PROFILE_ROLES = ("admin", "supervisor", "asesor", "responsable_datos")


def render_profiles(profiles, csrf: str, error: str | None = None) -> str:
    rows = []
    for profile in profiles:
        linked = "Sí" if profile.telegram_user_id is not None else "No"
        # `cliente` solo aparece si ya es el rol actual: los clientes se crean
        # en /admin/clientes, que les asigna credencial.
        roles = STAFF_PROFILE_ROLES + (
            ("cliente",) if profile.role == "cliente" else ()
        )
        role_options = "".join(
            f'<option value="{_esc(role)}"'
            f'{" selected" if role == profile.role else ""}>{_esc(role)}</option>'
            for role in roles
        )
        rows.append(
            "<tr>"
            f"<td>{_esc(profile.username)}</td>"
            f"<td>{_esc(profile.role)}</td>"
            f"<td>{linked}</td>"
            "<td>"
            f'<form method="post" action="/admin/profiles/{_esc(profile.id)}/role">'
            f"{csrf_field(csrf)}"
            f'<select name="role">{role_options}</select>'
            '<button type="submit" class="btn-secondary">Cambiar rol</button>'
            "</form>"
            "</td>"
            "<td>"
            f'<form method="post" action="/admin/profiles/{_esc(profile.id)}/link-token">'
            f"{csrf_field(csrf)}"
            '<button type="submit" class="btn-secondary">Generar enlace</button>'
            "</form>"
            "</td>"
            "</tr>"
        )
    error_html = ""
    if error:
        error_html = f'<p class="error" role="alert">{_esc(error)}</p>\n'
    body = (
        f"{error_html}"
        '<p>Para crear clientes que inician sesión en el bot usa '
        '<a href="/admin/clientes">Clientes</a>.</p>'
        '<form method="post" action="/admin/profiles" class="card">'
        f"{csrf_field(csrf)}"
        '<label>Usuario <input name="username" autocomplete="off" required></label>'
        '<label>Rol <select name="role">'
        '<option value="admin">admin</option>'
        '<option value="supervisor">supervisor</option>'
        '<option value="asesor">asesor</option>'
        '<option value="responsable_datos">responsable_datos</option>'
        "</select></label>"
        '<label>Contraseña <input type="password" name="password" '
        'autocomplete="new-password" required></label>'
        '<button type="submit">Crear perfil</button>'
        "</form>"
        + _table_wrap(
            "<table><thead><tr><th>Usuario</th><th>Rol</th><th>Vinculado</th>"
            "<th>Cambiar rol</th><th>Enlace de Telegram</th>"
            "</tr></thead><tbody>"
            f"{''.join(rows)}"
            "</tbody></table>"
        )
    )
    return render_page("Perfiles y roles", body, csrf, "/admin/profiles")


def render_link(token: str, link: str | None, expires_at: datetime, csrf: str) -> str:
    shown = link if link is not None else token
    body = (
        f"<p>Enlace: <code>{_esc(shown)}</code></p>"
        f"<p>Caduca: <code>{_esc(expires_at.isoformat())}</code></p>"
        '<p><a href="/admin/profiles">Volver a perfiles</a></p>'
    )
    return render_page("Enlace de vinculación", body, csrf, "/admin/profiles")


def render_events(events, csrf: str) -> str:
    rows = "".join(
        "<tr>"
        f"<td>{_esc(short_id(event.contact_id))}</td>"
        f"<td>{_esc(event.type)}</td>"
        f"<td>{_esc(redact_reason(event.reason))}</td>"
        f"<td>{_esc(event.at.isoformat())}</td>"
        "</tr>"
        for event in events
    )
    body = _table_wrap(
        "<table><thead><tr><th>Contacto</th><th>Tipo</th><th>Motivo</th>"
        f"<th>Fecha</th></tr></thead><tbody>{rows}</tbody></table>"
    )
    return render_page("Eventos recientes", body, csrf, "/admin/events")


def render_manuals(manuals, csrf: str, error: str | None = None) -> str:
    error_html = ""
    if error:
        error_html = f'<p class="error" role="alert">{_esc(error)}</p>\n'
    table = ""
    if manuals is not None:
        rows = "".join(
            "<tr>"
            f'<td><a href="/admin/manuals/{quote(manual.manual_id, safe="")}">'
            f"{_esc(manual.name)}</a></td>"
            f"<td>{_esc(manual.chunks)}</td>"
            "</tr>"
            for manual in manuals
        )
        table = _table_wrap(
            "<table><thead><tr><th>Manual</th><th>Fragmentos</th></tr></thead>"
            f"<tbody>{rows}</tbody></table>"
        )
    upload = (
        '<form method="post" action="/admin/manuals" '
        'enctype="multipart/form-data" class="card">'
        f"{csrf_field(csrf)}"
        '<label>Nombre <input name="name" maxlength="200" required></label>'
        '<label>Archivo <input type="file" name="file" accept=".pdf,.docx" required></label>'
        '<button type="submit">Cargar manual</button>'
        "</form>"
    )
    return render_page("Manuales", f"{error_html}{upload}\n{table}", csrf, "/admin/manuals")


def render_manual_chunks(manual_id: str, chunks, csrf: str) -> str:
    rows = []
    for chunk in chunks:
        chunk_path = quote(chunk.chunk_id, safe="")
        state = "Sí" if chunk.active else "No"
        next_active = "false" if chunk.active else "true"
        action = "Desactivar" if chunk.active else "Activar"
        rows.append(
            "<tr>"
            f"<td>{_esc(chunk.order)}</td>"
            f"<td>{_esc(chunk.text)}</td>"
            f"<td>{state}</td>"
            "<td>"
            f'<form method="post" action="/admin/chunks/{chunk_path}">'
            f"{csrf_field(csrf)}"
            f'<textarea name="text" required>{_esc(chunk.text)}</textarea>'
            '<button type="submit" class="btn-secondary">Guardar texto</button>'
            "</form>"
            "</td>"
            "<td>"
            f'<form method="post" action="/admin/chunks/{chunk_path}/active">'
            f"{csrf_field(csrf)}"
            f'<input type="hidden" name="active" value="{next_active}">'
            f'<button type="submit" class="{_toggle_class(chunk.active)}">{action}</button>'
            "</form>"
            "</td>"
            "</tr>"
        )
    body = (
        f'<p><a href="/admin/manuals">Volver a manuales</a></p>'
        + _table_wrap(
            "<table><thead><tr><th>Orden</th><th>Texto</th><th>Activo</th>"
            "<th>Editar texto</th><th>Estado</th></tr></thead>"
            f"<tbody>{''.join(rows)}</tbody></table>"
        )
    )
    return render_page(
        f"Fragmentos del manual {manual_id}", body, csrf, "/admin/manuals"
    )


def render_categories(categories, threshold: float, csrf: str, error: str | None = None) -> str:
    rows = []
    for category in categories:
        category_path = quote(category.id, safe="")
        keywords_text = ", ".join(category.keywords)
        state = "Sí" if category.active else "No"
        next_active = "false" if category.active else "true"
        action = "Desactivar" if category.active else "Activar"
        rows.append(
            "<tr>"
            f"<td>{_esc(category.code)}</td>"
            f"<td>{_esc(category.name)}</td>"
            f"<td>{_esc(keywords_text)}</td>"
            f"<td>{state}</td>"
            "<td>"
            f'<form method="post" action="/admin/categories/{category_path}">'
            f"{csrf_field(csrf)}"
            f'<label>Nombre <input name="name" value="{_esc(category.name)}" '
            'maxlength="60" required></label>'
            f'<label>Palabras clave <textarea name="keywords" required>'
            f"{_esc(keywords_text)}</textarea></label>"
            '<button type="submit" class="btn-secondary">Guardar</button>'
            "</form>"
            "</td>"
            "<td>"
            f'<form method="post" action="/admin/categories/{category_path}/active">'
            f"{csrf_field(csrf)}"
            f'<input type="hidden" name="active" value="{next_active}">'
            f'<button type="submit" class="{_toggle_class(category.active)}">'
            f"{action}</button>"
            "</form>"
            "</td>"
            "</tr>"
        )
    error_html = ""
    if error:
        error_html = f'<p class="error" role="alert">{_esc(error)}</p>\n'
    create = (
        '<form method="post" action="/admin/categories" class="card">'
        f"{csrf_field(csrf)}"
        '<label>Código <input name="code" maxlength="16" required></label>'
        '<label>Nombre <input name="name" maxlength="60" required></label>'
        '<label>Palabras clave <textarea name="keywords" required></textarea></label>'
        '<button type="submit">Crear categoría</button>'
        "</form>"
    )
    threshold_text = f"{threshold:g}"
    threshold_form = (
        f"<p>Umbral vigente: <code>{_esc(threshold_text)}</code></p>"
        '<form method="post" action="/admin/categories/threshold" class="card">'
        f"{csrf_field(csrf)}"
        f'<label>Umbral <input name="threshold" value="{_esc(threshold_text)}" '
        'inputmode="decimal" required></label>'
        '<button type="submit" class="btn-secondary">Guardar umbral</button>'
        "</form>"
    )
    body = (
        f"{error_html}{threshold_form}\n{create}\n"
        + _table_wrap(
            "<table><thead><tr><th>Código</th><th>Nombre</th><th>Palabras clave</th>"
            "<th>Activa</th><th>Editar</th><th>Estado</th></tr></thead>"
            f"<tbody>{''.join(rows)}</tbody></table>"
        )
    )
    return render_page("Categorías", body, csrf, "/admin/categories")


def render_tags(tags, csrf: str, error: str | None = None) -> str:
    """R14-R18, R29: administración de etiquetas sin JS."""
    error_html = ""
    if error:
        error_html = f'<p class="error" role="alert">{_esc(error)}</p>\n'
    rows = []
    for tag in tags:
        path = quote(tag.id, safe="")
        state = "Sí" if tag.active else "No"
        next_active = "0" if tag.active else "1"
        action = "Desactivar" if tag.active else "Activar"
        rows.append(
            "<tr>"
            f"<td>{_esc(tag.name)}</td>"
            f"<td>{state}</td>"
            "<td>"
            f'<form method="post" action="/admin/etiquetas/{path}">'
            f"{csrf_field(csrf)}"
            f'<label>Nombre <input name="name" value="{_esc(tag.name)}" '
            'maxlength="100" required></label>'
            '<button type="submit" class="btn-secondary">Renombrar</button>'
            "</form>"
            "</td>"
            "<td>"
            f'<form method="post" action="/admin/etiquetas/{path}/activa">'
            f"{csrf_field(csrf)}"
            f'<input type="hidden" name="active" value="{next_active}">'
            f'<button type="submit" class="{_toggle_class(tag.active)}">'
            f"{action}</button>"
            "</form>"
            "</td>"
            "</tr>"
        )
    create = (
        '<form method="post" action="/admin/etiquetas" class="card">'
        f"{csrf_field(csrf)}"
        '<label>Nombre <input name="name" maxlength="100" required></label>'
        '<button type="submit">Crear etiqueta</button>'
        "</form>"
    )
    body = (
        f"{error_html}{create}\n"
        + _table_wrap(
            "<table><thead><tr><th>Nombre</th><th>Activa</th><th>Renombrar</th>"
            f"<th>Estado</th></tr></thead><tbody>{''.join(rows)}</tbody></table>"
        )
    )
    return render_page("Etiquetas", body, csrf, "/admin/etiquetas")


def render_saved_replies(replies, csrf: str, error: str | None = None) -> str:
    """R1-R3, R12, R21: administración de respuestas guardadas sin JS."""
    error_html = ""
    if error:
        error_html = f'<p class="error" role="alert">{_esc(error)}</p>\n'
    rows = []
    for reply in replies:
        path = quote(reply.id, safe="")
        state = "Sí" if reply.active else "No"
        next_active = "0" if reply.active else "1"
        action = "Desactivar" if reply.active else "Activar"
        rows.append(
            "<tr>"
            f"<td>{_esc(reply.title)}</td>"
            f"<td>{_esc(reply.body)}</td>"
            f"<td>{state}</td>"
            "<td>"
            f'<form method="post" action="/admin/respuestas/{path}">'
            f"{csrf_field(csrf)}"
            f'<label>Título <input name="title" value="{_esc(reply.title)}" '
            'maxlength="200" required></label>'
            '<label>Texto <textarea name="body" maxlength="4096" required>'
            f"{_esc(reply.body)}</textarea></label>"
            '<button type="submit" class="btn-secondary">Guardar</button>'
            "</form>"
            "</td>"
            "<td>"
            f'<form method="post" action="/admin/respuestas/{path}/activa">'
            f"{csrf_field(csrf)}"
            f'<input type="hidden" name="active" value="{next_active}">'
            f'<button type="submit" class="{_toggle_class(reply.active)}">'
            f"{action}</button>"
            "</form>"
            "</td>"
            "</tr>"
        )
    create = (
        '<form method="post" action="/admin/respuestas" class="card">'
        f"{csrf_field(csrf)}"
        '<label>Título <input name="title" maxlength="200" required></label>'
        '<label>Texto <textarea name="body" maxlength="4096" required></textarea></label>'
        '<button type="submit">Crear respuesta</button>'
        "</form>"
    )
    body = (
        f"{error_html}{create}\n"
        + _table_wrap(
            "<table><thead><tr><th>Título</th><th>Texto</th><th>Activa</th>"
            f"<th>Editar</th><th>Estado</th></tr></thead><tbody>{''.join(rows)}</tbody>"
            "</table>"
        )
    )
    return render_page("Respuestas guardadas", body, csrf, "/admin/respuestas")


TEXT_FIELD_LABELS = {
    "notice_text": "Texto legal de tratamiento de datos",
    "notice_version": "Versión del texto legal",
    "greeting": "Saludo",
    "accepted_reply": "Confirmación al aceptar",
    "rejected_reply": "Mensaje de cierre al rechazar",
    "login_reminder": "Recordatorio de inicio de sesión",
    "suspended_reply": "Aviso de servicio suspendido",
    "unsupported_reply": "Respuesta a contenido no textual",
    "active_welcome": "Bienvenida y temas",
    "confirm_button_reply": "Petición de confirmar con el botón",
    "login_link_label": "Texto del enlace de inicio de sesión",
    "session_closed_reply": "Aviso al cerrar la sesión",
    "expiry_notice": "Aviso de vencimiento de credencial",
    "out_of_hours_reply": "Respuesta de traspaso fuera de horario",
    "closing_reply": "Aviso al cerrar un caso",
    "topics_list": "Lista de temas de la bienvenida",
}


def render_conversation_texts(
    texts,
    csrf: str,
    error: str | None = None,
    versions: dict[str, int] | None = None,
) -> str:
    error_html = ""
    if error:
        error_html = f'<p class="error" role="alert">{_esc(error)}</p>\n'
    rows = []
    for field, label in TEXT_FIELD_LABELS.items():
        value = getattr(texts, field)
        version = (versions or {}).get(field)
        version_text = str(version) if version is not None else "sin historial"
        rows.append(
            f'<label>{_esc(label)} '
            f'<textarea name="{_esc(field)}" maxlength="4096" required>'
            f"{_esc(value)}</textarea></label>"
            f'<p>Versión vigente: <code>{_esc(version_text)}</code> '
            f'<a href="/admin/texts/{quote(field, safe="")}/historial">Historial</a></p>'
        )
    fields_html = "".join(rows)
    body = (
        f"{error_html}"
        '<form method="post" action="/admin/texts" class="card">'
        f"{csrf_field(csrf)}"
        f"{fields_html}"
        '<button type="submit">Guardar textos</button>'
        "</form>"
        '<p>La versión legal se guarda junto al texto; al cambiarla, los '
        "clientes deberán aceptar de nuevo antes de continuar.</p>"
    )
    return render_page("Textos del flujo", body, csrf, "/admin/texts")


def render_text_history(field: str, versions, csrf: str) -> str:
    rows = "".join(
        "<tr>"
        f"<td>{_esc(item.version)}</td>"
        f"<td>{_esc(item.created_by)}</td>"
        f"<td>{_esc(item.created_at.isoformat())}</td>"
        f"<td>{_esc(item.value)}</td>"
        "</tr>"
        for item in versions
    )
    body = (
        f'<p><a href="/admin/texts">Volver a textos</a></p>'
        + _table_wrap(
            "<table><thead><tr><th>Versión</th><th>Autor</th><th>Fecha</th>"
            f"<th>Valor</th></tr></thead><tbody>{rows}</tbody></table>"
        )
    )
    return render_page(f"Historial de {field}", body, csrf, "/admin/texts")


def render_clients(clients, csrf: str, error: str | None = None) -> str:
    error_html = ""
    if error:
        error_html = f'<p class="error" role="alert">{_esc(error)}</p>\n'
    rows = []
    for client in clients:
        path = quote(client.profile_id, safe="")
        rows.append(
            "<tr>"
            f"<td>{_esc(client.username)}</td>"
            f"<td>{_esc(client.status)}</td>"
            f"<td>{_esc(client.valid_from.isoformat())}</td>"
            f"<td>{_esc(client.valid_until.isoformat())}</td>"
            f"<td>{_esc(client.days_remaining)}</td>"
            f"<td>{'Sí' if client.has_active_session else 'No'}</td>"
            f"<td>{_esc(client.expiry_notice_status or '')}</td>"
            "<td>"
            f'<form method="post" action="/admin/clientes/{path}/renovar">'
            f"{csrf_field(csrf)}"
            '<button type="submit" class="btn-secondary">Renovar</button>'
            "</form>"
            f'<form method="post" action="/admin/clientes/{path}/revocar">'
            f"{csrf_field(csrf)}"
            '<button type="submit" class="btn-danger">Revocar</button>'
            "</form>"
            f'<form method="post" action="/admin/clientes/{path}/cerrar-sesion">'
            f"{csrf_field(csrf)}"
            '<button type="submit" class="btn-secondary">Cerrar sesión</button>'
            "</form>"
            "</td>"
            "</tr>"
        )
    body = (
        f"{error_html}"
        '<form method="post" action="/admin/clientes" class="card">'
        f"{csrf_field(csrf)}"
        '<label>Usuario <input name="username" autocomplete="off" required></label>'
        '<label>Contraseña <input type="password" name="password" '
        'autocomplete="new-password" required></label>'
        '<label>Válida desde <input type="date" name="valid_from"></label>'
        '<label>Válida hasta <input type="date" name="valid_until"></label>'
        '<button type="submit">Crear cliente</button>'
        "</form>"
        + _table_wrap(
            "<table><thead><tr><th>Usuario</th><th>Estado</th><th>Desde</th>"
            "<th>Hasta</th><th>Días</th><th>Sesión</th><th>Aviso</th>"
            f"<th>Acciones</th></tr></thead><tbody>{''.join(rows)}</tbody></table>"
        )
    )
    return render_page("Clientes", body, csrf, "/admin/clientes")


def render_templates(templates, csrf: str, error: str | None = None) -> str:
    error_html = ""
    if error:
        error_html = f'<p class="error" role="alert">{_esc(error)}</p>\n'
    rows = []
    for template in templates:
        path = quote(template.name, safe="")
        approved = (
            f"{template.approved_by} {template.approved_at.isoformat()}"
            if template.approved_by is not None and template.approved_at is not None
            else "—"
        )
        rows.append(
            "<tr>"
            f"<td>{_esc(template.name)}</td>"
            f"<td>{_esc(template.purpose)}</td>"
            f"<td>{_esc(template.language)}</td>"
            f"<td>{_esc(template.variables)}</td>"
            f"<td>{_esc(template.body)}</td>"
            f"<td>{_esc(template.status)}</td>"
            f"<td>{_esc(approved)}</td>"
            "<td>"
            f'<form method="post" action="/admin/plantillas/{path}">'
            f"{csrf_field(csrf)}"
            f'<label>Idioma <input name="language" value="{_esc(template.language)}" required></label>'
            f'<label>Variables <input name="variables" value="{_esc(template.variables)}" required></label>'
            f'<label>Texto <textarea name="body" maxlength="1024" required>{_esc(template.body)}</textarea></label>'
            '<button type="submit" class="btn-secondary">Guardar</button>'
            "</form>"
            f'<form method="post" action="/admin/plantillas/{path}/estado">'
            f"{csrf_field(csrf)}"
            '<select name="status">'
            + "".join(
                f'<option value="{_esc(status)}">{_esc(status)}</option>'
                for status in ("pending", "approved", "rejected", "paused", "draft")
            )
            + "</select>"
            '<button type="submit" class="btn-secondary">Cambiar estado</button>'
            "</form>"
            "</td>"
            "</tr>"
        )
    create = (
        '<form method="post" action="/admin/plantillas" class="card">'
        f"{csrf_field(csrf)}"
        '<label>Nombre <input name="name" required></label>'
        '<label>Propósito <select name="purpose">'
        '<option value="advisor_reply">advisor_reply</option>'
        '<option value="suppression_result">suppression_result</option>'
        '<option value="expiry_notice">expiry_notice</option>'
        "</select></label>"
        '<label>Idioma <input name="language" value="es" required></label>'
        '<label>Variables <input name="variables" value="0" required></label>'
        '<label>Texto de referencia <textarea name="body" maxlength="1024" required></textarea></label>'
        '<button type="submit">Crear plantilla</button>'
        "</form>"
    )
    body = (
        f"{error_html}{create}\n"
        + _table_wrap(
            "<table><thead><tr><th>Nombre</th><th>Propósito</th><th>Idioma</th>"
            "<th>Variables</th><th>Texto</th><th>Estado</th><th>Aprobación</th>"
            f"<th>Acciones</th></tr></thead><tbody>{''.join(rows)}</tbody></table>"
        )
    )
    return render_page("Plantillas de WhatsApp", body, csrf, "/admin/plantillas")


def render_settings(settings_rows, csrf: str, error: str | None = None) -> str:
    error_html = ""
    if error:
        error_html = f'<p class="error" role="alert">{_esc(error)}</p>\n'
    rows = []
    inputs = []
    for row in settings_rows:
        rows.append(
            "<tr>"
            f"<td>{_esc(row['key'])}</td>"
            f"<td>{_esc(row['effective'])}</td>"
            f"<td>{_esc(row['default'])}</td>"
            f"<td>{_esc(row['origin'])}</td>"
            f"<td>{_esc(row['range'])}</td>"
            "</tr>"
        )
        if row.get("options"):
            choices = "".join(
                f'<option value="{_esc(option)}"'
                f'{" selected" if option == row["effective"] else ""}>'
                f"{_esc(option)}</option>"
                for option in row["options"]
            )
            inputs.append(
                f'<label>{_esc(row["key"])} '
                f'<select name="{_esc(row["key"])}">{choices}</select></label>'
            )
        else:
            inputs.append(
                f'<label>{_esc(row["key"])} '
                f'<input name="{_esc(row["key"])}" value="{_esc(row["effective"])}" '
                f'placeholder="{_esc(row["default"])}"></label>'
            )
    body = (
        f"{error_html}"
        + _table_wrap(
            "<table><thead><tr><th>Clave</th><th>Efectivo</th><th>Por defecto</th>"
            f"<th>Origen</th><th>Rango</th></tr></thead><tbody>{''.join(rows)}</tbody></table>"
        )
        + '<form method="post" action="/admin/ajustes" class="card">'
        f"{csrf_field(csrf)}"
        f"{''.join(inputs)}"
        '<button type="submit">Guardar ajustes</button>'
        "</form>"
        "<p>Deja un campo vacío para volver al valor de entorno.</p>"
    )
    return render_page("Ajustes operativos", body, csrf, "/admin/ajustes")


def render_metrics(metrics, csrf: str) -> str:
    first = metrics.first_response
    average = f"{first.avg_minutes:.1f}" if first.avg_minutes is not None else "—"
    median = (
        f"{first.median_minutes:.1f}" if first.median_minutes is not None else "—"
    )
    advisors = "".join(
        f"<tr><td>{_esc(label)}</td><td>{_esc(count)}</td></tr>"
        for label, count in metrics.per_advisor
    ) or '<tr><td colspan="2">Sin datos</td></tr>'
    reasons = "".join(
        f"<tr><td>{_esc(reason)}</td><td>{_esc(count)}</td></tr>"
        for reason, count in metrics.escalation_reasons
    ) or '<tr><td colspan="2">Sin datos</td></tr>'
    samples = "".join(
        f"<li>{_esc(at.isoformat())}: {_esc(text)}</li>"
        for at, text in metrics.unanswered_samples
    ) or "<li>Sin muestras</li>"
    body = (
        f'<p>Intervalo: {_esc(metrics.since.isoformat())} — '
        f"{_esc(metrics.until.isoformat())}</p>"
        "<h3>Primera respuesta</h3>"
        f"<p>Casos: {_esc(first.cases)} · Respondidos: {_esc(first.answered)} · "
        f"Sin respuesta: {_esc(first.unanswered)} · Promedio: {_esc(average)} min · "
        f"Mediana: {_esc(median)} min</p>"
        "<h3>Conversaciones por asesor</h3>"
        + _table_wrap(f"<table><tbody>{advisors}</tbody></table>")
        + "<h3>Motivos de escalamiento</h3>"
        + _table_wrap(f"<table><tbody>{reasons}</tbody></table>")
        + f"<h3>Preguntas sin respuesta: {_esc(metrics.unanswered_total)}</h3>"
        f"<ul>{samples}</ul>"
    )
    return render_page("Métricas", body, csrf, "/admin/metricas")


def render_error(status: int, code: str, csrf: str | None = None) -> str:
    message = ERROR_MESSAGES.get(code, "No se pudo completar la operación.")
    return render_page(f"Error {status}", f"<p>{_esc(message)}</p>", csrf)


def render_message(title: str, message: str, csrf: str | None = None) -> str:
    return render_page(title, f"<p>{_esc(message)}</p>", csrf)


# ── Canales (#66) ────────────────────────────────────────────────────────────

CHANNELS_JS = """'use strict';
document.addEventListener('click', function (event) {
  var button = event.target.closest('button[data-copy]');
  if (!button) { return; }
  var field = document.getElementById(button.getAttribute('data-copy'));
  if (!field) { return; }
  var done = function () { button.textContent = 'Copiado'; };
  field.select();
  if (navigator.clipboard && navigator.clipboard.writeText) {
    navigator.clipboard.writeText(field.value).then(done, function () {});
  } else if (document.execCommand && document.execCommand('copy')) {
    done();
  }
});
"""


def _channel_label(info, glyph: str) -> str:
    """R31: etiqueta SVG (sin estilos inline) con el color del canal y texto blanco."""
    text = f"{glyph} {info.name}"
    width = 24 + 9 * len(text)
    return (
        f'<svg class="channel-label" width="{width}" height="26" role="img" '
        f'aria-label="{_esc(info.name)}">'
        f'<rect width="{width}" height="26" rx="6" fill="{_esc(info.color)}"></rect>'
        f'<text x="10" y="18" fill="#FFFFFF" font-size="14">{_esc(text)}</text>'
        "</svg>"
    )


def _copy_field(field_id: str, value: str, label: str) -> str:
    return (
        f'<label>{_esc(label)} <input id="{_esc(field_id)}" value="{_esc(value)}" readonly></label>'
        f'<button type="button" class="btn-secondary" data-copy="{_esc(field_id)}">Copiar</button>'
    )


def _icon_options(selected: str, icons: dict[str, str]) -> str:
    return "".join(
        f'<option value="{_esc(key)}"{" selected" if key == selected else ""}>'
        f"{_esc(glyph)} {_esc(key)}</option>"
        for key, glyph in icons.items()
    )


def _consent_options(selected: str) -> str:
    labels = (("texto", "Texto (frase de aceptación)"), ("boton", "Botones Acepto / No acepto"))
    return "".join(
        f'<option value="{value}"{" selected" if value == selected else ""}>{label}</option>'
        for value, label in labels
    )


def render_channels(
    listing,
    csrf: str,
    *,
    icons: dict[str, str],
    glyph_for,
    webhook_for,
    error: str | None = None,
    revealed: tuple[str, str] | None = None,
    revealed_title: str = "Secreto del canal",
) -> str:
    """R10–R14, R20–R22, R30, R31: listado, alta y edición de canales."""
    parts: list[str] = []
    if error:
        parts.append(f'<p class="error" role="alert">{_esc(error)}</p>')
    if revealed is not None:
        channel_id, secret = revealed
        parts.append(
            '<section class="card" aria-live="polite">'
            f"<h3>{_esc(revealed_title)}: {_esc(channel_id)}</h3>"
            "<p>Guárdalo ahora: no se vuelve a mostrar en el listado.</p>"
            f"{_copy_field('secreto-revelado', secret, 'Secreto')}"
            "</section>"
        )
    rows = []
    for info in listing.channels:
        path = quote(info.id, safe="")
        consent = str(info.config.get("consent_mode", "texto"))
        hints = ", ".join(
            f"{_esc(name)} {_esc(hint)}" for name, hint in info.credential_hints.items()
        ) or "—"
        state = "Activo" if info.active else "Inactivo"
        toggle_to = "false" if info.active else "true"
        toggle_label = "Desactivar" if info.active else "Activar"
        webhook_html = ""
        secret_html = ""
        credentials_html = ""
        callback_html = ""
        if not info.managed_by_environment:
            url, configured = webhook_for(info.id)
            webhook_html = _copy_field(f"webhook-{info.id}", url, "URL del webhook")
            if not configured:
                webhook_html += (
                    '<p class="hint">Configura GATEWAY_PUBLIC_BASE_URL para ver la URL completa.</p>'
                )
            secret_html = (
                f'<form method="post" action="/admin/canales/{path}/secreto">'
                f"{csrf_field(csrf)}"
                '<button type="submit" class="btn-secondary">Ver secreto</button></form>'
                f'<form method="post" action="/admin/canales/{path}/secreto/regenerar">'
                f"{csrf_field(csrf)}"
                '<label><input type="checkbox" name="confirmar" value="si" required> '
                "Invalidar el secreto actual</label>"
                '<button type="submit" class="btn-secondary">Regenerar secreto</button></form>'
            )
            callback = str(info.config.get("callback_url", ""))
            callback_html = (
                '<label>URL de callback (si el adaptador la usa) '
                f'<input name="callback_url" value="{_esc(callback)}" placeholder="https://"></label>'
                '<label><input type="checkbox" name="clear_callback_url" value="si"> '
                "Quitar la URL de callback</label>"
            )
            credentials_html = (
                "<label>Credenciales (nombre=valor por línea; vacío = no cambiar) "
                '<textarea name="credentials" autocomplete="off"></textarea></label>'
            )
        rows.append(
            "<tr>"
            f"<td>{_channel_label(info, glyph_for(info.icon))}</td>"
            f"<td>{_esc(info.id)}</td>"
            f"<td>{_esc(info.adapter_type)}</td>"
            f"<td>{_esc(state)}</td>"
            f"<td>{_esc(consent)}</td>"
            f"<td>{hints}</td>"
            "<td>"
            f"{webhook_html}"
            f'<form method="post" action="/admin/canales/{path}">'
            f"{csrf_field(csrf)}"
            f'<label>Nombre <input name="name" value="{_esc(info.name)}" maxlength="60" required></label>'
            f'<label>Ícono <select name="icon">{_icon_options(info.icon, icons)}</select></label>'
            f'<label>Color <input name="color" value="{_esc(info.color)}" pattern="#[0-9A-Fa-f]{{6}}" required></label>'
            f'<label>Consentimiento <select name="consent_mode">{_consent_options(consent)}</select></label>'
            f"{callback_html}{credentials_html}"
            '<button type="submit" class="btn-secondary">Guardar</button>'
            "</form>"
            f'<form method="post" action="/admin/canales/{path}/activo">'
            f"{csrf_field(csrf)}"
            f'<input type="hidden" name="active" value="{toggle_to}">'
            f'<button type="submit" class="btn-secondary">{toggle_label}</button>'
            "</form>"
            f"{secret_html}"
            "</td>"
            "</tr>"
        )
    adapter_options = "".join(
        f'<option value="{_esc(adapter)}">{_esc(adapter)}</option>'
        for adapter in listing.adapter_types
    )
    if adapter_options:
        create = (
            '<form method="post" action="/admin/canales" class="card">'
            "<h3>Nuevo canal</h3>"
            f"{csrf_field(csrf)}"
            '<label>Id <input name="id" required minlength="2" maxlength="32" '
            'pattern="[a-z][a-z0-9]*([_\\-][a-z0-9]+)*"></label>'
            '<label>Nombre <input name="name" maxlength="60" required></label>'
            f'<label>Tipo de adaptador <select name="adapter_type">{adapter_options}</select></label>'
            f'<label>Ícono <select name="icon">{_icon_options("chat", icons)}</select></label>'
            '<label>Color <input name="color" value="#1B6FA8" pattern="#[0-9A-Fa-f]{6}" required></label>'
            f'<label>Consentimiento <select name="consent_mode">{_consent_options("texto")}</select></label>'
            '<label>URL de callback (si el adaptador la usa) '
            '<input name="callback_url" placeholder="https://"></label>'
            "<label>Credenciales (nombre=valor por línea) "
            '<textarea name="credentials" autocomplete="off"></textarea></label>'
            '<button type="submit">Crear canal</button>'
            "</form>"
        )
    else:
        create = "<p>No hay tipos de adaptador disponibles para crear canales.</p>"
    parts.append(create)
    parts.append(
        _table_wrap(
            "<table><thead><tr><th>Canal</th><th>Id</th><th>Adaptador</th><th>Estado</th>"
            "<th>Consentimiento</th><th>Credenciales</th><th>Acciones</th></tr></thead>"
            f"<tbody>{''.join(rows)}</tbody></table>"
        )
    )
    parts.append('<script src="/admin/static/canales.js" defer></script>')
    return render_page("Canales", "\n".join(parts), csrf, "/admin/canales")
