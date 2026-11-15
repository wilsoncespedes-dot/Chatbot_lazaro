# Tasks — rediseño_visual_paneles (#56)

- [x] T1 — Escribir primero `services/orchestrator/tests/test_panel_visual.py` con pruebas de `ADMIN_CSS` (variables, tipografía, botones, `.card`, `.badge`, tablas, media queries, `:focus-visible`, hover/disabled, reduced-motion, sin `url(`/`@import`/`http`). Cubre: R1, R2, R4, R5, R7, R8, R9, R11, R12, R14, R17, R19, R23, R24.
- [x] T2 — Añadir a `test_panel_visual.py` el cálculo de contraste WCAG desde las variables y verificar 4.5:1 / 3:1. Cubre: R13.
- [x] T3 — Reescribir `ADMIN_CSS` en `admin.py` (variables, escala tipográfica, layout móvil primero, `.site-header`, `.site-nav`, botones, `.card`, `.badge`, `.error/.ok`, campos inválidos, tablas y `.table-wrap`, foco, reduced-motion). Cubre: R1, R2, R4, R5, R7, R8, R9, R11, R12, R13, R14, R17, R19, R23, R24.
- [x] T4 — Añadir helpers `_skip_link` y `_nav_html` y ajustar `admin.render_page` (skip link, `id="contenido"`, `aria-label`, `aria-current` vía `current_path`, viewport, clases compartidas). Cubre: R3, R6, R15, R16, R20.
- [x] T5 — Ajustar `advisor_panel._page` para usar los mismos helpers y estructura (parámetro `wide` para la bandeja). Cubre: R3, R6, R9, R15, R16, R20.
- [x] T6 — Añadir clases (`btn-secondary`, `btn-danger`, `card`, `ok`/`error`) a formularios y secciones en `admin.py` sin tocar acciones, campos ni CSRF; envolver tablas en `<div class="table-wrap">`. Cubre: R4, R5, R8, R10, R14, R19, R20, R22.
- [x] T7 — Igual en `advisor_panel.py`: clases, `.table-wrap` en `render_inbox_table` y demás tablas, y `<span class="badge …">` para el estado del caso en bandeja y vista de caso. Cubre: R5, R8, R10, R14, R18, R20, R22.
- [x] T8 — Verificar `two_factor_page.py` e `identity_page.py` con la cabecera/hoja compartidas y ajustar solo clases necesarias. Cubre: R3, R10, R22.
- [x] T9 — Completar `test_panel_visual.py` con pruebas de HTML renderizado de admin (login, inicio, perfiles, manuales, ajustes, métricas, 2FA) y asesor (login, inicio, bandeja, caso, supresiones, métricas, error): skip link, `aria-*`, viewport, sin `style=`/`<style>`/recursos externos, formularios y CSRF preservados, `panel_live.js` y regiones en vivo intactos. Cubre: R3, R6, R10, R15, R16, R18, R20, R22, R23, R26.
- [x] T10 — Añadir pruebas de cabeceras: `/admin/static/admin.css` y páginas de panel conservan `CSP`/`PANEL_CSP`, `nosniff`, `no-store` (incluye `script-src 'self'`). Cubre: R21, R25.
- [x] T11 — Ajustar tests existentes que dependan de HTML literal roto solo por clases añadidas (sin debilitar aserciones). Cubre: R20, R22, R26.
- [x] T12 — Comprobar que no cambian `requirements*.txt`/`pyproject.toml` ni se crean estáticos nuevos; actualizar `docs/architecture.md` con una nota breve sobre la hoja compartida. Cubre: R24.
- [x] T13 — Ejecutar `./init.sh` hasta verde y documentar trazabilidad R→test en `progress/impl_rediseño_visual_paneles.md`. Cubre: R26, R27.
