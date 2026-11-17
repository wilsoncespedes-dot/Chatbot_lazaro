"""Utilidades puras y plantillas HTML del panel administrativo."""
from __future__ import annotations

import html
import json
import re
import secrets
from datetime import date, datetime, timedelta, timezone
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

_BASE_CSS = """
:root {
  color-scheme: light;
  --brand: #0f5257;
  --brand-contrast: #ffffff;
  --accent: #1fc5d6;
  --btn: #0b7f8a;
  --bg: #eef8f8;
  --surface: #ffffff;
  --surface-2: #f4fbfb;
  --soft: #e0f5f7;
  --line: #cde6e8;
  --text: #0b3b40;
  --muted: #4d6b70;
  --primary: #0b7f8a;
  --primary-contrast: #ffffff;
  --border: #5f8b90;
  --focus: #0b7f8a;
  --ok: #0f6b44;
  --ok-bg: #dcf5e8;
  --warn: #7a4f00;
  --warn-bg: #fff1d2;
  --danger: #8a1c1c;
  --danger-bg: #fdecec;
  --info: #0b4f6c;
  --info-bg: #e0f5f7;
  --stripe: #f7fcfc;
  --hover: #e0f5f7;
  --radius: 0.625rem;
  --radius-lg: 0.875rem;
  --space-1: 0.25rem;
  --space-2: 0.5rem;
  --space-3: 1rem;
  --space-4: 1.5rem;
  --shadow: 0 4px 18px rgba(31, 197, 214, 0.12);
  --glow: 0 12px 40px rgba(31, 197, 214, 0.28);
  --font: system-ui, "Segoe UI", Roboto, sans-serif;
}
@media (prefers-color-scheme: dark) {
  :root {
    color-scheme: dark;
    --brand: #14727a;
    --brand-contrast: #ffffff;
    --btn: #1fc5d6;
    --bg: #0a1719;
    --surface: #102326;
    --surface-2: #142b2f;
    --soft: #17383c;
    --line: #24474b;
    --text: #e3f4f5;
    --muted: #a3c2c6;
    --primary: #1fc5d6;
    --primary-contrast: #062a2e;
    --border: #6f9a9e;
    --focus: #1fc5d6;
    --ok: #6fe0aa;
    --ok-bg: #14382a;
    --warn: #f2c46b;
    --warn-bg: #3a2f12;
    --danger: #ff9b9b;
    --danger-bg: #3d1717;
    --info: #8fdde6;
    --info-bg: #123238;
    --stripe: #122a2d;
    --hover: #17383c;
    --shadow: none;
    --glow: 0 12px 40px rgba(0, 0, 0, 0.45);
  }
}
* { box-sizing: border-box; }
body { font-family: var(--font); margin: 0; min-height: 100vh; color: var(--text);
  background: linear-gradient(180deg, var(--bg), var(--surface-2));
  font-size: 0.9375rem; line-height: 1.5; }
h1, h2, h3 { line-height: 1.2; margin: 0 0 var(--space-2); }
h1 { font-size: 2.125rem; letter-spacing: -0.01em; margin-top: var(--space-2); }
h2 { font-size: 1.25rem; }
h3 { font-size: 0.875rem; font-weight: 600; color: var(--muted);
  margin-top: var(--space-4); }
a { color: var(--primary); }
a:hover { color: var(--text); }
p { margin: 0 0 var(--space-3); }
.lead { color: var(--muted); }
.icon { width: 1.125rem; height: 1.125rem; fill: none; stroke: currentColor;
  stroke-width: 1.8; stroke-linecap: round; stroke-linejoin: round; flex: none; }
.skip-link { position: absolute; left: -9999px; top: 0; background: var(--surface);
  color: var(--text); padding: var(--space-2) var(--space-3);
  border-radius: var(--radius); }
.skip-link:focus { left: var(--space-2); z-index: 10; }
.shell { display: grid; grid-template-columns: 15.5rem minmax(0, 1fr);
  min-height: 100vh; }
.shell-bare { grid-template-columns: minmax(0, 1fr); }
.sidebar { background: var(--surface); border-right: 1px solid var(--line);
  padding: 1.125rem 0.875rem; display: flex; flex-direction: column;
  gap: var(--space-1); position: sticky; top: 0; height: 100vh; overflow-y: auto; }
.brand { display: flex; align-items: center; gap: 0.625rem;
  padding: 0.125rem 0.5rem 0.875rem; }
.brand-mark { width: 2.125rem; height: 2.125rem; border-radius: 50%;
  background: var(--brand); color: var(--brand-contrast); display: grid;
  place-items: center; flex: none; }
.brand-name { font-weight: 700; font-size: 1.125rem; line-height: 1.2; }
.brand-name small { display: block; color: var(--muted); font-size: 0.75rem;
  font-weight: 400; }
.nav-group { font-size: 0.8125rem; font-weight: 600; color: var(--muted);
  margin: 0.875rem 0.5rem 0.25rem; }
.site-nav ul { list-style: none; padding: 0; margin: 0; display: flex;
  flex-direction: column; gap: 0.125rem; }
.site-nav a { display: flex; align-items: center; gap: 0.75rem;
  padding: 0.5rem 0.625rem; border-radius: 0.5rem; color: var(--text);
  text-decoration: none; font-size: 0.90625rem; }
.site-nav a:hover { background: var(--soft); color: var(--text); }
.site-nav a[aria-current="page"] { background: var(--brand);
  color: var(--brand-contrast); font-weight: 600; }
.sidebar-foot { margin: auto 0 0; padding-top: var(--space-3); }
.sidebar-foot button { width: 100%; display: flex; align-items: center;
  justify-content: center; gap: var(--space-2); }
.main-col { min-width: 0; display: flex; flex-direction: column; }
.site-header { display: flex; flex-wrap: wrap; align-items: center;
  justify-content: space-between; gap: var(--space-3); padding: 1rem 1.75rem; }
.crumb { margin: 0; font-size: 0.9375rem; }
.crumb span { color: var(--muted); }
main { width: 100%; max-width: 70rem; margin: 0 auto; padding: 0.5rem 1.75rem 3rem; }
main.wide { max-width: 96rem; }
.card { background: var(--surface); border: 1px solid var(--line);
  border-radius: var(--radius-lg); box-shadow: var(--shadow); padding: 1.25rem;
  margin: 0 0 1.125rem; }
.card-title { grid-column: 1 / -1; font-size: 1rem; margin: 0; }
form { display: flex; flex-direction: column; gap: var(--space-2);
  align-items: stretch; margin: var(--space-3) 0; }
td form { margin: 0; }
label { display: flex; flex-direction: column; font-size: 0.875rem;
  font-weight: 600; color: var(--muted); gap: var(--space-1); }
input, select, textarea, button { font: inherit; padding: 0.5625rem 0.75rem;
  border-radius: 0.5rem; border: 1px solid var(--border);
  background: var(--surface); color: var(--text); min-height: 2.5rem; }
input:focus, select:focus, textarea:focus { border-color: var(--accent); }
textarea { min-height: 4rem; line-height: 1.5; }
button, .btn { cursor: pointer; background: var(--primary);
  color: var(--primary-contrast); border: 1px solid var(--primary);
  border-radius: var(--radius); font-weight: 600; padding: 0 1.25rem;
  white-space: nowrap; }
button:hover, .btn:hover { filter: brightness(1.08); }
button:disabled, .btn:disabled { opacity: 0.45; cursor: not-allowed; }
.btn-secondary { background: transparent; color: var(--primary);
  border-color: var(--primary); }
.btn-secondary:hover { background: var(--soft); filter: none; }
.btn-danger { background: var(--danger); border-color: var(--danger);
  color: var(--surface); }
.form-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)) auto;
  gap: 0.875rem; align-items: end; }
.form-grid input, .form-grid select { width: 100%; }
.inline-form { flex-direction: row; flex-wrap: wrap; align-items: center;
  gap: var(--space-2); }
.row-actions { display: grid; grid-template-columns: repeat(3, 6.75rem);
  gap: 0.375rem; align-items: center; }
.row-actions form { margin: 0; display: block; }
.row-actions button { width: 100%; min-height: 2.125rem; padding: 0 0.5rem;
  font-size: 0.8125rem; }
form.create-form { display: grid;
  grid-template-columns: repeat(auto-fill, minmax(min(100%, 13rem), 1fr));
  gap: 0.875rem 1rem; align-items: start; }
.create-form input, .create-form select, .create-form textarea { width: 100%; }
.create-form label:has(textarea), .create-form label:has(input[type="file"]) {
  grid-column: 1 / -1; }
.create-form textarea { min-height: 5.5rem; resize: vertical; }
.create-form > button { grid-column: 1 / -1; justify-self: start; }
time { white-space: nowrap; }
.badge { display: inline-block; padding: 0.125rem 0.625rem; border-radius: 999px;
  border: 1px solid transparent; background: var(--soft); color: var(--text);
  font-size: 0.8125rem; font-weight: 600; }
.badge-ok { background: var(--ok-bg); color: var(--ok); border-color: var(--ok); }
.badge-warn { background: var(--warn-bg); color: var(--warn);
  border-color: var(--warn); }
.badge-error { background: var(--danger-bg); color: var(--danger);
  border-color: var(--danger); }
.badge-info { background: var(--info-bg); color: var(--info);
  border-color: var(--info); }
.pill { display: inline-flex; align-items: center; gap: 0.375rem;
  padding: 0.125rem 0.625rem; border-radius: 999px; font-size: 0.8125rem;
  font-weight: 600; }
.pill::before { content: ""; width: 0.4375rem; height: 0.4375rem;
  border-radius: 50%; background: currentColor; }
.pill-yes { background: var(--ok-bg); color: var(--ok); }
.pill-no { background: var(--soft); color: var(--muted); }
.av { width: 2.125rem; height: 2.125rem; border-radius: 50%;
  background: var(--brand); color: var(--brand-contrast); display: inline-grid;
  place-items: center; font-size: 0.8125rem; font-weight: 700; flex: none; }
.user-cell { display: flex; align-items: center; gap: 0.625rem; font-weight: 600; }
.chip { background: var(--soft); color: var(--text); font-weight: 700;
  border-radius: 999px; padding: 0 0.5625rem; }
.note { background: var(--warn-bg); color: var(--warn); border-radius: var(--radius);
  padding: 0.625rem 0.875rem; font-size: 0.875rem; margin: 0; }
.error, .ok { padding: 0.625rem 0.875rem; border-radius: var(--radius);
  border: 1px solid var(--border); border-left-width: 6px;
  margin: var(--space-2) 0 var(--space-3); }
.error { background: var(--danger-bg); color: var(--danger);
  border-left-color: var(--danger); }
.ok { background: var(--ok-bg); color: var(--ok); border-left-color: var(--ok); }
.error::before { content: "Atención: "; font-weight: 700; }
.ok::before { content: "Hecho: "; font-weight: 700; }
input:user-invalid, select:user-invalid, textarea:user-invalid,
[aria-invalid="true"] { border: 2px solid var(--danger); border-left-width: 6px; }
.table-wrap { overflow-x: auto; max-width: 100%; margin: 0 0 var(--space-3);
  background: var(--surface); border: 1px solid var(--line);
  border-radius: var(--radius-lg); box-shadow: var(--shadow); }
table { width: 100%; border-collapse: collapse; background: var(--surface); }
th, td { border-bottom: 1px solid var(--line); padding: var(--space-2) var(--space-3);
  text-align: left; vertical-align: middle; }
thead th { background: var(--surface-2); color: var(--muted); font-size: 0.8125rem;
  font-weight: 600; }
tbody tr:nth-child(even) { background: var(--stripe); }
tbody tr:hover { background: var(--hover); }
tbody tr:last-child td { border-bottom: 0; }
code { background: var(--soft); padding: 0.1rem 0.3rem; border-radius: 0.375rem; }
.quick { list-style: none; padding: 0; margin: 0 0 var(--space-4); display: grid;
  grid-template-columns: repeat(auto-fill, minmax(15rem, 1fr)); gap: var(--space-3); }
.quick a { display: flex; align-items: flex-start; gap: 0.875rem; height: 100%;
  padding: 1.125rem; background: var(--surface); border: 1px solid var(--line);
  border-radius: var(--radius-lg); box-shadow: var(--shadow); color: var(--text);
  text-decoration: none; }
.quick a:hover { border-color: var(--accent); }
.quick b { display: block; }
.quick small { display: block; color: var(--muted); font-size: 0.8125rem; }
.quick-icon { width: 2.5rem; height: 2.5rem; border-radius: 0.75rem;
  background: var(--soft); color: var(--primary); display: grid;
  place-items: center; flex: none; }
.card-title { display: flex; align-items: center; gap: var(--space-2); }
.card-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(18rem, 1fr));
  gap: var(--space-3); align-items: start; margin: 0 0 var(--space-3); }
.card-grid .card { margin: 0; }
form.action-card, form.presence-card { flex-direction: column; flex-wrap: nowrap;
  align-items: stretch; }
.action-card input, .action-card textarea, .presence-card select { width: 100%; }
.presence-card select { max-width: 20rem; }
.action-card button, .presence-card button { align-self: flex-start; }
.card-title .pill { margin-left: auto; }
.stats { list-style: none; padding: 0; margin: 0 0 var(--space-4); display: grid;
  grid-template-columns: repeat(auto-fit, minmax(11rem, 1fr)); gap: var(--space-3); }
.stat { background: var(--surface); border: 1px solid var(--line);
  border-radius: var(--radius-lg); box-shadow: var(--shadow); padding: 1rem 1.125rem;
  display: flex; flex-direction: column; gap: var(--space-1); }
.stat-label { color: var(--muted); font-size: 0.8125rem; font-weight: 600; }
.stat-value { color: var(--primary); font-size: 1.75rem; line-height: 1.1; }
.stat-value small { font-size: 0.875rem; color: var(--muted); font-weight: 600; }
.split { display: grid; grid-template-columns: repeat(auto-fit, minmax(20rem, 1fr));
  gap: var(--space-3); }
.samples { margin: 0; padding-left: 1.25rem; }
.texts-editor { display: grid; grid-template-columns: 18rem minmax(0, 1fr);
  gap: 0; padding: 0; overflow: hidden; align-items: stretch; margin: 0 0 var(--space-3); }
.texts-list { border-right: 1px solid var(--line); background: var(--surface-2);
  padding: var(--space-2); overflow-y: auto; max-height: 40rem; }
.texts-group { font-size: 0.75rem; font-weight: 600; color: var(--muted);
  margin: 0.875rem 0.625rem 0.25rem; }
.texts-list ul { list-style: none; padding: 0; margin: 0; }
.texts-list a { display: block; padding: 0.5rem 0.625rem; border-radius: 0.5rem;
  color: var(--text); text-decoration: none; }
.texts-list a:hover { background: var(--soft); }
.texts-main { display: flex; flex-direction: column; min-width: 0; }
.text-pane { display: none; flex-direction: column; gap: 0.875rem; padding: 1.5rem;
  scroll-margin-top: var(--space-3); }
.text-pane:target { display: flex; }
.texts-panes:not(:has(.text-pane:target)) .text-pane:first-child { display: flex; }
.text-pane-group { color: var(--muted); font-size: 0.8125rem; margin: 0; }
.text-pane h2 { margin: 0; }
.text-pane h2 label { font-size: inherit; font-weight: 700; color: var(--text); }
.text-pane textarea { width: 100%; min-height: 13.75rem; resize: vertical; }
.text-meta { display: flex; flex-wrap: wrap; align-items: center; gap: 0.625rem;
  font-size: 0.8125rem; color: var(--muted); margin: 0; }
.text-meta a { color: var(--primary); font-weight: 600; }
.texts-foot { display: flex; align-items: center; justify-content: space-between;
  gap: var(--space-3); margin-top: auto; padding: 1rem 1.5rem;
  border-top: 1px solid var(--line); }
.texts-foot span { font-size: 0.8125rem; color: var(--muted); }
body.auth { position: relative; overflow-x: hidden;
  background: linear-gradient(160deg, var(--surface) 0%, var(--bg) 55%, var(--surface-2) 100%); }
.auth-waves { position: fixed; inset: 0; width: 100%; height: 100%; z-index: 0;
  pointer-events: none; }
.wave-fill { fill: var(--soft); opacity: 0.7; }
.wave-line { fill: none; stroke: var(--brand); stroke-width: 2; opacity: 0.75; }
.wave-line-2 { stroke: var(--accent); opacity: 0.5; }
.auth-header { position: relative; z-index: 1; }
.auth-title { margin: 0; padding-left: 0.75rem; border-left: 4px solid var(--accent);
  color: var(--brand); font-size: 1.75rem; font-weight: 700; line-height: 1.15; }
main.auth-main { position: relative; z-index: 1; max-width: none; display: grid;
  place-items: center; min-height: calc(100vh - 6rem); padding: var(--space-3); }
.auth-card { width: min(100%, 26rem); padding: 1.5rem 1.75rem;
  background: var(--surface); border: 1px solid var(--border);
  border-radius: 1rem; box-shadow: var(--glow); }
@supports (backdrop-filter: blur(1px)) {
  .auth-card { background: color-mix(in srgb, var(--surface) 78%, transparent);
    backdrop-filter: blur(14px); }
}
.auth-card h1 { font-size: 1.375rem; margin: 0 0 var(--space-3);
  padding-left: 0.625rem; border-left: 4px solid var(--btn); }
.auth-form { display: grid; grid-template-columns: minmax(0, 1fr) auto;
  gap: 0.875rem 0.75rem; align-items: end; margin: 0; }
.auth-form .span-2 { grid-column: 1 / -1; }
.auth-form button { display: flex; align-items: center; gap: var(--space-2); }
.field { position: relative; display: flex; align-items: center; }
.field .icon { position: absolute; left: 0.75rem; color: var(--muted);
  pointer-events: none; }
.field input { width: 100%; padding-left: 2.5rem; }
.field input.has-toggle { padding-right: 2.75rem; }
.pw-toggle { position: absolute; right: 0.375rem; width: 2rem; height: 2rem;
  min-height: 2rem; padding: 0; display: grid; place-items: center;
  background: transparent; border: 0; border-radius: 0.375rem; color: var(--muted); }
.pw-toggle[hidden] { display: none; }
.pw-toggle:hover { color: var(--primary); background: var(--soft); filter: none; }
.field .pw-toggle .icon { position: static; }
.chat { background: var(--surface); border: 1px solid var(--line);
  border-radius: var(--radius-lg); box-shadow: var(--shadow); display: flex;
  flex-direction: column; margin: 0 0 var(--space-3); overflow: hidden; }
.chat-header, .chat-tools, .chat-composer { padding: var(--space-2) var(--space-3);
  border-bottom: 1px solid var(--line); margin: 0; }
.chat-log { background: var(--surface-2); max-height: 60vh; min-height: 12rem;
  overflow-y: auto; padding: var(--space-3); }
.chat-messages { list-style: none; padding: 0; margin: 0; display: flex;
  flex-direction: column; gap: var(--space-2); }
.chat-msg { max-width: 85%; align-self: flex-start; background: var(--surface);
  color: var(--text); border: 1px solid var(--line);
  border-radius: var(--radius-lg); padding: var(--space-2) var(--space-3);
  display: flex; flex-direction: column; gap: var(--space-1); }
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
  .shell { grid-template-columns: minmax(0, 1fr); }
  .sidebar { position: static; height: auto; flex-direction: row; align-items: center;
    overflow-x: auto; padding: 0.625rem 0.75rem; border-right: 0;
    border-bottom: 1px solid var(--line); }
  .brand { padding: 0 0.5rem 0 0; }
  .brand-name, .nav-group { display: none; }
  .site-nav { display: flex; gap: 0.125rem; }
  .site-nav ul { flex-direction: row; }
  .site-nav a { white-space: nowrap; }
  .sidebar-foot { margin: 0 0 0 auto; padding: 0 0 0 var(--space-2); }
  .site-header { padding: 0.75rem 1rem; }
  main { padding: 0.5rem 1rem 2.5rem; }
  h1 { font-size: 1.75rem; }
  form { flex-direction: column; align-items: stretch; }
  .form-grid, .auth-form, .texts-editor { grid-template-columns: minmax(0, 1fr); }
  .texts-list { border-right: 0; border-bottom: 1px solid var(--line);
    max-height: 14rem; }
  .texts-foot { flex-direction: column; align-items: stretch; }
  input, select, textarea, button, .btn { width: 100%; }
  .sidebar-foot button { width: auto; }
}
@media (min-width: 48.01rem) {
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


# #61: fechas legibles. Se muestran en la zona del negocio
# (BUSINESS_HOURS_UTC_OFFSET_MINUTES, Colombia = -300); `main` la fija al crear la app.
_MONTHS = ("ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic")
_display_tz = timezone(timedelta(minutes=-300))


def set_display_utc_offset(minutes: int) -> None:
    global _display_tz
    _display_tz = timezone(timedelta(minutes=minutes))


def _offset_label() -> str:
    offset = _display_tz.utcoffset(None)
    minutes = int(offset.total_seconds() // 60)
    sign = "+" if minutes >= 0 else "−"
    hours, rest = divmod(abs(minutes), 60)
    return f"UTC{sign}{hours}" + (f":{rest:02d}" if rest else "")


def human_datetime(value: datetime | date | None, with_time: bool = True) -> str:
    """#61: "17 nov 2026, 2:33 p. m." en la zona del negocio; solo fecha si es `date`
    o si `with_time` es falso (la fecha es la local, no la UTC)."""
    if value is None:
        return "—"
    if not isinstance(value, datetime):
        return f"{value.day} {_MONTHS[value.month - 1]} {value.year}"
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    local = value.astimezone(_display_tz)
    if not with_time:
        return f"{local.day} {_MONTHS[local.month - 1]} {local.year}"
    hour = local.hour % 12 or 12
    suffix = "a. m." if local.hour < 12 else "p. m."
    return (
        f"{local.day} {_MONTHS[local.month - 1]} {local.year}, "
        f"{hour}:{local.minute:02d} {suffix}"
    )


def time_html(value: datetime | date | None, with_time: bool = True) -> str:
    """#61: `<time>` con la fecha exacta en `datetime` y el texto legible."""
    if value is None:
        return "—"
    title = (
        f' title="Hora local ({_offset_label()})"' if isinstance(value, datetime) else ""
    )
    return (
        f'<time datetime="{_esc(value.isoformat())}"{title}>'
        f"{_esc(human_datetime(value, with_time))}</time>"
    )


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


ICON_PATHS = {
    "home": "M3 11l9-8 9 8v10H3z",
    "bolt": "M13 2L4 14h7l-1 8 9-12h-7z",
    "users": (
        "M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2M9 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8"
        "M22 21v-2a4 4 0 0 0-3-3.9"
    ),
    "chart": "M5 21V10M12 21V4M19 21v-7",
    "book": (
        "M4 5h6a2 2 0 0 1 2 2v13a2 2 0 0 0-2-2H4zM20 5h-6a2 2 0 0 0-2 2v13"
        "a2 2 0 0 1 2-2h6z"
    ),
    "file": "M6 2h8l5 5v15H6zM14 2v5h5",
    "chat": "M4 4h16v12H9l-5 4z",
    "flow": "M4 6h16M4 12h10M4 18h16",
    "folder": "M3 6h6l2 2h10v11H3z",
    "tag": "M3 12V3h9l9 9-9 9z",
    "shield": "M12 2l8 3v6c0 5-3.5 9-8 11-4.5-2-8-6-8-11V5z",
    "gear": (
        "M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8zM12 2v3M12 19v3M2 12h3M19 12h3"
    ),
    "trash": "M4 7h16M9 7V4h6v3M6 7l1 14h10l1-14",
    "headset": "M4 14v-2a8 8 0 0 1 16 0v2M4 14h3v5H4zM20 14h-3v5h3z",
    "user": "M20 21a8 8 0 0 0-16 0M12 13a5 5 0 1 0 0-10 5 5 0 0 0 0 10",
    "lock": "M6 11h12v10H6zM8 11V7a4 4 0 0 1 8 0v4",
    "arrow": "M5 12h14M13 6l6 6-6 6",
    "logout": "M15 4h4v16h-4M10 8l-4 4 4 4M6 12h10",
    "memory": "M12 3a9 9 0 1 0 9 9M12 7v5l3 3",
    "dot": "M12 9a3 3 0 1 0 0 6 3 3 0 0 0 0-6z",
    "eye": (
        "M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12z"
        "M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6z"
    ),
    "eye_off": (
        "M3 3l18 18M10.6 5.1A10.8 10.8 0 0 1 12 5c6.5 0 10 7 10 7a17 17 0 0 1-3.2 4.1"
        "M6.6 6.6C3.9 8.4 2 12 2 12s3.5 7 10 7c1.8 0 3.4-.5 4.8-1.3M9.9 9.9a3 3 0 0 0 4.2 4.2"
    ),
}

# Icono por ruta para las listas planas de enlaces (panel de asesores).
HREF_ICONS = {
    "/admin": "home",
    "/asesor": "home",
    "/asesor/cases": "chat",
    "/asesor/supresiones": "trash",
    "/asesor/metricas": "chart",
    "/asesor/memoria": "memory",
}

BRAND_NAME = "Lázaro Software"

# #60 R26: mostrar u ocultar la contraseña en los inicios de sesión. Se sirve
# en /admin/static/login.js porque la CSP no admite scripts en línea.
LOGIN_JS = """// Mostrar u ocultar la contraseña (#60 R26).
(function () {
  "use strict";
  var EYE = %(eye)s;
  var EYE_OFF = %(eye_off)s;
  var buttons = document.querySelectorAll("[data-pw-toggle]");
  Array.prototype.forEach.call(buttons, function (button) {
    var input = document.getElementById(button.getAttribute("aria-controls"));
    if (!input) { return; }
    var path = button.querySelector("path");
    var set = function (show) {
      input.type = show ? "text" : "password";
      button.setAttribute("aria-pressed", show ? "true" : "false");
      button.setAttribute("aria-label", show ? "Ocultar contraseña" : "Mostrar contraseña");
      if (path) { path.setAttribute("d", show ? EYE_OFF : EYE); }
    };
    button.hidden = false;
    button.addEventListener("click", function () {
      set(input.type === "password");
      input.focus();
    });
    if (input.form) {
      input.form.addEventListener("submit", function () { set(false); });
    }
  });
})();
""" % {"eye": json.dumps(ICON_PATHS["eye"]), "eye_off": json.dumps(ICON_PATHS["eye_off"])}


def _icon(name: str) -> str:
    """R7: icono decorativo en línea; la CSP no lo trata como recurso externo."""
    path = ICON_PATHS.get(name, ICON_PATHS["dot"])
    return (
        '<svg class="icon" viewBox="0 0 24 24" aria-hidden="true" focusable="false">'
        f'<path d="{path}"/></svg>'
    )


NavLink = tuple[str, str] | tuple[str, str, str]
NavGroup = tuple[str | None, list[NavLink]]


def _as_groups(links) -> list[NavGroup]:
    """Acepta grupos `(título, enlaces)` o una lista plana `(href, texto)`."""
    if links and isinstance(links[0][1], str):
        return [(None, list(links))]
    return list(links)


def _nav_html(
    links,
    current: str | None = None,
    label: str = "Navegación",
) -> str:
    """R6, R7, R10: navegación lateral agrupada con iconos y enlace actual.

    `advisor_panel` importa estos helpers privados a propósito para compartir la
    estructura visual (decisiones de #56 y #60).
    """
    parts = []
    for group, group_links in _as_groups(links):
        if group:
            parts.append(f'<p class="nav-group">{_esc(group)}</p>')
        items = []
        for link in group_links:
            href, text = link[0], link[1]
            icon = link[2] if len(link) > 2 else HREF_ICONS.get(href, "dot")
            is_current = bool(current) and (
                current == href
                or (
                    href not in ("/admin", "/asesor")
                    and current.startswith(f"{href}/")
                )
            )
            marker = ' aria-current="page"' if is_current else ""
            items.append(
                f'<li><a href="{_esc(href)}"{marker}>{_icon(icon)}'
                f"<span>{_esc(text)}</span></a></li>"
            )
        parts.append(f"<ul>{''.join(items)}</ul>")
    return (
        f'<nav class="site-nav" aria-label="{_esc(label)}">'
        f"{''.join(parts)}</nav>\n"
    )


ADMIN_NAV_GROUPS: list[NavGroup] = [
    (
        "Operación",
        [
            ("/admin", "Inicio", "home"),
            ("/admin/events", "Eventos recientes", "bolt"),
            ("/admin/clientes", "Clientes", "users"),
            ("/admin/metricas", "Métricas", "chart"),
        ],
    ),
    (
        "Contenido",
        [
            ("/admin/manuals", "Manuales", "book"),
            ("/admin/plantillas", "Plantillas", "file"),
            ("/admin/respuestas", "Respuestas guardadas", "chat"),
            ("/admin/texts", "Textos del flujo", "flow"),
        ],
    ),
    (
        "Organización",
        [
            ("/admin/categories", "Categorías", "folder"),
            ("/admin/etiquetas", "Etiquetas", "tag"),
        ],
    ),
    (
        "Administración",
        [
            ("/admin/profiles", "Perfiles y roles", "shield"),
            ("/admin/ajustes", "Ajustes", "gear"),
            ("/admin/supresiones", "Supresiones", "trash"),
        ],
    ),
]

# Lista plana derivada, conservada para quien la importe.
ADMIN_NAV_LINKS = [
    (href, text) for _, links in ADMIN_NAV_GROUPS for href, text, _icon_name in links
]


def _logout_form(action: str, csrf: str) -> str:
    """R8: la salida vive al pie de la barra lateral, con su CSRF."""
    return (
        f'<form method="post" action="{_esc(action)}" class="sidebar-foot">'
        f"{csrf_field(csrf)}"
        f'<button type="submit" class="btn-secondary">{_icon("logout")}Salir</button>'
        "</form>"
    )


def _brand(panel_name: str) -> str:
    return (
        f'<div class="brand"><span class="brand-mark">{_icon("headset")}</span>'
        f'<span class="brand-name">{_esc(BRAND_NAME)}'
        f"<small>{_esc(panel_name)}</small></span></div>"
    )


def _shell(
    title: str,
    body_html: str,
    *,
    panel_name: str,
    navigation: str = "",
    logout_html: str = "",
    head_extra: str = "",
    main_class: str = "",
) -> str:
    """R4, R5, R9, R10: documento común a ambos paneles (barra lateral + contenido)."""
    sidebar = ""
    shell_class = "shell shell-bare"
    if navigation:
        shell_class = "shell"
        sidebar = (
            f'<aside class="sidebar">{_brand(panel_name)}\n'
            f"{navigation}{logout_html}</aside>\n"
        )
    main_attr = f' class="{_esc(main_class)}"' if main_class else ""
    return (
        "<!DOCTYPE html>\n"
        '<html lang="es">\n'
        "<head>\n"
        '<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f"{head_extra}"
        f"<title>{_esc(title)}</title>\n"
        '<link rel="stylesheet" href="/admin/static/admin.css">\n'
        "</head>\n"
        "<body>\n"
        f"{_skip_link()}\n"
        f'<div class="{shell_class}">\n'
        f"{sidebar}"
        '<div class="main-col">\n'
        '<header class="site-header"><p class="crumb"><b>Panel</b> '
        f"<span>/</span> <span>{_esc(title)}</span></p></header>\n"
        f'<main id="contenido"{main_attr}>\n<h1>{_esc(title)}</h1>\n{body_html}\n</main>\n'
        "</div>\n"
        "</div>\n"
        "</body>\n"
        "</html>\n"
    )


_AUTH_WAVES = (
    '<svg class="auth-waves" viewBox="0 0 1440 900" preserveAspectRatio="none" '
    'aria-hidden="true" focusable="false">'
    '<path class="wave-fill" d="M0 640C320 500 560 780 860 660C1120 560 1260 320 '
    '1440 180L1440 900L0 900Z"/>'
    '<path class="wave-line" d="M0 540C300 440 520 840 840 720C1100 620 1250 280 '
    '1440 60"/>'
    '<path class="wave-line wave-line-2" d="M0 720C360 620 600 880 920 780C1180 700 '
    '1320 440 1440 320"/>'
    "</svg>"
)


def render_auth_page(title: str, panel_name: str, body_html: str) -> str:
    """R19: diseño de acceso (curvas decorativas y tarjeta translúcida)."""
    return (
        "<!DOCTYPE html>\n"
        '<html lang="es">\n'
        "<head>\n"
        '<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f"<title>{_esc(title)}</title>\n"
        '<link rel="stylesheet" href="/admin/static/admin.css">\n'
        '<script src="/admin/static/login.js" defer></script>\n'
        "</head>\n"
        '<body class="auth">\n'
        f"{_skip_link()}\n"
        f"{_AUTH_WAVES}\n"
        f'<header class="site-header auth-header"><p class="auth-title">'
        f"{_esc(panel_name)}</p></header>\n"
        '<main id="contenido" class="auth-main">\n'
        f'<div class="auth-card"><h1>{_esc(title)}</h1>\n{body_html}\n</div>\n'
        "</main>\n"
        "</body>\n"
        "</html>\n"
    )


def login_form(action: str, hidden_html: str = "") -> str:
    """R20: usuario y contraseña con icono; conserva nombres y autocompletado."""
    return (
        f'<form method="post" action="{_esc(action)}" class="auth-form">'
        f"{hidden_html}"
        '<label class="span-2">Usuario <span class="field">'
        f'{_icon("user")}<input name="username" autocomplete="username" '
        'placeholder="Ingresa tu usuario" required></span></label>'
        '<label>Contraseña <span class="field">'
        f'{_icon("lock")}<input type="password" name="password" id="campo-password" '
        'class="has-toggle" autocomplete="current-password" '
        'placeholder="Ingresa tu contraseña" required>'
        # R26: el script de login lo muestra; sin JavaScript queda oculto.
        '<button type="button" class="pw-toggle" data-pw-toggle hidden '
        'aria-controls="campo-password" aria-pressed="false" '
        f'aria-label="Mostrar contraseña">{_icon("eye")}</button>'
        "</span></label>"
        f'<button type="submit">Entrar {_icon("arrow")}</button>'
        "</form>"
    )


def _alert(message: str | None, code: str | None = None) -> str:
    if not message:
        return ""
    data = f' data-error="{_esc(code)}"' if code else ""
    return f'<p class="error" role="alert"{data}>{_esc(message)}</p>\n'


def render_page(
    title: str,
    body_html: str,
    csrf: str | None = None,
    current_path: str | None = None,
) -> str:
    navigation = ""
    logout = ""
    if csrf is not None:
        logout = _logout_form("/admin/logout", csrf)
        navigation = _nav_html(
            ADMIN_NAV_GROUPS, current_path, "Navegación administrativa"
        )
    return _shell(
        title,
        body_html,
        panel_name="Panel administrativo",
        navigation=navigation,
        logout_html=logout,
    )


def render_login(message: str | None = None, code: str | None = None) -> str:
    body = f"{_alert(message, code)}{login_form('/admin/login')}"
    return render_auth_page("Iniciar sesión", "Panel administrativo", body)


QUICK_ACTIONS = (
    ("/admin/clientes", "users", "Clientes", "Cuentas que inician sesión en el bot."),
    ("/admin/manuals", "book", "Manuales", "Documentos que alimentan las respuestas."),
    ("/admin/plantillas", "file", "Plantillas", "Mensajes de WhatsApp aprobados."),
    ("/admin/etiquetas", "tag", "Etiquetas", "Clasificación de los casos."),
    ("/admin/texts", "flow", "Textos del flujo", "Lo que dice el bot en cada paso."),
    ("/admin/metricas", "chart", "Métricas", "Tiempos de respuesta y escalamientos."),
)


def render_home(csrf: str) -> str:
    """R11: accesos rápidos a las secciones más usadas."""
    cards = "".join(
        f'<li><a href="{_esc(href)}"><span class="quick-icon">{_icon(icon)}</span>'
        f"<span><b>{_esc(name)}</b><small>{_esc(hint)}</small></span></a></li>"
        for href, icon, name, hint in QUICK_ACTIONS
    )
    body = (
        '<p class="lead">Te damos la bienvenida al panel de Lázaro Software. '
        "Elige una sección para empezar.</p>"
        '<h2>Accesos rápidos</h2>'
        f'<ul class="quick">{cards}</ul>'
    )
    return render_page("Inicio", body, csrf, current_path="/admin")


STAFF_PROFILE_ROLES = ("admin", "supervisor", "asesor", "responsable_datos")


def render_profiles(profiles, csrf: str, error: str | None = None) -> str:
    rows = []
    for profile in profiles:
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
        initial = (profile.username or "?")[:1].upper()
        rows.append(
            "<tr>"
            f'<td><span class="user-cell"><span class="av" aria-hidden="true">'
            f"{_esc(initial)}</span>{_esc(profile.username)}</span></td>"
            f'<td><span class="badge">{_esc(profile.role)}</span></td>'
            "<td>"
            f'<form method="post" action="/admin/profiles/{_esc(profile.id)}/role" '
            'class="inline-form">'
            f"{csrf_field(csrf)}"
            f'<select name="role">{role_options}</select>'
            '<button type="submit" class="btn-secondary">Cambiar rol</button>'
            "</form>"
            "</td>"
            "</tr>"
        )
    error_html = ""
    if error:
        error_html = f'<p class="error" role="alert">{_esc(error)}</p>\n'
    body = (
        f"{error_html}"
        '<p class="lead">Para crear clientes que inician sesión en el bot usa '
        '<a href="/admin/clientes">Clientes</a>.</p>'
        '<form method="post" action="/admin/profiles" class="card form-grid">'
        '<h2 class="card-title">Nuevo perfil</h2>'
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
            "<table><thead><tr><th>Usuario</th><th>Rol</th><th>Cambiar rol</th>"
            "</tr></thead><tbody>"
            f"{''.join(rows)}"
            "</tbody></table>"
        )
    )
    return render_page("Perfiles y roles", body, csrf, "/admin/profiles")


def render_events(events, csrf: str) -> str:
    rows = "".join(
        "<tr>"
        f"<td>{_esc(short_id(event.contact_id))}</td>"
        f"<td>{_esc(event.type)}</td>"
        f"<td>{_esc(redact_reason(event.reason))}</td>"
        f"<td>{time_html(event.at)}</td>"
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
        'enctype="multipart/form-data" class="card create-form">'
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
        '<form method="post" action="/admin/categories" class="card create-form">'
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
        '<form method="post" action="/admin/categories/threshold" class="card create-form">'
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
        '<form method="post" action="/admin/etiquetas" class="card create-form">'
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
        '<form method="post" action="/admin/respuestas" class="card create-form">'
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


TEXT_GROUPS = (
    ("Consentimiento legal", ("notice_text", "notice_version", "confirm_button_reply")),
    (
        "Conversación",
        (
            "greeting",
            "active_welcome",
            "topics_list",
            "accepted_reply",
            "rejected_reply",
            "unsupported_reply",
        ),
    ),
    (
        "Sesión y acceso",
        ("login_reminder", "login_link_label", "session_closed_reply", "expiry_notice"),
    ),
    ("Servicio y casos", ("suspended_reply", "out_of_hours_reply", "closing_reply")),
)
LEGAL_TEXT_FIELDS = frozenset({"notice_text", "notice_version"})


def text_groups() -> list[tuple[str, list[str]]]:
    """R12, R16: grupos del editor; los campos sin grupo van a "Otros"."""
    grouped: list[tuple[str, list[str]]] = []
    seen: set[str] = set()
    for name, fields in TEXT_GROUPS:
        present = [field for field in fields if field in TEXT_FIELD_LABELS]
        seen.update(present)
        if present:
            grouped.append((name, present))
    others = [field for field in TEXT_FIELD_LABELS if field not in seen]
    if others:
        grouped.append(("Otros", others))
    return grouped


def _text_anchor(field: str) -> str:
    return f"texto-{field}"


def render_conversation_texts(
    texts,
    csrf: str,
    error: str | None = None,
    versions: dict[str, int] | None = None,
) -> str:
    """R12–R17: editor de dos columnas; un solo formulario con todos los campos."""
    error_html = ""
    if error:
        error_html = f'<p class="error" role="alert">{_esc(error)}</p>\n'
    nav_parts = []
    panes = []
    for group, fields in text_groups():
        items = []
        for field in fields:
            label = TEXT_FIELD_LABELS[field]
            anchor = _text_anchor(field)
            version = (versions or {}).get(field)
            version_text = str(version) if version is not None else "sin historial"
            legal = (
                '<p class="note">La versión legal se guarda junto al texto; al '
                "cambiarla, los clientes deberán aceptar de nuevo antes de "
                "continuar.</p>"
                if field in LEGAL_TEXT_FIELDS
                else ""
            )
            items.append(f'<li><a href="#{_esc(anchor)}">{_esc(label)}</a></li>')
            # Sin `required`: un campo inválido oculto bloquearía el envío sin
            # aviso visible; el servidor valida los vacíos.
            panes.append(
                f'<section class="text-pane" id="{_esc(anchor)}">'
                f'<p class="text-pane-group">{_esc(group)}</p>'
                f'<h2><label for="campo-{_esc(field)}">{_esc(label)}</label></h2>'
                f'<textarea id="campo-{_esc(field)}" name="{_esc(field)}" '
                f'maxlength="4096">{_esc(getattr(texts, field))}</textarea>'
                '<p class="text-meta">Versión vigente '
                f'<span class="chip">{_esc(version_text)}</span> '
                f'<a href="/admin/texts/{quote(field, safe="")}/historial">Historial</a>'
                "</p>"
                f"{legal}"
                "</section>"
            )
        nav_parts.append(
            f'<p class="texts-group">{_esc(group)}</p><ul>{"".join(items)}</ul>'
        )
    body = (
        f"{error_html}"
        '<p class="lead">Elige un mensaje de la lista y edítalo.</p>'
        '<form method="post" action="/admin/texts" class="card texts-editor">'
        f"{csrf_field(csrf)}"
        f'<nav class="texts-list" aria-label="Mensajes">{"".join(nav_parts)}</nav>'
        '<div class="texts-main">'
        f'<div class="texts-panes">{"".join(panes)}</div>'
        '<div class="texts-foot"><span>Se guardan juntos todos los mensajes '
        "modificados.</span>"
        '<button type="submit">Guardar textos</button></div>'
        "</div>"
        "</form>"
    )
    return render_page("Textos del flujo", body, csrf, "/admin/texts")


def _texts_css() -> str:
    """R17: resalta en la lista el mensaje visible, sin JavaScript."""
    current = ",\n".join(
        f'.texts-editor:has(#{_text_anchor(field)}:target) '
        f'a[href="#{_text_anchor(field)}"]'
        for field in TEXT_FIELD_LABELS
    )
    return (
        f"{current} {{ background: var(--brand); color: var(--brand-contrast);\n"
        "  font-weight: 600; }\n"
        ".texts-editor:not(:has(.text-pane:target)) .texts-list > "
        "ul:first-of-type > li:first-child > a { background: var(--brand);\n"
        "  color: var(--brand-contrast); font-weight: 600; }\n"
    )


def render_text_history(field: str, versions, csrf: str) -> str:
    rows = "".join(
        "<tr>"
        f"<td>{_esc(item.version)}</td>"
        f"<td>{_esc(item.created_by)}</td>"
        f"<td>{time_html(item.created_at)}</td>"
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
            f"<td>{time_html(client.valid_from, with_time=False)}</td>"
            f"<td>{time_html(client.valid_until, with_time=False)}</td>"
            f"<td>{_esc(client.days_remaining)}</td>"
            f"<td>{'Sí' if client.has_active_session else 'No'}</td>"
            f"<td>{_esc(client.expiry_notice_status or '')}</td>"
            '<td><div class="row-actions">'
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
            "</div></td>"
            "</tr>"
        )
    body = (
        f"{error_html}"
        '<form method="post" action="/admin/clientes" class="card create-form">'
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
            f"{_esc(template.approved_by)} · {time_html(template.approved_at)}"
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
            f"<td>{approved}</td>"
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
        '<form method="post" action="/admin/plantillas" class="card create-form">'
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


def _minutes(value: float | None) -> str:
    return f"{value:.1f}" if value is not None else "—"


def metrics_body(metrics) -> str:
    """#60 R25: métricas en tarjetas y tablas; compartido por admin y supervisor."""
    first = metrics.first_response
    stats = (
        ("Casos", first.cases, None),
        ("Respondidos", first.answered, None),
        ("Sin respuesta", first.unanswered, None),
        ("Primera respuesta promedio", _minutes(first.avg_minutes), "min"),
        ("Primera respuesta mediana", _minutes(first.median_minutes), "min"),
    )
    cards = "".join(
        f'<li class="stat"><span class="stat-label">{_esc(label)}</span>'
        f'<b class="stat-value">{_esc(value)}'
        f'{f" <small>{_esc(unit)}</small>" if unit else ""}</b></li>'
        for label, value, unit in stats
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
        f"<li>{time_html(at)}: {_esc(text)}</li>"
        for at, text in metrics.unanswered_samples
    ) or "<li>Sin muestras</li>"
    return (
        f'<p class="lead">Intervalo: {time_html(metrics.since)} — '
        f"{time_html(metrics.until)}</p>"
        f'<ul class="stats">{cards}</ul>'
        '<div class="split"><section>'
        "<h2>Conversaciones por asesor</h2>"
        + _table_wrap(
            "<table><thead><tr><th>Asesor</th><th>Conversaciones</th></tr></thead>"
            f"<tbody>{advisors}</tbody></table>"
        )
        + "</section><section><h2>Motivos de escalamiento</h2>"
        + _table_wrap(
            "<table><thead><tr><th>Motivo</th><th>Casos</th></tr></thead>"
            f"<tbody>{reasons}</tbody></table>"
        )
        + "</section></div>"
        f'<section class="card"><h2>Preguntas sin respuesta: '
        f"{_esc(metrics.unanswered_total)}</h2>"
        f'<ul class="samples">{samples}</ul></section>'
    )


def render_metrics(metrics, csrf: str) -> str:
    return render_page("Métricas", metrics_body(metrics), csrf, "/admin/metricas")


def render_error(status: int, code: str, csrf: str | None = None) -> str:
    message = ERROR_MESSAGES.get(code, "No se pudo completar la operación.")
    return render_page(f"Error {status}", f"<p>{_esc(message)}</p>", csrf)


def render_message(title: str, message: str, csrf: str | None = None) -> str:
    return render_page(title, f"<p>{_esc(message)}</p>", csrf)


ADMIN_CSS = _BASE_CSS + _texts_css()
