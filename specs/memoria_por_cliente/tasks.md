# #40 memoria_por_cliente — Tasks

Orden pensado para que cada paso deje la suite en verde. Tests con
`FakeRepository`, `FakeGatewayClient`, `FakeRAG`, `FakeHandover`, `ScriptedLLM`
y reloj inyectado; sin red ni Docker. Nombres de test con prefijo
`test_r<n>_…` para la trazabilidad en `progress/impl_memoria_por_cliente.md`.

## Preparación

- [x] T0 — Revisar `referencias/` (si no existe, anotarlo) por piezas
  MIT/Apache 2.0 aplicables a resúmenes o memoria de chat. Solo se copia tras
  confirmar archivo, commit y licencia, con registro en
  `THIRD_PARTY_NOTICES.md`. Si no hay nada, dejar una línea en
  `progress/impl_memoria_por_cliente.md`. Cubre: — (higiene de licencias).

## Puros (sin IO)

- [x] T1 — `memory.py`: `session_window`, `in_window`. Tests en
  `tests/test_memory.py`: límites inclusivos de inicio/fin, límite idle
  exclusivo, sesión abierta usa `now`, mensaje que dispara el cierre por
  inactividad queda fuera. Cubre: R10 (soporte), R42 (soporte).
- [x] T2 — `memory.py`: `is_sensitive`, `clean_memory_items`,
  `clean_summary`. Tests: cada familia de keyword (con y sin tildes), 6 dígitos
  con y sin separadores, correo, 5 dígitos no marca; recorte, vacíos,
  duplicados por `normalize_text`, truncado y máximo de elementos; oración
  sensible eliminada del resumen y truncado. Cubre: R15–R19.
- [x] T3 — `memory.py`: `MEMORY_SUMMARY_PROMPT`, `build_summary_prompt`,
  `parse_summary_answer`, `SummaryInvalid`, `PromptContext`,
  `MEMORY_CONTEXT_NOTE`. Tests: el prompt de sistema menciona contraseñas,
  documentos, tarjetas, salud, religión, política, sindicatos, biometría y
  otras personas; etiquetas neutralizadas; JSON válido; rechazo de JSON
  inválido, claves extra/faltantes, tipos incorrectos. Cubre: R9, R11, R20.

## Configuración y persistencia

- [x] T4 — `config.py` + `.env.example` + `render.yaml`: variables de la tabla
  de design con rangos y validación de `SUPPRESSION_EXECUTOR_ROLES`. Tests en
  `tests/test_config.py` (o nuevo `test_memory_config.py`): defaults, cada
  rango fuera de límite, roles vacíos o con `cliente`. Cubre: R52, R54.
- [x] T5 — `repository.py`: tablas, índices y migraciones; métodos
  `session_messages`, `get_client_memory`, `set_client_memory`,
  `upsert_conversation_summary`, `list_conversation_summaries`,
  `link_case(..., profile_id=None)`, `get_case_profile`,
  `get_suppression_request`, `execute_suppression` en Protocol, Fake y
  Postgres; `StoredSuppressionRequest` con campos nuevos opcionales. Tests de
  Fake (upsert sin duplicar, ventana, aislamiento por `profile_id`) y de
  esquema/SQL con conexión falsa si el patrón existe. Cubre: R3–R5, R31, R44,
  R43 (soporte).
- [x] T6 — `purge_personal_data` (Fake y Postgres) borra
  `conversation_summaries` antiguos y nunca `client_memory`. Tests en
  `tests/test_memory_suppression.py`: memoria antigua sobrevive a la purga;
  resumen antiguo se borra y se cuenta; resumen reciente se conserva. Cubre:
  R47, R53.

## Dominio

- [x] T7 — `_summarize_session` y llamada desde `end_client_session`
  (motivos logout, idle, revoked, admin_closed; nunca `suppression`). Tests en
  `tests/test_memory_flow.py`: con `MEMORY_ENABLED=true` se guarda resumen
  `session_end` y memoria depurada; con `false` no hay llamada al LLM ni
  escrituras; ventana vacía no llama al LLM; mensajes sensibles no llegan al
  prompt; LLM caído y JSON inválido no escriben y dejan `memory_failed`; el
  cierre de sesión y su respuesta al cliente ocurren igual; el resumidor no
  envía ni guarda mensajes. Cubre: R1, R3, R6–R9, R11–R13, R15, R19.
- [x] T8 — Resumen al escalar en `_tool_escalate`. Tests: escalamiento por
  palabra clave con sesión guarda/reemplaza resumen `escalation` sin tocar la
  memoria; handover caído no resume; sin sesión no resume. Cubre: R2, R4, R5.
- [x] T9 — `build_llm_prompt(..., context)` y `_memory_context` en
  `_tool_rag`. Tests: con contexto, user contiene `<memoria>` e
  `<historial>` del cliente y system incluye `MEMORY_CONTEXT_NOTE`; sin sesión
  no hay bloques; `MEMORY_CONTEXT_MESSAGES=0` omite historial; con
  `MEMORY_ENABLED=false` el prompt es idéntico al anterior (comparar con la
  cadena esperada de los tests de #6); router y SQL no reciben memoria
  (`ScriptedLLM.calls`). Cubre: R21–R23, R25, R26.
- [x] T10 — `_handover` guarda `profile_id` en el vínculo; `advisor_client_memory`.
  Tests: vínculo con y sin sesión; authorize se llama antes de leer memoria
  (repositorio espía); denegaciones `forbidden`/`case_closed`/`not_found` y
  `ServiceUnavailable` no devuelven memoria; sin `profile_id` →
  `authenticated=False`; evento `memory_viewed`. Cubre: R27–R33, R55, R56.
- [x] T11 — `execute_suppression`. Tests en
  `tests/test_memory_suppression.py`: actor inexistente, rol `asesor` con
  default y rol `cliente` → 403 sin borrar; solicitud inexistente → 404;
  ya ejecutada → 409; sesión activa se cierra sin resumir; se borran memoria,
  resúmenes y mensajes de las ventanas del cliente; se conservan memoria,
  resúmenes y mensajes de otro cliente en el mismo chat y los mensajes previos
  al login; solicitud `executed` con recuentos; auditoría
  `suppression_executed`; ejecutar `crear_solicitud_supresion` y las demás
  herramientas no borra memoria ni resúmenes. Cubre: R35–R46.

## Panel del asesor

- [x] T12 — Ruta `GET /asesor/cases/{case_id}/memoria`,
  `render_advisor_memory` y enlace en la lista. Tests en
  `tests/test_memory_panel.py` con `TestClient`: sin sesión redirige a login;
  sin Telegram vinculado 403; `case_id` inválido 422; 403/404/409/502 con la
  página de error; 200 muestra elementos y resúmenes del cliente del caso y no
  los de otro cliente; texto con `<script>` aparece escapado; "Sin cliente
  autenticado" cuando el vínculo no tiene perfil. Cubre: R27–R30, R32, R34,
  R55, R56.

## Pruebas de aceptación

- [x] T13 — Continuidad entre sesiones y canales: cliente P conversa en
  Telegram, cierra sesión (logout) y, en otro escenario, su sesión queda
  inactiva y se cierra perezosamente al hacer login desde WhatsApp; en ambos
  casos el prompt RAG de la nueva sesión contiene el elemento de memoria.
  Cubre: R14, R48.
- [x] T14 — Aislamiento: clientes A y B en el mismo chat (sesiones
  consecutivas) y en chats distintos; el prompt del resumidor de A no contiene
  mensajes de B; el prompt RAG de A no contiene memoria de B aunque el texto
  nombre el `profile_id` de B. Cubre: R10, R24, R49.
- [x] T15 — Borrado: tras `execute_suppression`, una sesión nueva del mismo
  cliente no recibe la memoria anterior en el prompt RAG y el panel no la
  muestra. Cubre: R50.

## Cierre

- [x] T16 — `docs/architecture.md` (línea en §4) y comentario de sección en
  `.env.example`. Ejecutar `./init.sh` una vez; todas las suites verdes.
  Escribir `progress/impl_memoria_por_cliente.md` con la tabla R → tests.
  Cubre: R51. Nota: docs y mapa completados; `./init.sh` lo ejecuta Claude
  al cerrar la sesión del implementer.
