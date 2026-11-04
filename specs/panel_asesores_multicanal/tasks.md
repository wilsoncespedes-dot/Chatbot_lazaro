# #41 panel_asesores_multicanal — Tasks

Orden: contratos → handover → orchestrator (puro → repositorio → dominio →
rutas/plantillas) → config/docs → tests → `./init.sh`. Cada test nombra su
`R<n>` en el docstring. Los tests de bandeja, respuesta, acciones y vista se
parametrizan con un contacto Telegram y uno WhatsApp (A5).

## Contratos

- [x] T1 — Añadir `CaseTransferRequest` y `CaseTransferResponse` en `contracts/lazaro_contracts/cases.py`, exportarlos en `__init__.py`, crear `contracts/examples/case_transfer_request.json` y `case_transfer_response.json`, mapearlos en `contracts/tests/test_examples.py` y documentar `POST /cases/{id}/transfer` en `contracts/CONTRATOS.md`. Cubre: R26.

## Handover

- [x] T2 — `transfer_if_assigned_to(case_id, from_id, to_id, at) -> bool` en el Protocol, `FakeCaseRepository` y Postgres de `services/handover/handover/adapters/repository.py`. Cubre: R27, R31.
- [x] T3 — `DenialAction` con `"transfer"`, `TransferTargetInvalid` y `transfer_case` en `services/handover/handover/domain.py`. Cubre: R27–R31.
- [x] T4 — Ruta `POST /cases/{case_id}/transfer` en `services/handover/handover/main.py` con `X-Service-Token`. Cubre: R27, R74.
- [x] T5 — `services/handover/tests/test_transfer.py`: éxito, actor no registrado/no dueño (denegación `transfer`), destino inválido/igual, 404, 409, carrera perdida a destino (200) y a otro (403). Añadir la ruta a las tablas 401/422 de `test_security.py`. Cubre: R27–R31, R74.

## Orchestrator — puro

- [x] T6 — Crear `services/orchestrator/orchestrator/panel.py` con `channel_window`, `case_wait`, `business_deadline`, `business_days_left`, `suppression_priority`, `effective_presence`, `mask_external_id`, `history_visible`. Cubre: R4, R5, R34, R44, R46, R63, R64.
- [x] T7 — `services/orchestrator/tests/test_panel_pure.py`: límites de ventana (exacto 24 h cerrada, sin mensajes cerrada, Telegram `not_applicable`), espera en sus tres ramas, fecha límite saltando fin de semana, prioridad en sus tres ramas, presencia expirada, máscara, visibilidad dentro/fuera de ventana ajena. Cubre: R4, R5, R34, R44, R63, R64.

## Orchestrator — config

- [x] T8 — Variables de R71 con validación en `config.py` (propiedad `advisor_whatsapp_template_list`); declararlas en `.env.example` y `render.yaml`. Tests en `test_config.py` (defaults y cada valor inválido nombrado). Cubre: R71, R72.

## Orchestrator — adaptadores y repositorio

- [x] T9 — `ChannelRejected(ServiceUnavailable)` en `domain.py`; `HttpGatewayClient._post` la lanza con 422; `FakeGatewayClient` gana `reject_channel: bool`. Test en `test_adapters.py` con transporte simulado. Cubre: R21.
- [x] T10 — `transfer` en `HandoverClient` (Protocol, Http con `_TRANSFER_DENIAL_CODES`, Fake con `transferred`, `transfer_error`, `fail_transfer`). Tests en `test_adapters.py`. Cubre: R32, R33.
- [x] T11 — Repositorio (Protocol, Fake, Postgres): `get_case_contact` Postgres completo; `get_case_link`, `case_activity`, `last_user_message_at`, `case_messages`, `foreign_session_windows`, `last_privacy_decision`; presencia (`set_`, `touch_`, `get_advisor_presence`); `add_panel_audit`, `list_panel_audit`; `list_suppression_requests`, `set_suppression_outcome`; tablas `panel_audit`, `advisor_presence`, columnas `result_note`, `notification_result` e índices en `_SCHEMA`/`_INDEXES`/`_MIGRATIONS`. Cubre: R13, R55, R56, R58, R62, R66.
- [x] T12 — `test_repository_schema.py`: tablas, columnas e índices nuevos ejecutados dos veces sin error; consulta de `get_case_contact` con las seis columnas. Cubre: R13, R55.

## Orchestrator — dominio

- [x] T13 — Excepciones `ChannelWindowClosed`, `PanelValidationError`, `AdvisorUnavailable`; mensajes en `advisor_panel.ERROR_MESSAGES`. Cubre: R16, R34, R52.
- [x] T14 — `reply_to_case` con comprobación de ventana tras `authorize` y mapeo de `ChannelRejected`; `_command_reply` captura `ChannelWindowClosed`. Cubre: R14, R16, R21, R22, R23.
- [x] T15 — `advisor_send_template`. Cubre: R17–R20, R23.
- [x] T16 — `transfer_case` (validación de destino, presencia, mapeo de errores, evento). Cubre: R32–R35, R54.
- [x] T17 — `_close_with_notice`, `close_case` sobre él y `return_case`. Cubre: R36–R39, R73.
- [x] T18 — `advisor_inbox` con filtros validados antes de handover. Cubre: R1–R10.
- [x] T19 — `advisor_case_view` (memoria vía `advisor_client_memory`, historial filtrado, datos permitidos, plantillas, destinos con presencia, acciones). Cubre: R40–R47, R49.
- [x] T20 — `record_panel_audit`, `set_advisor_presence`, `touch_advisor_presence`. Cubre: R50–R53, R56–R59.
- [x] T21 — `suppression_queue` y `execute_suppression_from_panel` (rol, nota, ventana antes del borrado, aviso sin `add_message`, resultado de notificación). Cubre: R60–R70.

## Orchestrator — rutas y plantillas

- [x] T22 — `advisor_panel.py`: `_page(refresh=...)`, `render_advisor_cases` con columnas y filtros, `render_advisor_case` (historial con etiquetas por rol, datos de cliente, memoria/resúmenes, textarea o selector de plantillas, formularios transferir/resolver/devolver), presencia en inicio, `render_suppression_queue(rows, csrf, action_prefix)`; todo con `_esc`. Cubre: R2–R7, R12, R24, R25, R43, R46–R49, R65.
- [x] T23 — `advisor_routes.py`: `GET /asesor/cases` con filtros; `GET /asesor/cases/{case_id}`; `POST /asesor/reply` con `text`|`template`; `POST /asesor/transfer`; `POST /asesor/return`; `POST /asesor/presence`; `GET /asesor/supresiones`; `POST /asesor/supresiones/{request_id}/execute`; `touch` de presencia en `_require_session`; presencia `away` en logout; auditoría en cada ruta. Cubre: R1, R8, R11, R14, R15, R32, R37, R40, R50–R52, R56–R61, R66, R67, R70.
- [x] T24 — `admin_routes.py`: `GET /admin/supresiones`, `POST /admin/supresiones/{request_id}/execute` con CSRF y auditoría; enlace "Supresiones" en la navegación de `admin.py`. Actualizar el test de superficie `APIRoute` de `test_config.py` con todas las rutas nuevas. Cubre: R60, R61, R66.

## Orchestrator — tests

- [x] T25 — `test_panel_inbox.py`: bandeja Telegram + WhatsApp con columnas, asignación, espera, ventana, nombre/`Sin autenticar`; filtros y filtro inválido (422 sin llamar a handover); orden; caso sin contacto; sesión `admin` o sin sesión redirige; meta refresh con 30 y ausente con 0; solo casos del asesor (`handover.listed`). Cubre: R1–R12.
- [x] T26 — `test_panel_reply.py`: texto Telegram (`gateway.sent`) y WhatsApp abierta (`channel_sent`); WhatsApp cerrada → 409 sin envío ni mensaje; plantilla válida enviada como `TemplateBlock` y guardada `[plantilla:…]`; plantilla desconocida, en Telegram o con ventana abierta → 422; `text` y `template` a la vez o ninguno → 422; gateway 422 → 409; `authorize` antes de la ventana (denegado no consulta mensajes); `/responder` a WhatsApp cerrada → `ADVISOR_COMMAND_FAILED_REPLY`; vista con selector vs textarea. Cubre: R14–R25.
- [x] T27 — `test_panel_actions.py`: transferir con éxito y evento; destino inexistente/no asesor/sin Telegram/propio → 422 sin handover; destino `away` → 409; errores de handover → 403/404/409/422/502; resolver conserva `CASE_CLOSED_REPLY` y `ADVISOR_RESOLVED`; devolver envía `ADVISOR_RETURN_REPLY`, estado `active` y evento; WhatsApp cerrada en resolver/devolver → `notice_skipped` y caso cerrado; presencia `available`/`away`, inválida 422, `touch` y logout `away`. Cubre: R32–R39, R56–R59.
- [x] T28 — `test_panel_case_view.py`: autorización previa (denegado → sin lecturas: `repo` espía); historial desde lookback con límite y etiquetas; mensajes en ventana de sesión de otro cliente excluidos (con y sin perfil del caso); memoria/resúmenes mostrados; datos permitidos exactos y ID enmascarado; caso sin perfil `Sin cliente autenticado`; escape de `<script>` en mensaje, memoria, nombre y plantilla; destinos con presencia; `GET /asesor/cases/{id}/memoria` sigue respondiendo; `get_case_contact` del fake devuelve canal WhatsApp. Cubre: R13, R40–R49, R73.
- [x] T29 — `test_panel_audit.py`: una fila por lectura (`inbox_viewed`, `case_viewed`, `memory_viewed`, `suppression_queue_viewed`) y por acción con `ok`; errores con su código; ninguna fila contiene el texto enviado, el `username` del cliente, el ID externo ni la nota; `advisor_forbidden` sigue registrándose. Cubre: R50–R55.
- [x] T30 — `test_panel_suppression.py`: cola en `/admin/supresiones` (admin) y `/asesor/supresiones` (con `SUPPRESSION_EXECUTOR_ROLES=admin,asesor`); rol no ejecutor → 403 sin leer; orden pending por fecha límite y luego executed limitados; prioridad vencida/urgente/alta; campos mostrados exactos; ejecución con CSRF llama `execute_suppression` y guarda nota; nota > 500 → 422 sin ejecutar; aviso Telegram texto, WhatsApp abierta texto, WhatsApp cerrada plantilla (ventana medida antes del borrado), sin fila en `messages`; fallo de aviso → `failed`; contacto inexistente → `skipped`; 404/409/403 sin avisos; sin CSRF → 403. Cubre: R60–R70.
- [x] T31 — Comprobar que `test_advisor_commands.py`, `test_advisor_panel.py`, `test_case_reply.py` y `test_memory_panel.py` siguen verdes sin cambios de aserciones (salvo textos de botones renombrados a "Resolver"). Cubre: R73.

## Cierre

- [x] T32 — Línea en `docs/architecture.md` §1 (panel multicanal y cola de supresión en el orchestrator; transferencia en handover). Trazabilidad R1–R74 → tests en `progress/impl_panel_asesores_multicanal.md`. Ejecutar `./init.sh` una vez y dejarlo verde. Cubre: R1–R74.
