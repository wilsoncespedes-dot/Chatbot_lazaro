# #38 identidad_credenciales — Tasks

Orden pensado para que cada paso deje la suite en verde. Tests con
`FakeRepository`, `FakeGatewayClient` y reloj inyectado; sin red ni Docker.
Nombres de test sugeridos con prefijo `test_r<n>_…` para la trazabilidad en
`progress/impl_identidad_credenciales.md`.

## Preparación

- [x] T0 — Revisar `referencias/` (fuera de git; si no existe en la máquina,
  anotarlo) buscando piezas reutilizables para login web con token de un solo
  uso, scrypt o sesiones únicas. Solo se copia de repos MIT/Apache 2.0 tras
  confirmar archivo, commit y licencia; cada copia se registra en
  `THIRD_PARTY_NOTICES.md` y conserva su aviso. Si no hay nada aplicable,
  dejar una línea en `progress/impl_identidad_credenciales.md`. Cubre: —
  (higiene de licencias, `docs/architecture.md` §5).

## Puros (sin IO)

- [x] T1 — `accounts.py`: `hash_password_scrypt` y despacho por prefijo en
  `verify_password`. Tests en `tests/test_identity_crypto.py`: formato
  `scrypt$…`, sal distinta en dos hashes, verificación correcta/incorrecta,
  hash PBKDF2 de #20 sigue validando, prefijo desconocido → `False`.
  Cubre: R19, R20.
- [x] T2 — `identity.py`: `sign_login_token`, `verify_login_token_signature`.
  Tests: formato `<nonce>.<hex>`, firma con otra clave falla, token alterado
  falla, token sin punto falla. Cubre: R3, R13.
- [x] T3 — `identity.py`: `credential_status`, `credential_allows_access`,
  `days_remaining`. Tests parametrizados con reloj fijo para los cinco estados,
  frontera exacta de `valid_until` y de `notice_days`, días ≥ 0. Cubre: R45 (y
  base de R34–R36).
- [x] T4 — `identity.py`: `IdentityPolicy`, `resolve_identity_policy`,
  `is_logout_command`. Tests: override válido de `app_settings` gana, inválido
  o fuera de rango se descarta con log `identity_setting_invalid`; comandos de
  cierre con mayúsculas/espacios coinciden, "/cerrar 12" no. Cubre: R49, R29.

## Configuración

- [x] T5 — `config.py` + `.env.example` + `render.yaml`: variables de la tabla
  de design con rangos; validación de producción para
  `IDENTITY_PUBLIC_BASE_URL` (https), `IDENTITY_LINK_SIGNING_KEY` (≥ 32) e
  `IDENTITY_LOGIN_REQUIRED=false`. Tests en `tests/test_config.py` o
  `tests/test_production_config.py`. Cubre: R6, R8, R50.
- [x] T6 — `privacy.py`: añadir `login_link_label` y `session_closed_reply` a
  `ConversationTexts`; comprobar que el formulario `/admin/texts` los guarda y
  que `consent_configured` no depende de ellos. Test en
  `tests/test_conversation_texts.py`. Cubre: R9.

## Repositorio

- [x] T7 — Esquema e índices (`client_credentials`, `login_links`,
  `client_sessions`, `identity_login_attempts`, `identity_audit`, índices
  parciales únicos). Test en `tests/test_repository_schema.py` que verifica
  las sentencias e idempotencia. Cubre: R4, R27.
- [x] T8 — Métodos de credenciales (`create_client_credential`,
  `get_client_credential`, `get_client_credentials_by_username`,
  `renew_client_credential`, `revoke_client_credential`) en Protocol, Fake y
  Postgres. Tests Fake en `tests/test_identity_repository.py`. Cubre: R38,
  R39, R46.
- [x] T9 — Métodos de enlaces (`add_login_link` invalida previos,
  `get_login_link` solo vigentes/sin usar) y de sesiones
  (`start_client_session` atómico, `get_active_session_by_*`,
  `touch_client_session`, `end_client_session`). Tests: solo se guarda el
  hash, enlace previo invalidado, vencido → `None`, segundo
  `start_client_session` con el mismo token → `invalid_link`, dos tokens del
  mismo perfil en hilos concurrentes → un `ok` y un `conflict` con token del
  perdedor sin usar. Cubre: R4, R5, R15, R27.
- [x] T10 — Intentos, auditoría y overrides
  (`count/record/clear_identity_login_failures`, `add_identity_audit`,
  `get_identity_overrides`). Tests Fake. Cubre: R37, R48, R49.

## Dominio

- [x] T11 — Transiciones nuevas `(no_access, session_closed|session_idle_timeout)
  → awaiting_login`. Test en `tests/test_conversation_states.py` que además
  confirma que el resto de la tabla de #37 no cambia. Cubre: R43.
- [x] T12 — `issue_login_link` + envío de `TextBlock` + `LinkBlock` y hook en
  `_handle_consent_button`. Tests en `tests/test_identity_link.py`: tras pulsar
  Acepto llega `LinkBlock` con URL base + `/acceso?t=`, al mismo canal/chat
  (Telegram y WhatsApp falsos); `expires_at` = ahora + TTL; sin URL base o
  clave → solo recordatorio y log `identity_link_unavailable` sin filas;
  etiqueta vacía → log `identity_texts_not_configured`. Cubre: R1, R6, R7, R9.
- [x] T13 — `login_client` (orden fijo de design) + excepciones nuevas. Tests
  en `tests/test_identity_login.py`: credencial vigente → sesión + `active` +
  `active_welcome`; `por_vencer` → `active`; vencida → sesión + `no_access` +
  `suspended_reply`; revocada / no iniciada / sin fila → 403 sin sesión y
  audit; usuario inexistente, contraseña mala y rol `asesor` → mismo mensaje
  401, intento registrado, token sin consumir, verificación con hash ficticio
  (spy); 5 fallos → 429 aun con contraseña correcta; éxito borra intentos;
  token reutilizado/vencido/firma mala → 400 y sin consulta al repo cuando la
  firma falla. Cubre: R12–R16, R21–R24, R34, R36, R37, R48.
- [x] T14 — Sesión única. Tests: segundo login de la misma credencial desde
  otro chat → 409 sin consumir token y audit `login_conflict`; tras simular
  inactividad ≥ política el segundo login sí entra y la sesión vieja termina
  con `idle` y su contacto pasa a `awaiting_login`. Cubre: R26, R27, R30.
- [x] T15 — Sin vinculación manual. Tests: login para un contacto WhatsApp y
  uno Telegram cuyo perfil no tiene `telegram_user_id` funciona; formulario
  con campos extra (`external_chat_id`, `contact_id`) asocia el contacto del
  enlace; `profiles.telegram_user_id` no cambia; spy de repo verifica que no
  se llama `get_profile_by_telegram_user_id`. Cubre: R17, R18.
- [x] T16 — Hooks en `_route_consented_text` (pasos 1–7 de design). Tests en
  `tests/test_identity_messages.py`: mensaje en `awaiting_login` → recordatorio
  + enlace nuevo (anterior invalidado); estado `None` → igual; mensaje con
  sesión actualiza `last_activity_at`; inactividad → reminder + enlace y RAG/LLM
  no llamados; con `with_advisor` no expira; `active` sin sesión →
  `awaiting_login`; comando `/salir` → sesión `logout`, `session_closed_reply`
  + enlace; `privacy_consents` intacto tras cada cierre; credencial vencida en
  `active` → `no_access`, `suspended_reply`, sin RAG; `no_access` con
  credencial renovada → `active` antes de enrutar. Cubre: R2, R5, R28–R33,
  R35, R41, R47.
- [x] T17 — `IDENTITY_LOGIN_REQUIRED=false` conserva el flujo previo; ajustar
  `tests/conftest.py` para que las suites históricas (RAG, traspaso,
  clasificador, multicanal) lo usen explícitamente. Test dedicado que con
  `true` el mismo mensaje no llega a RAG. Cubre: R44, R47.
- [x] T18 — Funciones admin (`create_client`, `renew_credential`,
  `revoke_credential`, `close_client_session`, `get_client_status`,
  `active_client_id`). Tests: renovar suma desde `max(valid_until, now)`;
  renovar con sesión en `no_access` → `active` + `active_welcome`; renovar
  revocada → `CredentialRevoked` sin cambios; revocar y cerrar sesión →
  sesión terminada con motivo, `awaiting_login`, `session_closed_reply`, audit;
  login posterior a revocar → 403. Cubre: R37–R40, R42, R45, R46.

## HTTP

- [x] T19 — `identity_routes.py` + `identity_page.py` + registro en `main.py`
  (exención del middleware solo para `/acceso`). Tests en
  `tests/test_identity_routes.py` con `TestClient`: GET con token válido → 200,
  formulario con `t` oculto, token no consumido; encabezados `no-store`,
  `no-referrer` y CSP; HTML sin `http(s)://` externos; GET/POST sin
  `X-Service-Token` aceptados; mapeo 400/401/403/409/429; respuesta nunca
  contiene la contraseña enviada; `/acceso/otra` sigue exigiendo token
  interno. Cubre: R10, R11, R12, R14, R17.
- [x] T20 — Rutas internas `/clients…` en `main.py`. Tests: sin token → 401;
  `POST /clients` → 201 sin `password`/`hash` en la respuesta y hash `scrypt$`
  guardado; `GET` devuelve `status` y `days_remaining`; `renew` de revocada →
  409 `credential_revoked`; `revoke` y `close-session` → 200. Cubre: R38,
  R39, R42, R45, R46.
- [x] T21 — Test de no filtración: con `caplog` y `FakeGatewayClient`,
  recorrer creación, login fallido, login correcto, cierre y revocación, y
  afirmar que la contraseña y el token en claro no aparecen en logs, envíos al
  gateway, `events` ni `identity_audit`. Además, emitir un `LogRecord` en el
  logger `uvicorn.access` con args al estilo uvicorn y ruta `/acceso?t=<token>`
  tras instalar el filtro de `main.py`, y afirmar que el token no aparece en la
  salida formateada (sí `t=***`). Comprobar con spy que en todo el flujo de
  `_route_consented_text` no se llama a `get_profile_by_telegram_user_id`.
  Cubre: R25.

## Cierre

- [x] T22 — Actualizar `docs/architecture.md` (módulo de identidad y ruta
  pública `/acceso`) y la sección de variables de `docs/` correspondiente;
  ejecutar `./init.sh` y dejarlo verde. Escribir la trazabilidad R→test en
  `progress/impl_identidad_credenciales.md`. Cubre: todos (verificación final).
