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

## 2026-11-17 — #60 rediseno_identidad_panel (in_progress, rama `lazaro/rediseno-identidad-panel`)

- Nueva identidad visual del prototipo del dueño (paleta turquesa, claro y
  oscuro); la marca visible sigue siendo "Lázaro Software" (decisión del usuario).
- Shell común `admin._shell` (barra lateral con menú agrupado e iconos SVG en
  línea, ruta `Panel / título`, salida al pie) usado por `/admin` y `/asesor`.
- Inicio con accesos rápidos; editor de "Textos del flujo" de dos columnas sin
  JavaScript (`:target` + `:has()`); perfiles con tarjeta, avatar, insignia y
  Sí/No; login con curvas y tarjeta translúcida en `/admin/login`,
  `/asesor/login` y `/acceso`.
- Escrito directamente por Claude a pedido del usuario (OpenCode no está
  instalado en este equipo). Sin cambios de rutas, formularios ni CSP.
- Pruebas: `tests/test_rediseno_identidad.py` (R1–R22) y ajuste en
  `test_panel_visual.py`. `./init.sh`: 3643 passed, 1 skipped.
- Panel de asesores (R23–R25): menú por rol (Atención / Supervisión /
  Privacidad) vía `ContextVar` fijada en `_require_session`; Inicio con accesos
  rápidos, tarjeta de presencia y tarjetas de acción; métricas en tarjetas
  (`admin.metrics_body`, compartido con `/admin/metricas`).
- `./init.sh`: 3648 passed, 1 skipped.
- Pendiente: revisión del dueño en el PR; marcar `done` tras el merge.
