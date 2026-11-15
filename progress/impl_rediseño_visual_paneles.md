# Implementación — #56 rediseño_visual_paneles

## Resumen

Rediseño visual compartido de los paneles de administración y de asesores sin
cambiar rutas, lógica, permisos, formularios ni dependencias:

- `orchestrator/admin.py`: nueva `ADMIN_CSS` con variables de diseño, escala
  tipográfica, layout móvil/escritorio, botones, tarjetas, insignias, tablas
  con `.table-wrap`, foco visible, estados inválidos y `prefers-reduced-motion`.
  Helpers `_skip_link`, `_nav_html`, `_table_wrap` y `_toggle_class`.
- `orchestrator/advisor_panel.py`: `_page` reutiliza la cabecera, navegación y
  salto de contenido de admin; bandeja con `main.wide`; tablas envueltas e
  insignias semánticas para el estado del caso.
- `orchestrator/identity_page.py`: enlace «Saltar al contenido» e
  `id="contenido"`.
- `docs/architecture.md`: nota de la hoja compartida.
- Tests: `services/orchestrator/tests/test_panel_visual.py` y ajuste puntual de
  `test_panel_live_fragments.py` (el fragmento de bandeja ahora empieza por el
  contenedor `.table-wrap`).

`./init.sh` lo ejecuta Claude al terminar la sesión; no se ejecutó shell desde
esta sesión.

## Trazabilidad

- R1 → `tests/test_panel_visual.py::test_css_declares_shared_design_tokens`
- R2 → `tests/test_panel_visual.py::test_heading_scale_is_distinct`
- R3 → `tests/test_panel_visual.py::test_both_panels_share_header_navigation_and_skip_link`
- R4 → `tests/test_panel_visual.py::test_css_defines_button_card_and_badge_styles`
- R5 → `tests/test_panel_visual.py::test_css_defines_button_card_and_badge_styles`
- R6 → `tests/test_panel_visual.py::test_every_page_declares_viewport`
- R7 → `tests/test_panel_visual.py::test_mobile_media_query_stacks_navigation_and_forms`
- R8 → `tests/test_panel_visual.py::test_tables_are_wrapped_with_own_scroll` y `test_tables_are_wrapped_and_live_regions_are_intact`
- R9 → `tests/test_panel_visual.py::test_main_width_is_limited_and_inbox_is_wider`
- R10 → `tests/test_panel_visual.py::test_forms_actions_fields_and_csrf_are_preserved`
- R11 → `tests/test_panel_visual.py::test_focus_is_visible_without_removing_outline`
- R12 → `tests/test_panel_visual.py::test_hover_disabled_and_current_navigation_are_styled`
- R13 → `tests/test_panel_visual.py::test_color_pairs_meet_wcag_contrast`
- R14 → `tests/test_panel_visual.py::test_error_ok_and_invalid_fields_do_not_rely_on_color_only`
- R15 → `tests/test_panel_visual.py::test_both_panels_share_header_navigation_and_skip_link`
- R16 → `tests/test_panel_visual.py::test_both_panels_share_header_navigation_and_skip_link`
- R17 → `tests/test_panel_visual.py::test_reduced_motion_disables_animations`
- R18 → `tests/test_panel_visual.py::test_case_status_uses_semantic_badges`
- R19 → `tests/test_panel_visual.py::test_table_styles_are_readable_and_striped`
- R20 → `tests/test_panel_visual.py::test_forms_actions_fields_and_csrf_are_preserved`
- R21 → `tests/test_panel_visual.py::test_css_and_panels_keep_security_headers`
- R22 → `tests/test_panel_visual.py::test_tables_are_wrapped_and_live_regions_are_intact`
- R23 → `tests/test_panel_visual.py::test_pages_and_css_have_no_inline_or_external_resources`
- R24 → `tests/test_panel_visual.py::test_no_new_static_files_are_added`
- R25 → `tests/test_panel_visual.py::test_css_and_panels_keep_security_headers`
- R26 → suite `tests/test_panel_visual.py` (páginas admin y asesor renderizadas)
- R27 → `./init.sh` (lo ejecuta Claude tras esta sesión)

## Notas para la revisión

- No se tocaron `admin_routes.py`, `advisor_routes.py`, `panel_live_js.py`,
  `contracts/`, otros servicios, `requirements*.txt` ni `.env.example`.
- `CSP` y `PANEL_CSP` no cambian; la hoja se sirve con las mismas cabeceras.
- El único test existente ajustado es la comprobación del prefijo del fragmento
  de bandeja (ahora `.table-wrap`), sin debilitar su intención.

## `init.sh` intento 1 — fallo

- Resultado: 6 failed, 3552 passed, 1 skipped. Todos los fallos vienen de `_advisor_pages` en `test_panel_visual.py`: crea una configuración `suppression_executor_roles="supervisor"`, que está prohibida. Separar el fixture de métricas (rol supervisor, configuración normal) y el fixture de cola de supresión (rol `responsable_datos`, `SUPPRESSION_EXECUTOR_ROLES=responsable_datos`), sin ampliar permisos ni relajar validaciones.

## Corrección tras `init.sh` intento 1

- `tests/test_panel_visual.py::_advisor_pages`: dos entornos separados.
  - Métricas: `env_factory()` con configuración normal y `panel.login(role="supervisor")`.
  - Cola de supresión: `env_factory(suppression_executor_roles="responsable_datos")` y `panel.login(role="responsable_datos")`.
- No se relajó ninguna validación de `Settings` ni se ampliaron roles; la corrección es solo del test. El resto de la implementación y trazabilidad no cambia.

## Verificación final

`bash ./init.sh`: exit 0, 3558 passed, 1 skipped y 2 avisos de deprecación.
T1–T13 completas; queda pendiente la revisión de código Claude.
