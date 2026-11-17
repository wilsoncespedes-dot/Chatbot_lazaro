# Sesión actual

## 2026-11-16 — pruebas manuales con Telegram (fuera del flujo SDD, pedido del dueño)

- Hotfix directo (opción A del dueño): `HttpLLMClient` acepta un encabezado de
  sesión opcional (`LLM_SESSION_HEADER`, p. ej. `x-opencode-session` para
  OpenCode Go) y la IA tiene su propio tiempo de espera (`LLM_TIMEOUT_SECONDS`,
  60 s por defecto; antes usaba los 10 s de los servicios internos). Archivos:
  `adapters/llm.py`, `config.py`, `main.py`, `tests/test_adapters.py`,
  `.env.example`. Tests de `services/orchestrator` en verde.
- Hallazgos de configuración local (no de código): la IA apuntaba a OpenAI con
  clave de OpenCode Go; faltaban `IDENTITY_PUBLIC_BASE_URL` e
  `IDENTITY_LINK_SIGNING_KEY`; `RAG_SIMILARITY_THRESHOLD=0.75` es demasiado alto
  para `text-embedding-3-small` (preguntas del manual Siigo puntúan ~0.69,
  preguntas ajenas ~0.40). Para las pruebas se usó 0.5 vía override de compose
  fuera del repo.
- Corregido (directo, a pedido del dueño): `/admin/profiles` ya no crea ni
  cambia perfiles a rol `cliente` (sin credencial nunca podían entrar:
  `login_denied credential_revocada`); remite a `/admin/clientes`. Tests en
  `test_admin.py`; `test_roles_matrix.py::test_admin_role_selector_lists_five_roles`
  ajustado a la regla nueva.
- Corregido (directo): orchestrator, handover y rag reconectan a Postgres si la
  base se reinicia (antes: `BrokenPipeError` y 500 hasta reiniciar el
  servicio). La conexión se comprueba con `SELECT 1` tras 10 s sin uso y se
  descarta ante errores de red. Tests en `handover/tests/test_db_reconnect.py`.
  Verificado reiniciando el contenedor de Postgres: 0 errores.
- `./init.sh`: 3622 passed, 1 skipped.
- Pendiente de decidir: umbral RAG definitivo y si el cambio del encabezado de
  sesión se formaliza como feature.

## 2026-11-17 — #61 fechas_y_formularios_panel (in_progress, rama `lazaro/ajustes-fechas-formularios`)

- Fechas legibles ("17 nov 2026, 2:33 p. m.") en la zona del negocio
  (`BUSINESS_HOURS_UTC_OFFSET_MINUTES`) con `admin.time_html`; el chat del caso
  y el JS en vivo usan el mismo formato (sustituye `dd/mm HH:MM UTC` de #59 R3).
- Formularios de alta en cuadrícula alineada (`create-form`) y acciones de
  Clientes con botones del mismo ancho (`row-actions`).
- Pruebas en `tests/test_fechas_formularios.py`.
