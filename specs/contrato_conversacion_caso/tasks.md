# Tasks — contrato_conversacion_caso (feature #15)

> Orden pensado para que cada paso sea verificable. Solo se toca `contracts/`
> (ver `design.md` §1). En los tests existentes solo se añaden entradas a
> dicts/listas multilínea; no se borra ni relaja ninguna aserción.
> Cada test nuevo lleva en su docstring el `R<n>` que cubre con el prefijo
> `contrato_conversacion_caso` (p. ej. `"""contrato_conversacion_caso R22: ..."""`).
> Los tests nuevos de `test_contratos_doc.py` van en un bloque propio
> `# ── contrato_conversacion_caso (feature #15) ──` con la constante
> `CLIENT_MESSAGE_ROUTE = "POST /cases/{id}/client-message"`.

## Precondición

- [x] T0 — Comprobar que la #13 está implementada: `CONTRATOS.md` tiene la fila `S12` y la fila `403 | forbidden` en `## Reglas comunes`. Si no, NO empezar: parar y anotarlo en `progress/impl_contrato_conversacion_caso.md` (S13 se numera sobre ese estado y cita S12, R38). R37/R39 son un supuesto conservador ya adoptado (`design.md` §7): no hace falta esperar confirmación del humano; solo si el humano hubiera elegido por escrito la alternativa (ids positivos) se aplica antes el cambio de spec (sustituir R39 y T34). Ejecutar `python -m pytest contracts` y anotar la línea base. Cubre: R34, R35.

## Modelos

- [x] T1 — Añadir `CaseClientMessageRequest` y `CaseClientMessageResponse` al final de `contracts/lazaro_contracts/cases.py`, según `design.md` §3; ampliar la docstring de módulo con `/cases/{id}/client-message` (≤ 100 caracteres por línea). Cubre: R19, R22, R23, R24, R26, R27.
- [x] T2 — Importar ambos modelos en `contracts/lazaro_contracts/__init__.py` y añadirlos a `__all__`. Cubre: R28.

## Ejemplos

- [x] T3 — Crear `contracts/examples/case_client_message_request.json`, `contracts/examples/case_client_message_response.json` y `contracts/examples/case_client_message_response_not_assigned.json` (UTF-8, 2 espacios, valores de `design.md` §2). Cubre: R29, R30, R31.

## Documento

- [x] T4 — Añadir en `contracts/CONTRATOS.md` la sección `### POST /cases/{id}/client-message` al final de `## Rutas`, con el texto de `design.md` §4.1. Cubre: R1, R2, R3, R4, R5, R6, R7, R8, R9, R10, R11, R12, R13.
- [x] T5 — Sustituir la línea `- **Llama:**` de `### POST /cases/{id}/close` por la de `design.md` §4.2 (única edición de texto existente con efecto en el contrato). No tocar `## Reglas comunes` ni `### POST /messages`. Cubre: R14, R33.
- [x] T6 — Añadir la fila `S13` al final de la tabla de `## Supuestos a confirmar` (texto de `design.md` §4.3). Cubre: R15, R16, R17, R18, R36, R37, R38, R39.

## Tests — ampliación de los existentes

- [x] T7 — `contracts/tests/test_contratos_doc.py`: añadir `"POST /cases/{id}/client-message": "handover"` a `ROUTES`, `"POST /cases/{id}/client-message": "200"` a `SUCCESS_CODES` y `"POST /cases/{id}/client-message": [("404", "not_found"), ("502", "upstream_error")]` a `OWN_ERRORS`. Así `test_doc_has_a_section_per_route` (R1), `test_route_names_exposing_service[POST /cases/{id}/client-message]` (R2), `test_route_names_caller[…]` (R3), `test_route_names_models_in_package[…]` (R4), `test_request_table_lists_every_request_field[…]` (R5), `test_response_section_has_success_code_and_fields[…]` (R6), `test_errors_table_has_common_rows[…]` (R7) y `test_errors_table_has_route_specific_rows[…]` (R8) cubren la ruta nueva. Cubre: R1, R2, R3, R4, R5, R6, R7, R8.
- [x] T8 — `contracts/tests/test_examples.py`: importar los dos modelos; añadir a `EXAMPLES` `"case_client_message_request.json": CaseClientMessageRequest`, `"case_client_message_response.json": CaseClientMessageResponse` y `"case_client_message_response_not_assigned.json": CaseClientMessageResponse`; añadir `"CaseClientMessageRequest"` y `"CaseClientMessageResponse"` a `MODEL_NAMES`. Así `test_every_example_validates_against_its_model[case_client_message_request.json]` (R29), `[case_client_message_response.json]` (R30), `[case_client_message_response_not_assigned.json]` (R31), `test_every_example_file_is_mapped` y `test_every_model_has_an_example` (R32) los cubren. Cubre: R29, R30, R31, R32.
- [x] T9 — `contracts/tests/test_models.py`: importar los dos modelos; añadir a `BASE_EXAMPLES` `CaseClientMessageRequest: ("case_client_message_request.json", None)` y `CaseClientMessageResponse: ("case_client_message_response.json", None)`; añadir `(CaseClientMessageResponse, "case_id")` a `IDENTIFIER_FIELDS`. Así `test_missing_required_field_is_rejected[CaseClientMessageRequest.text]` (R20), `[CaseClientMessageRequest.at]` (R21), `[CaseClientMessageResponse.status]` y `[CaseClientMessageResponse.case_id]` (R24), `test_unexpected_field_is_rejected[CaseClientMessageRequest]` y `[CaseClientMessageResponse]` (R27), y `test_invalid_identifier_is_rejected[empty-CaseClientMessageResponse.case_id]` y `[too_long-…]` (R26) los cubren. Cubre: R20, R21, R24, R26, R27.
- [x] T10 — `contracts/tests/test_packaging.py`: añadir `"CaseClientMessageRequest"` y `"CaseClientMessageResponse"` a `MODEL_NAMES`, de modo que `test_model_is_exported_and_is_base_model[CaseClientMessageRequest]` y `[CaseClientMessageResponse]` los cubran. Cubre: R28.

## Tests — nuevos

En `contracts/tests/test_contratos_doc.py`:

- [x] T11 — `test_client_message_route_is_called_by_orchestrator`: la línea `- **Llama:**` de la ruta contiene `orchestrator`. Cubre: R3.
- [x] T12 — `test_client_message_errors_table_has_internal_error`: la tabla `#### Errores` de la ruta contiene `("500", "internal_error")`. Cubre: R9.
- [x] T13 — `test_client_message_section_documents_path_id`: la sección de la ruta contiene `` `{id}` es el `case_id` (identificador, 1–64 caracteres) ``. Cubre: R10.
- [x] T14 — `test_client_message_section_documents_statuses`: la sección de la ruta (texto previo a `#### Request`) contiene `` `assigned` ``, `` `200` ``, `` `forwarded` ``, `` `not_assigned` ``, «asesor asignado», «sin enviar nada» y `S13`. Cubre: R11.
- [x] T15 — `test_client_message_upstream_error_row_mentions_advisor`: la fila `| 502 | upstream_error |` de `#### Errores` de la ruta contiene «envío al asesor». Cubre: R12.
- [x] T16 — `test_client_message_error_codes_are_declared_in_common_rules`: cada par `(HTTP, error)` de `_error_rows` de `#### Errores` de la ruta está en `set(re.findall(r"^\| (\d{3})\s+\| `([a-z_]+)`", rules, re.MULTILINE))` de `## Reglas comunes`. Cubre: R13.
- [x] T17 — `test_close_route_is_also_called_by_orchestrator`: la línea `- **Llama:**` de `POST /cases/{id}/close` contiene `orchestrator` y contiene `asesor (herramienta interna con token; panel en el futuro)`. Cubre: R14.
- [x] T18 — `test_assumptions_include_client_message_forwarding`: `_assumption_row("S13")` contiene `` `POST /cases/{id}/client-message` ``, `` `assigned` ``, `` `open` ``, `` `not_assigned` ``, `` `404` `` y «flujo actual». Cubre: R15.
- [x] T19 — `test_assumptions_s13_forward_failure_does_not_fall_back_to_rag`: `_assumption_row("S13")` contiene `` `502` ``, «texto fijo» y «no se vuelve al RAG». Cubre: R16.
- [x] T20 — `test_assumptions_s13_advisor_commands_use_messages_route`: `_assumption_row("S13")` contiene `` `/responder <case_id> <texto>` ``, `` `/cerrar <case_id>` ``, `` `POST /messages` `` y «no cambia». Cubre: R17.
- [x] T21 — `test_assumptions_s13_advisor_id_is_telegram_sender`: `_assumption_row("S13")` contiene `` `advisor_id` ``, `` `telegram_user_id` ``, `` `TELEGRAM_WEBHOOK_SECRET` `` y «nunca un id escrito en el texto». Cubre: R18.
- [x] T31 — `test_assumptions_s13_non_command_advisor_message_follows_current_flow`: `_assumption_row("S13")` contiene «un mensaje de un asesor que no es `/responder` ni `/cerrar` sigue el flujo actual» y «como el de cualquier cliente». Cubre: R36.
- [x] T32 — `test_assumptions_s13_advisor_commands_follow_s12`: `_assumption_row("S13")` contiene «se autorizan con las reglas de S12» y `_assumption_row("S12")` existe (no vacía). Cubre: R38.
- [x] T33 — `test_assumptions_s13_advisor_list_matches_sender_user_id`: `_assumption_row("S13")` contiene `` `ADVISOR_CHAT_IDS` ``, «se comprueba con ese `telegram_user_id`» y «no con el `chat_id`». Cubre: R37.
- [x] T34 — `test_assumptions_s13_group_ids_cannot_use_commands`: `_assumption_row("S13")` contiene «id de grupo (negativo)» y «no puede usar los comandos». Cubre: R39.

En `contracts/tests/test_models.py`:

- [x] T22 — `test_case_client_message_request_requires_text_and_at`: es subclase de `ContractModel`; sus campos obligatorios son exactamente `{"text", "at"}`; `_validate(CaseClientMessageRequest, {"at": "2026-10-30T19:20:00Z"})` (sin `text`) lanza `ValidationError`. Cubre: R19, R20.
- [x] T23 — `test_case_client_message_request_rejects_naive_at`: con `at` = `"2026-10-30T19:20:00+00:00"` valida y con `at` = `"2026-10-30T19:20:00"` lanza `ValidationError`. Cubre: R22.
- [x] T24 — `test_case_client_message_request_rejects_invalid_text`, parametrizado con `""` y `"a" * (MAX_TEXT_LENGTH + 1)` (ids `empty`, `too_long`): lanza `ValidationError`; y `test_case_client_message_request_accepts_text_at_max_length`: `"a" * MAX_TEXT_LENGTH` valida. Cubre: R23.
- [x] T25 — `test_case_client_message_response_requires_status_and_case_id`: es subclase de `ContractModel`; sus campos obligatorios son exactamente `{"status", "case_id"}`. Cubre: R24.
- [x] T26 — `test_case_client_message_response_accepts_valid_status`, parametrizado con `["forwarded", "not_assigned"]`: valida. Cubre: R24.
- [x] T27 — `test_case_client_message_response_rejects_invalid_status`, parametrizado con `["assigned", "open", "closed", "FORWARDED", "sent", ""]`: lanza `ValidationError`. Cubre: R25.

## Verificación

- [x] T28 — Ejecutar `python -m pytest contracts` y luego la batería completa (`./init.sh` o `python -m pytest`); todo en verde y el total = línea base de T0 + tests nuevos. Cubre: R35.
- [x] T29 — Comprobar con `git diff -U0 -- contracts/ | grep -E '^-[^-]'` que las únicas líneas eliminadas son la línea `- **Llama:**` de `### POST /cases/{id}/close` y la(s) de la docstring de módulo de `cases.py`; que `git diff --name-only -- 'contracts/examples/*.json'` está vacío; que la sección `### POST /messages`, la tabla de `## Reglas comunes`, `messages.py` y `services/` no cambian. Cubre: R33, R34.
- [x] T30 — Documentar la trazabilidad R1–R39 → test (R36 → T31, R37 → T33, R38 → T32, R39 → T34) en `progress/impl_contrato_conversacion_caso.md` (R33 → `test_message_request_requires_its_fields`, `test_message_response_accepts_valid_status`, `test_route_names_exposing_service[POST /messages]` más la comprobación de T29; R34 y R35 → la batería previa intacta más T28/T29). Cubre: R33, R34, R35.
