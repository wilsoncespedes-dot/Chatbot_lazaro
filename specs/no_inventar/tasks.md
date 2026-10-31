# Tasks — no_inventar

Todos los archivos están bajo `services/orchestrator/` salvo indicación.

- [x] T1 — Añadir `invalid_answer_handover: bool = True` en `orchestrator/config.py` y `INVALID_ANSWER_HANDOVER=true` en `/.env.example`. Cubre: R16, R17.
- [x] T2 — En `orchestrator/domain.py`: modelos `Citation` y `LLMAnswer`, excepción `InvalidAnswer`, constante `INVALID_REASONS`. Cubre: R2, R3, R15.
- [x] T3 — En `domain.py`: `normalize_quote` y `extract_numbers`. Cubre: R7, R8, R10.
- [x] T4 — En `domain.py`: `validate_llm_answer(raw, chunks)` pura, con el orden fijo de comprobaciones del design. Cubre: R2, R3, R4, R5, R6, R7, R8, R9, R10, R21.
- [x] T5 — Reescribir `LLM_SYSTEM_PROMPT` para exigir el JSON `{answer, citations: [{chunk_id, quote}]}` conservando la regla de datos no instrucciones. Cubre: R1.
- [x] T6 — En `domain.py`: `_reject_invalid_answer` (evento `invalid_answer`, envío de `NO_ANSWER_REPLY`, traspaso condicionado) y cableado en `process_message` paso 5 (válida: evento `rag_answer` + envío de `answer`; inválida: rechazo). Logs solo con ids y motivo. Cubre: R11, R12, R13, R14, R15, R16, R17, R18, R22.
- [x] T7 — Actualizar los tests de la feature 4 que usan `FakeLLM` con texto libre (`tests/test_messages.py`, `tests/test_decisions.py`, `tests/test_security.py`) para que respondan JSON válido con cita literal; mantener sus asserts originales. Cubre: R11.
- [x] T8 — `tests/test_no_inventar.py::test_system_prompt_requests_json_schema`. Cubre: R1.
- [x] T9 — `tests/test_no_inventar.py::test_valid_answer_is_sent_and_logged` (envía solo `answer`, evento `rag_answer`, sin evento `invalid_answer`). Cubre: R11, R12, R18.
- [x] T10 — `tests/test_no_inventar.py::test_invalid_json_rejected` (motivo `invalid_json`). Cubre: R2.
- [x] T11 — `tests/test_no_inventar.py::test_invalid_shape_rejected` (parametrizado: falta `citations`, `answer` vacío, cita sin `quote`, tipos erróneos; motivo `invalid_shape`). Cubre: R3.
- [x] T12 — `tests/test_no_inventar.py::test_no_citations_rejected`. Cubre: R4.
- [x] T13 — `tests/test_no_inventar.py::test_foreign_chunk_id_rejected`. Cubre: R5.
- [x] T14 — `tests/test_no_inventar.py::test_non_literal_quote_rejected` (incluye quote vacío y quote con tilde distinta). Cubre: R6, R8.
- [x] T15 — `tests/test_no_inventar.py::test_quote_ignores_case_and_repeated_spaces` (`validate_llm_answer` directo). Cubre: R7.
- [x] T16 — `tests/test_no_inventar.py::test_invented_number_rejected` y `test_number_in_cited_chunk_accepted` (incluye `1.500,75`, y que un número solo presente en un fragmento NO citado se rechaza). Cubre: R9, R10.
- [x] T17 — `tests/test_no_inventar.py::test_invalid_answer_sends_fixed_reply_and_event` (envía `NO_ANSWER_REPLY`, no envía texto del LLM, evento `invalid_answer` con cada uno de los 6 motivos, parametrizado). Cubre: R13, R14, R15.
- [x] T18 — `tests/test_no_inventar.py::test_invalid_answer_triggers_handover_when_enabled` y `test_invalid_answer_no_handover_when_disabled`. Cubre: R16, R17.
- [x] T19 — `tests/test_security.py::test_fake_llm_invented_quote_gets_fixed_rejection` (prueba de seguridad). Cubre: R19.
- [x] T20 — `tests/test_security.py::test_fake_llm_invented_number_gets_fixed_rejection` (prueba de seguridad). Cubre: R20.
- [x] T21 — `tests/test_no_inventar.py::test_validate_llm_answer_is_pure` (estático: `validate_llm_answer` no recibe adaptadores y no hay llamadas a red/`open`; el cuerpo no referencia `adapters`). Cubre: R21.
- [x] T22 — `tests/test_no_inventar.py::test_logs_do_not_contain_llm_text` (usa `caplog` con una salida con texto reconocible). Cubre: R22.
- [x] T23 — `tests/test_no_inventar.py::test_third_party_notices_cover_copied_files` (todo `.py` del paquete cuya cabecera mencione `rag-support-bot` figura en `THIRD_PARTY_NOTICES.md`). Si se copió código, añadir la fila con aviso MIT y cabecera en el archivo. Cubre: R23.
- [x] T24 — Ejecutar `python -m pytest services/orchestrator` y `./init.sh`; documentar la trazabilidad R→test en `progress/impl_no_inventar.md`. Cubre: R1-R23.
