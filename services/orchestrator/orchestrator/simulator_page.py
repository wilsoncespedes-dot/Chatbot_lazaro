"""Renderizado HTML puro de la página del canal SIMULADO (#63)."""
from __future__ import annotations

import html
from urllib.parse import urlencode

from .admin import csrf_field

SIMULATED_SUFFIX = "[SIMULADO]"


def _esc(value: object) -> str:
    return html.escape(str(value), quote=True)


def simulated_label(name: str) -> str:
    """Etiqueta del canal con la palabra SIMULADO, sin duplicarla."""
    label = (name or "").strip()
    if label.upper().endswith(SIMULATED_SUFFIX):
        return f"{label[: -len(SIMULATED_SUFFIX)].rstrip()} {SIMULATED_SUFFIX}"
    return f"{label} {SIMULATED_SUFFIX}"


def _canal_field(channels, selected: str | None) -> str:
    if not channels:
        return (
            '<label>Canal simulado '
            f'<input name="canal" value="{_esc(selected or "")}" maxlength="32" required>'
            "</label>"
        )
    options = []
    for channel in channels:
        chosen = " selected" if channel.id == selected else ""
        options.append(
            f'<option value="{_esc(channel.id)}"{chosen}>'
            f"{_esc(simulated_label(channel.name))}</option>"
        )
    return (
        '<label>Canal simulado '
        f'<select name="canal">{"".join(options)}</select></label>'
    )


def _entry_item(entry) -> str:
    if entry.kind == "rejected":
        return (
            '<li class="error" role="status">'
            "<strong>Rechazo</strong>"
            "<p>El orquestador no procesó el mensaje: "
            f"{_esc(entry.text)}</p>"
            "</li>"
        )
    author = (
        "Cliente de prueba"
        if entry.kind == "client"
        else "Plataforma (bot o asesor)"
    )
    return (
        "<li>"
        f"<strong>{author}</strong>"
        f"<p>{_esc(entry.text)}</p>"
        f'<span class="chat-time">{_esc(entry.created_at.isoformat())}</span>'
        "</li>"
    )


def _conversation(entries, base_path: str, canal: str, user_id: str) -> str:
    query = urlencode({"canal": canal, "usuario": user_id})
    refresh = f"{base_path}?{query}"
    items = "".join(_entry_item(entry) for entry in entries)
    if not items:
        items = "<li class=\"chat-empty\">Todavía no hay mensajes en el buzón.</li>"
    return (
        "<h3>Conversación</h3>"
        f'<p><a class="btn btn-secondary" href="{_esc(refresh)}">Actualizar</a></p>'
        '<div class="chat-log" aria-live="polite">'
        f'<ol class="chat-messages">{items}</ol>'
        "</div>"
    )


def render_simulator(
    channels,
    selected: str | None,
    user_id: str | None,
    entries,
    csrf: str,
    base_path: str,
    error: str | None = None,
) -> str:
    """Cuerpo HTML; todos los valores se escapan siempre."""
    parts: list[str] = [
        "<p>Esta página es una demostración: el canal simulado no tiene "
        "credenciales ni envía mensajes a ninguna plataforma real.</p>"
    ]
    if error:
        parts.append(
            f'<p class="error" role="alert">{_esc(error)}</p>'
        )
    if not channels and error is None:
        parts.append(
            "<p>Todavía no hay canales simulados registrados. Crea uno con "
            "tipo <code>simulado</code> para probar el recorrido.</p>"
        )
        return "\n".join(parts)

    parts.append(
        f'<form method="post" action="{_esc(base_path)}" class="card">'
        f"{csrf_field(csrf)}"
        f"{_canal_field(channels, selected)}"
        '<label>Id externo de prueba '
        f'<input name="usuario" value="{_esc(user_id or "")}" maxlength="64" '
        'pattern="[A-Za-z0-9_.:\\-]{1,64}" required></label>'
        '<label>Texto del cliente '
        '<textarea name="texto" maxlength="4096" required></textarea></label>'
        '<button type="submit">Enviar como cliente</button>'
        "</form>"
    )
    if selected and user_id:
        parts.append(_conversation(entries, base_path, selected, user_id))
    return "\n".join(parts)
