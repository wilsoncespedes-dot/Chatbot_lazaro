# Design — #75 `dashboard_canales_svg`

## Decisiones registradas (defaults configurables, no bloquean)
- Rango = `dias` 1-90 (default 7), igual que `/admin/metricas`; no se añaden fechas libres.
- «Conversaciones por estado» = estado del caso en handover (`open`, `assigned`, `timed_out`, `closed`) de los casos creados en el rango (el estado derivado de la bandeja no es acotable por fecha).
- «Respuesta de asesor» = cliente sin responder → siguiente mensaje de asesor del mismo contacto.
- Tope de barras de canal: constante `DASHBOARD_MAX_CHANNELS = 12`.

## Archivos
- `services/orchestrator/orchestrator/administration.py`: `percentile_minutes(values, pct)` (junto a `median_minutes`); `FirstResponseSummary.p90_minutes: float | None = None`; `first_response_summary` lo rellena.
- `services/orchestrator/orchestrator/dashboard.py` (nuevo, puro, sin IO):
  - `@dataclass(frozen=True) BarDatum(label: str, value: float, color: str)`
  - `advisor_response_minutes(rows: Sequence[tuple[str, str, datetime]]) -> list[float]` (rows `(contact_id, role, at)` ordenadas por `at`).
  - `response_summary(minutes) -> ResponseSummary(count, median, p90)` usando `median_minutes` y `percentile_minutes`.
  - `render_bar_chart(chart_id, title, desc, data, unit="") -> str` (SVG), `render_data_table(caption, headers, rows) -> str`, `render_chart_block(...)` (h3 + SVG + tabla), `group_top(data, max_items)` (agrupa «Otros»).
  - `render_dashboard_body(data, days, include_simulated, action) -> str`; las páginas lo envuelven con `admin.render_page` / `advisor_panel._page`.
- `services/orchestrator/orchestrator/domain.py`: `@dataclass DashboardData`, `parse_dashboard_query(params) -> tuple[int, bool]` (lanza `PanelValidationError`; compartido por ambas rutas, sin duplicar) y `channel_dashboard(days, include_simulated, settings, adapters) -> DashboardData`. Obtiene `list_policies()` (try/except `ServiceUnavailable` → vacío, R12), llama `repo.dashboard_messages`, `repo.case_channels`, `repo.case_first_responses(since, until, exclude_channels)`, `handover.list_cases(actor, "overview")` (try/except → `statuses=None`, R15) y usa `channel_labels`.
- Repositorio (`Protocol`, fake en memoria y PostgreSQL, en `adapters/repository.py`):
  - `dashboard_messages(since, until) -> list[tuple[str, str, str, datetime]]` `(contact_id, channel, role, at)` de `messages`+`contacts`, ordenado por `at`.
  - `case_channels(since, until) -> dict[str, str]` `case_id → channel` desde `case_links`+`contacts`.
  - `case_first_responses(since, until, exclude_channels: frozenset[str] = frozenset())`: parámetro opcional que añade `AND contacts.channel NOT IN (...)`; sin él, comportamiento idéntico (R26).
- `services/orchestrator/orchestrator/admin_routes.py`: `GET /admin/dashboard` (`_require_any_session(..., frozenset({"admin"}))`).
- `services/orchestrator/orchestrator/advisor_routes.py`: `GET /asesor/dashboard` (`SUPERVISOR_ROLES`).
- `admin.py`: entrada «Dashboard» en la navegación y `render_dashboard`; `advisor_panel.py`: enlace en «Supervisión» y `render_supervisor_dashboard`. CSS de barras sin cambiar la CSP (atributos de presentación SVG, hoja `'self'` ya existente).
- Auditoría `dashboard_viewed` con `_audit`.
- Tests: `services/orchestrator/tests/test_dashboard_svg.py` (puro), `test_dashboard_metrics.py` (cálculos), `test_dashboard_routes.py` (permisos, filtros, CSP).

## SVG
`viewBox` fijo, barras horizontales `<rect>` con `fill` como atributo (sin `style`), texto `<text>`; ancho de barra = `value / max * ANCHO`; `max == 0` → SVG con «Sin datos». Mismo patrón que `render_channel_label` (atributos escapados con `html.escape`). La CSP no cambia porque no hay `style` ni scripts. Los canales usan el color de `ChannelLabel`; la etiqueta completa (#67) se muestra en la tabla de datos.

## Excepciones
`PanelValidationError` (422), `ServiceUnavailable` capturada y degradada; permisos como el resto del panel.

## Alternativa descartada
Librería de gráficos (Chart.js/matplotlib) o SVG generado en el navegador: exigiría JS de terceros/CDN o relajar la CSP, contra el acceptance. También se descartó duplicar el SQL de primera respuesta por canal: se extiende `case_first_responses` con un parámetro opcional.
