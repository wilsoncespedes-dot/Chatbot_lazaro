"""Plantillas HTML del panel de asesores (renderizado en el servidor, sin JS)."""
from __future__ import annotations

import html
from datetime import datetime, timezone
from urllib.parse import quote, urlencode

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
    "case_changed": "El caso cambió mientras se reasignaba. Vuelve a cargarlo.",
    "case_not_assigned": "El caso no está asignado.",
    "tag_name_taken": "Ya existe una etiqueta con ese nombre.",
    "note_not_found": "La nota no existe.",
    "tag_not_found": "La etiqueta no existe.",
    "saved_reply_not_found": "La respuesta guardada no existe.",
    "saved_reply_variables_not_allowed": (
        "Las respuestas guardadas son texto plano y no admiten variables."
    ),
}

OK_MESSAGES = {
    "reply": "Respuesta enviada al cliente.",
    "assign": "Caso asignado.",
    "close": "Caso cerrado.",
    "transfer": "Caso transferido.",
    "reassign": "Caso reasignado.",
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
ROLE_CLASSES = {
    "user": "chat-msg-client",
    "advisor": "chat-msg-advisor",
    "bot": "chat-msg-bot",
}


def _esc(value: object) -> str:
    return html.escape(str(value), quote=True)


def _chat_datetime(at: datetime) -> datetime:
    """R3: un `at` sin zona se interpreta como UTC también en `datetime`."""
    if at.tzinfo is None:
        return at.replace(tzinfo=timezone.utc)
    return at


def _chat_time(at: datetime) -> str:
    """R3: fecha y hora en UTC con el formato `dd/mm HH:MM UTC`."""
    return _chat_datetime(at).astimezone(timezone.utc).strftime("%d/%m %H:%M") + " UTC"


def _page(
    title: str,
    body_html: str,
    csrf: str | None = None,
    refresh: int = 0,
    nav_links: list[tuple[str, str]] | None = None,
    script: str = "",
    current_path: str | None = None,
    wide: bool = False,
) -> str:
    logout = ""
    navigation = ""
    if csrf is not None:
        logout = (
            '<form method="post" action="/asesor/logout">'
            f"{admin.csrf_field(csrf)}"
            '<button type="submit" class="btn-secondary">Salir</button>'
            "</form>"
        )
        links = nav_links or [
            ("/asesor", "Inicio"),
            ("/asesor/cases", "Casos"),
            ("/asesor/supresiones", "Supresiones"),
        ]
        # #56: se reutilizan a propósito los helpers privados de `admin` para
        # que ambos paneles compartan cabecera, navegación y enlace de salto.
        navigation = admin._nav_html(
            links, current_path, "Navegación del panel de asesores"
        )
    meta = (
        f'<noscript><meta http-equiv="refresh" content="{int(refresh)}"></noscript>\n'
        if refresh > 0
        else ""
    )
    main_class = ' class="wide"' if wide else ""
    return (
        "<!DOCTYPE html>\n"
        '<html lang="es">\n'
        "<head>\n"
        '<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f"{meta}{script}"
        f"<title>{_esc(title)}</title>\n"
        '<link rel="stylesheet" href="/admin/static/admin.css">\n'
        "</head>\n"
        "<body>\n"
        f"{admin._skip_link()}\n"
        f'<header class="site-header"><h1>Panel de asesores</h1>{logout}</header>\n'
        f'<main id="contenido"{main_class}>\n{navigation}<h2>{_esc(title)}</h2>\n'
        f"{body_html}\n</main>\n"
        "</body>\n"
        "</html>\n"
    )


def _badge_class(status: str | None) -> str:
    """R18: clase semántica distinta para abierto, asignado y cerrado."""
    key = (status or "").lower()
    if key in ("open", "new", "active"):
        return "badge badge-ok"
    if key in ("assigned", "with_advisor"):
        return "badge badge-info"
    if key in ("closed", "timed_out"):
        return "badge badge-warn"
    return "badge"


def _badge(status: str | None) -> str:
    text = status if status else "—"
    return f'<span class="{_badge_class(status)}">{_esc(text)}</span>'


def render_advisor_login(message: str | None = None, code: str | None = None) -> str:
    error = ""
    if message:
        data = f' data-error="{_esc(code)}"' if code else ""
        error = f'<p class="error" role="alert"{data}>{_esc(message)}</p>\n'
    body = (
        f"{error}"
        '<form method="post" action="/asesor/login" class="card">'
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
    role: str = "asesor",
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
        return _page("Inicio", f"{ok_html}{warning}", csrf, current_path="/asesor")

    presence_form = (
        '<h3>Mi presencia</h3>'
        '<form method="post" action="/asesor/presence" class="card">'
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
        '<form method="post" action="/asesor/reply" class="card">'
        f"{admin.csrf_field(csrf)}"
        '<label>Caso <input name="case_id" maxlength="64" required></label>'
        '<label>Respuesta <textarea name="text" maxlength="4096" required></textarea></label>'
        '<button type="submit">Enviar respuesta</button>'
        "</form>"
    )
    assign = (
        '<h3>Asignarme un caso</h3>'
        '<form method="post" action="/asesor/assign" class="card">'
        f"{admin.csrf_field(csrf)}"
        '<label>Caso <input name="case_id" maxlength="64" required></label>'
        '<button type="submit">Asignar</button>'
        "</form>"
    )
    close = (
        '<h3>Cerrar un caso</h3>'
        '<form method="post" action="/asesor/close" class="card">'
        f"{admin.csrf_field(csrf)}"
        '<label>Caso <input name="case_id" maxlength="64" required></label>'
        '<button type="submit" class="btn-danger">Resolver</button>'
        "</form>"
    )
    supervisor = ""
    if role == "supervisor":
        supervisor = (
            '<h3>Supervisión</h3>'
            '<ul>'
            '<li><a href="/asesor/todos">Todos los casos</a></li>'
            '<li><a href="/asesor/metricas">Métricas</a></li>'
            "</ul>"
        )
    return _page(
        "Inicio",
        f"{ok_html}{presence_form}\n{reply}\n{assign}\n{close}\n{supervisor}",
        csrf,
        current_path="/asesor",
    )


def render_inbox_table(
    rows,
    csrf: str,
    show_advisor: bool = False,
    all_view: bool = False,
    reassign_targets: tuple[tuple[str, str, str], ...] = (),
) -> str:
    """R23, R30: solo la tabla de casos, para reemplazarla sin duplicar filas."""
    table_rows = []
    target_options = "".join(
        f'<option value="{_esc(profile_id)}">{_esc(username)} '
        f"({_esc(presence)})</option>"
        for profile_id, username, presence in reassign_targets
    )
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
        advisor_cell = (
            f"<td>{_esc(row.assigned_advisor or '—')}</td>"
            if show_advisor
            else ""
        )
        reassign_cell = ""
        if all_view and "reassign" in row.actions and target_options:
            reassign_cell = (
                "<td>"
                '<form method="post" class="inline" action="/asesor/casos/'
                f'{_esc(quote(row.case_id, safe=""))}/reasignar">'
                f"{admin.csrf_field(csrf)}"
                f'<select name="target_profile_id">{target_options}</select>'
                '<button type="submit" class="btn-secondary">Reasignar</button>'
                "</form>"
                "</td>"
            )
        table_rows.append(
            "<tr>"
            f"<td>{_esc(row.case_id)}</td>"
            f"<td>{_esc(row.channel)}</td>"
            f"<td>{_badge(row.status)}</td>"
            f"<td>{_esc(row.created_at.isoformat())}</td>"
            f"<td>{_esc(conversation)}</td>"
            f"<td>{_esc(assignment)}</td>"
            f"{advisor_cell}"
            f"<td>{_esc(wait)}</td>"
            f"<td>{_esc(window)}</td>"
            f"<td>{_esc(client)}</td>"
            f"<td>{_esc(', '.join(row.tags))}</td>"
            f"<td>{_esc(', '.join(row.actions))}</td>"
            '<td><a href="/asesor/cases/'
            f'{_esc(quote(row.case_id, safe=""))}">Abrir</a></td>'
            '<td><a href="/asesor/cases/'
            f'{_esc(quote(row.case_id, safe=""))}/memoria">Memoria</a></td>'
            f"{reassign_cell}"
            "</tr>"
        )
    advisor_header = "<th>Asesor</th>" if show_advisor else ""
    reassign_header = "<th>Reasignar</th>" if all_view and target_options else ""
    table = (
        "<table><thead><tr><th>Caso</th><th>Canal</th><th>Estado</th>"
        "<th>Creado</th><th>Conversación</th><th>Asignación</th>"
        f"{advisor_header}<th>Espera</th>"
        "<th>Ventana</th><th>Cliente</th><th>Etiquetas</th><th>Acciones</th>"
        f"<th>Abrir</th><th>Memoria</th>{reassign_header}"
        f"</tr></thead><tbody>{''.join(table_rows)}</tbody></table>"
    )
    return admin._table_wrap(table)


def _live_inbox_src(
    all_view: bool,
    selected_channel: str | None,
    selected_assignment: str | None,
    selected_tag: str | None,
) -> str:
    params: list[tuple[str, str]] = []
    if selected_channel:
        params.append(("canal", selected_channel))
    if selected_assignment:
        params.append(("asignacion", selected_assignment))
    if selected_tag:
        params.append(("tag", selected_tag))
    if all_view:
        params.append(("scope", "all"))
    query = urlencode(params)
    return "/asesor/live/inbox" + (f"?{query}" if query else "")


def render_advisor_cases(
    rows,
    csrf: str,
    refresh: int = 0,
    title: str = "Casos",
    show_advisor: bool = False,
    all_view: bool = False,
    reassign_targets: tuple[tuple[str, str, str], ...] = (),
    tags=(),
    selected_channel: str | None = None,
    selected_assignment: str | None = None,
    selected_tag: str | None = None,
    live_enabled: bool = False,
) -> str:
    filters_action = "/asesor/todos" if all_view else "/asesor/cases"
    channel_options = "".join(
        f'<option value="{_esc(value)}"'
        f'{" selected" if selected_channel == value else ""}>{_esc(label)}</option>'
        for value, label in (
            ("", "Todos"),
            ("telegram", "Telegram"),
            ("whatsapp", "WhatsApp"),
        )
    )
    assignment_options = "".join(
        f'<option value="{_esc(value)}"'
        f'{" selected" if selected_assignment == value else ""}>{_esc(label)}</option>'
        for value, label in (
            ("", "Todas"),
            ("mias", "Mías"),
            ("sin_asignar", "Sin asignar"),
        )
    )
    tag_options = "".join(
        f'<option value="{_esc(tag.id)}"'
        f'{" selected" if selected_tag == tag.id else ""}>{_esc(tag.name)}</option>'
        for tag in tags
    )
    filters = (
        f'<form method="get" action="{filters_action}" class="card">'
        f'<label>Canal <select name="canal">{channel_options}</select></label>'
        f'<label>Asignación <select name="asignacion">{assignment_options}'
        "</select></label>"
        '<label>Etiqueta <select name="tag">'
        f'<option value="">Todas</option>{tag_options}'
        "</select></label>"
        '<button type="submit" class="btn-secondary">Filtrar</button>'
        "</form>"
    )
    table = render_inbox_table(
        rows,
        csrf,
        show_advisor=show_advisor,
        all_view=all_view,
        reassign_targets=reassign_targets,
    )
    live_src = _esc(
        _live_inbox_src(
            all_view, selected_channel, selected_assignment, selected_tag
        )
    )
    ws_src = "/asesor/ws?scope=all" if all_view else "/asesor/ws?scope=mine"
    live_region = (
        '<div id="live-region" '
        f'data-live-src="{live_src}" data-ws="{_esc(ws_src)}" '
        f'data-poll="{int(refresh)}" data-case-id="">'
        f"{table}</div>"
    )
    script = (
        '<script src="/asesor/static/panel_live.js" defer></script>\n'
        if live_enabled
        else ""
    )
    return _page(
        title,
        f"{filters}\n{live_region}",
        csrf,
        refresh=refresh,
        script=script,
        current_path="/asesor/todos" if all_view else "/asesor/cases",
        wide=True,
    )


def render_history_fragment(history) -> str:
    """R1-R6: historial como burbujas de chat, para reemplazar sin anexar."""
    if not history:
        return '<p class="chat-empty">Sin mensajes en el periodo visible.</p>'
    bubbles = "".join(
        f'<li class="chat-msg {ROLE_CLASSES.get(item.role, "chat-msg-other")}">'
        f'<span class="chat-author">{_esc(ROLE_LABELS.get(item.role, item.role))}</span>'
        f'<p class="chat-text">{_esc(item.text)}</p>'
        f'<time class="chat-time" '
        f'datetime="{_esc(_chat_datetime(item.at).isoformat())}">'
        f"{_esc(_chat_time(item.at))}</time>"
        "</li>"
        for item in history
    )
    return f'<ol class="chat-messages">{bubbles}</ol>'


def _chat_block(view, csrf: str, poll_seconds: int) -> str:
    """R8-R18: cabecera, región en vivo y compositor en un único bloque."""
    case_path = _esc(quote(view.case_id, safe=""))
    name = view.client.username or "Cliente sin autenticar"
    title = f"{name} · {view.client.channel}"
    live_region = (
        '<div id="live-region" class="chat-log" role="log" '
        'aria-label="Mensajes de la conversación" tabindex="0" '
        f'data-live-src="/asesor/live/cases/{case_path}" '
        'data-ws="/asesor/ws?scope=mine" '
        f'data-poll="{int(poll_seconds)}" '
        f'data-case-id="{_esc(view.case_id)}">'
        f"{render_history_fragment(view.history)}</div>"
    )
    tools = ""
    if view.window == "closed":
        options = "".join(
            f'<option value="{_esc(template_name)}">'
            f"{_esc(template_name)}</option>"
            for template_name in view.templates
        )
        field = (
            '<label class="chat-field">Plantilla <select name="template">'
            f"{options}</select></label>"
        )
    else:
        notice = ""
        if view.reply_notice:
            notice = (
                '<p class="error" role="alert">'
                "La respuesta guardada no existe o está desactivada."
                "</p>\n"
            )
        selector = ""
        if view.saved_replies:
            reply_options = "".join(
                f'<option value="{_esc(reply.id)}">{_esc(reply.title)}</option>'
                for reply in view.saved_replies
            )
            selector = (
                '<form method="get" action="/asesor/cases/'
                f'{case_path}">'
                '<label>Respuesta guardada <select name="respuesta">'
                f"{reply_options}</select></label>"
                '<button type="submit" class="btn-secondary">Cargar</button>'
                "</form>\n"
            )
        if notice or selector:
            tools = f'<div class="chat-tools">{notice}{selector}</div>'
        selected_body = (
            _esc(view.selected_reply.body) if view.selected_reply is not None else ""
        )
        field = (
            '<label class="chat-field">Escribe un mensaje '
            '<textarea name="text" maxlength="4096" required>'
            f"{selected_body}</textarea></label>"
        )
    composer = (
        '<form method="post" action="/asesor/reply" class="chat-composer">'
        f"{admin.csrf_field(csrf)}"
        f'<input type="hidden" name="case_id" value="{_esc(view.case_id)}">'
        '<input type="hidden" name="origen" value="caso">'
        f"{field}"
        '<button type="submit">Enviar</button>'
        "</form>"
    )
    return (
        '<section class="chat" aria-label="Conversación del caso">'
        f'<div class="chat-header"><h3>Historial</h3>'
        f'<p class="chat-title">{_esc(title)}</p></div>'
        f"{live_region}{tools}{composer}</section>"
    )


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
        + admin._table_wrap(
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
        + admin._table_wrap(
            "<table><thead><tr><th>Canal</th><th>Fecha</th><th>Motivo</th>"
            f"<th>Resumen</th></tr></thead><tbody>{summary_rows}</tbody></table>"
        )
    )


def _notes_section(view, csrf: str) -> str:
    """R2, R29: notas internas separadas del historial, con autor y fecha."""
    case_path = _esc(quote(view.case_id, safe=""))
    if view.notes:
        rows = admin._table_wrap(
            "<table><thead><tr><th>Autor</th><th>Fecha</th><th>Nota</th>"
            "<th>Borrar</th></tr></thead><tbody>"
            + "".join(
                "<tr>"
                f"<td>{_esc(note.author_username or note.author_profile_id)}</td>"
                f"<td>{_esc(note.created_at.isoformat())}</td>"
                f"<td>{_esc(note.body)}</td>"
                "<td>"
                '<form method="post" action="/asesor/cases/'
                f'{case_path}/notes/{_esc(quote(note.id, safe=""))}/delete">'
                f"{admin.csrf_field(csrf)}"
                '<button type="submit" class="btn-danger">Borrar</button>'
                "</form>"
                "</td>"
                "</tr>"
                for note in view.notes
            )
            + "</tbody></table>"
        )
    else:
        rows = "<p>Sin notas internas.</p>"
    form = (
        '<form method="post" action="/asesor/cases/'
        f'{case_path}/notes" class="card">'
        f"{admin.csrf_field(csrf)}"
        '<label>Nota <textarea name="text" maxlength="4000" required></textarea>'
        "</label>"
        '<button type="submit" class="btn-secondary">Añadir nota</button>'
        "</form>"
    )
    return f"<h3>Notas internas</h3>{rows}{form}"


def _tags_section(view, csrf: str) -> str:
    """R25, R29: etiquetas asignadas y solo activas sin asignar para asignar."""
    case_path = _esc(quote(view.case_id, safe=""))
    if view.tags:
        assigned = "<ul>" + "".join(
            "<li>"
            f"{_esc(tag.name)}"
            f"{' (inactiva)' if not tag.active else ''} "
            '<form method="post" class="inline" action="/asesor/cases/'
            f'{case_path}/tags/{_esc(quote(tag.id, safe=""))}/remove">'
            f"{admin.csrf_field(csrf)}"
            '<button type="submit" class="btn-danger">Quitar</button>'
            "</form>"
            "</li>"
            for tag in view.tags
        ) + "</ul>"
    else:
        assigned = "<p>Sin etiquetas asignadas.</p>"
    assign_form = ""
    if view.assignable_tags:
        options = "".join(
            f'<option value="{_esc(tag.id)}">{_esc(tag.name)}</option>'
            for tag in view.assignable_tags
        )
        assign_form = (
            '<form method="post" action="/asesor/cases/'
            f'{case_path}/tags" class="card">'
            f"{admin.csrf_field(csrf)}"
            f'<label>Etiqueta <select name="tag_id">{options}</select></label>'
            '<button type="submit" class="btn-secondary">Asignar etiqueta</button>'
            "</form>"
        )
    return f"<h3>Etiquetas</h3>{assigned}{assign_form}"


def render_advisor_case(
    view,
    csrf: str,
    can_reassign: bool = False,
    live_enabled: bool = False,
    poll_seconds: int = 0,
) -> str:
    case_path = _esc(quote(view.case_id, safe=""))
    chat_block = _chat_block(view, csrf, poll_seconds)
    targets = "".join(
        f'<option value="{_esc(profile_id)}">{_esc(username)} '
        f"({_esc(presence)})</option>"
        for profile_id, username, presence in view.transfer_targets
    )
    transfer_form = (
        '<h3>Transferir</h3>'
        '<form method="post" action="/asesor/transfer" class="card">'
        f"{admin.csrf_field(csrf)}"
        f'<input type="hidden" name="case_id" value="{_esc(view.case_id)}">'
        f'<label>Asesor destino <select name="target_profile_id">{targets}'
        "</select></label>"
        '<button type="submit" class="btn-secondary">Transferir</button>'
        "</form>"
    )
    resolve_form = (
        '<h3>Resolver</h3>'
        '<form method="post" action="/asesor/close" class="card">'
        f"{admin.csrf_field(csrf)}"
        f'<input type="hidden" name="case_id" value="{_esc(view.case_id)}">'
        '<button type="submit" class="btn-danger">Resolver</button>'
        "</form>"
    )
    return_form = (
        '<h3>Devolver al asistente</h3>'
        '<form method="post" action="/asesor/return" class="card">'
        f"{admin.csrf_field(csrf)}"
        f'<input type="hidden" name="case_id" value="{_esc(view.case_id)}">'
        '<button type="submit" class="btn-secondary">Devolver</button>'
        "</form>"
    )
    reassign_form = ""
    if can_reassign:
        reassign_targets = "".join(
            f'<option value="{_esc(profile_id)}">{_esc(username)} '
            f"({_esc(presence)})</option>"
            for profile_id, username, presence in view.transfer_targets
        )
        reassign_form = (
            '<h3>Reasignar (supervisor)</h3>'
            '<form method="post" action="/asesor/casos/'
            f'{case_path}/reasignar" class="card">'
            f"{admin.csrf_field(csrf)}"
            f'<label>Asesor destino <select name="target_profile_id">'
            f"{reassign_targets}</select></label>"
            '<button type="submit" class="btn-secondary">Reasignar</button>'
            "</form>"
        )
    script = (
        '<script src="/asesor/static/panel_live.js" defer></script>\n'
        if live_enabled
        else ""
    )
    body = (
        f'<p><a href="/asesor/cases">Volver a la bandeja</a> · '
        f"Caso {_esc(view.case_id)} · Estado: "
        f"{_badge(view.client.conversation_state)}"
        f" · Ventana: {_esc(WINDOW_LABELS.get(view.window, view.window))}</p>"
        f"{chat_block}"
        f"{_client_section(view)}"
        f"{_notes_section(view, csrf)}"
        f"{_tags_section(view, csrf)}"
        f"{_memory_section(view)}"
        f"{transfer_form}\n{resolve_form}\n{return_form}\n{reassign_form}"
    )
    return _page(
        f"Caso {view.case_id}",
        body,
        csrf,
        refresh=0,
        script=script,
        current_path="/asesor/cases",
    )


def render_suppression_queue(
    rows, csrf: str, action_prefix: str, show_inbox: bool = True
) -> str:
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
    body = admin._table_wrap(
        "<table><thead><tr><th>Solicitud</th><th>Cliente</th><th>Canal</th>"
        "<th>Creada</th><th>Fecha límite</th><th>Prioridad</th><th>Estado</th>"
        "<th>Caso</th><th>Acción</th></tr></thead>"
        f"<tbody>{''.join(table_rows)}</tbody></table>"
    )
    nav_links = (
        [("/asesor", "Inicio"), ("/asesor/supresiones", "Supresiones")]
        if show_inbox
        else [("/asesor/supresiones", "Supresiones")]
    )
    return _page(
        "Cola de supresión",
        body,
        csrf,
        nav_links=nav_links,
        current_path="/asesor/supresiones",
    )


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
        + admin._table_wrap(
            "<table><thead><tr><th>Canal</th><th>Fecha</th><th>Motivo</th>"
            f"<th>Resumen</th></tr></thead><tbody>{summary_rows}</tbody></table>"
        )
    )
    body = f"<h3>Memoria</h3>{updated}{memory}{summaries}"
    return _page("Memoria del cliente", body, csrf, current_path="/asesor/cases")


def render_supervisor_metrics(metrics, csrf: str) -> str:
    """R19: las mismas métricas de #42 en solo lectura, sin formularios."""
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
        + admin._table_wrap(f"<table><tbody>{advisors}</tbody></table>")
        + "<h3>Motivos de escalamiento</h3>"
        + admin._table_wrap(f"<table><tbody>{reasons}</tbody></table>")
        + f"<h3>Preguntas sin respuesta: {_esc(metrics.unanswered_total)}</h3>"
        f"<ul>{samples}</ul>"
    )
    return _page("Métricas", body, csrf, current_path="/asesor/metricas")


def render_advisor_error(status: int, code: str, csrf: str | None = None) -> str:
    message = ERROR_MESSAGES.get(code, "No se pudo completar la operación.")
    body = (
        f'<p class="error" role="alert" data-code="{_esc(code)}">'
        f"{_esc(message)}</p>"
    )
    return _page(f"Error {status}", body, csrf)
