"""Vista de chat en el detalle del caso del panel de asesores (#59)."""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser

import pytest
from lazaro_contracts import TemplateBlock

from orchestrator import admin, advisor_panel
from orchestrator.domain import HistoryItem, SavedReply

from fakes import drain_queues

NOW = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
R5_TEXT = '<script>alert(1)</script>"><img src=x onerror=1>'
FORM_CONTROLS = ("form", "input", "textarea", "select", "button")
VOID_TAGS = frozenset({"input", "br", "img", "meta", "link", "hr"})


class _LiveRegionParser(HTMLParser):
    """Extrae las etiquetas y el HTML interno de `#live-region`."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self.capturing = False
        self.depth = 0
        self.inner: list[str] = []
        self.tags: list[str] = []

    def handle_starttag(self, tag, attrs):
        if not self.capturing and dict(attrs).get("id") == "live-region":
            self.capturing = True
            self.depth = 1
            return
        if not self.capturing:
            return
        self.tags.append(tag)
        self.inner.append(self.get_starttag_text())
        if tag not in VOID_TAGS:
            self.depth += 1

    def handle_startendtag(self, tag, attrs):
        if self.capturing:
            self.tags.append(tag)
            self.inner.append(self.get_starttag_text())

    def handle_endtag(self, tag):
        if not self.capturing:
            return
        self.depth -= 1
        if self.depth <= 0:
            self.capturing = False
            return
        self.inner.append(f"</{tag}>")

    def handle_data(self, data):
        if self.capturing:
            self.inner.append(data)

    def handle_entityref(self, name):
        if self.capturing:
            self.inner.append(f"&{name};")

    def handle_charref(self, name):
        if self.capturing:
            self.inner.append(f"&#{name};")


def _live_region(html: str) -> tuple[list[str], str]:
    parser = _LiveRegionParser()
    parser.feed(html)
    return parser.tags, "".join(parser.inner)


def _form_block(html: str, marker: str) -> str:
    start = html.index(marker)
    end = html.index("</form>", start)
    return html[start:end]


def _saved_reply(body: str = "Hola cliente", reply_id: str = "reply-1") -> SavedReply:
    return SavedReply(
        id=reply_id,
        title="Saludo",
        body=body,
        active=True,
        updated_at=NOW,
    )


def _client_profile(env, username: str = "cliente1"):
    return env.repo.create_profile(username, "cliente", "hash", NOW)


# --- T2: fragmento en burbujas (R1-R6) -------------------------------------------------


def test_fragment_renders_one_bubble_per_message_in_order(panel):
    """R1: un `<li class="chat-msg">` por mensaje, en el mismo orden."""
    history = [
        HistoryItem("user", "primero", panel.NOW),
        HistoryItem("bot", "segundo", panel.NOW),
        HistoryItem("advisor", "tercero", panel.NOW),
    ]
    html = advisor_panel.render_history_fragment(history)
    assert html.startswith('<ol class="chat-messages">')
    assert html.endswith("</ol>")
    assert html.count('<li class="chat-msg ') == 3
    assert html.index("primero") < html.index("segundo") < html.index("tercero")


@pytest.mark.parametrize(
    ("role", "css_class", "label"),
    [
        ("user", "chat-msg-client", "Cliente"),
        ("advisor", "chat-msg-advisor", "Asesor"),
        ("bot", "chat-msg-bot", "Bot"),
        ("system", "chat-msg-other", "system"),
    ],
)
def test_fragment_bubble_side_and_author_label_by_role(panel, role, css_class, label):
    """R2: clase de lado y etiqueta de autor según el rol."""
    html = advisor_panel.render_history_fragment(
        [HistoryItem(role, "hola", panel.NOW)]
    )
    assert css_class in html
    assert f'<span class="chat-author">{label}</span>' in html


def test_fragment_bubble_has_time_with_iso_and_utc_text(panel):
    """R3: `datetime` ISO y texto legible en la zona del negocio (#61, UTC−5)."""
    html = advisor_panel.render_history_fragment(
        [HistoryItem("user", "hola", panel.NOW)]
    )
    assert 'datetime="2026-01-02T03:04:05+00:00"' in html
    assert "1 ene 2026, 10:04 p. m." in html

    offset = datetime(2026, 1, 1, 22, 4, 5, tzinfo=timezone(timedelta(hours=-5)))
    converted = advisor_panel.render_history_fragment(
        [HistoryItem("user", "hola", offset)]
    )
    assert "1 ene 2026, 10:04 p. m." in converted


def test_fragment_empty_history_message():
    """R4: historial vacío -> aviso exacto."""
    assert advisor_panel.render_history_fragment(()) == (
        '<p class="chat-empty">Sin mensajes en el periodo visible.</p>'
    )


def test_fragment_escapes_message_text_and_unknown_role(panel):
    """R5: texto y rol desconocido se escapan sin crear etiquetas nuevas."""
    html = advisor_panel.render_history_fragment(
        [HistoryItem("<b>x", R5_TEXT, panel.NOW)]
    )
    assert "<script" not in html
    assert "<img" not in html
    assert "<b>" not in html
    assert "&lt;script&gt;" in html
    assert "&lt;b&gt;x" in html


def test_fragment_has_no_table_script_style_or_form_controls(panel):
    """R6: el fragmento no contiene tablas, scripts, `style=` ni controles."""
    html = advisor_panel.render_history_fragment(
        [
            HistoryItem("user", "hola", panel.NOW),
            HistoryItem("advisor", "respuesta", panel.NOW),
        ]
    )
    for forbidden in ("<table", "<script", "style="):
        assert forbidden not in html
    for control in ("<form", "<input", "<textarea", "<select", "<button"):
        assert control not in html


# --- T4: estructura de la página del caso (R7-R10, R17, R18) ---------------------------


def test_case_page_has_single_chat_block_in_order(env_factory, panel):
    """R8: un único bloque de chat con cabecera, región y compositor en orden."""
    env = env_factory()
    panel.login(env)
    panel.link_case(env, "case-1")
    html = env.client.get("/asesor/cases/case-1").text
    assert html.count('<section class="chat"') == 1
    assert (
        html.index('class="chat-header"')
        < html.index('id="live-region"')
        < html.index('class="chat-composer"')
    )


def test_chat_header_shows_client_or_unauthenticated(env_factory, panel):
    """R9: cabecera con usuario escapado o `Cliente sin autenticar`, y canal."""
    env = env_factory()
    panel.login(env)
    client = _client_profile(env, "<b>cli")
    panel.link_case(env, "case-1", profile_id=client.id)
    html = env.client.get("/asesor/cases/case-1").text
    assert '<p class="chat-title">' in html
    assert "&lt;b&gt;cli · <svg class=\"channel-label\"" in html
    assert "Telegram" in html
    assert "<b>cli" not in html

    anonymous = env_factory()
    panel.login(anonymous)
    panel.link_case(anonymous, "case-1", profile_id=None)
    html = anonymous.client.get("/asesor/cases/case-1").text
    assert "Cliente sin autenticar · <svg class=\"channel-label\"" in html
    assert "Telegram" in html


def test_live_region_is_accessible_log_and_keeps_data_attributes(env_factory, panel):
    """R10: log accesible con foco y atributos del panel en vivo intactos."""
    env = env_factory(advisor_inbox_refresh_seconds=30)
    panel.login(env)
    panel.link_case(env, "case-1")
    html = env.client.get("/asesor/cases/case-1").text
    assert 'class="chat-log"' in html
    assert 'role="log"' in html
    assert 'aria-label="Mensajes de la conversación"' in html
    assert 'tabindex="0"' in html
    assert 'data-live-src="/asesor/live/cases/case-1"' in html
    assert 'data-ws="/asesor/ws?scope=mine"' in html
    assert 'data-poll="30"' in html
    assert 'data-case-id="case-1"' in html


def test_live_region_contains_no_form_controls(env_factory, panel):
    """R17: el compositor, el selector y el aviso quedan fuera de la región."""
    env = env_factory()
    panel.login(env)
    contact = panel.link_case(env, "case-1")
    panel.add_message(env, contact, "user", "hola", panel.NOW)
    env.repo.add_saved_reply(_saved_reply())
    html = env.client.get("/asesor/cases/case-1?respuesta=no-existe").text
    tags, _ = _live_region(html)
    for control in FORM_CONTROLS:
        assert control not in tags


def test_case_page_drops_reply_heading_and_history_table(env_factory, panel):
    """R18: sin `<h3>Responder</h3>` ni tabla de historial Rol/Mensaje/Fecha."""
    env = env_factory()
    panel.login(env)
    contact = panel.link_case(env, "case-1")
    panel.add_message(env, contact, "user", "hola", panel.NOW)
    html = env.client.get("/asesor/cases/case-1").text
    assert "<h3>Responder</h3>" not in html
    for header in ("<th>Rol</th>", "<th>Mensaje</th>", "<th>Fecha</th>"):
        assert header not in html


def test_live_fragment_equals_live_region_content(env_factory, panel):
    """R7: la ruta en vivo devuelve el mismo HTML de la región en vivo."""
    env = env_factory()
    panel.login(env)
    contact = panel.link_case(env, "case-1")
    panel.add_message(env, contact, "user", "uno", panel.NOW - timedelta(minutes=2))
    panel.add_message(env, contact, "bot", "dos", panel.NOW - timedelta(minutes=1))
    panel.add_message(env, contact, "advisor", "tres", panel.NOW)
    page = env.client.get("/asesor/cases/case-1").text
    _, inner = _live_region(page)
    live = env.client.get("/asesor/live/cases/case-1").text
    assert inner == live


# --- T5: compositor y respuestas guardadas (R11-R16) -----------------------------------


def test_composer_is_only_reply_form_with_csrf_case_and_origin(env_factory, panel):
    """R11: único formulario de respuesta con CSRF, caso y origen."""
    env = env_factory()
    panel.login(env)
    panel.link_case(env, "case-1")
    html = env.client.get("/asesor/cases/case-1").text
    assert html.count('action="/asesor/reply"') == 1
    form = _form_block(
        html, '<form method="post" action="/asesor/reply" class="chat-composer">'
    )
    assert 'name="csrf_token"' in form
    assert 'name="case_id" value="case-1"' in form
    assert 'name="origen" value="caso"' in form
    assert '<button type="submit">Enviar</button>' in form


def test_composer_offers_textarea_when_window_not_closed(env_factory, panel):
    """R12: ventana no cerrada -> etiqueta visible y textarea de texto libre."""
    env = env_factory()
    panel.login(env)
    panel.link_case(env, "case-1")
    html = env.client.get("/asesor/cases/case-1").text
    form = _form_block(
        html, '<form method="post" action="/asesor/reply" class="chat-composer">'
    )
    assert "Escribe un mensaje" in form
    assert '<textarea name="text" maxlength="4096" required>' in form
    assert '<select name="template">' not in form


def test_composer_offers_template_select_when_window_closed(env_factory, panel):
    """R13: ventana cerrada -> selector de plantillas y sin textarea."""
    env = env_factory()
    panel.login(env)
    panel.link_case(env, "case-1", channel="whatsapp", user="57300", chat="57301")
    html = env.client.get("/asesor/cases/case-1").text
    form = _form_block(
        html, '<form method="post" action="/asesor/reply" class="chat-composer">'
    )
    assert '<select name="template">' in form
    assert "<textarea" not in form


def test_saved_reply_selector_sits_between_log_and_composer(env_factory, panel):
    """R14: selector de respuestas guardadas entre la región y el compositor."""
    env = env_factory()
    panel.login(env)
    panel.link_case(env, "case-1")
    env.repo.add_saved_reply(_saved_reply())
    html = env.client.get("/asesor/cases/case-1").text
    assert '<form method="get" action="/asesor/cases/case-1">' in html
    assert (
        html.index('id="live-region"')
        < html.index('name="respuesta"')
        < html.index('class="chat-composer"')
    )


def test_selected_saved_reply_prefills_composer(env_factory, panel):
    """R15: `?respuesta=` carga el cuerpo escapado sin enviar al cliente."""
    env = env_factory()
    panel.login(env)
    panel.link_case(env, "case-1")
    env.repo.add_saved_reply(_saved_reply(body="Hola <b>x</b>"))
    html = env.client.get("/asesor/cases/case-1?respuesta=reply-1").text
    assert "Hola &lt;b&gt;x&lt;/b&gt;" in html
    assert env.gateway.sent == []
    assert env.gateway.channel_sent == []


def test_invalid_saved_reply_shows_notice_outside_live_region(env_factory, panel):
    """R16: aviso `role=alert` fuera de la región en vivo."""
    env = env_factory()
    panel.login(env)
    panel.link_case(env, "case-1")
    html = env.client.get("/asesor/cases/case-1?respuesta=no-existe").text
    notice = "La respuesta guardada no existe o está desactivada."
    assert notice in html
    assert 'role="alert"' in html
    _, inner = _live_region(html)
    assert notice not in inner


# --- T6: resto de la página del caso (R37-R39) -----------------------------------------


def test_case_page_keeps_other_sections_and_forms(env_factory, panel):
    """R37: secciones, formularios, acciones y CSRF se conservan."""
    env = env_factory()
    panel.login(env)
    client = _client_profile(env)
    panel.link_case(env, "case-1", profile_id=client.id)
    html = env.client.get("/asesor/cases/case-1").text
    for heading in (
        "<h3>Cliente</h3>",
        "<h3>Notas internas</h3>",
        "<h3>Etiquetas</h3>",
        "<h3>Memoria y resúmenes</h3>",
        "<h3>Transferir</h3>",
        "<h3>Resolver</h3>",
        "<h3>Devolver al asistente</h3>",
    ):
        assert heading in html
    for action in (
        "/asesor/cases/case-1/notes",
        "/asesor/transfer",
        "/asesor/close",
        "/asesor/return",
    ):
        assert f'method="post" action="{action}"' in html
    assert html.count('name="csrf_token"') >= 5


def test_supervisor_case_page_keeps_reassign_form(env_factory, panel):
    """R38: el formulario de reasignación solo lo ve un supervisor."""
    env = env_factory()
    panel.login(env, role="asesor")
    panel.link_case(env, "case-1")
    advisor_html = env.client.get("/asesor/cases/case-1").text
    assert 'action="/asesor/casos/case-1/reasignar"' not in advisor_html

    supervisor = env_factory()
    panel.login(supervisor, role="supervisor")
    panel.link_case(supervisor, "case-1")
    html = supervisor.client.get("/asesor/cases/case-1").text
    assert '<h3>Reasignar (supervisor)</h3>' in html
    assert 'action="/asesor/casos/case-1/reasignar"' in html


def test_chat_block_precedes_client_and_notes(env_factory, panel):
    """R39: el chat va tras el resumen y antes de Cliente y Notas internas."""
    env = env_factory()
    panel.login(env)
    client = _client_profile(env)
    panel.link_case(env, "case-1", profile_id=client.id)
    html = env.client.get("/asesor/cases/case-1").text
    chat = html.index('<section class="chat"')
    assert html.index("Volver a la bandeja") < chat
    assert chat < html.index("<h3>Cliente</h3>")
    assert chat < html.index("<h3>Notas internas</h3>")


# --- T8: envío desde el chat (R19-R22) -------------------------------------------------


def test_reply_from_chat_redirects_back_to_case(env_factory, panel):
    """R19: texto y plantilla desde el chat vuelven al mismo caso."""
    env = env_factory()
    panel.login(env)
    contact = panel.link_case(env, "case-1")
    response = env.client.post(
        "/asesor/reply",
        data={
            "csrf_token": panel.CSRF,
            "case_id": "case-1",
            "text": "Hola desde el chat",
            "origen": "caso",
        },
        follow_redirects=False,
    )
    drain_queues(env.settings, env.adapters)
    assert response.status_code == 303
    assert response.headers["location"] == "/asesor/cases/case-1"
    assert (contact.chat_id, "Hola desde el chat") in env.gateway.sent
    assert ("case-1", "700", "reply") in env.handover.authorized

    closed = env_factory()
    panel.login(closed)
    panel.link_case(closed, "case-1", channel="whatsapp", user="57300", chat="57301")
    template = closed.client.post(
        "/asesor/reply",
        data={
            "csrf_token": panel.CSRF,
            "case_id": "case-1",
            "template": "respuesta_asesor",
            "origen": "caso",
        },
        follow_redirects=False,
    )
    drain_queues(closed.settings, closed.adapters)
    assert template.status_code == 303
    assert template.headers["location"] == "/asesor/cases/case-1"
    [(channel, destination, blocks)] = closed.gateway.blocks_sent
    assert (channel, destination) == ("whatsapp", "57301")
    assert isinstance(blocks[0], TemplateBlock)


@pytest.mark.parametrize("origen", [None, "otro"])
def test_reply_without_origin_keeps_home_redirect(env_factory, panel, origen):
    """R20: sin `origen=caso` el envío sigue volviendo a la bandeja."""
    env = env_factory()
    panel.login(env)
    panel.link_case(env, "case-1")
    data = {"csrf_token": panel.CSRF, "case_id": "case-1", "text": "Hola"}
    if origen is not None:
        data["origen"] = origen
    response = env.client.post("/asesor/reply", data=data, follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/asesor?ok=reply"


def test_reply_from_chat_without_csrf_is_forbidden(env_factory, panel):
    """R21: sin CSRF válido responde 403 y no envía nada."""
    env = env_factory()
    panel.login(env)
    panel.link_case(env, "case-1")
    response = env.client.post(
        "/asesor/reply",
        data={"case_id": "case-1", "text": "Hola", "origen": "caso"},
        follow_redirects=False,
    )
    assert response.status_code == 403
    assert env.gateway.sent == []
    assert env.handover.authorized == []


def test_reply_from_chat_errors_use_fixed_error_page(env_factory, panel):
    """R22: validación y errores de dominio usan la misma página fija."""
    env = env_factory()
    panel.login(env)
    panel.link_case(env, "case-1")
    empty = env.client.post(
        "/asesor/reply",
        data={
            "csrf_token": panel.CSRF,
            "case_id": "case-1",
            "text": "",
            "origen": "caso",
        },
        follow_redirects=False,
    )
    assert empty.status_code == 422
    assert 'data-code="validation_error"' in empty.text

    invalid = env.client.post(
        "/asesor/reply",
        data={
            "csrf_token": panel.CSRF,
            "case_id": "x" * 65,
            "text": "Hola",
            "origen": "caso",
        },
        follow_redirects=False,
    )
    assert invalid.status_code == 422
    assert 'data-code="validation_error"' in invalid.text

    forbidden = env_factory()
    panel.login(forbidden)
    panel.link_case(forbidden, "case-1")
    forbidden.handover.authorize_error = "forbidden"
    denied = forbidden.client.post(
        "/asesor/reply",
        data={
            "csrf_token": panel.CSRF,
            "case_id": "case-1",
            "text": "Hola",
            "origen": "caso",
        },
        follow_redirects=False,
    )
    assert denied.status_code == 403
    assert 'data-code="forbidden"' in denied.text


# --- T10: JavaScript propio (R23-R29) --------------------------------------------------


def test_js_scrolls_chat_log_to_last_message(env_factory):
    """R23, R24: autoscroll al arrancar y al crecer el número de mensajes."""
    js = env_factory().client.get("/asesor/static/panel_live.js").text
    for marker in ("chat-log", ".chat-msg", "scrollTop", "scrollHeight"):
        assert marker in js


def test_js_localizes_times_with_text_content(env_factory):
    """R25, R26: hora local con `textContent` y fechas inválidas intactas."""
    js = env_factory().client.get("/asesor/static/panel_live.js").text
    for marker in ("time[datetime]", "textContent", "isNaN", "getHours"):
        assert marker in js


def test_js_does_not_touch_composer_or_inner_html(env_factory):
    """R27: el script no toca el compositor ni usa `innerHTML`."""
    js = env_factory().client.get("/asesor/static/panel_live.js").text
    for forbidden in ("innerHTML", "textarea", "chat-composer", "document.forms"):
        assert forbidden not in js


def test_case_page_has_only_own_script_and_no_inline_code(env_factory, panel):
    """R28: un único script propio, sin `style=`, `on*` ni recursos externos."""
    env = env_factory()
    panel.login(env)
    contact = panel.link_case(env, "case-1")
    panel.add_message(env, contact, "user", "hola", panel.NOW)
    html = env.client.get("/asesor/cases/case-1").text
    assert html.count("<script") == 1
    assert '<script src="/asesor/static/panel_live.js" defer>' in html
    assert "style=" not in html
    assert re.search(r"\son[a-z]+\s*=", html.lower()) is None
    for value in re.findall(r'(?:src|href)="([^"]*)"', html):
        assert not value.startswith(("http://", "https://", "//"))


def test_case_page_without_live_flag_keeps_chat_without_script(env_factory, panel):
    """R29: sin panel en vivo se mantienen burbujas y compositor, sin script."""
    env = env_factory(panel_live_enabled=False)
    panel.login(env)
    contact = panel.link_case(env, "case-1")
    panel.add_message(env, contact, "user", "hola", panel.NOW)
    html = env.client.get("/asesor/cases/case-1").text
    assert '<section class="chat"' in html
    assert 'class="chat-msg ' in html
    assert 'class="chat-composer"' in html
    assert "<script" not in html


# --- T12: estilos (R31-R36) ------------------------------------------------------------


def _css_vars(css: str = admin.ADMIN_CSS) -> dict[str, str]:
    block = re.search(r":root\s*\{(.*?)\}", css, re.S)
    assert block is not None
    return dict(re.findall(r"(--[\w-]+)\s*:\s*([^;]+);", block.group(1)))


def _css_block(css: str, selector: str) -> str:
    match = re.search(r"(?m)^" + re.escape(selector) + r"\s*\{([^}]*)\}", css)
    assert match is not None, selector
    return match.group(1)


def _background(block: str) -> str:
    match = re.search(r"background:\s*(var\([^)]*\))", block)
    assert match is not None
    return match.group(1)


def _luminance(value: str) -> float:
    value = value.strip()
    assert re.fullmatch(r"#[0-9a-fA-F]{6}", value), value
    channels = []
    for index in (1, 3, 5):
        ratio = int(value[index:index + 2], 16) / 255
        channels.append(
            ratio / 12.92 if ratio <= 0.04045 else ((ratio + 0.055) / 1.055) ** 2.4
        )
    return (
        0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2]
    )


def _contrast(foreground: str, background: str) -> float:
    first, second = _luminance(foreground), _luminance(background)
    lighter, darker = max(first, second), min(first, second)
    return (lighter + 0.05) / (darker + 0.05)


def test_css_chat_log_scrolls_with_viewport_height():
    """R31: la región del chat desplaza y limita su alto a la ventana."""
    block = _css_block(admin.ADMIN_CSS, ".chat-log")
    assert "overflow-y: auto" in block
    assert re.search(r"max-height:\s*[\d.]+vh", block)


def test_css_aligns_client_left_and_staff_right():
    """R32: cliente a la izquierda; asesor y bot a la derecha."""
    assert "align-self: flex-start" in _css_block(admin.ADMIN_CSS, ".chat-msg")
    assert "align-self: flex-end" in _css_block(
        admin.ADMIN_CSS, ".chat-msg-advisor"
    )
    assert "align-self: flex-end" in _css_block(admin.ADMIN_CSS, ".chat-msg-bot")


def test_css_bubble_backgrounds_are_distinct_variables():
    """R33: tres fondos distintos tomados de variables existentes."""
    css = admin.ADMIN_CSS
    backgrounds = [
        _background(_css_block(css, ".chat-msg")),
        _background(_css_block(css, ".chat-msg-advisor")),
        _background(_css_block(css, ".chat-msg-bot")),
    ]
    assert len(set(backgrounds)) == 3
    assert all(value.startswith("var(--") for value in backgrounds)
    for selector, body in re.findall(r"(?m)^(\.chat[\w-]*[^{]*)\{([^}]*)\}", css):
        assert "#" not in body, selector
        assert "rgb" not in body, selector


def test_css_bubble_colors_meet_wcag_contrast():
    """R34: `--text` y `--muted` superan 4.5:1 en los tres fondos."""
    variables = _css_vars()
    for background in ("--surface", "--ok-bg", "--info-bg"):
        for foreground in ("--text", "--muted"):
            ratio = _contrast(variables[foreground], variables[background])
            assert ratio >= 4.5, (foreground, background, ratio)


def test_css_chat_log_has_visible_focus():
    """R35: `.chat-log:focus-visible` en la regla de foco existente."""
    match = re.search(r"([^{}]*\.chat-log:focus-visible[^{}]*)\{([^}]*)\}", admin.ADMIN_CSS)
    assert match is not None
    assert "var(--focus)" in match.group(2)


def test_css_bubbles_wrap_and_have_relative_max_width():
    """R36: ancho relativo acotado y texto que envuelve en móvil."""
    message = _css_block(admin.ADMIN_CSS, ".chat-msg")
    match = re.search(r"max-width:\s*([\d.]+)%", message)
    assert match is not None
    assert float(match.group(1)) <= 85
    text = _css_block(admin.ADMIN_CSS, ".chat-text")
    assert "white-space: pre-wrap" in text
    assert "overflow-wrap: anywhere" in text
