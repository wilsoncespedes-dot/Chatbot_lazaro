# Implementación — #29 panel_asesores

Feature implementada en `services/orchestrator` siguiendo
`specs/panel_asesores/{requirements,design,tasks}.md`. No se modificó
`feature_list.json`, `progress/current.md`, el harness ni `contracts/`.

## Resumen

- `adapters/repository.py`: `get_session_for_role` en Protocol, Fake y Postgres;
  `get_session` delega con `"admin"`.
- `domain.py`: `authenticate_profile`, `assign_case`, `close_case`;
  `authenticate_admin` y `_command_close` delegan conservando su comportamiento.
- `adapters/handover.py`: `try_assign` y `list_cases` en Protocol, Http y Fake;
  `assign` no cambia.
- `advisor_panel.py`: plantillas de login, inicio con formularios por `case_id`,
  listado de casos y errores con mensaje fijo por código.
- `advisor_routes.py`: `/asesor/login`, `/asesor/logout`, `/asesor`,
  `/asesor/cases`, `/asesor/reply`, `/asesor/assign`, `/asesor/close`.
- `main.py`: router incluido, exención de `X-Service-Token` para `/asesor`,
  `LoginRequired` según path y `CsrfInvalid` con la página del panel.
- `tests/test_advisor_panel.py`: R1–R15 con adaptadores falsos (sin red).

T9–T10 se implementaron porque #33 `contrato_listar_casos_asesor` está `done`
y handover ya expone `GET /cases`.

## Trazabilidad

- R1 → `tests/test_advisor_panel.py::test_login_creates_advisor_session_and_cookie_attributes`
- R1 → `tests/test_advisor_panel.py::test_login_uses_secure_cookie_when_configured`
- R2 → `tests/test_advisor_panel.py::test_login_rejects_unknown_wrong_password_admin_and_client_identically`
- R3 → `tests/test_advisor_panel.py::test_login_throttle_is_shared_with_admin_login_by_username`
- R3 → `tests/test_advisor_panel.py::test_login_throttle_is_shared_with_admin_login_by_ip`
- R3 → `tests/test_advisor_panel.py::test_throttled_advisor_login_does_not_verify_password`
- R4 → `tests/test_advisor_panel.py::test_advisor_routes_redirect_without_session`
- R4 → `tests/test_advisor_panel.py::test_expired_or_demoted_session_redirects_to_login`
- R4 → `tests/test_advisor_panel.py::test_logout_closes_advisor_session`
- R5 → `tests/test_advisor_panel.py::test_admin_session_does_not_open_advisor_panel_and_vice_versa`
- R6 → `tests/test_advisor_panel.py::test_post_without_valid_csrf_is_forbidden_without_calls`
- R7 → `tests/test_advisor_panel.py::test_advisor_html_has_csp_and_no_external_resources`
- R8 → `tests/test_advisor_panel.py::test_advisor_responses_never_include_secrets`
- R9 → `tests/test_advisor_panel.py::test_unlinked_profile_cannot_act`
- R10 → `tests/test_advisor_panel.py::test_reply_uses_session_advisor_and_ignores_form_advisor`
- R11 → `tests/test_advisor_panel.py::test_assign_uses_session_advisor_and_redirects`
- R11 → `tests/test_advisor_panel.py::test_http_try_assign_uses_assign_route_and_fails_closed`
- R12 → `tests/test_advisor_panel.py::test_close_authorizes_closes_and_notifies_client`
- R13 → `tests/test_advisor_panel.py::test_cases_page_uses_session_advisor_and_hides_contact_data`
- R13 → `tests/test_advisor_panel.py::test_cases_page_upstream_error_returns_502`
- R13 → `tests/test_advisor_panel.py::test_http_list_cases_uses_session_advisor_and_token`
- R14 → `tests/test_advisor_panel.py::test_reply_errors_use_fixed_panel_page`
- R14 → `tests/test_advisor_panel.py::test_assign_errors_use_fixed_panel_page`
- R14 → `tests/test_advisor_panel.py::test_close_errors_use_fixed_panel_page`
- R14 → `tests/test_advisor_panel.py::test_invalid_forms_return_422_without_calls`
- R14 → `tests/test_advisor_panel.py::test_http_try_assign_maps_denials`
- R15 → `tests/test_advisor_panel.py::test_forbidden_actions_record_advisor_forbidden_event`
- R15 → `tests/test_advisor_panel.py::test_forbidden_without_linked_case_only_logs`
- R14/R15 → `tests/test_advisor_panel.py::test_orphan_case_can_be_closed_but_not_replied_or_assigned`

## Verificación

Pendiente de `./init.sh` por Claude (el implementer no ejecuta shell).
## Corrección solicitada tras ./init.sh
- Resultado: 1 failed, 1978 passed.
- Falla: services/orchestrator/tests/test_config.py::test_only_health_and_messages_routes_exposed. Su inventario exacto de rutas no incluye las rutas del panel /asesor nuevas y aprobadas en este spec.
- Actualiza el inventario para incluir exactamente las rutas públicas del panel definidas en design.md, conservando las comprobaciones de las rutas anteriores. No elimines ni debilites la prueba. Actualiza este informe, no ejecutes shell.

### Corrección aplicada
- `tests/test_config.py::test_only_health_and_messages_routes_exposed`: el
  inventario exacto conserva todas las rutas anteriores y añade las 7 rutas del
  panel aprobadas en `design.md`: `/asesor`, `/asesor/login`,
  `/asesor/logout`, `/asesor/cases`, `/asesor/reply`, `/asesor/assign` y
  `/asesor/close` (una entrada por path, como el resto del inventario).
- No se eliminó ni debilitó ninguna comprobación.
- Verificación pendiente de que Claude ejecute `./init.sh`.
