# Design — fechas_y_formularios_panel (#61)

- `admin.human_datetime(value)` y `admin.time_html(value)`; zona global del
  módulo fijada con `admin.set_display_utc_offset()` desde `create_app`
  (`settings.business_hours_utc_offset_minutes`, Colombia = -300 por defecto).
  Valores sin zona se tratan como UTC.
- Todos los `isoformat()` visibles de `admin.py` y `advisor_panel.py` pasan a
  `time_html`; el chat del caso usa `human_datetime` (sustituye el formato
  `dd/mm HH:MM UTC` de #59 R3) y `panel_live_js.localizeTimes` usa el mismo
  formato con la hora del navegador; ignora `<time>` sin hora.
- CSS: `form.create-form` (grid `auto-fill minmax(13rem)`, `align-items: start`,
  `label:has(textarea)` y archivo a todo el ancho, botón en fila propia) y
  `.row-actions` (grid de 3 columnas de 8.5rem, botones al 100%).
