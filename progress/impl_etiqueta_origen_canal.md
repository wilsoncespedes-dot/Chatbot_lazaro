# Implementación — #67 `etiqueta_origen_canal`

## Resumen

- Nuevo componente puro `orchestrator/channel_label.py` (`ChannelLabel`,
  `label_from_policy`, `label_from_values`, `unknown_label`,
  `render_channel_label`). `admin._channel_label` delega en él.
- `ChannelPolicy.known` distingue un id ausente del directorio
  (`default_policy` → `known=False`).
- `HistoryItem.channel` se rellena con el canal del contacto en
  `_case_history`; `channel_labels()` resuelve el mapa id → etiqueta con una
  sola consulta al directorio y absorbe su caída (etiquetas neutras, sin error).
- El panel (bandeja, encabezado del chat, cada burbuja, ficha del cliente,
  resúmenes y `/memoria`) recibe `labels` y pinta el componente en las rutas
  iniciales y en vivo.
- CSS: `.channel-label { vertical-align: middle; }` (sin `style=` en línea).
- El panel tolera la caída del directorio: política por defecto para la ventana
  y opciones de filtro vacías, sin romper la validación del filtro.
- Tests existentes ajustados al nuevo texto visible de la etiqueta (nombre del
  canal en lugar del id) en `test_panel_inbox.py`, `test_chat_caso_asesor.py` y
  `test_panel_case_view.py`.

## Trazabilidad

- R1 → `services/orchestrator/tests/test_channel_label.py::test_component_renders_svg_with_glyph_and_name`
- R2 → `services/orchestrator/tests/test_channel_label.py::test_component_escapes_name_icon_and_color`
- R3 → `services/orchestrator/tests/test_channel_label.py::test_name_is_visible_text_and_aria_label`
- R4 → `services/orchestrator/tests/test_channel_label.py::test_illegible_or_malformed_color_uses_neutral`
- R4 → `services/orchestrator/tests/test_channel_label.py::test_legible_color_is_kept`
- R5 → `services/orchestrator/tests/test_channel_label.py::test_unknown_icon_uses_default_glyph`
- R6 → `services/orchestrator/tests/test_channel_label.py::test_unknown_label_is_neutral`
- R6 → `services/orchestrator/tests/test_channel_label.py::test_default_policy_is_not_known`
- R6 → `services/orchestrator/tests/test_etiqueta_origen_panel.py::test_unknown_channel_shows_neutral_label_without_error`
- R7 → `services/orchestrator/tests/test_etiqueta_origen_panel.py::test_directory_down_uses_neutral_labels_without_error`
- R8 → `services/orchestrator/tests/test_etiqueta_origen_panel.py::test_inactive_channel_keeps_its_label_in_panel_and_history`
- R9 → `services/orchestrator/tests/test_etiqueta_origen_panel.py::test_inbox_channel_column_shows_label`
- R9 → `services/orchestrator/tests/test_etiqueta_origen_panel.py::test_all_cases_channel_column_shows_label`
- R10 → `services/orchestrator/tests/test_etiqueta_origen_panel.py::test_chat_header_shows_channel_label`
- R11 → `services/orchestrator/tests/test_etiqueta_origen_panel.py::test_each_chat_message_shows_its_channel_label`
- R12 → `services/orchestrator/tests/test_etiqueta_origen_panel.py::test_history_items_carry_contact_channel`
- R13 → `services/orchestrator/tests/test_etiqueta_origen_panel.py::test_client_card_shows_label_with_and_without_profile`
- R14 → `services/orchestrator/tests/test_etiqueta_origen_panel.py::test_summaries_show_label_in_case_and_memory_views`
- R15 → `services/orchestrator/tests/test_etiqueta_origen_panel.py::test_channel_filter_lists_every_registered_channel_including_inactive`
- R16 → `services/orchestrator/tests/test_etiqueta_origen_panel.py::test_channel_filter_combines_with_assignment_and_tag`
- R17 → `services/orchestrator/tests/test_etiqueta_origen_panel.py::test_invalid_channel_filter_is_422_without_listing`
- R18 → `services/orchestrator/tests/test_etiqueta_origen_panel.py::test_live_inbox_uses_the_same_labels_as_initial_load`
- R19 → `services/orchestrator/tests/test_etiqueta_origen_panel.py::test_live_case_history_uses_the_same_labels_as_initial_load`
- R20 → `services/orchestrator/tests/test_channel_label.py::test_rendered_label_has_no_inline_styles_or_scripts`
- R21 → cobertura en `test_channel_label.py` y `test_etiqueta_origen_panel.py` (ubicaciones, filtro, vivo, inactivo, desconocido y escape).

## Verificación

`./init.sh` lo ejecuta Claude al cerrar la sesión de implementación; el
resultado se añade al informe de revisión.

## Resultado de init.sh

`./init.sh`: 4330 passed, 1 skipped, exit 0. Trazabilidad R1..R21 -> test presente arriba.
