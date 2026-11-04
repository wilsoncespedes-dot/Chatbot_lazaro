"""Utilidades puras y plantillas HTML del panel administrativo."""
from __future__ import annotations

import html
import re
import secrets
from datetime import datetime
from urllib.parse import quote

CSP = "default-src 'self'; form-action 'self'; frame-ancestors 'none'"
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
}

_EMAIL_RE = re.compile(r"[^\s@]+@[^\s@]+")
_LONG_DIGITS_RE = re.compile(r"\d{6,}")
_LONG_TOKEN_RE = re.compile(r"[A-Za-z0-9_-]{20,}")

ADMIN_CSS = """
:root { color-scheme: light; }
body { font-family: system-ui, sans-serif; margin: 0; background: #f5f6f8; color: #1f2933; }
header { background: #1f3a5f; color: #fff; display: flex; align-items: center;
  justify-content: space-between; padding: 0.75rem 1.5rem; }
header h1 { font-size: 1.1rem; margin: 0; }
main { max-width: 960px; margin: 1.5rem auto; padding: 0 1rem; }
table { width: 100%; border-collapse: collapse; background: #fff; }
th, td { border: 1px solid #cbd2d9; padding: 0.4rem 0.6rem; text-align: left;
  vertical-align: top; }
th { background: #e4e7eb; }
form { display: flex; flex-wrap: wrap; gap: 0.5rem; align-items: end;
  margin: 0.75rem 0; }
label { display: flex; flex-direction: column; font-size: 0.85rem; gap: 0.2rem; }
input, select, button { font: inherit; padding: 0.35rem 0.45rem; }
button { cursor: pointer; }
.error { background: #fde8e8; border: 1px solid #c81e1e; padding: 0.5rem; }
code { background: #e4e7eb; padding: 0.1rem 0.3rem; }
nav ul { list-style: none; padding: 0; display: flex; gap: 1rem; }
"""


def redact_reason(reason: str) -> str:
    """Oculta correos, secuencias de 6+ dígitos y cadenas URL-safe de 20+ caracteres."""
    reason = _EMAIL_RE.sub(REDACTED, reason)
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


def _esc(value: object) -> str:
    return html.escape(str(value), quote=True)


def csrf_field(csrf: str) -> str:
    return f'<input type="hidden" name="csrf_token" value="{_esc(csrf)}">'


def render_page(title: str, body_html: str, csrf: str | None = None) -> str:
    logout = ""
    navigation = ""
    if csrf is not None:
        logout = (
            '<form method="post" action="/admin/logout">'
            f"{csrf_field(csrf)}"
            '<button type="submit">Salir</button>'
            "</form>"
        )
        navigation = (
            '<nav><ul>'
            '<li><a href="/admin">Inicio</a></li>'
            '<li><a href="/admin/profiles">Perfiles y roles</a></li>'
            '<li><a href="/admin/events">Eventos recientes</a></li>'
            '<li><a href="/admin/manuals">Manuales</a></li>'
            '<li><a href="/admin/categories">Categorías</a></li>'
            '<li><a href="/admin/texts">Textos del flujo</a></li>'
            '<li><a href="/admin/clientes">Clientes</a></li>'
            '<li><a href="/admin/plantillas">Plantillas</a></li>'
            '<li><a href="/admin/ajustes">Ajustes</a></li>'
            '<li><a href="/admin/metricas">Métricas</a></li>'
            '<li><a href="/admin/supresiones">Supresiones</a></li>'
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
        f"<header><h1>Panel administrativo</h1>{logout}</header>\n"
        f"<main>\n{navigation}<h2>{_esc(title)}</h2>\n{body_html}\n</main>\n"
        "</body>\n"
        "</html>\n"
    )


def render_login(message: str | None = None) -> str:
    error = ""
    if message:
        error = f'<p class="error" role="alert">{_esc(message)}</p>\n'
    body = (
        f"{error}"
        '<form method="post" action="/admin/login">'
        '<label>Usuario <input name="username" autocomplete="username" required></label>'
        '<label>Contraseña <input type="password" name="password" '
        'autocomplete="current-password" required></label>'
        '<button type="submit">Entrar</button>'
        "</form>"
    )
    return render_page("Iniciar sesión", body)


def render_home(csrf: str) -> str:
    return render_page("Inicio", "<p>Selecciona una sección del panel.</p>", csrf)


def render_profiles(profiles, csrf: str, error: str | None = None) -> str:
    rows = []
    for profile in profiles:
        linked = "Sí" if profile.telegram_user_id is not None else "No"
        role_options = "".join(
            f'<option value="{_esc(role)}"'
            f'{" selected" if role == profile.role else ""}>{_esc(role)}</option>'
            for role in ("admin", "asesor", "cliente")
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
            '<button type="submit">Cambiar rol</button>'
            "</form>"
            "</td>"
            "<td>"
            f'<form method="post" action="/admin/profiles/{_esc(profile.id)}/link-token">'
            f"{csrf_field(csrf)}"
            '<button type="submit">Generar enlace</button>'
            "</form>"
            "</td>"
            "</tr>"
        )
    error_html = ""
    if error:
        error_html = f'<p class="error" role="alert">{_esc(error)}</p>\n'
    body = (
        f"{error_html}"
        '<form method="post" action="/admin/profiles">'
        f"{csrf_field(csrf)}"
        '<label>Usuario <input name="username" autocomplete="off" required></label>'
        '<label>Rol <select name="role">'
        '<option value="admin">admin</option>'
        '<option value="asesor">asesor</option>'
        '<option value="cliente">cliente</option>'
        "</select></label>"
        '<label>Contraseña <input type="password" name="password" '
        'autocomplete="new-password" required></label>'
        '<button type="submit">Crear perfil</button>'
        "</form>"
        "<table><thead><tr><th>Usuario</th><th>Rol</th><th>Vinculado</th>"
        "<th>Cambiar rol</th><th>Enlace de Telegram</th></tr></thead><tbody>"
        f"{''.join(rows)}"
        "</tbody></table>"
    )
    return render_page("Perfiles y roles", body, csrf)


def render_link(token: str, link: str | None, expires_at: datetime, csrf: str) -> str:
    shown = link if link is not None else token
    body = (
        f"<p>Enlace: <code>{_esc(shown)}</code></p>"
        f"<p>Caduca: <code>{_esc(expires_at.isoformat())}</code></p>"
        '<p><a href="/admin/profiles">Volver a perfiles</a></p>'
    )
    return render_page("Enlace de vinculación", body, csrf)


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
    body = (
        "<table><thead><tr><th>Contacto</th><th>Tipo</th><th>Motivo</th>"
        f"<th>Fecha</th></tr></thead><tbody>{rows}</tbody></table>"
    )
    return render_page("Eventos recientes", body, csrf)


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
        table = (
            "<table><thead><tr><th>Manual</th><th>Fragmentos</th></tr></thead>"
            f"<tbody>{rows}</tbody></table>"
        )
    upload = (
        '<form method="post" action="/admin/manuals" enctype="multipart/form-data">'
        f"{csrf_field(csrf)}"
        '<label>Nombre <input name="name" maxlength="200" required></label>'
        '<label>Archivo <input type="file" name="file" accept=".pdf,.docx" required></label>'
        '<button type="submit">Cargar manual</button>'
        "</form>"
    )
    return render_page("Manuales", f"{error_html}{upload}\n{table}", csrf)


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
            '<button type="submit">Guardar texto</button>'
            "</form>"
            "</td>"
            "<td>"
            f'<form method="post" action="/admin/chunks/{chunk_path}/active">'
            f"{csrf_field(csrf)}"
            f'<input type="hidden" name="active" value="{next_active}">'
            f'<button type="submit">{action}</button>'
            "</form>"
            "</td>"
            "</tr>"
        )
    body = (
        f'<p><a href="/admin/manuals">Volver a manuales</a></p>'
        "<table><thead><tr><th>Orden</th><th>Texto</th><th>Activo</th>"
        "<th>Editar texto</th><th>Estado</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table>"
    )
    return render_page(f"Fragmentos del manual {manual_id}", body, csrf)


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
            '<button type="submit">Guardar</button>'
            "</form>"
            "</td>"
            "<td>"
            f'<form method="post" action="/admin/categories/{category_path}/active">'
            f"{csrf_field(csrf)}"
            f'<input type="hidden" name="active" value="{next_active}">'
            f'<button type="submit">{action}</button>'
            "</form>"
            "</td>"
            "</tr>"
        )
    error_html = ""
    if error:
        error_html = f'<p class="error" role="alert">{_esc(error)}</p>\n'
    create = (
        '<form method="post" action="/admin/categories">'
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
        '<form method="post" action="/admin/categories/threshold">'
        f"{csrf_field(csrf)}"
        f'<label>Umbral <input name="threshold" value="{_esc(threshold_text)}" '
        'inputmode="decimal" required></label>'
        '<button type="submit">Guardar umbral</button>'
        "</form>"
    )
    body = (
        f"{error_html}{threshold_form}\n{create}\n"
        "<table><thead><tr><th>Código</th><th>Nombre</th><th>Palabras clave</th>"
        "<th>Activa</th><th>Editar</th><th>Estado</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table>"
    )
    return render_page("Categorías", body, csrf)


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
        '<form method="post" action="/admin/texts">'
        f"{csrf_field(csrf)}"
        f"{fields_html}"
        '<button type="submit">Guardar textos</button>'
        "</form>"
        '<p>La versión legal se guarda junto al texto; al cambiarla, los '
        "clientes deberán aceptar de nuevo antes de continuar.</p>"
    )
    return render_page("Textos del flujo", body, csrf)


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
        "<table><thead><tr><th>Versión</th><th>Autor</th><th>Fecha</th>"
        f"<th>Valor</th></tr></thead><tbody>{rows}</tbody></table>"
    )
    return render_page(f"Historial de {field}", body, csrf)


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
            '<button type="submit">Renovar</button>'
            "</form>"
            f'<form method="post" action="/admin/clientes/{path}/revocar">'
            f"{csrf_field(csrf)}"
            '<button type="submit">Revocar</button>'
            "</form>"
            f'<form method="post" action="/admin/clientes/{path}/cerrar-sesion">'
            f"{csrf_field(csrf)}"
            '<button type="submit">Cerrar sesión</button>'
            "</form>"
            "</td>"
            "</tr>"
        )
    body = (
        f"{error_html}"
        '<form method="post" action="/admin/clientes">'
        f"{csrf_field(csrf)}"
        '<label>Usuario <input name="username" autocomplete="off" required></label>'
        '<label>Contraseña <input type="password" name="password" '
        'autocomplete="new-password" required></label>'
        '<label>Válida desde <input type="date" name="valid_from"></label>'
        '<label>Válida hasta <input type="date" name="valid_until"></label>'
        '<button type="submit">Crear cliente</button>'
        "</form>"
        "<table><thead><tr><th>Usuario</th><th>Estado</th><th>Desde</th>"
        "<th>Hasta</th><th>Días</th><th>Sesión</th><th>Aviso</th>"
        f"<th>Acciones</th></tr></thead><tbody>{''.join(rows)}</tbody></table>"
    )
    return render_page("Clientes", body, csrf)


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
            '<button type="submit">Guardar</button>'
            "</form>"
            f'<form method="post" action="/admin/plantillas/{path}/estado">'
            f"{csrf_field(csrf)}"
            '<select name="status">'
            + "".join(
                f'<option value="{_esc(status)}">{_esc(status)}</option>'
                for status in ("pending", "approved", "rejected", "paused", "draft")
            )
            + "</select>"
            '<button type="submit">Cambiar estado</button>'
            "</form>"
            "</td>"
            "</tr>"
        )
    create = (
        '<form method="post" action="/admin/plantillas">'
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
        "<table><thead><tr><th>Nombre</th><th>Propósito</th><th>Idioma</th>"
        "<th>Variables</th><th>Texto</th><th>Estado</th><th>Aprobación</th>"
        f"<th>Acciones</th></tr></thead><tbody>{''.join(rows)}</tbody></table>"
    )
    return render_page("Plantillas de WhatsApp", body, csrf)


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
        inputs.append(
            f'<label>{_esc(row["key"])} '
            f'<input name="{_esc(row["key"])}" value="{_esc(row["effective"])}" '
            f'placeholder="{_esc(row["default"])}"></label>'
        )
    body = (
        f"{error_html}"
        "<table><thead><tr><th>Clave</th><th>Efectivo</th><th>Por defecto</th>"
        f"<th>Origen</th><th>Rango</th></tr></thead><tbody>{''.join(rows)}</tbody></table>"
        '<form method="post" action="/admin/ajustes">'
        f"{csrf_field(csrf)}"
        f"{''.join(inputs)}"
        '<button type="submit">Guardar ajustes</button>'
        "</form>"
        "<p>Deja un campo vacío para volver al valor de entorno.</p>"
    )
    return render_page("Ajustes operativos", body, csrf)


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
        f"<table><tbody>{advisors}</tbody></table>"
        "<h3>Motivos de escalamiento</h3>"
        f"<table><tbody>{reasons}</tbody></table>"
        f"<h3>Preguntas sin respuesta: {_esc(metrics.unanswered_total)}</h3>"
        f"<ul>{samples}</ul>"
    )
    return render_page("Métricas", body, csrf)


def render_error(status: int, code: str, csrf: str | None = None) -> str:
    message = ERROR_MESSAGES.get(code, "No se pudo completar la operación.")
    return render_page(f"Error {status}", f"<p>{_esc(message)}</p>", csrf)


def render_message(title: str, message: str, csrf: str | None = None) -> str:
    return render_page(title, f"<p>{_esc(message)}</p>", csrf)
