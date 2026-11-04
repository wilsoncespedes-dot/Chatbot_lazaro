# #39 harness_ia_por_estado — Tasks

Orden pensado para que cada paso deje la suite en verde. Tests con
`FakeRepository`, `FakeGatewayClient`, `FakeRAG`, `FakeClientData`,
`ScriptedLLM` y reloj inyectado; sin red ni Docker. Nombres de test con
prefijo `test_r<n>_…` para la trazabilidad en
`progress/impl_harness_ia_por_estado.md`.

## Preparación

- [x] T0 — Revisar `referencias/` (fuera de git; si no existe, anotarlo) por
  piezas MIT/Apache 2.0 aplicables a enrutado de herramientas o RLS. Solo se
  copia tras confirmar archivo, commit y licencia, con registro en
  `THIRD_PARTY_NOTICES.md`. Si no hay nada, dejar una línea en
  `progress/impl_harness_ia_por_estado.md`. Cubre: — (higiene de licencias).

## Puros (sin IO)

- [x] T1 — Si hace falta para evitar import circular, mover
  `ConversationState`, `ConversationEvent` y `transition_state` a
  `orchestrator/states.py` y reexportarlos desde `domain.py`; la suite actual
  sigue verde sin tocar sus imports. Cubre: R1 (soporte).
- [x] T2 — `harness.py`: `ToolName`, `TOOL_NAMES`, `TOOL_MATRIX`
  (`MappingProxyType`), `authorize_tool`, `default_tool`. Tests en
  `tests/test_harness_matrix.py`: tabla completa 7 estados × 6 herramientas
  parametrizada; `TOOL_NAMES` tiene exactamente seis nombres; la matriz no se
  puede mutar; herramienta desconocida → `False`. Cubre: R1, R2, R3, R19.
- [x] T3 — `harness.py`: `build_router_prompt`, `parse_router_answer`,
  `RouterInvalid`, `args_sha256`, `matches_any`. Tests: el prompt de cada
  estado lista solo sus herramientas; `</mensaje>` en el texto se neutraliza;
  el prompt no contiene un `profile_id`/username dados; JSON válido por cada
  herramienta; rechazo de JSON inválido, herramienta desconocida, `args` con
  `cliente_id`/`sql`/`query`, `motivo` fuera de `user_request|frustration`;
  hash estable con orden de claves distinto. Cubre: R15, R17, R18, R8.

## Configuración y persistencia

- [x] T4 — `config.py` + `.env.example` + `render.yaml`: variables de la tabla
  de design con rangos; validación de R35 (DSN vacío/igual a `DATABASE_URL` o
  `DB_QUERY_DATABASE_URL`, allowlist inválida, `CLIENT_DATA_RLS_SETTING`
  inválido) y `{request_id}` obligatorio en `SUPPRESSION_REQUEST_REPLY`. Tests
  en `tests/test_harness_config.py`: defaults, fuera de rango falla, cada caso
  de R35 falla. Cubre: R35, R59, R63.
- [x] T5 — `repository.py`: tablas `tool_calls` y `suppression_requests`
  (+ índice único parcial), `add_tool_call`,
  `create_or_get_pending_suppression`, `set_suppression_case` en Protocol,
  Fake y Postgres; purga borra `tool_calls` (antigüedad y contactos inactivos)
  y reporta `deleted["tool_calls"]`; la purga no toca `suppression_requests`.
  Ajustar los tests de purga que comparan el dict exacto de `deleted`. Tests
  en `tests/test_repository_schema.py` y `tests/test_privacy_purge.py`.
  Cubre: R7, R9, R36, R37, R42.

## Adaptador de datos de cliente

- [x] T6 — `adapters/db_query.py`: extraer `verify_view_catalog(cursor,
  allowlist)` y reutilizarlo en `PostgresReadOnlyQuery` sin cambiar su
  comportamiento (suite de #26 verde). Cubre: R29 (soporte).
- [x] T7 — `adapters/client_data.py`: `ClientDataClient`,
  `PostgresClientDataQuery`, `UnavailableClientData`, `FakeClientData`. Tests
  en `tests/test_client_data.py` con conexión/cursor falsos: orden exacto de
  sentencias (R27); `cliente_id` solo en parámetros y nunca en el texto SQL
  (R28); catálogo inválido → `DbQueryUnavailable` sin ejecutar (R29); rol
  `rolsuper` o `rolbypassrls` → `DbQueryUnavailable` (R30); sonda con fila →
  `DbQueryUnavailable` (R31); `ROLLBACK` y `close` siempre, también en error;
  verificación memorizada tras el primer éxito. Cubre: R27–R31.
- [x] T8 — `main.py` y `Adapters.client_data` (default
  `UnavailableClientData`): con `CLIENT_DATA_ENABLED=true` se construye
  `PostgresClientDataQuery`. Test en `tests/test_orchestrator_infra.py`.
  Cubre: R26 (soporte), R59.

## Harness en el dominio

- [x] T9 — `domain.py`: `ToolContext`, `execute_tool`, `_TOOL_EXECUTORS` con
  las seis claves y auditoría en `tool_calls`. Tests en
  `tests/test_harness_flow.py`: herramienta denegada no llama a ningún
  adaptador y registra `denied` (R5); denegada desde router responde
  `HARNESS_TOOL_DENIED_REPLY` (R6); fila de `tool_calls` con todos los campos
  y sin texto/SQL en claro (R7, R8); estado leído del repositorio en el turno
  (cambiar el estado entre resolución y ejecución → se deniega) (R4).
  Cubre: R4–R8.
- [x] T10 — Guardrails y `_resolve_and_run` en `_route_consented_text`
  (`active`, `no_access`). Tests: texto > `HARNESS_MAX_INPUT_CHARS` → respuesta
  fija, evento `guardrail:input_too_long`, sin rag/llm/handover (R11, R12);
  patrón de inyección → evento `guardrail:prompt_injection` y router no
  llamado aunque esté activo (R13, R14); orden de precedencia con texto que
  contiene supresión + asesor → supresión (R20); router apagado → una sola
  llamada al LLM (la de RAG) (R20). Cubre: R11–R14, R20.
- [x] T11 — Router (`HARNESS_ROUTER_ENABLED=true`) con `ScriptedLLM` en
  `tests/fakes.py`. Tests: decisión válida ejecuta la herramienta con origen
  `router` (R16); salida inválida / `cliente_id` en args / LLM caído →
  `tool_calls` `invalid` y herramienta por defecto (R10, R18, R19); en
  `no_access` inválido → `suspended_reply`; router nunca llamado en
  `with_advisor`, `awaiting_login`, `new`, `awaiting_consent`, `closed` (R55).
  Cubre: R10, R16, R19, R55.
- [x] T12 — `buscar_base_conocimiento` (`_tool_rag`) con el cuerpo actual de
  `_respond_to_client_text`. Tests: la consulta a RAG y `<pregunta>` usan el
  texto original aunque el router devuelva otra cosa (R44); validación con
  `validate_llm_answer` (R45); `chunk_id` ajeno / cita no literal →
  `no_answer_reply` y racha `invalid_answer` (R60). Suites #6/#24 verdes.
  Cubre: R44, R45, R60.
- [x] T13 — `consultar_mis_datos` (`_tool_client_data`). Tests: sin sesión →
  `no_session` (R22); deshabilitado → `disabled` sin LLM ni adaptador (R23);
  prompt SQL con `CLIENT_DATA_ALLOWLIST` y validación con el esquema de
  clientes (R24); SQL con tabla `public.*` o vista no permitida → `rejected`
  sin adaptador (R25); adaptador llamado con el `profile_id` de la sesión
  (R21, R26); `DbQueryUnavailable` o LLM caído → `unavailable` (R32);
  respuesta = `format_rows` (R33); `llm.calls` no contiene ningún valor de las
  filas devueltas (R34). Cubre: R21–R26, R32–R34.
- [x] T14 — `escalar_a_asesor` y `_auto_handover` vía harness. Tests: palabra
  clave de asesor → `escalation:user_request`, `HandoverRequest.reason =
  user_request` (R46, R49, R50); frustración con flag activo → `frustration` y
  reason `user_request`; con flag apagado → RAG normal (R47); racha alcanzada
  → `repeated_failure`, reason `no_relevant_chunks`/`invalid_answer` y
  `finish_auto_handover` como #24 (R48, R50); en `no_access` el estado pasa a
  `with_advisor` (R51). Cubre: R46–R51.
- [x] T15 — `crear_solicitud_supresion`. Tests: con sesión crea fila
  `pending` con `profile_id` de la sesión (R36, R21); segunda solicitud
  reutiliza el id (R37); `case_id` guardado tras handover (R38); respuesta
  `SUPPRESSION_REQUEST_REPLY` con el id y sin `handover_ack_reply` (R39); sin
  sesión no crea fila y escala con motivo `suppression` (R40); palabras clave
  configurables en `active` y `no_access` (R43); el test existente
  `test_no_access_suppression_request_moves_to_advisor_without_rag` sigue
  verde. Cubre: R21, R36–R40, R43.
- [x] T16 — `enviar_link_inicio_sesion` y `cerrar_sesion`. Tests: texto en
  `awaiting_login` → fila `tool_calls` `enviar_link_inicio_sesion`/`rule`,
  `LinkBlock` enviado, sin rag/llm/client_data (R52); router elige
  `cerrar_sesion` en `active` → sesión cerrada con `logout`,
  `session_closed_reply` con enlace (R53); suites de #38 verdes.
  Cubre: R52, R53.
- [x] T17 — Prueba de no borrado: para cada una de las seis herramientas
  ejecutada en un estado permitido, el número de filas de cada colección del
  `FakeRepository` (contactos, mensajes, eventos, consentimientos, sesiones,
  credenciales, casos, `tool_calls`, `suppression_requests`, …) no disminuye.
  Cubre: R41.
- [x] T18 — Consentimiento: remitente sin consentimiento vigente (Telegram
  legado y canal normalizado) envía "quiero que borren mis datos", "quiero un
  asesor", "estoy harto", un patrón de inyección y una pregunta de datos con
  router activo → sin filas en `tool_calls`/`suppression_requests`, sin
  llamadas a llm/rag/client_data; suites de #35/#37 verdes. Cubre: R54, R61.

## Evaluación

- [x] T19 — `tests/data/harness_eval_cases.json` + `tests/test_harness_eval.py`
  parametrizado: ≥2 casos por categoría (acceso entre clientes, inyección,
  herramienta prohibida por estado, consentimiento, fuentes inválidas); cada
  caso declara estado, sesión, texto, respuestas del `ScriptedLLM`, filas por
  cliente del `FakeClientData` y lo esperado (respuesta, herramienta/decisión,
  adaptadores llamados). Incluye A pidiendo datos de B por texto, por
  `args.cliente_id` del router y por `WHERE cliente_id = '<B>'` en el SQL
  generado. Cubre: R56, R57, R62.

## Documentación y cierre

- [x] T20 — `docs/consulta_bd.md`: sección "Datos propios del cliente (#39)"
  con rol `lazaro_cliente_lectura` sin `BYPASSRLS`, `GRANT SELECT` solo sobre
  vistas de `mis_datos`, tablas base con `ENABLE` + `FORCE ROW LEVEL SECURITY`
  y política `USING (cliente_id = current_setting('lazaro.cliente_id', true))`,
  vistas propiedad de un rol sin `BYPASSRLS`, la sonda de R31 y cómo
  habilitar. `docs/architecture.md` §4: referencia a `harness.py`. Cubre: R29–R31
  (documentación operativa).
- [ ] T21 — `progress/impl_harness_ia_por_estado.md` con la trazabilidad
  `R<n> → test` (R1–R63) y `./init.sh` verde. Cubre: R58.
