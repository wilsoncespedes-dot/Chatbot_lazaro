# impl_no_inventar

Estado: implementado, `./init.sh` verde (527 tests). Pendiente de reviewer; no marcado `done`.

Código de terceros: no se copió nada de rag-support-bot; `THIRD_PARTY_NOTICES.md` intacto.

Cambios: `orchestrator/domain.py` (modelos, `validate_llm_answer`, `_reject_invalid_answer`, prompt), `config.py` (`invalid_answer_handover`), `.env.example`, `tests/conftest.py` (helper `llm_json`, reply por defecto JSON), `test_decisions.py`, `test_security.py`, nuevo `test_no_inventar.py`.

## Trazabilidad R -> test (tests/test_no_inventar.py salvo indicación)

| R | Test |
|---|---|
| R1 | test_system_prompt_requests_json_schema |
| R2 | test_invalid_json_rejected |
| R3 | test_invalid_shape_rejected |
| R4 | test_no_citations_rejected |
| R5 | test_foreign_chunk_id_rejected |
| R6, R8 | test_non_literal_quote_rejected |
| R7 | test_quote_ignores_case_and_repeated_spaces |
| R9 | test_invented_number_rejected |
| R10 | test_number_in_cited_chunk_accepted |
| R11, R12, R18 | test_valid_answer_is_sent_and_logged (+ test_decisions::test_llm_answer_sent_to_chat) |
| R13, R14, R15 | test_invalid_answer_sends_fixed_reply_and_event (6 motivos) |
| R16 | test_invalid_answer_triggers_handover_when_enabled |
| R17 | test_invalid_answer_no_handover_when_disabled |
| R19 | test_security::test_fake_llm_invented_quote_gets_fixed_rejection |
| R20 | test_security::test_fake_llm_invented_number_gets_fixed_rejection |
| R21 | test_validate_llm_answer_is_pure |
| R22 | test_logs_do_not_contain_llm_text |
| R23 | test_third_party_notices_cover_copied_files |
