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

## 2026-11-21 — Fase 0 de la ampliación multicanal genérica (solo docs)

- **Origen:** revisión del profesor (plataforma multicanal y multiagente de
  verdad). El dueño aprobó el plan por fases con cambios: login obligatorio,
  etiqueta de origen en todo el panel como prioridad alta, outbox en Postgres,
  importación de clientes y API de Lázaro solo como «a futuro».
- **Rama:** `feat/multicanal-generico` (los push a `feat/lazaro-backlog-complete`
  se despliegan solos en AWS; esta rama no).
- **Registrado:** features #60–#78 en `feature_list.json` (todas `pending`;
  #78 README con `sdd: false`) y `esqueleto_instagram` en `later`.
- **Docs:** `docs/especificacion.md` (sección «Ampliación multicanal genérica y
  multiagente», filas de Canales y Multimedia, campo `canal`, puntos abiertos),
  `docs/architecture.md` (mapa, sección «Multicanal genérico», principios 6 y
  8) y `docs/proyecto.md` (§1 y §13.6).
- **Decisiones pendientes del dueño:** protección de secretos de `canales`
  (antes de #61) y Excel en la importación (antes de #77).
- **Siguiente:** fase 1, feature #60 `contrato_canal_abierto` → `spec_author`.
