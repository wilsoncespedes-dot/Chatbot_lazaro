# Revisión de spec — feature #59 `chat_caso_asesor`

**Veredicto:** APROBADO

- Acceptance 1-6 cubiertos (tabla de cobertura de `requirements.md`); R1-R39 en EARS, un solo `DEBE`, verificables; cada `R<n>` tiene un test nombrado y una task (T1-T13; T14 es el cierre).
- El design coincide con el código actual: `render_history_fragment` mantiene su firma (`panel_live_routes.py:245` no cambia); `#live-region` conserva `data-*`; el compositor, el selector de respuestas guardadas y el aviso quedan fuera de la región que reemplaza `panel_live.js` (R17, R27).
- Tests fijados que siguen siendo compatibles: `test_panel_reply.py:194-203` y `test_saved_replies_advisor.py:98` (etiqueta exacta `<textarea name="text" maxlength="4096" required>`); `test_notes.py:75` (`Historial` antes de `Notas internas`); `test_panel_case_view.py:56-60`; `test_panel_visual.py:322,340` (`method="post" action="/asesor/reply"`; la página del caso sigue teniendo tablas en Cliente/Notas); `test_panel_live_js.py` (un único `<script`, marcadores de #53, sin `http(s)://`); `test_panel_live_fragments.py:33` solo afecta al fragmento de la bandeja, que no cambia.
- Redirección de `POST /asesor/reply`: solo se compara con el literal `origen == "caso"`. El destino se arma con un `case_id` que ya pasó `_valid_case_id` (`advisor_routes.py:517`), codificado con `quote(..., safe='')`, y apunta a una ruta fija del mismo origen, así que no hay redirección abierta. `_require_csrf` (l. 509) y `_audit` (l. 549) quedan antes y sin cambios.
- No hay JS en línea, contratos, variables de entorno ni dependencias nuevas. La CSS solo usa variables existentes de `:root`; el contraste de `--text`/`--muted` sobre `--surface`/`--ok-bg`/`--info-bg` es ≥ 4.5:1 con los valores actuales.

Notas no bloqueantes para el implementer:
1. `advisor_routes.py` todavía no importa `quote`; hay que añadir `from urllib.parse import quote`.
2. En `_chat_time`, una fecha `at` sin zona horaria debe tratarse como UTC también en `datetime` (R3), para que `localizeTimes` no la lea como hora local.
