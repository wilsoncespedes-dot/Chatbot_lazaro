# Review — feature 29 panel_asesores

**Veredicto:** APPROVED

`./init.sh` verde según el leader (1979 passed, 1 warning); no se repitió.
#33 `contrato_listar_casos_asesor` está `done`, así que T9–T10 se podían hacer.
Handover `GET /cases` sigue protegido por `X-Service-Token`
(`services/handover/handover/main.py:57,104-106`).

## Trazabilidad requirements ↔ tests (`services/orchestrator/tests/test_advisor_panel.py`)
- R1: [x] `test_login_creates_advisor_session_and_cookie_attributes`, `test_login_uses_secure_cookie_when_configured`
- R2: [x] `test_login_rejects_unknown_wrong_password_admin_and_client_identically`
- R3: [x] `test_login_throttle_is_shared_with_admin_login_by_username` / `_by_ip`, `test_throttled_advisor_login_does_not_verify_password`
- R4: [x] `test_advisor_routes_redirect_without_session`, `test_expired_or_demoted_session_redirects_to_login`, `test_logout_closes_advisor_session`
- R5: [x] `test_admin_session_does_not_open_advisor_panel_and_vice_versa`
- R6: [x] `test_post_without_valid_csrf_is_forbidden_without_calls` (reply/assign/close × ausente/erróneo)
- R7: [x] `test_advisor_html_has_csp_and_no_external_resources`
- R8: [x] `test_advisor_responses_never_include_secrets`
- R9: [x] `test_unlinked_profile_cannot_act`
- R10: [x] `test_reply_uses_session_advisor_and_ignores_form_advisor`
- R11: [x] `test_assign_uses_session_advisor_and_redirects`, `test_http_try_assign_uses_assign_route_and_fails_closed`
- R12: [x] `test_close_authorizes_closes_and_notifies_client`
- R13: [x] `test_cases_page_uses_session_advisor_and_hides_contact_data`, `test_cases_page_upstream_error_returns_502`, `test_http_list_cases_uses_session_advisor_and_token`
- R14: [x] `test_reply_errors_use_fixed_panel_page`, `test_assign_errors_use_fixed_panel_page`, `test_close_errors_use_fixed_panel_page`, `test_invalid_forms_return_422_without_calls`, `test_http_try_assign_maps_denials`
- R15: [x] `test_forbidden_actions_record_advisor_forbidden_event`, `test_forbidden_without_linked_case_only_logs`, `test_orphan_case_can_be_closed_but_not_replied_or_assigned`

## Tasks completas
- T1–T10: [x]
- T11: [ ] justificada. `progress/impl_panel_asesores.md` («Verificación») explica
  que el implementer no ejecuta shell. Lo que pide T11 ya se cumple: `./init.sh`
  está verde (dato del leader) y la trazabilidad R→test está en el informe.

## Puntos revisados (foco pedido)
- **Aislamiento admin/asesor:** cookie `advisor_session` con `Path=/asesor`
  (`advisor_routes.py:118-126`). `get_session_for_role` filtra por rol con un
  parámetro SQL (`adapters/repository.py:865-874`) y `get_session` delega con
  `"admin"`. Además, `_current_profile` vuelve a comprobar el rol (`advisor_routes.py:62-66`). OK.
- **Login/limitación:** `authenticate_profile` comparte el límite de intentos
  con `/admin/login` y registra un fallo cuando el rol no coincide
  (`domain.py:1032-1072`). `authenticate_admin` no cambia de comportamiento. 401 y 429 usan el mismo `LOGIN_ERROR`. OK.
- **Sesión/rol revalidado:** en cada petición se hace el JOIN de rol y se lee el perfil
  con `get_profile`, así que una degradación o un cambio de vínculo cuenta desde la siguiente petición. OK.
- **CSRF:** todos los POST (`logout`, `reply`, `assign`, `close`) siguen el orden
  sesión → form → `_require_csrf` (`hmac.compare_digest`) antes de cualquier
  llamada (`advisor_routes.py:131-133,168-170,196-198,214-216`). Para `/asesor`,
  `CsrfInvalid` devuelve siempre 403 (`main.py:155-165`). OK.
- **advisor_id:** sale solo de `profile.telegram_user_id`
  (`advisor_routes.py:69-73`). Los campos `advisor_id` del form y de la query se ignoran y hay tests que lo comprueban. OK.
- **Autorización en handover:** reply usa `reply_to_case` (authorize "reply"),
  assign usa `try_assign` (403/404/409 se validan contra `_DENIAL_CODES` y cualquier otra respuesta falla cerrada),
  close hace authorize "close" → close, y list usa `GET /cases` con token. El panel no aplica ninguna regla S12 propia. OK.
- **PII:** el listado muestra solo `case_id`, `status`, `created_at` y `actions`
  (`advisor_panel.py:118-132`, con escape). No se muestran `chat_id`, `contact_id` ni el texto enviado. `ok` solo acepta claves conocidas. OK.
- **Errores upstream:** cada código tiene un mensaje fijo (`advisor_panel.py:8-15`) y nunca se usa el `message` de handover. `ServiceUnavailable`/`UpstreamError` → 502. OK.
- **Admin panel:** la exención de `X-Service-Token` está limitada a `/asesor` y `/asesor/`.
  `LoginRequired`/`CsrfInvalid` de `/admin` no cambian. Al inventario de rutas solo se le añadieron las 7 nuevas. OK.

## Checkpoints
- C1: [x]
- C2: [x] (#29 es la única feature en `in_progress`)
- C3: [x] (no hay dependencias nuevas, el SQL va parametrizado, el orchestrator no importa handover)
- C4: [x] (adaptadores falsos, `httpx` con monkeypatch, sin red)
- C5: [x] (a cargo del leader al cerrar)
- C6: [x] (T11 justificada, ver arriba)

## Observaciones no bloqueantes
1. **Baja — /cerrar con 403 escribe un evento más.** `_command_close` ahora llama
   a `close_case` (`domain.py:461`), que hace `_record_forbidden`
   (`domain.py:967`) antes del `_deny_command` de siempre. Resultado: un
   `advisor_forbidden` en el contacto del caso además del que ya quedaba en el contacto remitente.
   Es lo mismo que ya hace `/responder` (`reply_to_case` + `_deny_command`) y lo que pedía el
   design. Aun así, cambia lo que se observa de #16 y ningún test fija el número de eventos.
   Si se quiere conservar exactamente el comportamiento anterior, conviene documentarlo o añadir un test.
2. **Baja — cobertura:** no hay test de CSRF ausente o erróneo en `POST /asesor/logout`
   (el código es correcto, `advisor_routes.py:131-133`). Tampoco hay test de fallo del
   gateway en `/asesor/reply` → 502 `upstream_error`.
3. **Info:** un body no UTF-8 en `_form` (`admin_routes.py:63`) da 500. Ya pasaba antes y es compartido con `/admin`.
4. **Limpieza:** marcar T11 `[x]` en `specs/panel_asesores/tasks.md` y anotar el
   resultado de `./init.sh` en `progress/impl_panel_asesores.md`.
