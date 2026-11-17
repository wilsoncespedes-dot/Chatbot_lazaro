# Design — rediseno_identidad_panel (#60)

Fuente: prototipo `SoportePlus · Administración.html` del dueño (estructura,
menú y editor de textos) y dos imágenes de identidad (inicio y login). La
marca del prototipo se sustituye por "Lázaro Software" (decisión del usuario,
2026-11-17).

## Restricciones heredadas (#56)

- CSP `default-src 'self'` en `/admin` y `PANEL_CSP` en `/asesor`: nada de
  `<style>`, `style=`, scripts en línea, `url(` ni fuentes externas.
- Los estilos siguen viviendo solo en `admin.ADMIN_CSS` (servido en
  `/admin/static/admin.css`); no se crean archivos estáticos.
- Los iconos y las curvas del login son `<svg>` en línea (elementos del DOM,
  no recursos), con `aria-hidden="true"` y `focusable="false"`.

## Tokens (R1–R3)

`:root` toma la paleta del prototipo: `--brand #0f5257`, `--accent #1fc5d6`,
`--btn #0b7f8a`, `--bg #eef8f8`, `--surface #fff`, `--surface-2 #f4fbfb`,
`--soft #e0f5f7`, `--line #cde6e8` (decorativo), `--text #0b3b40`,
`--muted #4d6b70`. Los tokens de #56 se conservan como alias
(`--primary: var(--btn)` no sirve para el test de contraste, así que se
declaran como hex: `--primary #0b7f8a`, `--border #6a9599`, `--focus #0b7f8a`).
Modo oscuro: bloque `@media (prefers-color-scheme: dark)` que redefine
`:root` con la paleta oscura del prototipo. Tipografía:
`system-ui, "Segoe UI", Roboto, sans-serif` (sin fuentes externas).

## Estructura (R4–R10)

```
<body>
<a class="skip-link" href="#contenido">…</a>
<div class="shell">
  <aside class="sidebar">
    <div class="brand">[icono auriculares] Lázaro Software <small>Panel …</small></div>
    <nav class="site-nav" aria-label="…">
      <p class="nav-group">Operación</p><ul>…<li><a>[svg] Inicio</a></li></ul>
      …
    </nav>
    <form class="sidebar-foot" action="/admin/logout">csrf + Salir</form>
  </aside>
  <div class="main-col">
    <header class="site-header"><p class="crumb">Panel / Título</p></header>
    <main id="contenido">[class="wide"]<h1>Título</h1>…</main>
  </div>
</div>
```

- `admin._nav_html` recibe grupos `list[tuple[str, list[tuple[href, texto, icono]]]]`.
  Para compatibilidad acepta también una lista plana de `(href, texto)`
  (un solo grupo sin título, icono por defecto).
- `admin._shell(...)` construye todo el `<body>` y lo usan `render_page` y
  `advisor_panel._page`, que solo cambian marca, navegación y acción de salida.
- `ADMIN_NAV_GROUPS` define los cuatro grupos de R6; `ADMIN_NAV_LINKS` se
  conserva derivado (lista plana) para no romper importaciones.
- Panel de asesores: grupo "Atención" (Inicio, Casos, Supresiones o los
  `nav_links` que pase cada vista).
- Sin sesión (errores sin CSRF) se usa el mismo shell sin barra lateral.

## Inicio (R11)

`render_home` muestra un saludo y una rejilla `.quick` de tarjetas-enlace con
icono, título y descripción. No se inventan métricas: el panel no tiene aún
datos agregados para las tarjetas estadísticas de la imagen.

## Editor de textos (R12–R17)

- `TEXT_GROUPS` asigna los 16 campos a los cuatro grupos del prototipo;
  campos sin grupo → "Otros".
- Un solo `<form class="card texts-editor">` con dos columnas:
  `nav.texts-list` (enlaces `#texto-<campo>`) y `div.texts-panes` con un
  `section.text-pane id="texto-<campo>"` por campo (grupo, `<h2>` con
  `<label for>`, `textarea`, versión como `.chip`, enlace Historial y aviso
  legal en `notice_text`/`notice_version`).
- Selección sin JavaScript con `:target`; si no hay destino, `:has()` muestra
  el primer panel. El resaltado del enlace actual se genera en `ADMIN_CSS`
  a partir de `TEXT_FIELD_LABELS`.
- Las `textarea` ocultas no llevan `required` (un campo inválido oculto
  bloquearía el envío sin aviso); la validación de vacíos sigue en el servidor.
- Pie del formulario con "Guardar textos" y la nota de versiones.

## Perfiles (R18)

Tarjeta "Nuevo perfil" con `.form-grid` (3 campos + botón). Tabla: avatar
`.av` con la inicial, `.badge` con el rol, `.pill pill-yes|pill-no` con
Sí/No.

## Login (R19–R20)

`admin.render_auth_page(title, panel_name, body)` (usada por los tres logins
y por `/acceso`): `body.auth`, `<svg class="auth-waves">` decorativo,
`<p class="auth-title">` con el nombre del panel y `<div class="auth-card">`
con `<h1>Iniciar sesión</h1>`. Campos envueltos en `.field` con icono SVG.

## Móvil (R22)

`@media (max-width: 48rem)`: `.shell` en una columna, la barra lateral
horizontal con `overflow-x: auto`, grupos en fila, formularios y controles a
ancho completo, editor de textos en una columna.

## Panel de asesores (R23–R25)

- `advisor_panel.advisor_nav_groups(role, show_inbox)` arma los grupos.
  El rol llega por una `ContextVar` que `advisor_routes._require_session` fija
  al validar la sesión, para no pasar el rol a cada vista; sin rol (pruebas que
  llaman al renderizador directo) se usa el menú de asesor.
- `render_suppression_queue` deja de pasar enlaces sueltos y usa
  `show_inbox` (oculta "Atención" a `responsable_datos`).
- Inicio: `.quick` + `form.presence-card` (pill Disponible/Ausente) +
  `.card-grid` con tres `form.action-card`. Desaparece la lista "Supervisión"
  del cuerpo: esos enlaces viven en el menú y en los accesos rápidos.
- `admin.metrics_body(metrics)` lo usan `render_metrics` y
  `render_supervisor_metrics`: `.stats` con cinco tarjetas y `.split` con dos
  tablas con `thead`.
