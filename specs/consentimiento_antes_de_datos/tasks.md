# Tasks — consentimiento_antes_de_datos (feature #35)

Orden obligatorio: repositorio → dominio → pruebas → docs → `./init.sh`.

## Repositorio

- [x] T1 — Añadir `get_link_token_role(self, token_hash: str, now: datetime) -> str | None` al
  Protocol `Repository` en `services/orchestrator/orchestrator/adapters/repository.py`. Cubre: R4.
- [x] T2 — Implementarlo en `FakeRepository` (solo lectura: token existe, `used_at is None`,
  `expires_at > now` → rol del perfil; si no, `None`). Cubre: R4, R5.
- [x] T3 — Implementarlo en `PostgresRepository` con un único `SELECT p.role FROM link_tokens t
  JOIN profiles p ON p.id = t.profile_id WHERE t.token_hash = %s AND t.used_at IS NULL AND
  t.expires_at > %s`. Cubre: R4, R5.

## Dominio

- [x] T4 — Añadir `STAFF_ROLES = frozenset({"asesor", "admin"})` y
  `_is_linked_staff(request, adapters) -> bool` en
  `services/orchestrator/orchestrator/domain.py` (uid <= 0 → `False`, sin llamar al
  repositorio). Cubre: R1, R2.
- [x] T5 — Reordenar `process_message` según design §3: parsear `/start`, `/consultar` y
  comando de asesor; para cualquiera de ellos calcular la exención con `_is_linked_staff` y,
  en `/start`, `get_link_token_role`; si no está exento, `_privacy_gate` antes de
  `get_or_create_contact`; después, despachar a los manejadores actuales sin cambiarlos. La
  ruta de texto libre queda igual. Cubre: R1, R3, R6, R7, R8, R9, R10, R11, R12, R13, R14,
  R15, R16, R17, R18, R19, R20, R21, R22.

## Pruebas — `services/orchestrator/tests/test_accounts.py`

- [x] T6 — `test_get_link_token_role_returns_role_only_for_valid_tokens` (fake: válido →
  rol; vencido, usado, inexistente → `None`; el token y el perfil no cambian). Cubre: R4, R5.
- [x] T7 — `test_postgres_get_link_token_role_is_single_select` (cursor falso que registra el
  SQL: una sentencia, empieza por `SELECT`, contiene `used_at IS NULL` y `expires_at >`, sin
  `UPDATE`/`INSERT`/`DELETE`). Cubre: R4, R5.

## Pruebas — `services/orchestrator/tests/test_consent_before_data.py` (nuevo)

- [x] T8 — Helper `_linked_rows(repo, uid)` y `_assert_no_personal_data(env, uid)` según
  design §5. Cubre: R18.
- [x] T9 — `test_unconsented_sender_leaves_no_personal_data` parametrizado por ruta (texto
  libre, `/consultar …`, `/consultar` mal formado, `/responder case-1 hola`, `/cerrar case-1`,
  `/responder` mal formado, `/start <token de cliente>`): aviso enviado, sin filas ligadas,
  `privacy_consents == []`, sin llamadas a handover/LLM/db_query/RAG. Cubre: R10, R11, R15,
  R16, R18.
- [x] T10 — `test_unconsented_sender_only_stores_update_id` (`repo.processed == {update_id}`
  y nada más tras cada ruta de T9). Cubre: R20.
- [x] T11 — `test_acceptance_after_any_route_only_adds_privacy_consent` parametrizado con las
  mismas rutas seguidas de la frase de aceptación. Cubre: R19.
- [x] T12 — `test_staff_reads_happen_before_any_write` (subclase de `FakeRepository` que
  registra el orden de llamadas) para `/consultar`, `/responder` y `/start`. Cubre: R1, R3.
- [x] T13 — `test_non_positive_sender_is_never_staff` (`telegram_user_id <= 0` con perfil
  asesor ficticio: no se consulta el perfil y recibe el aviso). Cubre: R2.
- [x] T14 — `test_linked_staff_commands_skip_privacy_gate` parametrizado por rol `asesor` y
  `admin` y por comando (`/consultar`, `/responder`, `/cerrar`, mal formado), sin
  consentimiento y también con configuración de privacidad vacía: mismo resultado que hoy
  (auditoría, `handover.authorized`, ayuda), sin aviso ni `privacy_consents`. Cubre: R6, R7.
- [x] T15 — `test_start_with_staff_token_links_without_consent` (asesor y admin): perfil
  vinculado, token usado, `link_success_reply`, sin aviso. Cubre: R8.
- [x] T16 — `test_linked_staff_start_skips_gate` (personal vinculado envía `/start
  token-invalido` sin consentimiento → `link_failed_reply`, sin aviso). Cubre: R9.
- [x] T17 — `test_client_token_survives_until_acceptance` (`/start <token cliente>` sin
  consentimiento → aviso, `used_at is None`, perfil sin `telegram_user_id`; luego frase de
  aceptación; luego mismo `/start` → vinculado y `link_success_reply`). Cubre: R15, R16, R17.
- [x] T18 — `test_consented_non_staff_keeps_existing_authorization`: con consentimiento,
  `/consultar` → `db_query_forbidden_reply` + auditoría `forbidden`; `/responder` con
  `handover` que deniega → `advisor_command_forbidden_reply`; mal formado →
  `advisor_command_help`. Cubre: R12, R13, R14.
- [x] T19 — `test_consented_client_free_text_unchanged` (contacto, mensajes `user`/`bot`,
  RAG llamado, respuesta enviada). Cubre: R21.
- [x] T20 — `test_notice_version_change_blocks_new_data` (consentimiento `v0` precargado,
  versión vigente `v1`): texto libre y `/consultar` de un no-personal → aviso, sin mensajes,
  eventos ni auditorías nuevas. Cubre: R22.

## Pruebas existentes a ajustar — `services/orchestrator/tests/test_privacy.py`

- [x] T21 — Ajustar `test_personal_routes_never_create_consent`: el remitente no personal
  ahora recibe el aviso; se mantiene la aserción `privacy_consents == []` (R14 de la #27) y se
  sustituye la de «sin aviso» por «aviso enviado». Docstring con referencia a la #35. Cubre:
  R10, R15.
- [x] T22 — Ajustar `test_personal_routes_work_without_privacy_configuration`: vincular antes
  un perfil `asesor` al `telegram_user_id` 111 para que siga siendo una ruta de personal
  (R19 de la #27 queda reemplazado por R6 de la #35). Cubre: R6.

## Gateway (sin cambios de código)

- [x] T23 — Citar en `progress/impl_consentimiento_antes_de_datos.md` las pruebas existentes
  `services/telegram_gateway/tests/test_webhook.py::test_dedup_key_stored_with_ttl` y
  `services/telegram_gateway/tests/test_grouping.py::test_buffer_and_group_expire_after_ttl`
  (y `test_message_buffer.py::test_ttl_expires_buffer_and_inflight_group`); confirmar que
  pasan. Cubre: R23, R24.

## Documentación y cierre

- [x] T24 — Actualizar `docs/proyecto.md` §11 (fila «Datos personales») con: consentimiento
  antes de cualquier dato salvo personal vinculado; tratamiento técnico mínimo (dedup Redis
  `DEDUP_TTL_SECONDS`, búfer `MESSAGE_GROUPING_BUFFER_TTL_SECONDS`, `processed_updates` solo
  `update_id`). Cubre: R20, R23, R24.
- [x] T25 — Añadir en `specs/privacidad_y_retencion_datos/requirements.md`, bajo R19, la nota
  «Reemplazado por #35 (consentimiento_antes_de_datos) R6–R10». Cubre: R6, R10.
- [x] T26 — Escribir el mapa de trazabilidad R1–R24 en
  `progress/impl_consentimiento_antes_de_datos.md` y ejecutar `./init.sh` hasta verde, sin
  cambios en `contracts/`. Cubre: R1–R24. (Mapa hecho; `./init.sh` lo ejecuta Claude al cerrar
  la sesión: el implementer no ejecuta shell.)
