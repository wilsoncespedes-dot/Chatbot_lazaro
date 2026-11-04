"""Plantillas HTML del panel de asesores (renderizado en el servidor, sin JS)."""
from __future__ import annotations

import html
from urllib.parse import quote

from . import admin

ERROR_MESSAGES = {
    "forbidden": "No tienes permiso para realizar esa acción.",
    "not_found": "El caso no existe.",
    "case_closed": "El caso ya está cerrado.",
    "validation_error": "Los datos enviados no son válidos.",
    "upstream_error": "El servicio de casos no está disponible.",
    "telegram_not_linked": "Tu perfil no tiene una cuenta de Telegram vinculada.",
    "channel_window_closed": "La ventana de WhatsApp del cliente está cerrada.",
    "advisor_unavailable": "El asesor destino no está disponible.",
    "suppression_not_pending": "La solicitud de supresión ya no está pendiente.",
}

OK_MESSAGES = {
    "reply": "Respuesta enviada al cliente.",
    "assign": "Caso asignado.",
    "close": "Caso cerrado.",
    "transfer": "Caso transferido.",
    "return": "Caso devuelto al asistente virtual.",
    "presence": "Presencia actualizada.",
    "suppression": "Solicitud de supresión ejecutada.",
}

WINDOW_LABELS = {
    "open": "Abierta",
    "closed": "Cerrada",
    "not_applicable": "No aplica",
}
ROLE_LABELS = {"user": "Cliente", "bot": "Bot", "advisor": "Asesor"}


def _esc(value: object) -> str:
    return html.escape(str(value), quote=True)


def _page(
    title: str, body_html: str, csrf: str | None = None, refresh: int = 0
) -> str:
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
            '<li><a href="/asesor/supresiones">Supresiones</a></li>'
            "</ul></nav>\n"
        )
    meta = (
        f'<meta http-equiv="refresh" content="{int(refresh)}">\n'
        if refresh > 0
        else ""
    )
    return (
        "<!DOCTYPE html>\n"
        '<html lang="es">\n'
        "<head>\n"
        '<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f"{meta}"
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


def render_advisor_home(
    csrf: str,
    ok: str | None = None,
    linked: bool = True,
    presence: str | None = None,
) -> str:
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

    presence_form = (
        '<h3>Mi presencia</h3>'
        '<form method="post" action="/asesor/presence">'
        f"{admin.csrf_field(csrf)}"
        f'<label>Estado <select name="status">'
        f'<option value="available"{" selected" if presence == "available" else ""}>'
        "Disponible</option>"
        f'<option value="away"{" selected" if presence == "away" else ""}>'
        "Ausente</option>"
        "</select></label>"
        '<button type="submit">Guardar presencia</button>'
        "</form>"
    )
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
        '<button type="submit">Resolver</button>'
        "</form>"
    )
    return _page(
        "Inicio",
        f"{ok_html}{presence_form}\n{reply}\n{assign}\n{close}",
        csrf,
    )


def render_advisor_cases(rows, csrf: str, refresh: int = 0) -> str:
    table_rows = []
    for row in rows:
        wait = (
            f"{int(row.wait.total_seconds() // 60)} min"
            if row.wait is not None
            else "—"
        )
        window = WINDOW_LABELS.get(row.window, "—") if row.window else "—"
        assignment = "Mío" if row.assignment == "mine" else "Sin asignar"
        client = row.client_name if row.client_name else "Sin autenticar"
        conversation = row.conversation_state or "—"
        table_rows.append(
            "<tr>"
            f"<td>{_esc(row.case_id)}</td>"
            f"<td>{_esc(row.channel)}</td>"
            f"<td>{_esc(row.status)}</td>"
            f"<td>{_esc(row.created_at.isoformat())}</td>"
            f"<td>{_esc(conversation)}</td>"
            f"<td>{_esc(assignment)}</td>"
            f"<td>{_esc(wait)}</td>"
            f"<td>{_esc(window)}</td>"
            f"<td>{_esc(client)}</td>"
            f"<td>{_esc(', '.join(row.actions))}</td>"
            '<td><a href="/asesor/cases/'
            f'{_esc(quote(row.case_id, safe=""))}">Abrir</a></td>'
            '<td><a href="/asesor/cases/'
            f'{_esc(quote(row.case_id, safe=""))}/memoria">Memoria</a></td>'
            "</tr>"
        )
    filters = (
        '<form method="get" action="/asesor/cases">'
        '<label>Canal <select name="canal">'
        '<option value="">Todos</option>'
        '<option value="telegram">Telegram</option>'
        '<option value="whatsapp">WhatsApp</option>'
        "</select></label>"
        '<label>Asignación <select name="asignacion">'
        '<option value="">Todas</option>'
        '<option value="mias">Mías</option>'
        '<option value="sin_asignar">Sin asignar</option>'
        "</select></label>"
        '<button type="submit">Filtrar</button>'
        "</form>"
    )
    body = (
        f"{filters}"
        "<table><thead><tr><th>Caso</th><th>Canal</th><th>Estado</th>"
        "<th>Creado</th><th>Conversación</th><th>Asignación</th><th>Espera</th>"
        "<th>Ventana</th><th>Cliente</th><th>Acciones</th><th>Abrir</th>"
        "<th>Memoria</th>"
        f"</tr></thead><tbody>{''.join(table_rows)}</tbody></table>"
    )
    return _page("Casos", body, csrf, refresh=refresh)


def _history_section(view) -> str:
    if not view.history:
        rows = "<p>Sin mensajes en el periodo visible.</p>"
    else:
        rows = "<table><thead><tr><th>Rol</th><th>Mensaje</th><th>Fecha</th>" \
            "</tr></thead><tbody>" + "".join(
                "<tr>"
                f"<td>{_esc(ROLE_LABELS.get(item.role, item.role))}</td>"
                f"<td>{_esc(item.text)}</td>"
                f"<td>{_esc(item.at.isoformat())}</td>"
                "</tr>"
                for item in view.history
            ) + "</tbody></table>"
    return f"<h3>Historial</h3>{rows}"


def _client_section(view) -> str:
    client = view.client
    if client.username is None:
        return (
            "<h3>Cliente</h3>"
            '<p role="status">Sin cliente autenticado</p>'
            f"<p>Canal: {_esc(client.channel)} · Identificador: "
            f"{_esc(client.masked_external_id)} · Conversación: "
            f"{_esc(client.conversation_state or '—')}</p>"
        )
    return (
        "<h3>Cliente</h3>"
        "<table><tbody>"
        f"<tr><th>Canal</th><td>{_esc(client.channel)}</td></tr>"
        f"<tr><th>Identificador</th><td>{_esc(client.masked_external_id)}</td></tr>"
        f"<tr><th>Conversación</th>"
        f"<td>{_esc(client.conversation_state or '—')}</td></tr>"
        f"<tr><th>Consentimiento</th>"
        f"<td>{_esc(client.consent_result or '—')}</td></tr>"
        f"<tr><th>Versión del aviso</th>"
        f"<td>{_esc(client.consent_version or '—')}</td></tr>"
        f"<tr><th>Fecha del consentimiento</th>"
        f"<td>{_esc(client.consent_at.isoformat() if client.consent_at else '—')}"
        "</td></tr>"
        f"<tr><th>Usuario</th><td>{_esc(client.username)}</td></tr>"
        f"<tr><th>Credencial</th>"
        f"<td>{_esc(client.credential_status or '—')}</td></tr>"
        f"<tr><th>Días restantes</th>"
        f"<td>{_esc(client.days_remaining if client.days_remaining is not None else '—')}"
        "</td></tr>"
        f"<tr><th>Sesión activa</th>"
        f"<td>{_esc('Sí' if client.has_active_session else 'No')}</td></tr>"
        "</tbody></table>"
    )


def _memory_section(view) -> str:
    if view.client.username is None:
        return ""
    memory = view.memory
    if memory.items:
        items = "<ul>" + "".join(f"<li>{_esc(item)}</li>" for item in memory.items) + "</ul>"
    else:
        items = "<p>Sin elementos de memoria.</p>"
    summary_rows = "".join(
        "<tr>"
        f"<td>{_esc(item.channel)}</td>"
        f"<td>{_esc(item.updated_at.isoformat())}</td>"
        f"<td>{_esc(item.trigger)}</td>"
        f"<td>{_esc(item.summary)}</td>"
        "</tr>"
        for item in memory.summaries
    )
    return (
        "<h3>Memoria y resúmenes</h3>"
        f"{items}"
        "<table><thead><tr><th>Canal</th><th>Fecha</th><th>Motivo</th>"
        f"<th>Resumen</th></tr></thead><tbody>{summary_rows}</tbody></table>"
    )


def render_advisor_case(view, csrf: str) -> str:
    case_path = _esc(quote(view.case_id, safe=""))
    if view.window == "closed":
        options = "".join(
            f'<option value="{_esc(name)}">{_esc(name)}</option>'
            for name in view.templates
        )
        reply_field = (
            '<label>Plantilla <select name="template">'
            f"{options}</select></label>"
        )
    else:
        reply_field = (
            '<label>Respuesta <textarea name="text" maxlength="4096" required>'
            "</textarea></label>"
        )
    reply_form = (
        '<h3>Responder</h3>'
        '<form method="post" action="/asesor/reply">'
        f"{admin.csrf_field(csrf)}"
        f'<input type="hidden" name="case_id" value="{_esc(view.case_id)}">'
        f"{reply_field}"
        '<button type="submit">Enviar</button>'
        "</form>"
    )
    targets = "".join(
        f'<option value="{_esc(profile_id)}">{_esc(username)} '
        f"({_esc(presence)})</option>"
        for profile_id, username, presence in view.transfer_targets
    )
    transfer_form = (
        '<h3>Transferir</h3>'
        '<form method="post" action="/asesor/transfer">'
        f"{admin.csrf_field(csrf)}"
        f'<input type="hidden" name="case_id" value="{_esc(view.case_id)}">'
        f'<label>Asesor destino <select name="target_profile_id">{targets}'
        "</select></label>"
        '<button type="submit">Transferir</button>'
        "</form>"
    )
    resolve_form = (
        '<h3>Resolver</h3>'
        '<form method="post" action="/asesor/close">'
        f"{admin.csrf_field(csrf)}"
        f'<input type="hidden" name="case_id" value="{_esc(view.case_id)}">'
        '<button type="submit">Resolver</button>'
        "</form>"
    )
    return_form = (
        '<h3>Devolver al asistente</h3>'
        '<form method="post" action="/asesor/return">'
        f"{admin.csrf_field(csrf)}"
        f'<input type="hidden" name="case_id" value="{_esc(view.case_id)}">'
        '<button type="submit">Devolver</button>'
        "</form>"
    )
    body = (
        f'<p><a href="/asesor/cases">Volver a la bandeja</a> · '
        f"Caso {_esc(view.case_id)} · Estado: {_esc(view.client.conversation_state or '—')}"
        f" · Ventana: {_esc(WINDOW_LABELS.get(view.window, view.window))}</p>"
        f"{_client_section(view)}"
        f"{_history_section(view)}"
        f"{_memory_section(view)}"
        f"{reply_form}\n{transfer_form}\n{resolve_form}\n{return_form}"
    )
    return _page(f"Caso {view.case_id}", body, csrf, refresh=0)


def render_suppression_queue(rows, csrf: str, action_prefix: str) -> str:
    ordered = list(rows)
    table_rows = []
    for row in ordered:
        request = row.request
        state = "Pendiente" if request.status == "pending" else "Ejecutada"
        priority = row.priority or "—"
        executed = ""
        if request.status == "executed":
            counts = request.removed_counts or {}
            summary = ", ".join(f"{key}: {value}" for key, value in counts.items())
            executed = (
                f"<tr><th>Ejecutada</th><td>{_esc(request.executed_at.isoformat() if request.executed_at else '—')}"
                f" · {_esc(row.executor_username or '—')} · {_esc(summary)}"
                f" · Nota: {_esc(request.result_note or '—')}"
                f" · Aviso: {_esc(request.notification_result or '—')}</td></tr>"
            )
        form = ""
        if request.status == "pending":
            form = (
                f'<form method="post" action="{_esc(action_prefix)}/'
                f'{_esc(quote(request.id, safe=""))}/execute">'
                f"{admin.csrf_field(csrf)}"
                '<label>Nota <textarea name="note" maxlength="500"></textarea></label>'
                '<button type="submit">Ejecutar supresión</button>'
                "</form>"
            )
        table_rows.append(
            "<tr>"
            f"<td>{_esc(request.id)}</td>"
            f"<td>{_esc(row.client_username or '—')}</td>"
            f"<td>{_esc(request.channel)}</td>"
            f"<td>{_esc(request.created_at.isoformat())}</td>"
            f"<td>{_esc(row.deadline.isoformat())}</td>"
            f"<td>{_esc(priority)}</td>"
            f"<td>{_esc(state)}</td>"
            f"<td>{_esc(request.case_id or '—')}</td>"
            f"<td>{form}</td>"
            "</tr>"
            f"{''.join(item for item in [executed] if item)}"
        )
    body = (
        "<table><thead><tr><th>Solicitud</th><th>Cliente</th><th>Canal</th>"
        "<th>Creada</th><th>Fecha límite</th><th>Prioridad</th><th>Estado</th>"
        "<th>Caso</th><th>Acción</th></tr></thead>"
        f"<tbody>{''.join(table_rows)}</tbody></table>"
    )
    return _page("Cola de supresión", body, csrf)


def render_advisor_memory(view, csrf: str) -> str:
    if not view.authenticated:
        body = (
            '<p class="error" role="status">Sin cliente autenticado</p>'
            "<p>El caso no tiene un cliente autenticado asociado; no hay memoria "
            "ni resumen que mostrar.</p>"
        )
        return _page("Memoria del cliente", body, csrf)

    updated = ""
    if view.memory_updated_at is not None:
        updated = (
            "<p>Memoria actualizada: "
            f"{_esc(view.memory_updated_at.isoformat())}</p>"
        )
    if view.items:
        memory = "<ul>" + "".join(
            f"<li>{_esc(item)}</li>" for item in view.items
        ) + "</ul>"
    else:
        memory = "<p>Sin elementos de memoria.</p>"
    summary_rows = "".join(
        "<tr>"
        f"<td>{_esc(item.channel)}</td>"
        f"<td>{_esc(item.updated_at.isoformat())}</td>"
        f"<td>{_esc(item.trigger)}</td>"
        f"<td>{_esc(item.summary)}</td>"
        "</tr>"
        for item in view.summaries
    )
    summaries = (
        "<h3>Resúmenes de conversaciones</h3>"
        "<table><thead><tr><th>Canal</th><th>Fecha</th><th>Motivo</th>"
        f"<th>Resumen</th></tr></thead><tbody>{summary_rows}</tbody></table>"
    )
    body = f"<h3>Memoria</h3>{updated}{memory}{summaries}"
    return _page("Memoria del cliente", body, csrf)


def render_advisor_error(status: int, code: str, csrf: str | None = None) -> str:
    message = ERROR_MESSAGES.get(code, "No se pudo completar la operación.")
    body = (
        f'<p class="error" role="alert" data-code="{_esc(code)}">'
        f"{_esc(message)}</p>"
    )
    return _page(f"Error {status}", body, csrf)
