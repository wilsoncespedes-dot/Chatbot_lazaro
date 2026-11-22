# Tasks — #75 `dashboard_canales_svg`

- [x] T1 — `administration.py`: `percentile_minutes`, `FirstResponseSummary.p90_minutes`, relleno en `first_response_summary`. Cubre: R16, R17, R20, R25, R26.
- [x] T2 — Repositorio (Protocol, fake, PostgreSQL): `dashboard_messages`, `case_channels`, `exclude_channels` en `case_first_responses`. Cubre: R9, R14, R16, R18, R23, R26.
- [x] T3 — `dashboard.py` puro: `BarDatum`, `render_bar_chart`, `render_data_table`, `render_chart_block`, `group_top`, escape y «Sin datos». Cubre: R13, R27, R29, R30, R31, R32, R33.
- [x] T4 — `dashboard.py`: `advisor_response_minutes` y `response_summary`. Cubre: R18, R19, R20, R21, R25.
- [x] T5 — `domain.py`: `DashboardData`, `parse_dashboard_query`, `channel_dashboard` (etiquetas #67, simulados, fallos de directorio y handover). Cubre: R4, R5, R9-R15, R22-R24.
- [x] T6 — Rutas `/admin/dashboard` y `/asesor/dashboard`, renders, formulario GET, navegación, auditoría y cabeceras. Cubre: R1-R8, R28, R34.
- [x] T7 — Tests puros `test_dashboard_svg.py`: escape de nombres, datos vacíos/ceros, muchos canales, atributos a11y, sin `style`/`script`. Cubre: R13, R27, R29-R33.
- [x] T8 — Tests `test_dashboard_metrics.py`: p90, mediana, pares cliente→asesor, sin respuesta, simulados excluidos/incluidos, directorio y handover caídos, `/admin/metricas` sin cambios. Cubre: R9-R12, R14-R26.
- [x] T9 — Tests `test_dashboard_routes.py`: permisos (sin sesión, rol incorrecto, ambos roles), `dias`/`simulados` inválidos, CSP intacta, auditoría, enlaces. Cubre: R1-R8, R28, R34.
- [x] T10 — `./init.sh` verde e informe `progress/impl_dashboard_canales_svg.md` con la trazabilidad. Cubre: todas.
