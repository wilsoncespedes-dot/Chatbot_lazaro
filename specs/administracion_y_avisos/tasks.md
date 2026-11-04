# #42 administracion_y_avisos — Tasks

Orden: contratos → orchestrator (puro → repositorio → dominio → rutas/render)
→ worker y despliegue → config/docs → tests → `./init.sh`. Cada test nombra su
`R<n>` en el docstring. El reloj se inyecta (`adapters.clock`) en todos los
tests de fechas, horario y avisos.

## Ya cubierto por código existente (no reimplementar)

- [x] T0 — Verificar y reutilizar sin cambios de lógica: `create_client`,
  `renew_credential` (renueva desde `max(valid_until, now)` con
  `identity.validity_days`), `revoke_credential`, `close_client_session`,
  `_client_status`, `credential_status`, `days_remaining` (#38); textos en
  `app_settings` y `/admin/texts` (#37); `channel_window`, `TemplateBlock`,
  `panel_audit` (#41). Los tests nuevos de R2, R7–R10 los ejercitan desde el
  panel; no se duplican funciones. Cubre: R2, R7, R8, R9, R10.

## Contratos

- [x] T1 — Crear `contracts/lazaro_contracts/credentials.py` con
  `ExpiryNoticeRunRequest` / `ExpiryNoticeRunResponse`, exportarlos en
  `__init__.py`, añadir `contracts/examples/expiry_notice_run_request.json` y
  `expiry_notice_run_response.json`, mapearlos en
  `contracts/tests/test_examples.py` (y `test_packaging.py` si enumera
  módulos) y documentar `POST /credentials/expiry-notices` en
  `contracts/CONTRATOS.md`. Cubre: R45.

## Orchestrator — puro

- [x] T2 — `identity.py`: exponer `POLICY_FIELDS` (mantener `_POLICY_FIELDS`
  como alias). Cubre: R36, R39.
- [x] T3 — `privacy.py`: añadir `expiry_notice`, `out_of_hours_reply`,
  `closing_reply`, `topics_list` a `ConversationTexts`. Cubre: R15.
- [x] T4 — Nuevo `administration.py`: `SettingSpec`, `OPERATIONAL_SETTINGS`,
  `BusinessHours`, `OperationalSettings`, `resolve_operational_settings`
  (inválido → default + `warning` sin valor), `validate_settings_form`,
  `within_business_hours`, `format_local_date`, `render_expiry_notice`,
  `ALLOWED_TRANSITIONS`, validadores de plantilla, `effective_templates`,
  `median_minutes`, `first_response_summary`. Cubre: R26, R29, R32, R33, R36,
  R37, R38, R39, R41, R50, R63, R74.

## Orchestrator — repositorio (Protocol + Fake + Postgres)

- [x] T5 — Esquema: `text_versions`, `whatsapp_templates`,
  `credential_expiry_notices` e índices de `design.md`, idempotentes. Cubre:
  R16, R25, R53.
- [x] T6 — `get_app_settings(prefixes)`, `save_app_settings(upserts, deletes)`
  atómico. Cubre: R37, R74.
- [x] T7 — `save_conversation_texts` con versionado por campo cambiado en la
  misma transacción; `current_text_versions`, `text_history`. Cubre: R16, R17,
  R19, R20.
- [x] T8 — `list_client_credentials()` (perfil `cliente` + credencial + sesión
  activa) y `current_expiry_notice_status`. Cubre: R1.
- [x] T9 — `list_whatsapp_templates`, `create_whatsapp_template`
  (`TemplateExists`), `update_whatsapp_template` (vuelve a `draft`),
  `set_whatsapp_template_status` condicional. Cubre: R25, R26, R28, R29, R30,
  R31.
- [x] T10 — `list_expiring_credentials`, `last_client_contact`,
  `claim_expiry_notice` (SQL de `design.md`; Fake con lock),
  `finish_expiry_notice`. Cubre: R46, R49, R53, R54, R56.
- [x] T11 — `case_first_responses`, `advisor_reply_contacts`,
  `event_reason_counts`, `count_events`, `unanswered_samples`. Cubre: R63,
  R64, R65, R66.

## Orchestrator — dominio

- [x] T12 — Excepciones nuevas (`NoticeVersionRequired`, `SettingsInvalid`,
  `TemplateExists`, `TemplateNotFound`, `TemplateTransitionInvalid`) y
  `operational_settings(settings, adapters)` leído en cada llamada. Cubre:
  R18, R28, R30, R38, R40.
- [x] T13 — `update_conversation_texts` con la regla de R18; `text_history`.
  Cubre: R16, R17, R18, R20.
- [x] T14 — `_active_welcome_text` en `login_client` y `renew_credential`;
  `closing_reply` en `close_case`. Cubre: R23, R24.
- [x] T15 — `list_clients_admin` (usa `_client_status` + estado del aviso del
  periodo); el panel llama a las funciones de #38 para crear/renovar/
  revocar/cerrar. Cubre: R1, R2, R3, R4, R7–R11.
- [x] T16 — Plantillas: `create_template`, `update_template`,
  `change_template_status`, `effective_templates_for`; sustituir
  `settings.advisor_whatsapp_template_list` en `advisor_send_template` y
  `advisor_case_view`; plantilla de supresión efectiva o `skipped`. Cubre:
  R26–R35, R72, R73.
- [x] T17 — `save_operational_settings(form, actor, settings, adapters)`;
  `suppression_queue` / `execute_suppression_from_panel` con los plazos
  efectivos; `renew_credential`/`_client_status` ya usan `identity.*`. Cubre:
  R37, R38, R40, R74.
- [x] T18 — `_handover`: acuse fuera de horario y evento `out_of_hours`.
  Cubre: R42, R43.
- [x] T19 — `send_expiry_notices` según el orden de `design.md`. Cubre: R45–R59.
- [x] T20 — `admin_metrics(days, settings, adapters)`. Cubre: R62–R66, R68.

## Orchestrator — HTTP y render

- [x] T21 — `admin_routes.py`: rutas de clientes con validación de formulario
  (fechas, usuario, contraseña sin eco) y mapeo 404/409/422. Cubre: R3–R11.
- [x] T22 — `admin_routes.py`: `/admin/texts` con 422 de R18 y
  `/admin/texts/{field}/historial`. Cubre: R18, R19, R20, R21.
- [x] T23 — `admin_routes.py`: rutas de plantillas. Cubre: R25–R31.
- [x] T24 — `admin_routes.py`: `/admin/ajustes` GET/POST. Cubre: R36, R37,
  R38, R74.
- [x] T25 — `admin_routes.py`: `/admin/metricas` con validación de `dias`
  previa al repositorio. Cubre: R62, R67.
- [x] T26 — Auditoría `panel_audit` en todas las acciones admin nuevas y en
  `/admin/texts` (sin contraseñas ni valores). Cubre: R44.
- [x] T27 — `admin.py`: `render_clients`, `render_text_history`,
  `render_templates`, `render_settings`, `render_metrics`, versión vigente en
  `render_conversation_texts`, mensajes de error nuevos y enlaces de
  navegación; todo escapado. Cubre: R1, R19, R20, R25, R36, R63–R66, R70.
- [x] T28 — `main.py`: `POST /credentials/expiry-notices` tras el middleware
  de token. Cubre: R14, R45.

## Worker, despliegue, config y docs

- [x] T29 — `scripts/avisar_vencimientos.py` (patrón de `purgar_datos.py`) y
  `COPY` en `services/handover/Dockerfile`. Cubre: R60, R61.
- [x] T30 — `docker-compose.yml` (`expiry_notice_worker`) y `render.yaml`
  (`expiry-notice-worker` + variables nuevas del orchestrator). Cubre: R60.
- [x] T31 — `config.py` y `.env.example` con las variables de §Config y su
  validación. Cubre: R69.
- [x] T32 — `docs/architecture.md`: una línea en §1 sobre administración y el
  worker de avisos. Cubre: R45, R60 (documentación).

## Tests

- [x] T33 — `tests/test_administration_pure.py`: resolución de ajustes
  (válido gana, inválido → default + warning sin valor), validación de
  formulario (cada regla de R38, vacío → borrar), `within_business_hours`
  (bordes `start`/`end`, días, offset, cruce de medianoche),
  `render_expiry_notice` sin `str.format`, transiciones, `effective_templates`
  (con/sin registro, `expiry_notice` sin respaldo), mediana. Cubre: R29, R32,
  R33, R38, R39, R41, R50, R63, R74.
- [x] T34 — `tests/test_admin_permissions.py`: parametrizado sobre todas las
  rutas nuevas GET/POST → sin sesión, sesión vencida y sesión de asesor
  redirigen 303 sin efecto; POST sin/con CSRF incorrecto → 403 sin efecto;
  `POST /credentials/expiry-notices` sin token → 401 y sin pasada. Cubre: R12,
  R13, R14.
- [x] T35 — `tests/test_admin_clients.py`: tabla con estados y días; avanzar
  el reloj sin escrituras cambia días y estado (y no existe columna de
  contador); crear con/sin fechas; `valid_until` por defecto con
  `identity.validity_days` cambiado desde `/admin/ajustes` (sin reinicio);
  422 sin eco de contraseña; 409; renovar (desde vencida y desde vigente)
  usando el periodo configurado; renovar revocada 409; revocar cierra sesión;
  cerrar sesión no cambia fechas; 404; auditoría `client_*` con `profile_id`
  y sin contraseña. Cubre: R1–R11, R40, R44.
- [x] T36 — `tests/test_admin_texts_versions.py`: versión por campo
  cambiado, sin versión si no cambia, rollback total en 422 de R18, versión
  vigente visible, historial ordenado/limitado/escapado, campo desconocido
  404, el siguiente mensaje usa el texto nuevo, `closing_reply` en cierre,
  `topics_list` en bienvenida, defaults vacíos sin cambio; auditoría
  `texts_update` sin valores. Cubre: R15–R24, R44.
- [x] T37 — `tests/test_admin_templates.py`: crear válido en `draft`, 422 por
  cada campo, 409 duplicado, transiciones válidas/ inválidas con autor y fecha
  de aprobación, edición vuelve a `draft`, panel de asesor solo ofrece
  aprobadas cuando hay registro y la lista de entorno cuando no, plantilla no
  aprobada → 422 sin gateway, supresión con plantilla efectiva y `skipped` sin
  ella; auditoría `template_*` con el nombre. Cubre: R25–R35, R44, R72, R73.
- [x] T38 — `tests/test_admin_settings.py`: página con efectivo/default/origen,
  guardado atómico, 422 sin guardar nada, vacío restaura default, cambio
  efectivo sin reinicio en renovación, estado `por_vencer`, cola de supresión
  y traspaso fuera de horario; auditoría `settings_update` por clave. Cubre:
  R36–R40, R44, R74.
- [x] T39 — `tests/test_business_hours.py`: traspaso fuera de horario envía
  `out_of_hours_reply` (o el acuse si está vacío), evento `out_of_hours`, caso
  creado; dentro de horario o desactivado → acuse actual. Cubre: R42, R43.
- [x] T40 — `tests/test_expiry_notices.py` (Telegram y WhatsApp): candidatas
  según `identity.expiry_notice_days` (cambiado en caliente); desactivado →
  `enabled=false` sin escrituras; fuera de horario → `out_of_hours` sin
  reclamar; `no_chat`; texto con `{dias}`/`{fecha}`; WhatsApp ventana cerrada
  → solo `TemplateBlock` con variables; `no_text`/`no_template` sin fila;
  segunda y tercera pasada no reenvían (aviso único); dos pasadas en hilos →
  un envío; fallo → `failed` y reintento hasta el máximo; renovación → nuevo
  periodo avisa una vez y sin aviso mientras no sea candidata; sin
  `add_message`, sin cambio de estado ni `touch`; evento e `identity_audit`;
  respuesta conforme al contrato. Cubre: R45–R59.
- [x] T41 — `tests/test_admin_metrics.py`: primera respuesta (promedio,
  mediana, sin respuesta), conversaciones por asesor con etiqueta de usuario
  y fallback, motivos de escalamiento, preguntas sin respuesta (total,
  muestras truncadas y escapadas, límite 0 sin textos), `dias` inválido 422
  sin repositorio, auditoría `metrics_viewed`. Cubre: R44, R62–R68.
- [x] T42 — `scripts/tests/test_avisar_vencimientos.py`: llamada con token,
  bucle con `max_rounds`, error de red sigue iterando, variables ausentes/
  intervalo/timeout inválidos → código ≠ 0 sin red, logs sin datos
  personales. Ampliar `test_render_blueprint.py` con el worker nuevo. Cubre:
  R60, R61.
- [x] T43 — `tests/test_config.py` (variables y rangos; rutas nuevas en el
  test de superficie `APIRoute`), `tests/test_repository_schema.py` (tablas e
  índices nuevos idempotentes), navegación con los cuatro enlaces. Cubre:
  R69, R70.
- [x] T44 — Ejecutar `./init.sh` una vez al terminar; suites existentes verdes
  con los defaults. Documentar trazabilidad en
  `progress/impl_administracion_y_avisos.md`. Cubre: R71.
