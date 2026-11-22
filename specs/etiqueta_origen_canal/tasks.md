# Tasks — #67 `etiqueta_origen_canal`

- [x] T1 — `channels.py`: `ChannelPolicy.known` (default True; `default_policy` False). Cubre: R6.
- [x] T2 — `channel_label.py`: `ChannelLabel`, `label_from_policy`, `unknown_label`, `render_channel_label`; `admin._channel_label` delega. Cubre: R1, R2, R3, R4, R5, R6, R20.
- [x] T3 — `domain.py`: `HistoryItem.channel`, relleno en `_case_history`, `channel_labels` tolerante a fallo. Cubre: R7, R8, R12.
- [x] T4 — `advisor_panel.py`: parámetro `labels` y etiqueta en tabla, encabezado, burbujas, ficha y resúmenes; CSS `.channel-label`. Cubre: R9, R10, R11, R13, R14.
- [x] T5 — `advisor_routes.py` y `panel_live_routes.py`: calcular y pasar `labels` (carga inicial, `/asesor/live/inbox`, `/asesor/live/cases/{id}`, memoria). Cubre: R9-R14, R18, R19.
- [x] T6 — Tests `services/orchestrator/tests/test_channel_label.py` (puro: componente, escape, contraste, ícono desconocido, canal desconocido, SVG sin estilos en línea). Cubre: R1-R6, R20.
- [x] T7 — Tests `test_etiqueta_origen_panel.py`: etiqueta en bandeja, encabezado, mensajes, ficha y resúmenes; canal inactivo; canal desconocido; directorio caído; nombre e ícono con HTML escapado. Cubre: R2, R6-R14, R21.
- [x] T8 — Tests de filtro (canal registrado nuevo e inactivo, combinación con asignación y tag, canal inválido 422) y en vivo (`live_inbox`, `live_case` igual que la carga inicial). Cubre: R15-R19.
- [x] T9 — `./init.sh` verde e informe `progress/impl_etiqueta_origen_canal.md` con la trazabilidad. Cubre: todas.
