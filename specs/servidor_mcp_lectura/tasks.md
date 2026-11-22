# Tasks — #74 `servidor_mcp_lectura`

Prerrequisito humano: instalar `mcp>=1.2,<2` en el `.venv` (ver design §2).

## Servidor MCP

- [x] T1 — Crear `services/mcp_lectura/{Dockerfile,requirements.txt}` y `mcp_lectura/config.py`. Cubre: R8, R30.
- [x] T2 — `mcp_lectura/schema.py`: DDL de `demo_ofertas` (con `CHECK (es_demo)`) y `mcp_auditoria`, y `SEED_OFFERS`. Cubre: R12, R13.
- [x] T3 — `mcp_lectura/tools.py`: `buscar_manuales`, `ofertas_demo`, `args_sha256`, `FORBIDDEN_INPUT_FIELDS`. Cubre: R1, R3, R4, R5, R12.
- [x] T4 — `mcp_lectura/adapters.py`: `HttpRagSearch`, `PostgresDemoOffers` (READ ONLY, parametrizado), `PostgresAuditSink` y sus fakes. Cubre: R3, R4, R9.
- [x] T5 — `mcp_lectura/server.py`: `build_mcp` con `readOnlyHint`, decorador `audited` y fallo cerrado si la auditoría falla. Cubre: R1, R2, R9, R10, R11.
- [x] T6 — `mcp_lectura/main.py`: app Starlette con middleware de `X-Service-Token`, `/health` y arranque con DDL/seed. Cubre: R6, R7.
- [x] T7 — Tests `services/mcp_lectura/tests/test_tools.py`: `test_lists_only_two_tools` (R1), `test_all_tools_read_only_hint` (R2), `test_demo_query_is_select_read_only` (R3), `test_buscar_manuales_only_calls_search` (R4), `test_no_identity_field_in_schemas` (R5), `test_demo_rows_marked` (R12), `test_demo_ddl_enforces_marker` (R13). Cubre: R1–R5, R12, R13.
- [x] T8 — Tests `services/mcp_lectura/tests/test_security.py`: `test_missing_token_401` y `test_wrong_token_401` (R6), `test_health_without_token` (R7), `test_compose_publishes_no_port` (R8). Cubre: R6, R7, R8.
- [x] T9 — Tests `services/mcp_lectura/tests/test_audit.py`: `test_audit_row_fields` (R9), `test_audit_has_no_argument_values` (R10), `test_audit_failure_returns_error_without_data` (R11). Cubre: R9, R10, R11.

## Orquestador

- [x] T10 — `harness.py`: `consultar_herramientas_mcp` en `ToolName`, `TOOL_NAMES`, `TOOL_MATRIX[active]`, descripciones; `build_router_prompt(..., mcp_enabled)`. Cubre: R14, R15.
- [x] T11 — `config.py`: variables `MCP_*`; `adapters/mcp.py` con `McpClient`, `HttpMcpClient`, `FakeMcpClient`, `McpUnavailable`; `Adapters.mcp` y `build_default_adapters`. Cubre: R15, R17, R21, R30.
- [x] T12 — `adapters/llm.py`: `complete_with_tools` en `HttpLLMClient`, `FakeLLM` y `ScriptedLLM`. Cubre: R20, R25.
- [x] T13 — `domain.py`: `_tool_mcp` (cliente_id de sesión, filtro de args, lista blanca de herramientas, límite de pasos, fallback a RAG, aviso demo, detalle de auditoría) y registro en `_TOOL_EXECUTORS`. Cubre: R16–R24, R26.
- [x] T14 — `mcp_admin.py` y ruta `GET /admin/mcp` con badge «DEMOSTRACIÓN» y estado «no disponible». Cubre: R27, R28, R29.
- [x] T15 — Tests `services/orchestrator/tests/test_mcp_matrix.py`: `test_mcp_tool_only_in_active` (R14), `test_router_prompt_hides_mcp_when_disabled` (R15), `test_disabled_never_contacts_mcp` (R15), `test_denied_in_with_advisor_no_mcp_call` (R16). Cubre: R14, R15, R16.
- [x] T16 — Tests `services/orchestrator/tests/test_mcp_flow.py` con `FakeMcpClient` y `ScriptedLLM`: `test_cliente_id_comes_from_session` (R17), `test_model_cliente_id_arg_is_dropped` (R18), `test_unlisted_tool_rejected` (R19), `test_max_tool_steps` (R20), `test_mcp_down_falls_back_to_rag_and_logs` (R21), `test_no_tool_call_falls_back_to_rag` (R22), `test_demo_notice_appended` (R23), `test_tool_calls_audit_detail` (R24). Cubre: R17–R24.
- [x] T17 — Tests `services/orchestrator/tests/test_mcp_llm.py` con `httpx` simulado: `test_tools_sent_to_configured_endpoint` (R25). Cubre: R25.
- [x] T18 — Test `services/orchestrator/tests/test_mcp_channels.py`: `test_same_answer_telegram_and_simulado` (R26). Cubre: R26.
- [x] T19 — Tests `services/orchestrator/tests/test_mcp_admin.py`: `test_admin_lists_demo_offers_with_badge` (R27), `test_admin_mcp_down_shows_unavailable` (R28), `test_admin_mcp_requires_session` (R29). Cubre: R27, R28, R29.

## Infraestructura y documentación

- [x] T20 — `docker-compose.yml`: servicios `mcp_lectura` (sin `ports`) y `ollama` (perfil `ollama`); `.env.example` con las variables `MCP_*` y comentario Ollama. Cubre: R8, R30, R31.
- [x] T21 — Test `services/mcp_lectura/tests/test_config_files.py`: `test_env_example_declares_mcp_vars` (R30), `test_ollama_under_profile` (R31), `test_docs_mcp_covers_ollama_and_remote` (R32). Cubre: R30, R31, R32.
- [x] T22 — `docs/mcp.md`, nota en `docs/architecture.md` y `contracts/CONTRATOS.md`; `THIRD_PARTY_NOTICES.md` no cambia (solo dependencia, sin copia). Cubre: R32.
- [x] T23 — `./init.sh` verde; `progress/impl_servidor_mcp_lectura.md` con el mapa `R<n>` → test. Cubre: R1–R32.
