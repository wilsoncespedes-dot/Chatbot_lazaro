# Implementación — conversacion_cliente_asesor (feature #16)

## Resumen

Implementadas las tareas T1-T68, T70-T74 de `specs/conversacion_cliente_asesor/tasks.md`:

- **Orchestrator**: `parse_advisor_command`, `AdvisorCommand`, `MalformedCommand`,
  `ForwardRejected`; `_handle_advisor_command` (`/responder`, `/cerrar`, ayuda, denegaciones),
  `_forward_to_advisor`; `get_contact_last_case` en el repositorio; `forward_client_message` y
  `close` en `HandoverClient`/`HttpHandoverClient`/`FakeHandoverClient`; `fail_for` aditivo en
  `FakeGatewayClient`; ocho textos fijos en `Settings` y en `.env.example`.
- **Handover**: `UpstreamError`, `build_client_forward`, `forward_client_message` y la ruta
  `POST /cases/{id}/client-message`.
- **Tests**: dos archivos nuevos en el orquestador, uno nuevo en handover y las ampliaciones
  previstas en `handover/tests/test_security.py` (ROUTES/INVALID_BODIES) más las pruebas de
  seguridad obligatorias. Ningún test existente se elimina ni se relaja; el único cambio en
  tests previos es la ampliación de `handover/tests/test_security.py` descrita en `design.md` §8.

Sin cambios en `contracts/`, `services/telegram_gateway/`, `eval/`, `scripts/`,
`docker-compose.yml`, `.github/` ni en el harness.

## Verificación pendiente

- T0 (línea base) y T69 (`pytest` + `./init.sh`) no se ejecutaron en esta sesión de escritura:
  el implementer no ejecuta shell. Claude debe correr `./init.sh` y comparar con la línea base.

## Fallos de init.sh — intento 1 (Claude, 2026-11-01)

`./init.sh`: 2 failed, 1183 passed. Corregir solo esto (no tocar otros tests):

1. `services/handover/tests/test_client_message.py::test_client_message_gateway_payload_is_plain_text`
   (línea ~131): el `httpx.Response` falso que devuelve el transport/mock no tiene `request`
   asociado, y `handover/adapters/gateway.py:37` llama `raise_for_status()` →
   `RuntimeError: Cannot call raise_for_status as the request instance has not been set on this response.`
   Arreglar el test: construir la respuesta con `request=` (o usar `httpx.MockTransport`, que la
   asocia). No cambiar el adaptador de gateway existente.
2. `services/orchestrator/tests/test_security.py::test_security_responder_with_other_advisor_id_in_text_authorizes_only_sender`
   (línea 166): con `user=20, chat=200` la respuesta fija se envía al chat del remitente `200`
   (comportamiento correcto según R13/R14: la respuesta va al `chat_id` del remitente), pero el
   test espera `(20, ...)`. Corregir la aserción del test a `(200, ...)`; la autorización con
   `"20"` (telegram_user_id) ya es correcta.

## Correcciones — intento 2 (DeepSeek, 2026-11-01)

Atendidos los dos fallos de `./init.sh` del intento 1, sin tocar adaptadores ni otros tests:

1. `services/handover/tests/test_client_message.py::test_client_message_gateway_payload_is_plain_text`:
   el `httpx.Response` falso de `fake_post` ahora se construye con
   `request=httpx.Request("POST", url)`, así `raise_for_status()` funciona con el
   `HttpGatewayClient` real. El adaptador de gateway no cambia.
2. `services/orchestrator/tests/test_security.py::test_security_responder_with_other_advisor_id_in_text_authorizes_only_sender`:
   la aserción del remitente 20 pasa a esperar la respuesta en su `chat_id` `200`
   (`(200, ADVISOR_COMMAND_FORBIDDEN_REPLY)`), coherente con R13/R14; la autorización
   con `"20"` (`telegram_user_id`) no cambia.

T0 y T69 siguen pendientes de ejecución por Claude (`pytest` + `./init.sh`).

## Trazabilidad

- R1 → `services/orchestrator/tests/test_advisor_commands.py::test_parse_returns_none_for_non_commands`
- R2 → `services/orchestrator/tests/test_advisor_commands.py::test_parse_reply_command`
- R3 → `services/orchestrator/tests/test_advisor_commands.py::test_parse_close_command`
- R4 → `services/orchestrator/tests/test_advisor_commands.py::test_parse_malformed_commands`
- R5 → `services/orchestrator/tests/test_advisor_commands.py::test_parse_advisor_command_is_pure`
- R6 → `services/orchestrator/tests/test_advisor_commands.py::test_command_never_calls_rag_llm_or_handover_request`
  y `test_security.py::test_security_unauthorized_client_responder_reaches_no_other_client`
- R7 → `services/orchestrator/tests/test_advisor_commands.py::test_command_message_is_not_stored_in_sender_history`
- R8 → `services/orchestrator/tests/test_advisor_commands.py::test_command_from_client_with_assigned_case_is_not_forwarded`
- R9 → `services/orchestrator/tests/test_advisor_commands.py::test_malformed_command_sends_help_without_calling_handover`
- R10 → `services/orchestrator/tests/test_advisor_commands.py::test_command_from_non_positive_sender_is_forbidden_without_calling_handover`
- R11 → `services/orchestrator/tests/test_advisor_commands.py::test_command_uses_sender_telegram_user_id_not_chat_id`
  y `test_security.py::test_security_responder_with_other_advisor_id_in_text_authorizes_only_sender`
- R12 → `services/orchestrator/tests/test_advisor_commands.py::test_responder_runs_reply_to_case_flow`
- R13 → `services/orchestrator/tests/test_advisor_commands.py::test_responder_sends_confirmation_to_sender_chat`
- R14 → `services/orchestrator/tests/test_advisor_commands.py::test_responder_forbidden_sends_fixed_text`
  y `test_security.py::test_security_responder_with_other_advisor_id_in_text_authorizes_only_sender`
- R15 → `services/orchestrator/tests/test_advisor_commands.py::test_responder_not_found_or_upstream_sends_failed_text`
  y `test_fake_gateway_fail_for_fails_only_listed_chats`
- R16 → `services/orchestrator/tests/test_advisor_commands.py::test_cerrar_authorizes_before_close`
- R17 → `services/orchestrator/tests/test_advisor_commands.py::test_cerrar_authorizes_before_close`
  y `test_cerrar_closes_case_and_notifies_client`
- R18 → `services/orchestrator/tests/test_advisor_commands.py::test_cerrar_closes_case_and_notifies_client`
- R19 → `services/orchestrator/tests/test_advisor_commands.py::test_cerrar_sends_confirmation_to_sender`
- R20 → `services/orchestrator/tests/test_advisor_commands.py::test_cerrar_unlinked_case_logs_and_notifies_nobody`
- R21 → `services/orchestrator/tests/test_advisor_commands.py::test_cerrar_forbidden_sends_fixed_text_without_notice`
- R22 → `services/orchestrator/tests/test_advisor_commands.py::test_cerrar_failed_authorize_never_calls_close`
  y `test_cerrar_closed_case_sends_case_closed_text_without_notice`
- R23 → `services/orchestrator/tests/test_advisor_commands.py::test_cerrar_not_found_or_unavailable_sends_failed_text`
- R24 → `services/orchestrator/tests/test_advisor_commands.py::test_command_denials_record_advisor_forbidden_on_sender`
  y `test_security.py::test_security_unauthorized_client_responder_reaches_no_other_client`
- R25 → `services/orchestrator/tests/test_advisor_commands.py::test_command_replies_are_not_stored_in_sender_history`
- R26 → `services/orchestrator/tests/test_advisor_commands.py::test_command_logs_do_not_contain_text`
- R27 → `services/orchestrator/tests/test_client_forward.py::test_assigned_case_message_is_forwarded_without_rag`,
  `test_forward_runs_before_handover_keywords`, `test_forward_uses_last_linked_case` y
  `test_security.py::test_security_forwarded_client_text_is_not_interpreted`
- R28 → `services/orchestrator/tests/test_client_forward.py::test_assigned_case_message_is_forwarded_without_rag`
  y `test_security.py::test_security_forwarded_client_text_is_not_interpreted`
- R29 → `services/orchestrator/tests/test_client_forward.py::test_not_assigned_follows_current_flow`
- R30 → `services/orchestrator/tests/test_client_forward.py::test_unknown_case_follows_current_flow`
- R31 → `services/orchestrator/tests/test_client_forward.py::test_contact_without_case_does_not_call_client_message`
- R32 → `services/orchestrator/tests/test_client_forward.py::test_forward_failure_sends_fixed_text_without_rag`
  (caso `upstream_error`)
- R33 → `services/orchestrator/tests/test_client_forward.py::test_forward_failure_sends_fixed_text_without_rag`
  (caso `handover_unavailable`)
- R34 → `services/orchestrator/tests/test_client_forward.py::test_advisor_plain_message_follows_current_flow`
- R35 → `services/orchestrator/tests/test_client_forward.py::test_fake_repository_last_case_for_contact`,
  `test_postgres_last_case_uses_parameters_only` y `test_forward_uses_last_linked_case`
- R36 → `services/orchestrator/tests/test_client_forward.py::test_forward_logs_do_not_contain_client_text`
- R37 → `services/orchestrator/tests/test_client_forward.py::test_http_handover_client_forward_posts_to_client_message_route`
- R38 → `services/orchestrator/tests/test_client_forward.py::test_http_handover_client_forward_posts_to_client_message_route`
- R39 → `services/orchestrator/tests/test_client_forward.py::test_http_handover_client_forward_maps_rejections`
- R40 → `services/orchestrator/tests/test_client_forward.py::test_http_handover_client_forward_fails_closed`
- R41 → `services/orchestrator/tests/test_client_forward.py::test_http_handover_client_close_posts_to_close_route`
- R42 → `services/orchestrator/tests/test_client_forward.py::test_http_handover_client_close_maps_denials`
- R43 → `services/orchestrator/tests/test_client_forward.py::test_http_handover_client_close_fails_closed`
- R44 → `services/orchestrator/tests/test_client_forward.py::test_conversation_texts_have_defaults_and_read_env`
- R45 → `services/orchestrator/tests/test_client_forward.py::test_conversation_texts_are_in_env_example`
- R46 → `services/orchestrator/tests/test_client_forward.py::test_orchestrator_does_not_read_advisor_list`
- R47 → `services/handover/tests/test_client_message.py::test_client_message_assigned_case_is_forwarded_to_advisor`
- R48 → `services/handover/tests/test_client_message.py::test_client_message_is_truncated_to_4096`
- R49 → `services/handover/tests/test_client_message.py::test_client_message_not_assigned_cases_send_nothing`
- R50 → `services/handover/tests/test_client_message.py::test_client_message_unknown_case_returns_404`
- R51 → `services/handover/tests/test_client_message.py::test_client_message_send_failure_returns_502`
- R52 → `services/handover/tests/test_client_message.py::test_client_message_invalid_advisor_id_returns_502_without_send`
- R53 → `services/handover/tests/test_client_message.py::test_client_message_never_modifies_case`
  y `test_security.py::test_security_client_text_is_forwarded_verbatim_and_not_interpreted`
- R54 → `services/handover/tests/test_client_message.py::test_client_message_gateway_payload_is_plain_text`
  y `test_security.py::test_security_client_text_is_forwarded_verbatim_and_not_interpreted`
- R55 → `services/handover/tests/test_security.py::test_handover_routes_without_token_return_401_and_change_nothing`
  (entrada `/cases/case-x/client-message` añadida en T10)
- R56 → `services/handover/tests/test_security.py::test_handover_invalid_body_returns_422`
  (entradas de `/cases/case-x/client-message` añadidas en T10)
- R57 → `services/handover/tests/test_client_message.py::test_client_message_logs_do_not_contain_text`
- R58 → suite completa vía `./init.sh` (T0/T69 pendientes de ejecución); único cambio en tests
  existentes: ampliación de `services/handover/tests/test_security.py` (solo líneas añadidas)
- R59 → `services/handover/tests/test_client_message.py::test_http_close_sends_no_notice_to_client`
- R60 → `services/orchestrator/tests/test_advisor_commands.py::test_responder_closed_case_sends_case_closed_text`
- R61 → `services/orchestrator/tests/test_advisor_commands.py::test_cerrar_closed_case_sends_case_closed_text_without_notice`
- R62 → `services/orchestrator/tests/test_advisor_commands.py::test_closed_case_commands_record_no_advisor_forbidden`

## Supuestos conservadores aplicados (`design.md` §9.2)

- **D1** gramática estricta (nombre exacto, sin `@bot`, `case_id` 1-64): R1-R4.
- **D2** `telegram_user_id <= 0` → `sender_not_user` sin llamar a handover: R10.
- **D3** textos nuevos `ADVISOR_COMMAND_FAILED_REPLY` y `ADVISOR_COMMAND_CASE_CLOSED_REPLY`.
- **D4** `/cerrar` usa `authorize(action="close")` antes de `close`; caso cerrado con texto propio,
  sin `advisor_forbidden` ni aviso repetido al cliente.
- **D5** `client-message` sin respuesta válida → `FORWARD_FAILED_REPLY`, sin volver al RAG.
- **D6** la denegación registra `advisor_forbidden` en el contacto remitente (y `reply_to_case`
  mantiene el suyo, sin modificar la #14).
- **D7** ni el comando ni las respuestas fijas al asesor se guardan en su historial.
- **D8** los intentos de comando se detectan antes del reenvío.
- **D9** `CASE_CLOSED_REPLY` solo sale del cierre por `/cerrar`, no de la ruta HTTP `close`.
- **C1-C4** consecuencias aceptadas: un `assigned` no vence y bloquea el RAG; sin acuse al
  reenviar; una llamada a handover por mensaje de contacto con caso vinculado; carreras y conexión
  compartida ya mitigadas por #14 y #18.

## Riesgo residual documentado

Huérfanos (`design.md` §7): hasta que un asesor registrado cierre el caso con `/cerrar`, los
mensajes del cliente se siguen reenviando al Telegram del asesor retirado (`assigned` → forwarded).
No se cambia S13 de la #15; el `orphan_cases_present` del arranque es la señal operativa.
