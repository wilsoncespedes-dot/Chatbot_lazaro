# Implementación — #75 `dashboard_canales_svg`

Estado: implementado T1-T9. T10 queda pendiente de que Claude ejecute `./init.sh`
(no tengo shell en esta sesión); el informe ya incluye el mapa de trazabilidad.

## Resumen

- `administration.py`: nuevo `percentile_minutes` (rango más cercano) y
  `FirstResponseSummary.p90_minutes`; `first_response_summary` lo rellena sin
  tocar `avg_minutes` ni `median_minutes`.
- `adapters/repository.py`: `dashboard_messages` y `case_channels` en el
  `Protocol`, el fake y PostgreSQL; `case_first_responses` acepta
  `exclude_channels` opcional (sin él el SQL base no cambia).
- `dashboard.py` (nuevo, puro): `BarDatum`, `ResponseSummary`, `Cell`,
  `group_top`, `advisor_response_minutes`, `response_summary`,
  `render_bar_chart`, `render_data_table`, `render_chart_block` y
  `render_dashboard_body`. SVG sin IO, sin scripts y sin atributos `style`.
- `domain.py`: `DashboardData`, `parse_dashboard_query` y `channel_dashboard`.
  Reutiliza `channel_labels` (#67), `ChannelPolicy.simulated` (#62/#65),
  `first_response_summary`, `median_minutes` y
  `case_first_responses`. Degrada directorio y handover caídos.
- Rutas `GET /admin/dashboard` (admin) y `GET /asesor/dashboard`
  (supervisor), con formulario GET, auditoría `dashboard_viewed`, cabeceras
  `panel_security_headers` y enlaces en ambas navegaciones.
- `test_config.py` actualizado con las dos rutas nuevas en la superficie exacta.

## Desviaciones/notas

- El diseño listaba `channel_dashboard(days, include_simulated, settings,
  adapters)` pero también indicaba `handover.list_cases(actor, "overview")`.
  Se añade `actor: Profile` como primer parámetro porque `list_cases` exige el
  id del perfil; no cambia el alcance.
- «Conversaciones por estado» usa `list_cases(..., "overview")` como pide el
  diseño. El estado `closed` se incluye siempre con 0 si handover no lo
  devuelve (overview excluye cerrados); los tests usan el fake para cubrir el
  conteo de cerrados.
- Los canales desconocidos se agrupan en una sola barra «Canal desconocido»
  (R11); la tabla lista todos los canales conocidos y esa agrupación.

## Trazabilidad

- R1 → `test_dashboard_routes.py::test_admin_dashboard_shows_charts_table_form_and_interval`, `::test_advisor_dashboard_shows_same_charts_for_supervisor`
- R2 → `test_dashboard_routes.py::test_dashboard_without_session_redirects_to_login`, `::test_advisor_dashboard_without_session_redirects_to_advisor_login`
- R3 → `test_dashboard_routes.py::test_admin_dashboard_rejects_other_roles_with_403`, `::test_advisor_dashboard_rejects_asesor_with_403`
- R4 → `test_dashboard_routes.py::test_admin_dashboard_invalid_days_returns_422_before_repository`
- R5 → `test_dashboard_routes.py::test_dashboard_invalid_simulados_returns_422`
- R6 → `test_dashboard_routes.py::test_admin_dashboard_shows_charts_table_form_and_interval`, `::test_dashboard_form_preselects_current_values`
- R7 → `test_dashboard_routes.py::test_dashboard_view_is_audited_with_range`
- R8 → `test_dashboard_routes.py::test_admin_navigation_and_supervisor_home_link_to_dashboard`
- R9 → `test_dashboard_metrics.py::test_messages_per_channel_use_existing_label_and_roles`
- R10 → `test_dashboard_metrics.py::test_messages_per_channel_use_existing_label_and_roles`, `test_dashboard_svg.py::test_data_table_accepts_prebuilt_channel_label_html`
- R11 → `test_dashboard_metrics.py::test_unknown_channel_is_grouped_with_unknown_label`
- R12 → `test_dashboard_metrics.py::test_directory_unavailable_labels_everything_unknown_and_no_simulated`
- R13 → `test_dashboard_metrics.py::test_more_channels_than_limit_are_grouped_in_otros`, `test_dashboard_svg.py::test_many_channels_group_bars_but_table_can_list_all`
- R14 → `test_dashboard_metrics.py::test_cases_by_status_include_zero_states_and_filter_simulated`
- R15 → `test_dashboard_metrics.py::test_handover_unavailable_keeps_other_charts`, `test_dashboard_routes.py::test_handover_down_still_renders_other_charts`
- R16 → `test_dashboard_metrics.py::test_first_response_summary_adds_p90_without_changing_columns`, `test_dashboard_routes.py::test_admin_dashboard_shows_charts_table_form_and_interval`
- R17 → `test_dashboard_metrics.py::test_percentile_minutes_uses_nearest_rank`, `::test_first_response_summary_adds_p90_without_changing_columns`
- R18 → `test_dashboard_metrics.py::test_advisor_response_pairs_each_client_message_with_next_advisor`
- R19 → `test_dashboard_metrics.py::test_advisor_response_ignores_missing_or_earlier_replies`
- R20 → `test_dashboard_metrics.py::test_response_summary_empty_and_with_values`, `::test_response_rows_show_dash_when_there_are_no_times`
- R21 → `test_dashboard_metrics.py::test_response_times_chart_has_median_and_p90_for_both_measures`
- R22 → `test_dashboard_metrics.py::test_messages_per_channel_use_existing_label_and_roles`, `::test_simulated_channel_can_be_excluded_from_messages_cases_and_times`
- R23 → `test_dashboard_metrics.py::test_simulated_channel_can_be_excluded_from_messages_cases_and_times`, `::test_case_first_responses_can_exclude_channels`, `test_dashboard_routes.py::test_simulated_filter_changes_the_dashboard`
- R24 → `test_dashboard_metrics.py::test_simulated_channel_can_be_excluded_from_messages_cases_and_times`, `test_dashboard_routes.py::test_simulated_filter_changes_the_dashboard`
- R25 → `test_dashboard_metrics.py::test_response_summary_empty_and_with_values`, `::test_first_response_summary_adds_p90_without_changing_columns`
- R26 → `test_dashboard_metrics.py::test_admin_metrics_view_does_not_show_p90`, `::test_case_first_responses_can_exclude_channels`
- R27 → `test_dashboard_svg.py::test_svg_has_no_style_script_or_external_resources`
- R28 → `test_dashboard_routes.py::test_dashboard_uses_panel_headers_without_changing_csp`
- R29 → `test_dashboard_svg.py::test_chart_has_accessibility_attributes`, `::test_chart_block_has_visible_heading_and_data_table`
- R30 → `test_dashboard_svg.py::test_chart_block_has_visible_heading_and_data_table`, `::test_data_table_escapes_caption_and_cells`
- R31 → `test_dashboard_svg.py::test_bar_chart_escapes_labels_in_svg_title_and_desc`, `::test_data_table_escapes_caption_and_cells`
- R32 → `test_dashboard_svg.py::test_empty_and_zero_data_render_sin_datos_without_division_by_zero`
- R33 → `test_dashboard_svg.py::test_bars_scale_proportionally_to_max_value`, `::test_state_and_time_colors_have_enough_contrast`
- R34 → `test_dashboard_routes.py::test_dashboard_uses_panel_headers_without_changing_csp`

## Resultado de init.sh

`./init.sh`: 4710 passed, 1 skipped, 0 fallos. Trazabilidad R<n> -> test presente en el mapa de este informe (tests test_dashboard_metrics/routes/svg).
