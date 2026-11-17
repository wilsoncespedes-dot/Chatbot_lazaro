"""Pruebas del rediseño visual compartido de los paneles (#56).

Cubre `ADMIN_CSS` y el HTML renderizado de admin y asesor sin navegador:
identidad visual, adaptación a móvil/escritorio, accesibilidad, estados,
preservación de comportamiento y CSP.
"""
from __future__ import annotations

import re
from pathlib import Path

from orchestrator import admin, advisor_panel

ROOT = Path(__file__).resolve().parents[1]
CSS = admin.ADMIN_CSS


def _root_vars(css: str = CSS) -> dict[str, str]:
    block = re.search(r":root\s*\{(.*?)\}", css, re.S)
    assert block is not None
    return dict(re.findall(r"(--[\w-]+)\s*:\s*([^;]+);", block.group(1)))


def _block(css: str, selector: str) -> str:
    match = re.search(
        r"(?m)^" + re.escape(selector) + r"\s*\{([^}]*)\}", css
    )
    assert match is not None, selector
    return match.group(1)


def _media(css: str, condition: str) -> str:
    match = re.search(re.escape(condition) + r"\s*\{(.*?)\n\}", css, re.S)
    assert match is not None, condition
    return match.group(1)


def _hex(value: str) -> tuple[int, int, int]:
    value = value.strip()
    assert re.fullmatch(r"#[0-9a-fA-F]{6}", value), value
    return tuple(int(value[i : i + 2], 16) for i in (1, 3, 5))  # type: ignore[return-value]


def _luminance(value: str) -> float:
    channels = []
    for channel in _hex(value):
        ratio = channel / 255
        channels.append(
            ratio / 12.92 if ratio <= 0.04045 else ((ratio + 0.055) / 1.055) ** 2.4
        )
    return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2]


def _contrast(foreground: str, background: str) -> float:
    first, second = _luminance(foreground), _luminance(background)
    lighter, darker = max(first, second), min(first, second)
    return (lighter + 0.05) / (darker + 0.05)


def _admin_pages(env_factory, panel) -> dict[str, str]:
    env = env_factory()
    panel.login_admin(env)
    responses = {
        "login": env.client.get("/admin/login"),
        "inicio": env.client.get("/admin"),
        "perfiles": env.client.get("/admin/profiles"),
        "manuales": env.client.get("/admin/manuals"),
        "ajustes": env.client.get("/admin/ajustes"),
        "metricas": env.client.get("/admin/metricas"),
    }
    assert all(response.status_code == 200 for response in responses.values())
    return {name: response.text for name, response in responses.items()}


def _advisor_pages(env_factory, panel) -> dict[str, str]:
    env = env_factory()
    panel.login(env, role="asesor")
    client = env.repo.create_profile("cliente1", "cliente", "hash", panel.NOW)
    contact = panel.link_case(env, "case-1", profile_id=client.id)
    env.repo.set_conversation_state(contact.id, "active", panel.NOW)
    env.handover.case_list = [
        panel.case_item("case-1", "open"),
        panel.case_item("case-2", "assigned", ["reply", "close"]),
        panel.case_item("case-3", "closed", ["reply"]),
    ]
    responses = {
        "login": env.client.get("/asesor/login"),
        "inicio": env.client.get("/asesor"),
        "bandeja": env.client.get("/asesor/cases"),
        "caso": env.client.get("/asesor/cases/case-1"),
        "error": env.client.get("/asesor/cases?canal=email"),
    }
    assert all(response.status_code in (200, 422) for response in responses.values())

    supervisor = env_factory()
    panel.login(supervisor, role="supervisor")
    responses["metricas"] = supervisor.client.get("/asesor/metricas")

    data_owner = env_factory(suppression_executor_roles="responsable_datos")
    panel.login(data_owner, role="responsable_datos")
    responses["supresiones"] = data_owner.client.get("/asesor/supresiones")

    assert responses["metricas"].status_code == 200
    assert responses["supresiones"].status_code == 200
    return {name: response.text for name, response in responses.items()}


# --- R1, R2: identidad visual y escala tipográfica --------------------------------------


def test_css_declares_shared_design_tokens():
    """R1: color, espaciado, radio, sombra y tipografía viven en `:root`."""
    variables = _root_vars()
    required = {
        "--bg",
        "--surface",
        "--text",
        "--muted",
        "--primary",
        "--primary-contrast",
        "--border",
        "--ok",
        "--warn",
        "--danger",
        "--radius",
        "--space-1",
        "--space-2",
        "--space-3",
        "--space-4",
        "--shadow",
        "--font",
    }
    assert required <= set(variables)
    assert variables["--font"].startswith("system-ui")
    assert "rem" in variables["--space-1"]
    assert "rgba(" in variables["--shadow"]


def test_heading_scale_is_distinct():
    """R2: h1, h2 y h3 tienen tamaños distintos y están declarados."""
    sizes = {
        tag: re.search(r"font-size:\s*([^;]+);", _block(CSS, tag)).group(1).strip()
        for tag in ("h1", "h2", "h3")
    }
    assert len(set(sizes.values())) == 3
    assert all(value.endswith("rem") for value in sizes.values())


# --- R4, R5: botones, tarjetas e insignias ---------------------------------------------


def test_css_defines_button_card_and_badge_styles():
    """R4, R5: primario por defecto, secundario, destructivo, tarjeta e insignias."""
    assert re.search(r"\nbutton,\s*\.btn\s*\{", CSS)
    assert ".btn-secondary {" in CSS
    assert ".btn-danger {" in CSS
    for token in (".card {", ".badge {", ".badge-ok", ".badge-warn",
                  ".badge-error", ".badge-info"):
        assert token in CSS


# --- R7, R8, R9: móvil y escritorio ----------------------------------------------------


def test_mobile_media_query_stacks_navigation_and_forms():
    """R7: a 375 px los formularios se apilan y ocupan el ancho.

    #60 R22: la navegación lateral pasa arriba y se desplaza en horizontal.
    """
    block = _media(CSS, "@media (max-width: 48rem)")
    assert "flex-direction: column" in block
    assert block.count("flex-direction: column") >= 2
    assert "width: 100%" in block
    for selector in (".site-nav ul", "form", "input", "select", "textarea", "button"):
        assert selector in block


def test_tables_are_wrapped_with_own_scroll():
    """R8: `.table-wrap` contiene las tablas con desplazamiento propio."""
    block = _block(CSS, ".table-wrap")
    assert "overflow-x: auto" in block
    assert "max-width: 100%" in block


def test_main_width_is_limited_and_inbox_is_wider():
    """R9: `main` está centrado y la bandeja usa un máximo mayor."""
    main = _block(CSS, "main")
    wide = _block(CSS, "main.wide")
    assert "margin: 0 auto" in main
    main_max = float(re.search(r"max-width:\s*([\d.]+)rem", main).group(1))
    wide_max = float(re.search(r"max-width:\s*([\d.]+)rem", wide).group(1))
    assert wide_max > main_max


# --- R11, R12, R14, R17: accesibilidad y estados ---------------------------------------


def test_focus_is_visible_without_removing_outline():
    """R11: foco visible de 3 px para enlaces, botones y controles."""
    assert "outline: 3px solid var(--focus)" in CSS
    assert "outline-offset: 2px" in CSS
    for selector in ("a:focus-visible", "button:focus-visible", "input:focus-visible",
                     "select:focus-visible", "textarea:focus-visible"):
        assert selector in CSS


def test_hover_disabled_and_current_navigation_are_styled():
    """R12: hover, :disabled y enlace activo con `aria-current`."""
    assert ":hover" in CSS
    assert ":disabled" in CSS
    assert '[aria-current="page"]' in CSS


def test_error_ok_and_invalid_fields_do_not_rely_on_color_only():
    """R14: alertas con borde lateral y prefijo textual; campos inválidos marcados."""
    assert ".error {" in CSS and ".ok {" in CSS
    assert ":user-invalid" in CSS or '[aria-invalid="true"]' in CSS
    assert ".error::before" in CSS and ".ok::before" in CSS
    assert "border-left-width: 6px" in CSS
    assert 'content: "Atención: "' in CSS
    assert 'class="error" role="alert"' in advisor_panel.render_advisor_error(
        422, "validation_error", "csrf"
    )
    assert 'class="ok" role="status"' in advisor_panel.render_advisor_home(
        "csrf", ok="reply"
    )


def test_reduced_motion_disables_animations():
    """R17: `prefers-reduced-motion` anula animaciones y transiciones."""
    block = _media(CSS, "@media (prefers-reduced-motion: reduce)")
    assert "animation: none" in block
    assert "transition: none" in block


# --- R19: tablas -----------------------------------------------------------------------


def test_table_styles_are_readable_and_striped():
    """R19: cabecera diferenciada, filas alternas, hover y relleno."""
    assert "thead th" in CSS
    assert "tbody tr:nth-child(even)" in CSS
    assert "tbody tr:hover" in CSS
    assert "padding: var(--space-2)" in CSS


# --- R13: contraste ----------------------------------------------------------------


def test_color_pairs_meet_wcag_contrast():
    """R13: 4.5:1 para texto normal y 3:1 para bordes, calculado de las variables."""
    variables = _root_vars()
    pairs = [
        ("--text", "--surface", 4.5),
        ("--text", "--bg", 4.5),
        ("--primary", "--primary-contrast", 4.5),
        ("--danger", "--danger-bg", 4.5),
        ("--ok", "--ok-bg", 4.5),
        ("--warn", "--warn-bg", 4.5),
        ("--info", "--info-bg", 4.5),
        ("--border", "--surface", 3.0),
        ("--border", "--bg", 3.0),
    ]
    for foreground, background, minimum in pairs:
        ratio = _contrast(variables[foreground], variables[background])
        assert ratio >= minimum, (foreground, background, ratio)


# --- R3, R6, R10, R15, R16, R18, R20, R22, R23: HTML renderizado -----------------------


def test_both_panels_share_header_navigation_and_skip_link(env_factory, panel):
    """R3, R15, R16: misma cabecera, navegación con aria-label y enlace actual."""
    admin_pages = _admin_pages(env_factory, panel)
    advisor_pages = _advisor_pages(env_factory, panel)

    for html in list(admin_pages.values()) + list(advisor_pages.values()):
        # #60: el login usa `site-header auth-header` y `<body class="auth">`.
        assert re.search(r'<header class="site-header(?: auth-header)?">', html)
        assert 'id="contenido"' in html
        assert re.search(r'<body[^>]*>\s*<a class="skip-link" href="#contenido">', html)

    assert '<nav class="site-nav" aria-label="Navegación administrativa">' in admin_pages["inicio"]
    assert '<a href="/admin" aria-current="page">' in admin_pages["inicio"]
    assert ('<nav class="site-nav" aria-label="Navegación del panel de asesores">'
            in advisor_pages["inicio"])
    assert '<a href="/asesor" aria-current="page">' in advisor_pages["inicio"]
    assert '<a href="/asesor/cases" aria-current="page">' in advisor_pages["bandeja"]
    assert '<main id="contenido" class="wide">' in advisor_pages["bandeja"]
    assert '<main id="contenido">' in admin_pages["inicio"]


def test_every_page_declares_viewport(env_factory, panel):
    """R6: todas las páginas incluyen la meta viewport."""
    pages = _admin_pages(env_factory, panel) | _advisor_pages(env_factory, panel)
    for html in pages.values():
        assert '<meta name="viewport" content="width=device-width, initial-scale=1">' in html


def test_forms_actions_fields_and_csrf_are_preserved(env_factory, panel):
    """R10, R20: formularios, acciones, campos y CSRF siguen presentes."""
    admin_pages = _admin_pages(env_factory, panel)
    advisor_pages = _advisor_pages(env_factory, panel)

    login = admin_pages["login"]
    assert 'method="post" action="/admin/login"' in login
    for name in ("username", "password"):
        assert f'name="{name}"' in login
    assert 'name="code"' not in login

    profiles = admin_pages["perfiles"]
    assert 'method="post" action="/admin/profiles"' in profiles
    assert 'name="csrf_token"' in profiles

    manuals = admin_pages["manuales"]
    assert 'action="/admin/manuals"' in manuals
    assert 'enctype="multipart/form-data"' in manuals
    assert 'type="file" name="file"' in manuals

    assert 'action="/admin/ajustes"' in admin_pages["ajustes"]

    home = advisor_pages["inicio"]
    for action in ("/asesor/presence", "/asesor/reply", "/asesor/assign", "/asesor/close"):
        assert f'action="{action}"' in home
    case = advisor_pages["caso"]
    for action in ("/asesor/reply", "/asesor/transfer", "/asesor/close", "/asesor/return"):
        assert f'method="post" action="{action}"' in case
    assert 'name="csrf_token"' in case


def test_case_status_uses_semantic_badges(env_factory, panel):
    """R18: estado como insignia con clases distintas y el mismo texto."""
    pages = _advisor_pages(env_factory, panel)
    inbox = pages["bandeja"]
    assert '<span class="badge badge-ok">open</span>' in inbox
    assert '<span class="badge badge-info">assigned</span>' in inbox
    assert '<span class="badge badge-warn">closed</span>' in inbox
    assert '<span class="badge badge-ok">active</span>' in pages["caso"]


def test_tables_are_wrapped_and_live_regions_are_intact(env_factory, panel):
    """R8, R22: tablas envueltas y regiones en vivo conservadas."""
    pages = _advisor_pages(env_factory, panel)
    for html in (pages["bandeja"], pages["caso"]):
        assert "<table" in html
        assert html.count('<div class="table-wrap">') >= html.count("<table")

    case = pages["caso"]
    assert 'id="live-region"' in case
    assert 'data-live-src="/asesor/live/cases/case-1"' in case
    assert 'data-case-id="case-1"' in case
    assert 'data-code="validation_error"' in pages["error"]


def test_pages_and_css_have_no_inline_or_external_resources(env_factory, panel):
    """R23: sin `style=`, `<style>`, recursos externos, `@import` ni `url(`."""
    pages = _admin_pages(env_factory, panel) | _advisor_pages(env_factory, panel)
    for html in pages.values():
        assert "style=" not in html
        assert "<style" not in html
        assert "@import" not in html
        assert "url(" not in html
        for value in re.findall(r'(?:src|href)="([^"]*)"', html):
            assert not value.startswith(("http://", "https://", "//"))
    assert "@import" not in CSS
    assert "url(" not in CSS
    assert "http://" not in CSS
    assert "https://" not in CSS


def test_no_new_static_files_are_added():
    """R24: los estilos siguen viviendo solo en `ADMIN_CSS`, sin estáticos nuevos."""
    assert not (ROOT / "orchestrator" / "static").exists()
    assert not list(ROOT.rglob("*.css"))


# --- R21, R25: cabeceras de seguridad --------------------------------------------------


def test_css_and_panels_keep_security_headers(env_factory, panel):
    """R21, R25: CSP, nosniff y no-store se mantienen en CSS y páginas."""
    env = env_factory()
    css = env.client.get("/admin/static/admin.css")
    assert css.status_code == 200
    assert css.headers["content-security-policy"] == admin.CSP
    assert css.headers["x-content-type-options"] == "nosniff"
    assert css.headers["cache-control"] == "no-store"

    panel.login_admin(env)
    admin_page = env.client.get("/admin")
    assert admin_page.headers["content-security-policy"] == admin.CSP

    advisor = env_factory()
    panel.login(advisor, role="asesor")
    advisor_page = advisor.client.get("/asesor")
    assert advisor_page.headers["content-security-policy"] == admin.PANEL_CSP
    assert "default-src 'self'" in advisor_page.headers["content-security-policy"]
    assert "script-src 'self'" in advisor_page.headers["content-security-policy"]
    assert advisor_page.headers["x-content-type-options"] == "nosniff"
    assert advisor_page.headers["cache-control"] == "no-store"


def test_every_script_tag_is_closed(env_factory, panel):
    """R30: toda etiqueta `<script>` de los paneles se cierra de inmediato."""
    pages = _admin_pages(env_factory, panel) | _advisor_pages(env_factory, panel)
    pages["bandeja-live"] = advisor_panel.render_advisor_cases(
        [], "csrf", live_enabled=True
    )
    for name, html in pages.items():
        assert html.count("<script") == html.count("</script>"), name
        assert html.count("<script") == len(
            re.findall(r"<script\b[^>]*></script>", html)
        ), name
    assert "<script" in pages["bandeja"]
    assert "<script" in pages["caso"]
