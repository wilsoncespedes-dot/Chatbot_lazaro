"""Pruebas del rediseño con la nueva identidad visual (#60).

Cubren `ADMIN_CSS` y el HTML renderizado de admin, asesor y `/acceso` sin
navegador: tokens, barra lateral agrupada, editor de textos, perfiles y login.
"""
from __future__ import annotations

import re

from orchestrator import admin, advisor_panel, identity_page

CSS = admin.ADMIN_CSS


def _root_vars(css: str = CSS) -> dict[str, str]:
    block = re.search(r":root\s*\{(.*?)\}", css, re.S)
    assert block is not None
    return dict(re.findall(r"(--[\w-]+)\s*:\s*([^;]+);", block.group(1)))


def _admin_page(env_factory, panel, path: str) -> str:
    env = env_factory()
    panel.login_admin(env)
    response = env.client.get(path)
    assert response.status_code == 200
    return response.text


# --- R1, R2: tokens -------------------------------------------------------------------


def test_root_declares_new_identity_tokens():
    """R1: paleta turquesa del prototipo en el primer `:root`."""
    variables = _root_vars()
    assert variables["--brand"] == "#0f5257"
    assert variables["--accent"] == "#1fc5d6"
    assert variables["--btn"] == "#0b7f8a"
    assert variables["--bg"] == "#eef8f8"
    assert "--line" in variables


def test_dark_mode_redefines_colors():
    """R2: `prefers-color-scheme: dark` redefine los colores base."""
    block = re.search(r"@media \(prefers-color-scheme: dark\)\s*\{(.*?)\n\}", CSS, re.S)
    assert block is not None
    dark = dict(re.findall(r"(--[\w-]+)\s*:\s*([^;]+);", block.group(1)))
    for name in ("--bg", "--surface", "--text", "--primary", "--primary-contrast"):
        assert name in dark
        assert dark[name] != _root_vars()[name]


# --- R4–R10: estructura compartida ---------------------------------------------------


def test_admin_page_uses_shell_with_brand_and_crumb(env_factory, panel):
    """R4, R5, R9: barra lateral con la marca, ruta y título como `<h1>`."""
    html = _admin_page(env_factory, panel, "/admin/profiles")
    assert '<div class="shell">' in html
    assert '<aside class="sidebar">' in html
    assert "Lázaro Software" in html
    assert "SoportePlus" not in html
    assert '<p class="crumb"><b>Panel</b> <span>/</span> <span>Perfiles y roles</span></p>' in html
    assert re.search(r'<main id="contenido">\s*<h1>Perfiles y roles</h1>', html)


def test_admin_navigation_groups_in_prototype_order(env_factory, panel):
    """R6: cuatro grupos con sus enlaces en el orden del prototipo."""
    html = _admin_page(env_factory, panel, "/admin")
    nav = re.search(r'<nav class="site-nav"[^>]*>(.*?)</nav>', html, re.S).group(1)
    groups = re.findall(r'<p class="nav-group">([^<]+)</p>', nav)
    assert groups == ["Operación", "Contenido", "Organización", "Administración"]
    labels = re.findall(r"<span>([^<]+)</span></a>", nav)
    assert labels == [
        "Inicio", "Eventos recientes", "Clientes", "Métricas",
        "Manuales", "Plantillas", "Respuestas guardadas", "Textos del flujo",
        "Categorías", "Etiquetas",
        "Perfiles y roles", "Ajustes", "Supresiones",
    ]


def test_every_nav_link_has_decorative_icon(env_factory, panel):
    """R7: cada enlace lleva un SVG oculto a lectores de pantalla."""
    html = _admin_page(env_factory, panel, "/admin")
    nav = re.search(r'<nav class="site-nav"[^>]*>(.*?)</nav>', html, re.S).group(1)
    links = re.findall(r"<a [^>]*>(.*?)</a>", nav)
    assert len(links) == 13
    for inner in links:
        assert inner.startswith('<svg class="icon" viewBox="0 0 24 24" aria-hidden="true"')


def test_logout_lives_at_sidebar_foot(env_factory, panel):
    """R8: el formulario de salida cierra la barra lateral y lleva CSRF."""
    html = _admin_page(env_factory, panel, "/admin")
    aside = re.search(r'<aside class="sidebar">(.*?)</aside>', html, re.S).group(1)
    assert re.search(
        r'<form method="post" action="/admin/logout" class="sidebar-foot">'
        r'<input type="hidden" name="csrf_token"[^>]*>.*Salir</button></form>$',
        aside.strip(),
    )


def test_advisor_panel_shares_shell(env_factory, panel):
    """R4, R8, R10: el panel de asesores usa el mismo shell y su salida."""
    env = env_factory()
    panel.login(env, role="asesor")
    html = env.client.get("/asesor").text
    assert '<aside class="sidebar">' in html
    assert "Panel de asesores" in html
    assert '<p class="nav-group">Atención</p>' in html
    assert 'action="/asesor/logout" class="sidebar-foot"' in html
    assert '<a href="/asesor" aria-current="page">' in html


def test_page_without_session_has_no_sidebar():
    """R4: sin sesión no hay barra lateral ni navegación."""
    html = admin.render_error(404, "not_found")
    assert '<div class="shell shell-bare">' in html
    assert "<aside" not in html
    assert "site-nav" not in html


# --- R11: inicio -----------------------------------------------------------------------


def test_home_shows_quick_actions(env_factory, panel):
    """R11: tarjetas enlazadas a las secciones más usadas."""
    html = _admin_page(env_factory, panel, "/admin")
    quick = re.search(r'<ul class="quick">(.*?)</ul>', html, re.S).group(1)
    hrefs = re.findall(r'<a href="([^"]+)">', quick)
    assert hrefs == [
        "/admin/clientes", "/admin/manuals", "/admin/plantillas",
        "/admin/etiquetas", "/admin/texts", "/admin/metricas",
    ]


# --- R12–R17: textos del flujo ----------------------------------------------------


def test_texts_editor_has_list_and_panes(env_factory, panel):
    """R12: lista agrupada a la izquierda y paneles a la derecha."""
    html = _admin_page(env_factory, panel, "/admin/texts")
    assert 'class="card texts-editor"' in html
    nav = re.search(r'<nav class="texts-list" aria-label="Mensajes">(.*?)</nav>', html, re.S)
    groups = re.findall(r'<p class="texts-group">([^<]+)</p>', nav.group(1))
    assert groups == ["Consentimiento legal", "Conversación", "Sesión y acceso", "Servicio y casos"]
    assert html.count('<section class="text-pane"') == len(admin.TEXT_FIELD_LABELS)


def test_texts_form_posts_every_field_once(env_factory, panel):
    """R13: un único formulario POST con CSRF y todos los campos."""
    html = _admin_page(env_factory, panel, "/admin/texts")
    assert html.count('action="/admin/texts"') == 1
    assert 'name="csrf_token"' in html
    for field in admin.TEXT_FIELD_LABELS:
        assert html.count(f'name="{field}"') == 1


def test_each_pane_shows_group_name_version_and_history(env_factory, panel):
    """R14: grupo, nombre, versión vigente e historial en cada panel."""
    html = _admin_page(env_factory, panel, "/admin/texts")
    pane = re.search(r'<section class="text-pane" id="texto-greeting">(.*?)</section>', html, re.S)
    body = pane.group(1)
    assert '<p class="text-pane-group">Conversación</p>' in body
    assert '<label for="campo-greeting">Saludo</label>' in body
    assert '<span class="chip">' in body
    assert 'href="/admin/texts/greeting/historial"' in body


def test_legal_note_only_on_legal_fields(env_factory, panel):
    """R15: el aviso de reaceptación solo aparece en los campos legales."""
    html = _admin_page(env_factory, panel, "/admin/texts")
    panes = dict(re.findall(r'<section class="text-pane" id="texto-(\w+)">(.*?)</section>', html, re.S))
    with_note = {field for field, body in panes.items() if 'class="note"' in body}
    assert with_note == {"notice_text", "notice_version"}


def test_ungrouped_fields_go_to_others(monkeypatch):
    """R16: un campo nuevo sin grupo no se pierde."""
    labels = dict(admin.TEXT_FIELD_LABELS, nuevo_campo="Campo nuevo")
    monkeypatch.setattr(admin, "TEXT_FIELD_LABELS", labels)
    groups = admin.text_groups()
    assert groups[-1] == ("Otros", ["nuevo_campo"])


def test_selection_works_without_javascript(env_factory, panel):
    """R17: `:target` y `:has()` muestran y resaltan el mensaje sin scripts."""
    html = _admin_page(env_factory, panel, "/admin/texts")
    assert "<script" not in html
    assert ".text-pane:target { display: flex; }" in CSS
    assert ".texts-panes:not(:has(.text-pane:target)) .text-pane:first-child" in CSS
    for field in admin.TEXT_FIELD_LABELS:
        assert f'.texts-editor:has(#texto-{field}:target) a[href="#texto-{field}"]' in CSS
        assert f'href="#texto-{field}"' in html


# --- R18: perfiles -----------------------------------------------------------------


def test_profiles_card_avatar_badge_and_pill(env_factory, panel):
    """R18: tarjeta "Nuevo perfil", avatar e insignia de rol (#65 quitó la columna de Telegram)."""
    html = _admin_page(env_factory, panel, "/admin/profiles")
    assert 'class="card form-grid"><h2 class="card-title">Nuevo perfil</h2>' in html
    assert re.search(r'<span class="av" aria-hidden="true">A</span>admin1', html)
    assert '<span class="badge">admin</span>' in html
    assert "<th>Telegram vinculado</th>" not in html


# --- R19, R20: inicio de sesión ---------------------------------------------------------


def test_login_pages_use_auth_layout():
    """R19: los tres accesos comparten curvas, título del panel y tarjeta."""
    pages = {
        "Panel administrativo": admin.render_login(),
        "Panel de asesores": advisor_panel.render_advisor_login(),
        "Acceso de clientes": identity_page.render_login_form("tok"),
    }
    for panel_name, html in pages.items():
        assert '<body class="auth">' in html
        assert '<svg class="auth-waves"' in html
        assert f'<p class="auth-title">{panel_name}</p>' in html
        assert '<div class="auth-card"><h1>Iniciar sesión</h1>' in html


def test_login_fields_keep_names_and_have_icons():
    """R20: icono decorativo y mismos `name`, `autocomplete` y `required`."""
    html = identity_page.render_login_form("tok", error="Usuario o contraseña incorrectos.")
    assert '<input type="hidden" name="t" value="tok">' in html
    assert re.search(r'<span class="field"><svg class="icon"[^>]*>.*?</svg><input name="username" '
                     r'autocomplete="username"[^>]* required>', html)
    assert re.search(r'<input type="password" name="password"[^>]* '
                     r'autocomplete="current-password"[^>]* required>', html)
    assert 'class="error" role="alert"' in html


def test_login_error_code_is_preserved():
    """R19: el código de error del login sigue en `data-error`."""
    html = admin.render_login("Credenciales no válidas.", "invalid_credentials")
    assert 'data-error="invalid_credentials"' in html


# --- R21, R22: seguridad y móvil ----------------------------------------------------


def test_auth_pages_have_no_inline_or_external_resources():
    """R21: ni estilos en línea ni recursos externos en los accesos."""
    for html in (admin.render_login(), identity_page.render_success(),
                 identity_page.render_error(401)):
        assert "style=" not in html
        assert "<style" not in html
        assert "url(" not in html
        for value in re.findall(r'(?:src|href)="([^"]*)"', html):
            assert not value.startswith(("http://", "https://", "//"))


def test_mobile_moves_sidebar_on_top():
    """R22: a 48rem la barra lateral pasa arriba y se desplaza en horizontal."""
    block = re.search(r"@media \(max-width: 48rem\)\s*\{(.*?)\n\}", CSS, re.S).group(1)
    assert ".shell { grid-template-columns: minmax(0, 1fr); }" in block
    sidebar = re.search(r"\.sidebar \{([^}]*)\}", block).group(1)
    assert "flex-direction: row" in sidebar
    assert "overflow-x: auto" in sidebar
    assert ".site-nav ul { flex-direction: row; }" in block
    assert ".form-grid, .auth-form, .texts-editor { grid-template-columns: minmax(0, 1fr); }" in block


# --- R23–R25: panel de asesores --------------------------------------------------


def _advisor_nav(html: str) -> list[str]:
    nav = re.search(r'<nav class="site-nav"[^>]*>(.*?)</nav>', html, re.S).group(1)
    return re.findall(r'<p class="nav-group">([^<]+)</p>', nav)


def test_advisor_nav_groups_by_role(env_factory, panel):
    """R23: asesor ve Atención y Privacidad; supervisor además Supervisión."""
    advisor = env_factory()
    panel.login(advisor, role="asesor")
    html = advisor.client.get("/asesor").text
    assert _advisor_nav(html) == ["Atención", "Privacidad"]
    assert 'href="/asesor/metricas"' not in html

    supervisor = env_factory()
    panel.login(supervisor, role="supervisor")
    html = supervisor.client.get("/asesor/cases").text
    assert _advisor_nav(html) == ["Atención", "Supervisión", "Privacidad"]
    assert '<a href="/asesor/todos">' in html
    assert '<a href="/asesor/cases" aria-current="page">' in html


def test_data_owner_sees_only_privacy(env_factory, panel):
    """R23: `responsable_datos` solo ve Supresiones."""
    env = env_factory(suppression_executor_roles="responsable_datos")
    panel.login(env, role="responsable_datos")
    html = env.client.get("/asesor/supresiones").text
    assert _advisor_nav(html) == ["Privacidad"]
    assert '<a href="/asesor/supresiones" aria-current="page">' in html


def test_nav_groups_without_role_default_to_advisor():
    """R23: sin rol conocido se usa el menú de asesor."""
    groups = advisor_panel.advisor_nav_groups(None)
    assert [name for name, _ in groups] == ["Atención", "Privacidad"]
    assert [name for name, _ in advisor_panel.advisor_nav_groups(None, show_inbox=False)] == [
        "Privacidad"
    ]


def test_advisor_home_cards_keep_actions(env_factory, panel):
    """R24: accesos, presencia y tarjetas de acción con sus formularios."""
    env = env_factory()
    panel.login(env, role="supervisor")
    html = env.client.get("/asesor").text
    quick = re.search(r'<ul class="quick">(.*?)</ul>', html, re.S).group(1)
    assert re.findall(r'<a href="([^"]+)">', quick) == [
        "/asesor/cases", "/asesor/todos", "/asesor/metricas",
    ]
    assert 'action="/asesor/presence" class="card presence-card"' in html
    assert re.search(r'Mi presencia <span class="pill pill-(yes|no)">', html)
    grid = re.search(r'<div class="card-grid">(.*)</div>', html, re.S).group(1)
    for action in ("/asesor/reply", "/asesor/assign", "/asesor/close"):
        assert f'action="{action}" class="card action-card"' in grid
    assert html.count('name="csrf_token"') >= 5


def test_metrics_use_stat_cards(env_factory, panel):
    """R25: tarjetas de cifras y tablas con encabezado en ambos paneles."""
    env = env_factory()
    panel.login_admin(env)
    admin_html = env.client.get("/admin/metricas").text
    supervisor = env_factory()
    panel.login(supervisor, role="supervisor")
    advisor_html = supervisor.client.get("/asesor/metricas").text
    for html in (admin_html, advisor_html):
        assert html.count('<li class="stat">') == 5
        assert "<th>Asesor</th><th>Conversaciones</th>" in html
        assert "<th>Motivo</th><th>Casos</th>" in html
    assert "<form" not in advisor_html.split('<main id="contenido">')[1]


# --- R26: ver contraseña ----------------------------------------------------------


def test_login_pages_offer_hidden_password_toggle():
    """R26: botón con ojo, oculto sin JavaScript, y el script que lo activa."""
    for html in (
        admin.render_login(),
        advisor_panel.render_advisor_login(),
        identity_page.render_login_form("tok"),
    ):
        assert '<script src="/admin/static/login.js" defer></script>' in html
        assert 'id="campo-password"' in html
        assert re.search(
            r'<button type="button" class="pw-toggle" data-pw-toggle hidden '
            r'aria-controls="campo-password" aria-pressed="false" '
            r'aria-label="Mostrar contraseña"><svg class="icon"',
            html,
        )
    assert ".pw-toggle[hidden] { display: none; }" in CSS


def test_login_script_is_public_with_security_headers(env_factory):
    """R26: el script se sirve sin sesión, con CSP, nosniff y no-store."""
    env = env_factory()
    response = env.client.get("/admin/static/login.js")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/javascript")
    assert response.headers["content-security-policy"] == admin.CSP
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["cache-control"] == "no-store"
    body = response.text
    assert 'input.type = show ? "text" : "password";' in body
    assert "button.hidden = false;" in body
    assert admin.ICON_PATHS["eye_off"] in body
